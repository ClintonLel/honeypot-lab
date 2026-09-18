"""POST /ingest: Ereignisse vom Sensor annehmen.

Der Sensor weist sich mit einem Bearer-Token aus (``INGEST_TOKEN``). Jede Zeile
wird einzeln geprüft; eine kaputte Zeile wirft nicht den ganzen Stapel weg,
sondern wird gezählt und gemeldet. Doppelt gelieferte Zeilen erkennt ein
eindeutiger Index auf ``events.dedup_hash``: Vector darf nach einem Neustart
gefahrlos noch einmal senden (Schritt 4.2).

Reihenfolge je Ereignis: prüfen, anreichern, Quell-IP hashen, Klartext
verwerfen, speichern (E-009).
"""

from __future__ import annotations

import hmac
import json
import logging
from hashlib import sha256
from collections import Counter
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.enrichment import Enricher, Origin
from app.events import MAX_BATCH, EventRejected, NormalizedEvent, normalize
from app.hashing import hash_ip
from app.models import Command, Event, Session

logger = logging.getLogger("lab.ingest")
router = APIRouter()

bearer = HTTPBearer(auto_error=False)


def settings_of(request: Request) -> Settings:
    return request.app.state.settings


async def require_sensor_token(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> None:
    """Prüft das Bearer-Token des Sensors in konstanter Zeit."""
    expected = settings_of(request).ingest_token.get_secret_value()
    given = credentials.credentials if credentials else ""
    if not expected or not hmac.compare_digest(given, expected):
        # Für die Fehlersuche die Form des Headers festhalten, nie den Wert:
        # Schema, Länge und ob ein Platzhalter durchgereicht wurde.
        logger.warning(
            "ingest abgelehnt",
            extra={
                "scheme": credentials.scheme if credentials else None,
                "laenge": len(given),
                "erwartete_laenge": len(expected),
                "sieht_aus_wie_platzhalter": given.startswith("${"),
            },
        )
        # Die Antwort selbst sagt nicht, ob das Token fehlte oder falsch war.
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="nicht berechtigt")


async def db_session(request: Request) -> Any:
    factory = request.app.state.session_factory
    async with factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


# Obergrenze für den Rumpf. Caddy begrenzt ihn schon auf 1 MB (E-021); das
# hier ist die zweite Bremse, falls jemand an Caddy vorbeikommt.
MAX_BODY_BYTES = 2 * 1024 * 1024


def parse_batch(body: bytes) -> list[Any]:
    """Liest einen Stapel als JSON-Array, als Objekt mit ``events`` oder als NDJSON.

    Vector kann Stapel je nach Einstellung als Array oder als eine Zeile je
    Ereignis schicken. Beides anzunehmen kostet nichts und erspart einen
    Ausfall, falls sich die Einstellung auf dem Sensor einmal ändert.
    """
    text = body.strip()
    if not text:
        return []

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        parsed = None

    if isinstance(parsed, list):
        # Eine zweite Hülle um den Stapel ([[e1, e2]]) wird eine Ebene tief
        # entpackt. So kam es an, als Vector mit payload_prefix "[" lief und
        # das Array schon selbst gebaut hatte (E-027).
        if parsed and all(isinstance(item, list) for item in parsed):
            return [event for inner in parsed for event in inner]
        return parsed
    if isinstance(parsed, dict):
        if isinstance(parsed.get("events"), list):
            return parsed["events"]
        # Ein einzelnes Objekt ist ein Stapel mit einem Ereignis. In ruhigen
        # Minuten schickt Vector genau das.
        return [parsed]
    if parsed is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Liste erwartet"
        )

    events: list[Any] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="kein gültiges JSON"
            ) from None
    return events


async def upsert_session(
    db: AsyncSession, event: NormalizedEvent, ip_hash: str | None, origin: Origin
) -> int | None:
    """Legt die Sitzung an oder ergänzt sie. Gibt die interne ID zurück."""
    if ip_hash is None:
        # Ohne Herkunft lässt sich keine Sitzung anlegen, ip_hash ist Pflicht.
        return await db.scalar(
            select(Session.id).where(Session.cowrie_session == event.cowrie_session)
        )

    statement = insert(Session).values(
        cowrie_session=event.cowrie_session,
        variant=event.variant,
        sensor_name=event.sensor,
        ip_hash=ip_hash,
        country=origin.country,
        asn=origin.asn,
        as_name=origin.as_name,
        started_at=event.occurred_at,
    )
    statement = statement.on_conflict_do_update(
        constraint="uq_sessions_cowrie_session",
        set_={
            # Vorhandene Werte bleiben stehen, fehlende werden ergänzt.
            "country": func.coalesce(Session.country, statement.excluded.country),
            "asn": func.coalesce(Session.asn, statement.excluded.asn),
            "as_name": func.coalesce(Session.as_name, statement.excluded.as_name),
            # Der Anfang ist das früheste Ereignis, auch wenn der Stapel
            # unsortiert ankommt.
            "started_at": func.least(Session.started_at, statement.excluded.started_at),
        },
    ).returning(Session.id)
    return await db.scalar(statement)


async def apply_event(db: AsyncSession, event: NormalizedEvent, session_id: int) -> None:
    """Schreibt die Felder des Ereignisses in die Sitzung."""
    fields = event.fields
    changes: dict[str, Any] = {}

    if event.eventid == "cowrie.client.version" and fields.get("version"):
        changes["client_version"] = fields["version"]
    elif event.eventid == "cowrie.client.kex" and fields.get("hassh"):
        changes["hassh"] = fields["hassh"]
    elif event.eventid == "cowrie.client.size":
        # Wer eine Terminalgröße meldet, hat ein Pseudoterminal angefordert.
        # Das ist das Merkmal für eine interaktive Sitzung.
        changes["interactive"] = True
    elif event.eventid == "cowrie.login.success":
        changes["login_username"] = fields.get("username")
        changes["login_password"] = fields.get("password")
    elif event.eventid == "cowrie.login.failed":
        # Nur, solange kein erfolgreicher Login die Felder gefüllt hat.
        await db.execute(
            update(Session)
            .where(Session.id == session_id, Session.login_username.is_(None))
            .values(login_username=fields.get("username"), login_password=fields.get("password"))
        )
    elif event.eventid == "cowrie.session.closed":
        changes["ended_at"] = event.occurred_at
        if "duration_ms" in fields:
            changes["duration_ms"] = fields["duration_ms"]

    if changes:
        await db.execute(update(Session).where(Session.id == session_id).values(**changes))


async def add_command(db: AsyncSession, event: NormalizedEvent, session_id: int) -> None:
    """Hängt einen Befehl an die Sitzung und zählt ihn."""
    text = event.fields.get("input") or ""
    sequence = await db.scalar(
        update(Session)
        .where(Session.id == session_id)
        .values(command_count=Session.command_count + 1)
        .returning(Session.command_count)
    )
    # Ohne Terminalgröße ist es ein Exec-Aufruf. Kommt später doch eine
    # Größe, setzt das Ereignis interactive auf true.
    await db.execute(
        update(Session)
        .where(Session.id == session_id, Session.interactive.is_(None))
        .values(interactive=False)
    )
    await db.execute(
        insert(Command)
        .values(
            session_id=session_id,
            sequence=sequence or 1,
            occurred_at=event.occurred_at,
            command=text,
            command_hash=sha256(text.encode("utf-8")).hexdigest(),
        )
        .on_conflict_do_nothing(constraint="uq_commands_session_sequence")
    )


async def store_event(
    db: AsyncSession, event: NormalizedEvent, ip_hash: str | None, origin: Origin
) -> bool:
    """Speichert ein Ereignis. False heißt: war schon da."""
    session_id = await upsert_session(db, event, ip_hash, origin)

    inserted = await db.scalar(
        insert(Event)
        .values(
            dedup_hash=event.dedup_hash,
            session_id=session_id,
            cowrie_session=event.cowrie_session,
            eventid=event.eventid,
            variant=event.variant,
            occurred_at=event.occurred_at,
            payload=event.payload,
        )
        .on_conflict_do_nothing(constraint="uq_events_dedup_hash")
        .returning(Event.id)
    )
    if inserted is None:
        return False

    if session_id is not None:
        await apply_event(db, event, session_id)
        if event.eventid == "cowrie.command.input":
            await add_command(db, event, session_id)
    return True


@router.post("/ingest", dependencies=[Depends(require_sensor_token)])
async def ingest(
    request: Request,
    db: AsyncSession = Depends(db_session),
) -> dict[str, Any]:
    body = await request.body()
    if len(body) > MAX_BODY_BYTES:
        raise HTTPException(status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail="Rumpf zu groß")
    raw_events = parse_batch(body)
    if len(raw_events) > MAX_BATCH:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"höchstens {MAX_BATCH} Ereignisse je Anfrage",
        )

    settings: Settings = settings_of(request)
    enricher: Enricher = request.app.state.enricher
    key = settings.ip_hmac_key_bytes

    accepted = duplicates = 0
    rejected: Counter[str] = Counter()

    for raw in raw_events:
        try:
            event = normalize(raw)
        except EventRejected as exc:
            rejected[exc.reason] += 1
            continue

        # Anreichern, hashen, Klartext vergessen.
        origin = enricher.lookup(event.source_address)
        ip_hash = hash_ip(event.source_address, key) if event.source_address else None
        # Ab hier existiert die Adresse nirgends mehr: payload ist ohne sie
        # entstanden, gespeichert wird nur der Hash.

        # Jedes Ereignis in einem eigenen Savepoint: Scheitert eines an der
        # Datenbank, zählt es als abgelehnt und der Rest des Stapels bleibt
        # erhalten. Sonst verwirft Vector nach seinen Wiederholungen den
        # ganzen Stapel (E-027).
        try:
            async with db.begin_nested():
                stored = await store_event(db, event, ip_hash, origin)
        except SQLAlchemyError as exc:
            rejected["datenbankfehler"] += 1
            logger.warning(
                "ereignis nicht gespeichert",
                extra={"eventid": event.eventid, "error": type(exc).__name__},
            )
            continue

        if stored:
            accepted += 1
        else:
            duplicates += 1

    await db.commit()

    logger.info(
        "ingest",
        extra={
            "accepted": accepted,
            "duplicates": duplicates,
            "rejected": sum(rejected.values()),
            "reasons": dict(rejected),
        },
    )
    return {
        "accepted": accepted,
        "duplicates": duplicates,
        "rejected": sum(rejected.values()),
        "reasons": dict(rejected),
    }
