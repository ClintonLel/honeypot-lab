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
| `app/stream.py`             | `GET /stream`: Live-Ereignisse als Server-Sent Events       |
| `app/stats.py`              | `GET /stats/*`: Übersicht, Länder, Heatmap, Exec/interaktiv, Kampagnen |
| `app/ratelimit.py`          | Rate-Limit pro Client, Schlüssel ohne Adresse               |
| `app/config.py`             | Einstellungen aus Umgebungsvariablen, Secrets als `SecretStr` |
| `app/db.py`                 | Engine und Sessions (SQLAlchemy 2, psycopg 3, asynchron)    |
| `app/models.py`             | die sieben Tabellen aus Schritt 3.3                        |
| `app/hashing.py`            | HMAC-SHA256 der Quell-IPs (E-009, E-022)                   |
| `app/logging.py`            | JSON-Logs                                                  |
| `app/migrations/`           | Alembic, `0001_grundschema.py` legt alles an               |
| `worker/main.py`            | Zeitplan und Einzelläufe der Jobs                          |
| `worker/jobs.py`            | `ipinfo`, `statistik`, `aufraeumen` (Schritt 4.3)          |
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

## Stream und Statistik (Schritt 5.1)

| Endpunkt                               | Inhalt                                                  |
|----------------------------------------|---------------------------------------------------------|
| `GET /stream`                          | Server-Sent Events: `ts`, `variant`, `country`, `event`, bei Befehlen `command` (höchstens 80 Zeichen, entschärft) |
| `GET /stats/overview`                  | Sensor online, heute und gesamt je Variante: Sitzungen, Logins, Befehle |
| `GET /stats/countries?days=30`         | Sitzungen je Land und Variante, die 50 häufigsten      |
| `GET /stats/heatmap?days=28&variant=all` | 7 × 24, Montag bis Sonntag, Stunde in UTC             |
| `GET /stats/breakdown?days=30`         | je Variante: interaktiv, Exec, ohne Befehl              |
| `GET /stats/campaigns`                 | die 10 größten Kampagnen (ab Schritt 6.2)              |
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
