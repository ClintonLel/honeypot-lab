# Lab-API, Datenbank und Worker

Läuft auf dem Hauptserver als eigenes Compose-Projekt `honeypot-lab` in
`/opt/honeypot-lab`, getrennt von der Webseite in `/opt/globe-demo`
(E-020). Kein Dienst veröffentlicht einen Port auf dem Host; von außen ist nur
die API über Caddy erreichbar (E-021).

## Was hier liegt

| Pfad                        | Inhalt                                                     |
|-----------------------------|------------------------------------------------------------|
| `app/main.py`               | FastAPI-App, `GET /health`, Anfrage-Log ohne Adressen       |
| `app/auth.py`               | Bearer-Token des Sensors prüfen, für Ingest und Gateway     |
| `app/ingest.py`             | `POST /ingest`: Token, Prüfung, Idempotenz, Sitzungen       |
| `app/events.py`             | Ereignisse prüfen, Adressen entfernen, Felder ziehen        |
| `app/defang.py`             | URLs und Adressen entschärfen (hxxp, [.])                  |
| `app/enrichment.py`         | Land und Netzbetreiber aus der IPinfo-Lite-Datenbank        |
| `app/stream.py`             | `GET /stream`: Live-Ereignisse als Server-Sent Events       |
| `app/stats.py`              | `GET /stats/*`: Übersicht, Länder, Heatmap, Exec/interaktiv, Kampagnen |
| `app/attack.py`             | ATT&CK-Regeln laden, prüfen (ReDoS) und auf Befehle anwenden |
| `rules/attack.yml`          | die Regeln selbst: Muster → Technik, mit ATT&CK-Version (Schritt 6.1) |
| `app/campaigns.py`          | Befehle normalisieren, Fingerprint je Sitzung, Labels laden (Schritt 6.2) |
| `rules/campaigns.yml`       | Labels der Kampagnen: Fingerprint-Präfix → Label und Beschreibung |
| `app/ratelimit.py`          | Rate-Limit pro Client, Schlüssel ohne Adresse               |
| `app/llm_gateway.py`        | `POST /v1/chat/completions`: LLM-Gateway für cowrie-b (Schritt 7.2) |
| `app/llm_provider.py`       | Anbieter Gemini: feste URL, Modelle und Preise, Form der Nachrichten, Antworten lesen (E-045) |
| `app/llm_refusal.py`        | Merker für Weigerungen des Modells, nur ein Wahrheitswert (E-045) |
| `app/llm_request.py`        | Anfragen ans Gateway prüfen: Schema, Grenzen, Herkunft      |
| `app/llm_limits.py`         | Kosten, Budget, Minutengrenze des Gateways                  |
| `app/llm_probe.py`          | Rümpfe für Probeaufrufe des Gateways                        |
| `app/llm_check.py`          | Abgleich der Aufrufe von cowrie-b mit den Befehlen, nur Zähler (Schritt 7.3) |
| `app/config.py`             | Einstellungen aus Umgebungsvariablen, Secrets als `SecretStr` |
| `app/db.py`                 | Engine und Sessions (SQLAlchemy 2, psycopg 3, asynchron)    |
| `app/models.py`             | die sieben Tabellen aus Schritt 3.3, dazu `llm_responses` (7.3) |
| `app/hashing.py`            | HMAC-SHA256 der Quell-IPs (E-009, E-022)                   |
| `app/logging.py`            | JSON-Logs                                                  |
| `app/migrations/`           | Alembic, `0001_grundschema.py` legt alles an, `0002` ergänzt Kennzahlen der Kampagnen, `0003` zwischengespeicherte Tokens in `llm_usage`, `0004` Tabelle `llm_responses` und `commands.input_ref`, `0005` `reasoning_tokens` und `refusal` in `llm_usage` (E-045) |
| `worker/main.py`            | Zeitplan und Einzelläufe der Jobs                          |
| `worker/jobs.py`            | `ipinfo`, `statistik`, `aufraeumen` (Schritt 4.3), `attack` (6.1), `campaigns` (6.2) |
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
Die Variablen des LLM-Gateways sind dagegen optional: Ohne sie läuft die API,
nur das Gateway antwortet mit 503 (siehe „LLM-Gateway“ unten).

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

## Stream und Statistik (Schritt 5.1)

| Endpunkt                               | Inhalt                                                  |
|----------------------------------------|---------------------------------------------------------|
| `GET /stream`                          | Server-Sent Events: `ts`, `variant`, `country`, `event`, bei Befehlen `command` (höchstens 80 Zeichen, entschärft) |
| `GET /stats/overview`                  | Sensor online, heute und gesamt je Variante: Sitzungen, Logins, Befehle |
| `GET /stats/countries?days=30`         | Sitzungen je Land und Variante, die 50 häufigsten      |
| `GET /stats/heatmap?days=28&variant=all` | 7 × 24, Montag bis Sonntag, Stunde in UTC             |
| `GET /stats/breakdown?days=30`         | je Variante: interaktiv, Exec, ohne Befehl              |
| `GET /stats/campaigns`                 | die 10 größten Kampagnen mit Label (Schritt 6.2, E-039) |
| `GET /stats/recent`                    | die letzten 12 Befehle in der Form der Stream-Meldungen, älteste zuerst (Schritt 5.2) |

Statistik wird 30 Sekunden gecacht, 60 Anfragen pro Minute und höchstens 3
offene Streams je Client (E-029).

Den Stream von außen ansehen (Abbruch mit Strg-C):

```bash
curl -N https://api.tomkaufmann.dev/stream
```

Die Übersicht:

```bash
curl -s https://api.tomkaufmann.dev/stats/overview | python3 -m json.tool
```

**Ergebnis am 2026-09-18:** 208 Tests grün im Container. Von außen mitgeschnitten
kam eine eigene Testsitzung vollständig im Stream an (`connect`, `login`,
`command`, `closed`), die URL im Befehl entschärft
(`hxxp://example[.]test/lab-test.sh`). Im Mitschnitt stand keine einzige
Klartext-IPv4, und weder die Adresse des Sensors noch die des eigenen
Anschlusses, auch nicht entschärft. Alle Statistik-Endpunkte antworten mit
`Cache-Control: public, max-age=30`.

Stand der Statistik an diesem Tag, als Anhaltspunkt für Phase 7:

- 2.436 Sitzungen seit 2026-09-17, davon 3 interaktiv (zwei davon eigene
  Persona-Tests von `127.0.0.1`), 761 Exec-Aufrufe, 1.672 ohne Befehl.
- Rund drei Viertel der Sitzungen aus den Niederlanden (1.806), mit Abstand
  gefolgt von DE (143) und GB (103).

## Seite /lab (Schritt 5.2)

Die Seite selbst liegt im Repo Website-Demo unter `lab/`, `gate` liefert sie
aus (E-030). Aufbau und Datenquellen stehen in `docs/wireframe.md`. Von hier
kommt nur der Endpunkt `/stats/recent`, damit „Letzte Befehle“ nicht leer
startet.

Reihenfolge beim Ausrollen: erst die API (rsync, `build`, `up -d`, Tests wie
oben), dann den Pull Request in Website-Demo mergen. Die Seite kommt auch
ohne `/stats/recent` aus, die Liste füllt sich dann erst über den Stream.

Prüfen, dass der Endpunkt antwortet und keine Adresse enthält:

```bash
curl -s https://api.tomkaufmann.dev/stats/recent | python3 -m json.tool | head -20
```

**Ergebnis am 2026-09-18:**

- **API:** 212 Tests grün im Container. `/stats/recent` antwortet mit 12
  Befehlen, die längste Vorschau hat genau 80 Zeichen, und es steht keine
  IPv4 darin, weder im Klartext noch entschärft.
- **Pipeline:** Website-Demo#14 ist gemergt (`1a0b935`), alle Jobs der
  Pipeline sind grün. Der Smoke-Test meldet `/lab ohne Cookie: 200, mit CSP`,
  `/demo/` leitet weiter mit 302 auf `/login` um.
- **Seite von außen:**
  - Headless-Chrome bei 360 px und doppelter Pixeldichte: kein seitliches
    Scrollen, „Sensor online“, 1.296 Sitzungen heute, Stream live.
  - Die Liste „Letzte Befehle“ ist sofort voll, Exec-Aufrufe liegen bei
    99,7 %.
  - Der Weg über CORS zu `api.tomkaufmann.dev` funktioniert, und unter der
    CSP gibt es keine Verstöße.
- **Unverändert:** Shop-Demo, Landingpage und Caddyfile sind laut `git diff`
  gegenüber `main` nicht angefasst.

## Startseite als Projektseite (Schritt 5.3)

Statt einer Kachel ist die Startseite `tomkaufmann.dev` jetzt eine
Projektseite mit einer Karte je Projekt (E-031). Die Karte des Labs liest
`/stats/overview`, `/stats/countries?days=7` und `/stream`, zeigt aber nur
Zahlen und Länder, keine Befehle.

**Ergebnis am 2026-09-18:**

- **Pipeline:** Website-Demo#15 ist gemergt (`1b3d737`), alle Jobs der
  Pipeline sind grün.
- **Von außen:**
  - `/` und `/en` antworten mit CSP.
  - `/login` bleibt ohne CSP, `/demo/` leitet weiter mit 302 um.
  - `hub.js` und `globe.svg` kommen mit dem richtigen Typ.
- **Headless-Chrome bei 360 px:**
  - „Sensor online“, 1.562 Sitzungen heute und „latest: India, just now“.
  - Ein Live-Bogen aus Indien ist gezeichnet, der Weg über CORS zur API
    funktioniert also.
  - Kein seitliches Scrollen.
- **Ohne API** (lokal geprüft) bleiben beide Karten vollständig.

## Worker (Schritt 4.3)

| Job          | Takt      | Was er tut                                                        |
|--------------|-----------|-------------------------------------------------------------------|
| `ipinfo`     | täglich   | Prüfsumme der IPinfo-Lite-Datenbank abfragen, nur bei Änderung laden, prüfen und atomar ersetzen |
| `statistik`  | stündlich | `daily_stats` für heute, gestern und jeden Tag ohne Statistik neu rechnen |
| `aufraeumen` | täglich   | fehlende Statistik nachrechnen, dann Roh-Events älter als 90 Tage löschen |
| `campaigns`  | stündlich | Kampagnen neu aufbauen, Labels aus `rules/campaigns.yml` übernehmen (Schritt 6.2) |

Einen Job zur Rotation des HMAC-Schlüssels gibt es nicht, der Schlüssel bleibt
fest (E-022). Jeder Lauf schreibt `job fertig` oder `job fehlgeschlagen` mit
Dauer und Ergebnis ins Log.

**IPinfo-Token.** Aus dem kostenlosen Konto auf ipinfo.io, als `IPINFO_TOKEN`
in `/opt/honeypot-lab/.env`. Die URL mit Token taucht in keinem Log auf. IPinfo
erlaubt 10 Downloads am Tag je IP, die Abfrage der Prüfsumme zählt nicht mit.
Die Daten stehen unter CC BY-SA 4.0, der Quellenhinweis kommt in Schritt 5.2 auf
die Seite.

**Einzelne Läufe** ohne Warten auf den Zeitplan:

```bash
cd /opt/honeypot-lab && sudo docker compose -f docker-compose.server.yml exec worker python -m worker.main run ipinfo
```

`run statistik --alle-tage` rechnet jeden Tag neu, `run alle` alle Jobs
nacheinander.

**Länder für schon gespeicherte Sitzungen.** Was ankam, bevor die
IPinfo-Datenbank da war, hat kein Land, und nachträglich anreichern geht nicht:
Die Klartext-IPs sind weg. Solange die Rohlogs auf dem Sensor liegen
(14 Tage), hilft ein einmaliges Neueinlesen: Positionsmerker von Vector
löschen, Vector liest alles noch einmal, die API ergänzt bei bestehenden
Sitzungen das fehlende Land, und die Ereignisse selbst werden als Dubletten
verworfen (siehe `sensor/README.md`). Danach die Statistik neu rechnen:

```bash
cd /opt/honeypot-lab && sudo docker compose -f docker-compose.server.yml exec worker python -m worker.main run statistik --alle-tage
```

**Ergebnis am 2026-09-18:**

| Job          | Lauf                                                                 |
|--------------|----------------------------------------------------------------------|
| `ipinfo`     | Schleife nach dem Start: `aktualisiert`, 24,3 MB, Prüfsumme geprüft. Einzellauf zehn Sekunden später: `unverändert`, kein zweiter Download |
| `statistik`  | 2 Tage, 70 Zeilen; nach dem Nachtrag der Länder `--alle-tage`: 200 Zeilen |
| `aufraeumen` | 0 gelöscht, Stichtag 2026-06-20                                        |

Nach dem Neueinlesen vom Sensor haben 2.414 von 2.427 Sitzungen ein Land. Ohne
Land bleiben die eigenen Testsitzungen von `127.0.0.1`.

Ein Stolperstein beim Eintragen des Tokens: Landet der Wert ohne
`IPINFO_TOKEN=` in der `.env`, ist die Variable für Compose leer, und der
Worker wird bei `up -d` nicht neu erzeugt (`Running` statt `Started`). Die
Namen in der Datei lassen sich prüfen, ohne Werte zu zeigen:

```bash
sudo awk -F= '{ print (NF > 1 ? $1 : "(Zeile ohne =)") }' /opt/honeypot-lab/.env
```

**Einmalig bei einem schon vorhandenen Volume `honeypot-lab_ipinfo`:** Es wurde
angelegt, bevor das Image `/data` für den Worker vorbereitet hat, und gehört
deshalb root. So bekommt es den richtigen Eigentümer:

```bash
sudo docker run --rm --user 0 -v honeypot-lab_ipinfo:/data honeypot-lab-api:local chown 10001:10001 /data
```

## ATT&CK-Techniken (Schritt 6.1)

Jeder Befehl bekommt beim Ingest die Techniken, die er nach
`rules/attack.yml` trifft, in `commands.techniques` (E-037). Stream und
`/stats/recent` geben sie als zusätzliches Feld `techniques` aus, etwa
`["T1082", "T1105"]`. Ohne Treffer ist die Liste leer.

Die Regeln sind Daten. Eine Änderung braucht keinen neuen Code, aber einen
neuen Build, weil die Datei im Image liegt. Eine kaputte Regeldatei, etwa
mit einem Muster wie `(a+)+`, lässt die API gar nicht erst starten.

**Nachtaggen** nach einer Regeländerung oder für Befehle von vor Schritt 6.1.
Der Job `attack` läuft nur von Hand, nicht im Zeitplan und nicht bei `run alle`.
`<PFAD>` steht für das Projektverzeichnis auf dem Hauptserver:

```bash
cd <PFAD> && sudo docker compose -f docker-compose.server.yml exec worker python -m worker.main run attack
```

Das Ergebnis steht im Log: `geprueft`, `geaendert` und `attack_version`.

**Report der häufigsten Befehle ohne Technik.** Taggt erst neu und gibt dann
die 100 häufigsten Befehle ohne Treffer mit ihrer Anzahl aus:

```bash
cd <PFAD> && sudo docker compose -f docker-compose.server.yml exec worker python -m worker.main run attack --bericht
```

Die Ausgabe geht nur ins Terminal, nicht ins Log. Sie ist Angreifertext:
entschärft, auf 200 Zeichen gekürzt und mit sichtbar gemachten Steuerzeichen
(`\x1b` statt Escape-Sequenz). Trotzdem nur lesen, nichts daraus kopieren und
ausführen, und nicht ungeprüft an einen Coding-Agenten geben.

## Kampagnen (Schritt 6.2)

Der Job `campaigns` bündelt Sitzungen mit gleicher normalisierter
Befehlsfolge zu Kampagnen, ab 5 Sitzungen je Fingerprint (E-039). Er läuft
stündlich und bei `run alle`, jedes Mal als voller Neuaufbau. Labels kommen
nur aus `rules/campaigns.yml`; `/stats/campaigns` zeigt nur Kampagnen mit
Label. Wie Fingerprint und Normalisierung funktionieren und wie man ein Label
vergibt, steht in `docs/campaigns.md`.

**Ausrollen.** Nach rsync und `build` (siehe oben) die Migration 0002, dann
`up -d`, dann einmal von Hand laufen lassen. `<PFAD>` steht für das
Projektverzeichnis auf dem Hauptserver:

```bash
cd <PFAD> && sudo docker compose -f docker-compose.server.yml run --rm api alembic upgrade head
```

```bash
cd <PFAD> && sudo docker compose -f docker-compose.server.yml exec worker python -m worker.main run campaigns
```

Das Ergebnis steht im Log: `sitzungen`, `fingerprints`, `kampagnen`, `neu`,
`geaendert`, `entfernt`, `zugeordnet`, `gelabelt` und
`labels_ohne_kampagne` (Präfixe aus der Datei, zu denen es keine Kampagne
gibt). Hält der Ingest eine Sitzung länger als 5 Sekunden gesperrt, bricht der
Job ab (`OperationalError`) und versucht es beim nächsten Takt neu.

**Bericht der größten Kampagnen.** Baut erst neu auf und gibt dann die 20
größten Kampagnen aus, mit Präfix, `p3`, Art, Sitzungen je Variante,
Quellen, ASNs, typischem Abstand, Länge der Befehlsfolge, Label und den
ersten drei normalisierten Befehlen:

```bash
cd <PFAD> && sudo docker compose -f docker-compose.server.yml exec worker python -m worker.main run campaigns --bericht
```

Wie beim ATT&CK-Report: nur Terminal, nicht Log; Angreifertext, entschärft,
auf 200 Zeichen gekürzt, Steuerzeichen sichtbar. Nicht ungeprüft an einen
Coding-Agenten geben.

## LLM-Gateway (Schritt 7.2, Gemini seit E-045)

`POST /v1/chat/completions` nimmt ab Schritt 7.3 die Anfragen von cowrie-b
an, im OpenAI-Format. Das Gateway prüft Token und Anfrage, setzt Modell und
Grenzen aus der `.env` durch, leitet an die Gemini-API weiter (deren
OpenAI-kompatiblen Endpunkt) und schreibt jede Anfrage mit gültigem Token in
`llm_usage`, ohne Inhalt. Der echte API-Key steht nur in der `.env` des
Hauptservers (E-008). Herleitung der Grenzen und der Prüfung: E-043; Anbieter,
Modell, Denkmodus, Sperren und Kosten: E-045.

Adresse und Preise stehen fest in `app/llm_provider.py`, nicht in der `.env`:
`https://generativelanguage.googleapis.com/v1beta/openai/chat/completions`,
der Key nur im Header `Authorization`, nie als `?key=` in der URL. Erlaubt
sind nur feste Modellversionen aus der Liste dort, kein `-latest`.

| Antwort | Bedeutung | `llm_usage.status` |
|---------|-----------|--------------------|
| 200 | Antwort des Modells, auch leer | `ok` |
| 200 | leere Zeile oder Exec ohne Befehl, ohne Anbieter beantwortet | `local_empty` |
| 400, 413 | Anfrage ungültig oder zu groß, auch: nicht in Cowries Form, falscher Prompt-Hash | `rejected` |
| 401 | Token fehlt oder falsch | keine Zeile |
| 429 `rate_limited` | `LLM_CALLS_PER_MINUTE` erreicht, Anbieter nicht gerufen | `rate_limited` |
| 502 | 429 oder 402 des Anbieters: Rate-Limit, Ausgabenlimit, Prepay-Guthaben leer | `upstream_limited` |
| 502 | Antwort von Gemini gesperrt (`finish_reason` `content_filter…`, kein Kandidat) | `upstream_blocked` |
| 502 | jeder andere Fehler beim Anbieter | `upstream_error` |
| 503 `budget_exceeded` | Monats- oder Tagesbudget erreicht, Anbieter nicht gerufen | `budget_exceeded` |
| 503 `unavailable` | abgeschaltet oder unvollständig konfiguriert | `disabled`; ohne brauchbares `LLM_GATEWAY_TOKEN` keine Zeile |
| 504 | Zeitlimit beim Anbieter | `timeout` |

429 kommt nur von der Minutengrenze des Gateways, nie vom Budget und nie vom
Anbieter. Die Minutengrenze gehört zur Behandlung, ein Budgetstopp ist ein
Ausfall (`method.md` 8, V3); auf dem Sensor trennt beides nur `http_status`.
Für den Sensor sehen `upstream_limited`, `upstream_blocked` und
`upstream_error` gleich aus (502, gleicher Rumpf); getrennt zählt sie
`python -m app.llm_check` (siehe „Abgleich“ unten).

**Was an Gemini geht (E-045).** Gemini lehnt Anfragen ohne user-Nachricht
und Nachrichten mit leerem Text ab. Cowrie schickt bei Exec nur die
System-Nachricht mit dem Befehl am Ende. Das Gateway trennt den Befehl dort
ab und schickt ihn als user-Nachricht; der System-Prompt ist dann bei Exec
und interaktiv derselbe (Cache). Leere Nachrichten im Verlauf fallen weg, eine
leere letzte Zeile beantwortet das Gateway selbst leer. Geprüft wird vorher
Cowries Form; der Prompt-Hash ändert sich dadurch nicht.

**Kosten** in Millionstel US-Dollar (`cost_micros`), mit den Preisen aus
`app/llm_provider.py`. Denk-Tokens zählen als Ausgabe und stehen zusätzlich
in `reasoning_tokens`. `cost_micros` ist eine obere Schätzung ohne `usage`
und bei jedem Abbruch, nachdem die Verbindung stand (Zeitüberschreitung,
Lese- oder Schreibfehler, abgebrochene Verbindung, zu große Antwort): Der
Anbieter kann trotzdem abrechnen. 0 steht dort, wenn keine Verbindung
zustande kam, und bei einer Fehlerantwort des Anbieters (Google berechnet
400 und 500 nicht). So leert ein Ausfall des Anbieters nicht das Budget.

**Weigerungen.** Passt eine Antwort zu einer Wendung aus `app/llm_refusal.py`
(„I'm sorry“, „As an AI“ …), steht in `llm_usage.refusal` `true`. Kein Text,
nur der Merker; die Antwort geht trotzdem an Cowrie.

Jede Anfrage schreibt eine Logzeile `llm` mit Status, Tokens (auch
`reasoning_tokens`), Kosten, Latenz, `prompt_sha256`, `finish_reason` (nur
`stop`, `length`, `content_filter`, `sonst`), `block` (Grund einer Sperre aus
einer festen Liste), `leer` und `weigerung`. Prompt und Antwort stehen
nirgends, auch nicht bei Fehlern.

### Variablen

Alle in `/opt/honeypot-lab/.env`, Kommentare in `.env.example`. Fehlt ein Wert
oder ist er ungültig, startet die API trotzdem; nur das Gateway antwortet mit
503, und `llm-gateway aus` im Log nennt die Namen der fehlenden Variablen.

| Variable | Vorgabe | Bedeutung |
|----------|---------|-----------|
| `LLM_GATEWAY_ENABLED` | `false` | Schalter, aus heißt 503 |
| `LLM_GATEWAY_TOKEN` | – | Token von cowrie-b, auch in der `.env` des Sensors; mindestens 32 Zeichen |
| `LLM_API_KEY` | – | Gemini-API-Key des Lab-Projekts, nur hier |
| `LLM_MODEL` | – | `gemini-3.1-flash-lite` (E-045), nur Werte aus `app/llm_provider.py` |
| `LLM_MAX_TOKENS` | 2048 | Ausgabegrenze je Antwort, Denk-Tokens eingeschlossen |
| `LLM_TEMPERATURE` | 1 | Googles Vorgabe für Gemini 3, `method.md` 4.5 |
| `LLM_REASONING_EFFORT` | `minimal` | Denkmodus; `low` nur für `gemini-3.8-flash` |
| `LLM_MERGE_TURNS` | `false` | aufeinanderfolgende Nachrichten derselben Rolle zusammenfassen (Probe „verlauf“) |
| `LLM_TIMEOUT_SECONDS` | 30 | Zeitlimit beim Anbieter, höchstens 55 |
| `LLM_BUDGET_MONTH_USD`, `LLM_BUDGET_DAY_USD` | – | Budgets in US-Dollar, Kalendermonat und -tag in UTC |
| `LLM_CALLS_PER_MINUTE` | 60 | Aufrufe beim Anbieter je 60 Sekunden, alle zusammen |
| `LLM_PROMPT_SHA256` | leer | gepinnter Prompt-Hash, leer heißt nicht geprüft |

Seit E-045 entfallen `LLM_BASE_URL`, `LLM_MAX_TOKENS_PARAM`,
`LLM_PRICE_*_EUR` und `LLM_BUDGET_*_EUR`. Stehen sie noch in der `.env`,
werden sie ignoriert; besser löschen. Ohne Budgets gibt es kein Gateway.

Budget und Minutengrenze leben im Speicher des API-Prozesses. Nach einem
Neustart lädt das Gateway den Stand aus `llm_usage`. Die API läuft mit einem
Uvicorn-Prozess; mit mehreren hätte jeder sein eigenes Budget. Parallele
Anfragen können das Budget höchstens um die gerade laufenden überschreiten,
und davon gibt es nie mehr als `LLM_CALLS_PER_MINUTE`.

### Grenzen festlegen

Die Werte gehören zu den Behandlungsparametern und kommen vor dem Start in den
Start-Eintrag (`method.md` 4.5). Grundlage sind die Befehle der Vorperiode.
Die beiden Abfragen geben nur Zahlen aus, keinen Befehlstext. `<PFAD>` steht
für das Projektverzeichnis auf dem Hauptserver.

Befehle je Tag in den letzten 14 Tagen, Mittel und Höchstwert:

```bash
cd <PFAD> && sudo docker compose -f docker-compose.server.yml exec db psql -U honeypot -d honeypot -c "SELECT round(avg(n)) AS mittel, max(n) AS hoechstens FROM (SELECT count(*) AS n FROM commands WHERE occurred_at >= now() - interval '14 days' GROUP BY date_trunc('day', occurred_at)) AS je_tag;"
```

Höchste Zahl an Befehlen in einer Minute in den letzten 14 Tagen:

```bash
cd <PFAD> && sudo docker compose -f docker-compose.server.yml exec db psql -U honeypot -d honeypot -c "SELECT max(n) AS hoechstens_je_minute FROM (SELECT count(*) AS n FROM commands WHERE occurred_at >= now() - interval '14 days' GROUP BY date_trunc('minute', occurred_at)) AS je_minute;"
```

- **Kosten je Aufruf** mit `gemini-3.1-flash-lite` (Eingabe 0,25 $, Cache
  0,025 $, Ausgabe inkl. Denken 1,50 $ je Mio. Tokens): rund 8.000
  Eingabe-Tokens, davon ein unbekannter Teil aus dem Cache, dazu meist unter
  300 Ausgabe- und Denk-Tokens. Also `(Eingabe ohne Cache × 0,25 + Cache ×
  0,025 + Ausgabe × 1,50) / 1.000.000` Dollar: ohne Cache und mit 800
  Ausgabe-Tokens 3,2 m$, mit 70 % Cache und 250 Ausgabe-Tokens 1,1 m$.
- **Erwartete Tageskosten:** B bekommt etwa die Hälfte der Befehle, also
  `Mittel / 2 × Kosten je Aufruf`. Mit der Annahme aus E-045, rund 950
  Aufrufen je Tag in B: 3,04 $ an einem schlechten Tag ohne Cache, 92,40 $ im
  Monat.
- **Tagesbudget:** großzügig, etwa das Doppelte eines schlechten Tages, also
  6,10 $. Ein greifendes Tageslimit macht B für den Rest des Tages stumm; das
  sind Ausfallzeiten im Experiment (`method.md` 8).
- **Monatsbudget:** der schlechte Fall ohne Cache, aufgerundet: 100 $. Es
  muss die ganze Laufzeit samt Verlängerung tragen (`method.md` 10). Meldet
  Gemini `cached_tokens` nicht, bucht das Gateway alles zum vollen
  Eingabepreis; das Budget ist deshalb auf „ohne Cache“ gerechnet.
- **`LLM_CALLS_PER_MINUTE`:** über dem Höchstwert je Minute, mit Reserve. B
  bekommt im Mittel die Hälfte, aber die Zuteilung geht nach Adresse: Ein
  Schwall einer einzelnen Quelle landet ganz in einer Variante. Den Höchstwert
  deshalb nicht halbieren. Das Rate-Limit des Modells in AI Studio muss
  darüber liegen.

Nach dem Start zeigt `python -m app.llm_check --tage 7` die beobachtete
Cache-Quote und die hochgerechneten Kosten je Monat.

### Grenzen bei Google

Das Gateway ist die erste Grenze, Google die zweite. Beide zusammen fangen
auch einen Fehler im Gateway ab. Das Guthaben aus Google AI Pro (10 $ im
Monat) reicht allein nicht (E-045); darüber zahlt das Prepay-Guthaben.

1. **Guthaben aus AI Pro:** unter developers.google.com/profile den Vorteil
   des Google Developer Program aktivieren und das monatliche
   Cloud-Guthaben einem Cloud-Billing-Konto zuordnen.
2. **Eigenes Projekt** nur fürs Lab in AI Studio anlegen (oder ein
   Cloud-Projekt importieren). Key, Limits und Abrechnung hängen dann nur an
   diesem Projekt.
3. **Billing und Prepay:** im Projekt „Set up billing“ mit diesem Konto,
   Prepay mit mindestens 5 $. Ohne Prepay-Guthaben über 0 nutzt Google das
   Cloud-Guthaben nicht, und bei 0 $ antworten alle Keys mit 402
   (`upstream_limited`). Auto-Reload nur mit „Monthly auto-charge limit“ knapp
   über dem Monatsbudget des Gateways; ohne Auto-Reload rechtzeitig nachkaufen.
4. **Projekt-Ausgabenlimit:** Spend → „Monthly spend cap“ → „Edit spend cap“,
   etwas über dem Monatsbudget des Gateways (110 $), damit das Gateway zuerst
   greift. Laut Google experimentell und mit rund 10 Minuten Verzug.
5. **Key mit wenig Rechten:** in der Cloud Console unter APIs & Services →
   Credentials den Key auf „Generative Language API“ beschränken, optional
   auf die Adresse des Hauptservers.
6. **Bezahlte Stufe prüfen:** In AI Studio steht das Projekt auf „Paid“. Nur
   dann gilt: keine Nutzung von Prompts und Antworten zum Training
   (ai.google.dev/gemini-api/terms, „Paid Services“).

Prüfen:

- Projekt „Paid“, Prepay-Guthaben über 0, Ausgabenlimit gesetzt.
- Unter Rate limits: RPM des Modells über `LLM_CALLS_PER_MINUTE`.
- Monatlich die Ausgaben in AI Studio mit `llm_usage` vergleichen (Dollar):

```bash
cd <PFAD> && sudo docker compose -f docker-compose.server.yml exec db psql -U honeypot -d honeypot -c "SELECT date_trunc('month', occurred_at) AS monat, round(sum(cost_micros) / 1e6, 2) AS dollar, count(*) AS aufrufe FROM llm_usage GROUP BY 1 ORDER BY 1;"
```

### Ausrollen

1. Code übertragen wie oben unter „Auf den Hauptserver bringen“ (`server/`
   und `docker-compose.server.yml`).
2. Die Variablen aus `.env.example` in die `.env` übernehmen, zuerst mit
   `LLM_GATEWAY_ENABLED=false`; die entfallenen löschen (siehe „Variablen“).
3. Netz prüfen. `lab_edge` wurde ohne `--internal` angelegt; der Weg zum
   Anbieter läuft trotzdem ausdrücklich über `lab_egress` (E-043):

```bash
sudo docker network inspect lab_edge -f '{{.Internal}}'
```

   Erwartet: `false`.
4. Bauen, Migration 0005, Starten. Die Migration bricht ab, wenn in
   `llm_usage` schon Zeilen mit Kosten stehen: Das wären Euro aus der Zeit vor
   E-045. Bis dahin war kein Key eingetragen, also sollte es keine geben.
   Bricht sie doch ab, nicht weitermachen, sondern klären (Zeilen ansehen,
   Entscheidung in `docs/decisions.md`).

```bash
cd <PFAD> && sudo docker compose -f docker-compose.server.yml build
```

```bash
cd <PFAD> && sudo docker compose -f docker-compose.server.yml run --rm api alembic upgrade head
```

```bash
cd <PFAD> && sudo docker compose -f docker-compose.server.yml up -d
```

5. Log prüfen. Erwartet: `llm-gateway aus` mit `"abgeschaltet": true` und
   leerer Liste `fehlt`. Stehen dort Namen, fehlen diese Variablen:

```bash
cd <PFAD> && sudo docker compose -f docker-compose.server.yml logs api 2>&1 | grep llm-gateway
```

6. Weg nach außen, ohne Key. Erwartet: `erreichbar, HTTP` mit einem 4xx-Code:

```bash
cd <PFAD> && sudo docker compose -f docker-compose.server.yml exec api python -c "import urllib.request, urllib.error
try: urllib.request.urlopen('https://generativelanguage.googleapis.com/v1beta/openai/models', timeout=10)
except urllib.error.HTTPError as e: print('erreichbar, HTTP', e.code)"
```

7. Tests im Container wie unter „Tests auf dem Server“.

### Probeaufrufe

Das Token kommt in eine Shell-Variable, ohne dass es auf dem Bildschirm oder
in der Prozessliste erscheint; `curl -H @-` liest den Header von stdin:

```bash
TOKEN="$(sudo sed -n 's/^LLM_GATEWAY_TOKEN=//p' <PFAD>/.env)"
```

Die Rümpfe erzeugt `app/llm_probe.py` in der Form, die Cowrie schickt: Exec
nur mit der System-Nachricht, interaktiv mit einem Befehl, `verlauf` mit
einer früheren Antwort und einer leeren Antwort, `leer` mit einer leeren
Zeile. Alle haben dieselbe Probe-Persona, lang genug für Geminis Cache:

```bash
cd <PFAD> && for f in exec interactive verlauf leer; do sudo docker compose -f docker-compose.server.yml exec -T api python -m app.llm_probe $f > /tmp/llm-$f.json; done
```

1. Ohne Token. Erwartet: `HTTP 401`.

```bash
curl -sS -o /dev/null -w 'HTTP %{http_code}\n' -X POST --data-binary @/tmp/llm-exec.json https://api.tomkaufmann.dev/v1/chat/completions
```

2. Mit Token, Schalter noch aus. Erwartet: `HTTP 503`, Code `unavailable`.

```bash
printf 'Authorization: Bearer %s\n' "$TOKEN" | curl -sS -H @- -H 'Content-Type: application/json' --data-binary @/tmp/llm-exec.json -w '\nHTTP %{http_code}\n' https://api.tomkaufmann.dev/v1/chat/completions
```

3. `LLM_GATEWAY_ENABLED=true` in die `.env`, dann `up -d` wie oben. Im Log
   steht jetzt `llm-gateway bereit` mit Modell, `reasoning_effort` und Grenzen.
4. Ungültiger Rumpf. Erwartet: `HTTP 400`, Code `invalid_request`, kein
   Aufruf beim Anbieter:

```bash
printf 'Authorization: Bearer %s\n' "$TOKEN" | curl -sS -H @- -H 'Content-Type: application/json' -d '{}' -w '\nHTTP %{http_code}\n' https://api.tomkaufmann.dev/v1/chat/completions
```

5. Echter Aufruf in Exec-Form. Erwartet: `HTTP 200` und `gateway-probe-ok` in
   `choices[0].message.content`. Scheitert er mit 502, prüfen, ob das
   Gateway den Befehl abtrennt (Log: `upstream_status` 400):

```bash
printf 'Authorization: Bearer %s\n' "$TOKEN" | curl -sS -H @- -H 'Content-Type: application/json' --data-binary @/tmp/llm-exec.json -w '\nHTTP %{http_code}\n' https://api.tomkaufmann.dev/v1/chat/completions
```

6. Echter Aufruf in interaktiver Form, gleich danach. Erwartet ebenso
   `HTTP 200`:

```bash
printf 'Authorization: Bearer %s\n' "$TOKEN" | curl -sS -H @- -H 'Content-Type: application/json' --data-binary @/tmp/llm-interactive.json -w '\nHTTP %{http_code}\n' https://api.tomkaufmann.dev/v1/chat/completions
```

7. **Verlauf.** Nach dem Weglassen der leeren Antwort kommen zwei
   user-Nachrichten in Folge bei Gemini an, und die frühere Antwort hat keine
   Gemini-Signatur. Nur der echte Anbieter zeigt, ob er das annimmt. Erwartet:
   `HTTP 200` mit `gateway-probe-ok`. Bei `HTTP 502` und im Log
   `upstream_status` 400: `LLM_MERGE_TURNS=true` in die `.env`, `up -d`,
   wiederholen. Der Wert kommt in den Start-Eintrag (`method.md` 4.5).

```bash
printf 'Authorization: Bearer %s\n' "$TOKEN" | curl -sS -H @- -H 'Content-Type: application/json' --data-binary @/tmp/llm-verlauf.json -w '\nHTTP %{http_code}\n' https://api.tomkaufmann.dev/v1/chat/completions
```

8. **Leere Zeile.** Erwartet: `HTTP 200` mit leerem `content`, ohne Aufruf
   beim Anbieter (Status `local_empty`):

```bash
printf 'Authorization: Bearer %s\n' "$TOKEN" | curl -sS -H @- -H 'Content-Type: application/json' --data-binary @/tmp/llm-leer.json -w '\nHTTP %{http_code}\n' https://api.tomkaufmann.dev/v1/chat/completions
```

9. Log. Erwartet: Zeilen mit `"status": "ok"` und **demselben**
   `prompt_sha256`, `reasoning_tokens` klein (Denkmodus `minimal`), ab dem
   zweiten Aufruf meist `cached_tokens` über 0. Bleibt `cached_tokens` immer
   0, meldet Gemini den Cache nicht oder er greift nicht; dann bucht das
   Gateway alles zum vollen Preis (Budget ist darauf gerechnet):

```bash
cd <PFAD> && sudo docker compose -f docker-compose.server.yml logs --since 10m api 2>&1 | grep '"msg": "llm"'
```

10. `llm_usage`. Erwartet: die Zeilen aus 2, 4 bis 8 (`disabled`,
    `rejected`, `ok`, `ok`, `ok`, `local_empty`) mit Tokens, Kosten und
    Latenz:

```bash
cd <PFAD> && sudo docker compose -f docker-compose.server.yml exec db psql -U honeypot -d honeypot -c "SELECT id, occurred_at, model, status, prompt_tokens, cached_tokens, completion_tokens, reasoning_tokens, cost_micros, latency_ms, refusal FROM llm_usage ORDER BY id DESC LIMIT 7;"
```

11. Aufräumen:

```bash
rm -f /tmp/llm-exec.json /tmp/llm-interactive.json /tmp/llm-verlauf.json /tmp/llm-leer.json && unset TOKEN
```

Ist `LLM_PROMPT_SHA256` gepinnt, antworten die Probeaufrufe mit 400 und
`"grund": "prompt_hash"` im Log, denn die Probe-Persona ist nicht die von
cowrie-b. Auch das ist eine brauchbare Prüfung nach dem Pinnen.

### Hinweise zu cowrie-b

Umgesetzt in Schritt 7.3, Anleitung in `sensor/README.md`, Abschnitt
„cowrie-b (Schritt 7.3)“.

- **cowrie-b:** `COWRIE_LLM_HOST=https://api.tomkaufmann.dev` und
  `COWRIE_LLM_PATH=/v1/chat/completions` in `sensor/docker-compose.yml`, das
  `LLM_GATEWAY_TOKEN` als Datei unter `/srv/honeypot/secrets-b`. `model`,
  `max_tokens` und `temperature` von Cowrie ignoriert das Gateway. `debug`
  bleibt aus, sonst schreibt Cowrie Prompts und Antworten in sein Log.
- **Prompt-Hash pinnen:** Nach dem Prüfskript von cowrie-b den Wert holen und
  in `LLM_PROMPT_SHA256` übernehmen, siehe `sensor/README.md`; in den
  Start-Eintrag (`method.md` 4.5) kommt er zum Start.
- **Der Hash hängt an der Sensor-IP:** Der Prompt enthält die eigenen
  Adressen des Sensors (`{ip}`, `{ip6}`). Neue Adresse, neuer Hash: neu
  pinnen, sonst antwortet das Gateway mit 400.
- **Ein Prompt für beide Formen:** Der Hash setzt voraus, dass
  `system_prompt` und `system_prompt_exec` denselben Prompt bekommen. Sonst
  gibt es zwei Hashes, und das Gateway lehnt eine der beiden Formen ab.
- **Der Patch aus E-041** darf den Teil von Cowrie nicht verändern, der den
  System-Inhalt baut (`_build_system_context`: Guidance-Satz, Satz mit
  Hostname, Benutzer und Verzeichnis, Befehl am Ende). Sonst schlägt die
  Herkunftsprüfung an (400, `"grund": "herkunft"`). `tests/cowrie_llm.py`
  bildet Cowrie 3.0.14 nach.
- **`http_status` in `cowrie.llm.response`:** 429 heißt nur Minutengrenze
  des Gateways, sie gehört zur Behandlung. 503 heißt Gateway aus oder Budget
  erschöpft, beides ist ein Ausfall (`method.md` 8). 502 ist der Anbieter
  (in `llm_usage` `upstream_error`, `upstream_limited` oder
  `upstream_blocked`), 504 das Zeitlimit. Gesperrte Antworten gehören zur
  Behandlung; `method.md` 8 zieht sie bei der Ausfallzeit ab (E-045).

## cowrie-b am Ingest (Schritt 7.3)

Der Patch für cowrie-b schreibt je Befehl ein Ereignis `cowrie.llm.response`
(E-041, E-044). `/ingest` nimmt es an, prüft jedes Feld und legt es zusätzlich
in `llm_responses` ab; die Tabelle bleibt, wenn der Worker die Roh-Events nach
90 Tagen löscht.

| `outcome` | Bedeutung | `http_status` | in `method.md` |
|-----------|-----------|---------------|----------------|
| `ok` | Antwort da, auch leer (`output_chars` 0) | 200 | Behandlung |
| `rate_limited` | Minutengrenze des Gateways | 429 | Behandlung |
| `local_rate_limit` | Cowries Begrenzung je Adresse, kein Aufruf | leer | Behandlung |
| `unavailable` | Gateway aus oder Budget erschöpft | 503 | Ausfall |
| `upstream_error` | Fehler beim Anbieter | 502 | Ausfall |
| `timeout` | Zeitlimit des Gateways oder von Cowrie | 504 oder leer | Ausfall |
| `error` | alles andere | Code oder leer | Ausfall |

Zuordnung: Ein Aufruf gehört zur Zeile in `commands` derselben Sitzung mit
`sequence = command_index`. Beide Seiten tragen `input_ref`, einen HMAC über
den SHA-256 des rohen Befehls mit dem `IP_HMAC_KEY` (eigene Domain). Den
einfachen Hash speichert der Ingest nicht: Mit allen Adressen für `<src>`
eingesetzt ließe er sich zurückrechnen (E-044). Ein `llm.response` aus
Variante A wird abgelehnt.

Das Gateway kürzt seine Antworten jetzt auf 16.384 Zeichen und 65.536 Byte
als JSON, und `MAX_TOTAL_CHARS` liegt bei 163.840. So geht auch die größte
Anfrage durch, die Cowrie bauen kann (E-044).

### Ausrollen

**Vor** cowrie-b, sonst lehnt `/ingest` die neuen Ereignisse ab und Vector
verwirft sie (E-027).

1. Übertragen wie unter „Auf den Hauptserver bringen“.
2. Bauen, Migration 0004, starten:

```bash
cd /opt/honeypot-lab && sudo docker compose -f docker-compose.server.yml build
```

```bash
cd /opt/honeypot-lab && sudo docker compose -f docker-compose.server.yml run --rm api alembic upgrade head
```

```bash
cd /opt/honeypot-lab && sudo docker compose -f docker-compose.server.yml up -d
```

3. Tests im Container wie unter „Tests auf dem Server“. Erwartet: alle grün,
   nichts übersprungen.

### Abgleich

Gibt nur Zähler aus. Erwartet: `passt` gleich `aufrufe`, `passt_nicht`,
`ohne_befehl` und `befehle_ohne_aufruf` 0. Ein Wert über 0 bei
`passt_nicht` oder `ohne_befehl` heißt: In einer Sitzung ist ein
`command.input` verloren gegangen, die Nummern sind verrutscht.

Unter `gateway` steht die Sicht des Gateways aus `llm_usage` (E-045): Zahl je
`status` (darunter `upstream_blocked`, auf dem Sensor nur `upstream_error`),
`weigerungen`, `cache_quote` (Summe `cached_tokens` / Summe `prompt_tokens`),
`kosten_usd` im Zeitraum, `aufrufe_je_tag` und `kosten_je_monat_usd`, die
Kosten des Zeitraums hochgerechnet auf 30,4 Tage. Die gebuchten Kosten
enthalten die beobachtete Cache-Quote schon. Ohne `--tage` zählt der Zeitraum
ab der ersten Zeile in `llm_usage`.

```bash
cd /opt/honeypot-lab && sudo docker compose -f docker-compose.server.yml exec -T api python -m app.llm_check --tage 1
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
