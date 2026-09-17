# Lab-API, Datenbank und Worker

Läuft auf dem Hauptserver als eigenes Compose-Projekt `honeypot-lab` in
`/opt/honeypot-lab`, getrennt von der Webseite in `/opt/globe-demo`
(E-020). Kein Dienst veröffentlicht einen Port auf dem Host; von außen ist nur
die API über Caddy erreichbar (E-021).

## Was hier liegt

| Pfad                        | Inhalt                                                     |
|-----------------------------|------------------------------------------------------------|
| `app/main.py`               | FastAPI-App, `GET /health`, Anfrage-Log ohne Adressen       |
| `app/ingest.py`             | `POST /ingest`: Token, Prüfung, Idempotenz, Sitzungen       |
| `app/events.py`             | Ereignisse prüfen, Adressen entfernen, Felder ziehen        |
| `app/defang.py`             | URLs und Adressen entschärfen (hxxp, [.])                  |
| `app/enrichment.py`         | Land und Netzbetreiber aus der IPinfo-Lite-Datenbank        |
| `app/config.py`             | Einstellungen aus Umgebungsvariablen, Secrets als `SecretStr` |
| `app/db.py`                 | Engine und Sessions (SQLAlchemy 2, psycopg 3, asynchron)    |
| `app/models.py`             | die sieben Tabellen aus Schritt 3.3                        |
| `app/hashing.py`            | HMAC-SHA256 der Quell-IPs (E-009, E-022)                   |
| `app/logging.py`            | JSON-Logs                                                  |
| `app/migrations/`           | Alembic, `0001_grundschema.py` legt alles an               |
| `worker/main.py`            | Gerüst mit Schleife, Jobs folgen in Schritt 4.3            |
| `tests/`                    | Tests ohne Datenbank und, mit Marker `db`, mit Datenbank   |
| `../docker-compose.server.yml` | `db`, `api`, `worker` mit Limits und Netzen              |

## Lokal prüfen

Einmalig eine virtuelle Umgebung im Repo-Wurzelverzeichnis anlegen:

```bash
python3 -m venv .venv && .venv/bin/pip install -r server/requirements-dev.txt
```

Danach die Tests ohne Datenbank (die Datenbanktests überspringt pytest):

```bash
cd server && ../.venv/bin/python -m pytest
```

Die Migration lässt sich auch ohne Datenbank gegenlesen. Der Befehl gibt nur
SQL aus und verbindet sich nirgends hin:

```bash
cd server && ../.venv/bin/alembic -x url=postgresql+psycopg://u:p@localhost/db upgrade head --sql
```

Maßgeblich ist der Testlauf im Container: Dort läuft Python 3.12 wie im Betrieb
(E-010), lokal ist es die installierte Version.

## Auf den Hauptserver bringen

Übertragen wird per rsync vom Laptop, nicht per `git pull` auf dem Server
(E-017). Der Hauptserver steht in `~/.ssh/config` als Host `globe`
(159.69.188.127, User `deploy`, Schlüssel `globe_demo`). Mit der nackten IP
statt des Alias greift dieser Block nicht, ssh bietet dann den falschen
Schlüssel an und der Server antwortet „Permission denied (publickey)“.

Einmalig das Verzeichnis anlegen und dem Deploy-User geben. Danach kommt rsync
ohne sudo aus, was wichtig ist, weil rsync kein Terminal für eine
Passwortabfrage hat:

```bash
ssh -t globe 'sudo install -d -m 0750 /opt/honeypot-lab && sudo chown -R "$(id -un):$(id -gn)" /opt/honeypot-lab'
```

Dann bei jeder Änderung, aus dem Wurzelverzeichnis des Repos:

```bash
rsync -av --delete --exclude '__pycache__' --exclude '.pytest_cache' server/ globe:/opt/honeypot-lab/server/
```

```bash
rsync -av docker-compose.server.yml globe:/opt/honeypot-lab/
```

## Secrets

Die `.env` entsteht auf dem Server und wird nie übertragen, nie committet und
nie in den Chat kopiert. Werte erzeugen mit `openssl rand -hex 32`, Inhalt nach
`.env.example`, Abschnitt 1 und 2:

```bash
sudo touch /opt/honeypot-lab/.env && sudo chown root:root /opt/honeypot-lab/.env && sudo chmod 600 /opt/honeypot-lab/.env
```

```bash
sudo nano /opt/honeypot-lab/.env
```

Nötig sind `POSTGRES_PASSWORD`, `IP_HMAC_KEY` und `INGEST_TOKEN`, jeweils
mindestens 32 Zeichen. Fehlt einer davon oder steht dort noch `CHANGE_ME`,
startet die API absichtlich nicht. `IP_HMAC_KEY` wird nie gewechselt (E-022).

## Starten

```bash
cd /opt/honeypot-lab && sudo docker compose -f docker-compose.server.yml build
```

```bash
cd /opt/honeypot-lab && sudo docker compose -f docker-compose.server.yml up -d
```

Schema anlegen oder aktualisieren:

```bash
cd /opt/honeypot-lab && sudo docker compose -f docker-compose.server.yml run --rm api alembic upgrade head
```

## Tests auf dem Server

Das Laufzeit-Image enthält kein pytest. Dafür gibt es das Build-Ziel `test`:

```bash
sudo docker build --target test -t honeypot-lab-api:test /opt/honeypot-lab/server
```

Einmalig eine eigene Testdatenbank anlegen. Die Tests fahren das Schema hoch
und wieder herunter, das darf nie die echten Daten treffen:

```bash
cd /opt/honeypot-lab && sudo docker compose -f docker-compose.server.yml exec db psql -U honeypot -d honeypot -c 'CREATE DATABASE honeypot_test OWNER honeypot;'
```

Testlauf. Das Passwort kommt aus der `.env` und steht nicht in der Befehlszeile:

```bash
sudo docker run --rm --network honeypot-lab_lab_internal --env-file /opt/honeypot-lab/.env -e ENVIRONMENT=test -e POSTGRES_HOST=db -e LAB_TEST_DATABASE=honeypot_test honeypot-lab-api:test pytest -p no:cacheprovider
```

`-p no:cacheprovider`, weil `/app` im Image root gehört und der Container
ohne Root läuft. Erwartet: alle Tests grün, nichts übersprungen.

## Prüfen

```bash
curl -sS -o /dev/null -w 'HTTP %{http_code}\n' https://api.tomkaufmann.dev/health
```

Der Ingest muss ohne Token ablehnen:

```bash
curl -sS -o /dev/null -w 'HTTP %{http_code}\n' -X POST -H 'Content-Type: application/json' -d '[]' https://api.tomkaufmann.dev/ingest
```

Erwartet: `401`. Mit gültigem Token antwortet er mit Zählern für angenommene,
doppelte und abgelehnte Ereignisse; den Weg dorthin baut Vector in Schritt 4.2.

```bash
curl -sS https://api.tomkaufmann.dev/health
```

Erwartet: `200` und `{"status":"ok","database":"ok"}`.

Die Datenbank darf von außen nicht erreichbar sein. Auf dem Server darf kein
Prozess auf 5432 lauschen:

```bash
sudo ss -tlnp | grep -E ':(5432|8000)' || echo 'kein Lab-Port auf dem Host, richtig so'
```

Vom Laptop aus muss der Verbindungsversuch scheitern:

```bash
nc -z -w 5 159.69.188.127 5432; echo "Rückgabewert $? (1 heißt: nicht erreichbar, richtig so)"
```

Container und Grenzen:

```bash
cd /opt/honeypot-lab && sudo docker compose -f docker-compose.server.yml ps
```

```bash
sudo docker stats --no-stream --format 'table {{.Name}}\t{{.MemUsage}}\t{{.CPUPerc}}'
```

## Hinweise

- **Kein CORS in der App.** Das macht Caddy (E-021). Zwei Quellen für denselben
  Header ergäben doppelte Werte.
- **Kein Access-Log von Uvicorn.** Es würde die Adresse jedes Clients
  mitschreiben. Die App loggt stattdessen Methode, Pfad, Status und Dauer.
- **Die App ist eine Factory** (`app.main:create_app --factory`). So liest
  niemand beim Import Einstellungen, und Tests bauen ihre eigene App.
- **`docker compose down` nicht mit `-v`**, sonst ist das Volume `pgdata` weg.
- **Das Netz `lab_edge` gehört niemandem allein.** Es wurde von Hand angelegt
  und steht in beiden Projekten als `external`.
