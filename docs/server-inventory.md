# Hauptserver: Bestandsaufnahme und Plan

Stand: 2026-09-17 (Schritte 3.1 und 3.2). Grundlage sind die Ausgabe der Befehle
aus dem Bauplan auf dem Hauptserver, das Repo `ClintonLel/Website-Demo` (Stand
`main`) und die öffentlichen DNS-Einträge. Freigegeben ist Variante A mit rsync
(siehe „Freigabe“). Umgesetzt ist bisher nur die Anbindung an Caddy (Schritt
3.2, Pull Request `ClintonLel/Website-Demo#13`, gemerged am 2026-09-17 als
`af1a81b`); die Lab-Dienste selbst folgen in Schritt 3.3.

## Bestandsaufnahme

### System

| Merkmal       | Wert                                                            |
|---------------|-----------------------------------------------------------------|
| OS            | Ubuntu 26.04.1 LTS (resolute)                                   |
| CPU           | 2 vCPU                                                          |
| RAM           | 3,7 GiB, davon 683 MiB belegt, 3,1 GiB verfügbar                |
| Swap          | 2,0 GiB, ungenutzt                                              |
| Disk          | `/dev/sda1` 38 GB, 5,4 GB belegt (15 %), 31 GB frei             |
| Dienste       | docker, containerd, ssh, cron, atd, chrony, rsyslog, unattended-upgrades, qemu-guest-agent, multipathd, polkit, dbus |

### Docker

| Compose-Projekt | Datei                               | Status     |
|-----------------|-------------------------------------|------------|
| `globe-demo`    | `/opt/globe-demo/docker-compose.yml` | 2 Container |

| Container            | Image              | Ports                                                   | Netzwerk             |
|----------------------|--------------------|---------------------------------------------------------|----------------------|
| `globe-demo-caddy-1` | `caddy:2-alpine`   | Host 80/tcp, 443/tcp, 443/udp (IPv4 und IPv6), intern 2019 | `globe-demo_default` |
| `globe-demo-gate-1`  | `globe-demo-gate` (lokal gebaut) | intern 3000/tcp                        | `globe-demo_default` |

Netzwerke: `bridge`, `host`, `none` (Docker-Standard) und `globe-demo_default`.
Caddy ist der einzige Reverse Proxy. Außerhalb von Docker gibt es weder nginx
noch Traefik oder Caddy.

### Webseiten-Stack (Repo Website-Demo)

`/opt/globe-demo` ist ein Git-Checkout von `ClintonLel/Website-Demo`.
`docker-compose.yml` und `Caddyfile` im Repo sind seit Commit `cf1d7e8`
(2026-09-02) unverändert.

- **`gate`:** Node-Server auf Port 3000, nur per `expose` erreichbar. Er
  liefert die Startseite von tomkaufmann.dev (Deutsch und Englisch), den Login
  und hinter dem Login die Globus-Demo unter `/demo/`. Webseite und
  Shop-/Globus-Demo laufen also beide in diesem Container.
- **`caddy`:** Das Caddyfile hat einen Block für `www.{$DOMAIN}`
  (Weiterleitung) und einen für `{$DOMAIN}` mit `encode zstd gzip`, HSTS
  inklusive Subdomains und `reverse_proxy gate:3000`. Die Zertifikate liegen
  im Volume `caddy_data`, ein Neuaufbau des Containers holt also keine neuen.
- **Deployment:** GitHub Actions führt bei jedem Push auf `main` über einen
  Deploy-User mit Forced Command `/usr/local/bin/deploy-globe-demo` aus. Das
  Skript macht `git pull` und `docker compose up -d --build`. Danach prüft ein
  Smoke-Test `/healthz`, `/` und die Weiterleitung von `/demo/`.

### DNS

| Name                   | Typ  | Wert                    |
|------------------------|------|-------------------------|
| `tomkaufmann.dev`      | NS   | INWX (`ns.inwx.de`, `ns2.inwx.de`, `ns3.inwx.eu`) |
| `tomkaufmann.dev`      | A    | 159.69.188.127          |
| `tomkaufmann.dev`      | AAAA | 2a01:4f8:c17:3201::1    |
| `www.tomkaufmann.dev`  | A    | 159.69.188.127 (kein AAAA) |
| `api.tomkaufmann.dev`  | A    | 159.69.188.127 (bei INWX angelegt am 2026-09-17) |
| `api.tomkaufmann.dev`  | AAAA | 2a01:4f8:c17:3201::1 (bei INWX angelegt am 2026-09-17) |

Es gibt keinen CAA-Eintrag, Let's Encrypt ist also nicht eingeschränkt.

### Ports und Firewall

| Port       | Prozess                   | ufw                        |
|------------|---------------------------|----------------------------|
| 22/tcp     | sshd (IPv4 und IPv6)      | erlaubt von überall        |
| 80/tcp     | docker-proxy → Caddy      | erlaubt von überall        |
| 443/tcp    | docker-proxy → Caddy      | erlaubt von überall        |
| 443/udp    | docker-proxy → Caddy (HTTP/3) | nicht freigegeben, Docker umgeht ufw |
| 53         | systemd-resolved, nur lokal | –                        |

ufw ist aktiv: eingehend alles gesperrt außer 22, 80 und 443, ausgehend alles
erlaubt. nftables enthält nur die Tabellen von Docker (`ip filter`, `ip nat`,
`ip raw` sowie IPv6).

### Beobachtungen

- **Docker umgeht ufw.** Ports, die ein Container per `ports:` veröffentlicht,
  sind unabhängig von ufw von außen erreichbar. Man sieht das an 443/udp. Neue
  Dienste dürfen deshalb keine Ports auf dem Host veröffentlichen.
- **Wenig Speicher.** 3,7 GiB RAM und 2 vCPU teilen sich Webseite und Lab. Die
  Grenzen im Plan sind so gesetzt, dass unter Last immer die Webseite Vorrang
  hat.
- **Nicht gepinntes Caddy-Image.** `caddy:2-alpine` widerspricht der Regel
  „Image-Tags pinnen“. Die Datei gehört aber zur bestehenden Webseite und bleibt
  unverändert, solange du es nicht verlangst.
- **Änderungen am Webseiten-Stack nur über das Repo.** Eine Änderung direkt in
  `/opt/globe-demo` macht den Checkout „dirty“. Der nächste `git pull` der
  Pipeline kann dann scheitern.
- **Caddyfile-Änderungen allein greifen nicht.** Git ersetzt die Datei beim
  `git pull` durch eine neue, der Container sieht aber weiter die alte, die per
  Bind-Mount eingebunden ist. `docker compose up -d` baut Caddy nur neu, wenn
  sich die Compose-Konfiguration ändert. Eine reine Caddyfile-Änderung braucht
  deshalb ein zusätzliches `docker compose restart caddy`. Das betrifft die
  bestehende Pipeline und wird hier nicht geändert.
- **SSH auf Port 22.** Der Zugang ist von überall erlaubt. Das gehört nicht zu
  diesem Schritt, wäre aber einen eigenen Blick wert (Key-only, anderer Port wie
  beim Sensor).

## Plan

### Überblick

```text
Internet ──443──> Caddy (globe-demo, unverändert bis auf Netz und Site-Block)
                    │  Netz lab_edge
                    ▼
                  api (FastAPI, :8000) ──lab_internal──> db (PostgreSQL)
                                                           ▲
                  worker ──────────────lab_internal────────┘
                    │  Netz lab_egress
                    ▼
                  Internet (IPinfo-Download)

Sensor ──HTTPS──> api.tomkaufmann.dev/ingest, /v1/chat/completions
```

Das Lab läuft als eigenes Compose-Projekt `honeypot-lab` in
`/opt/honeypot-lab`, getrennt von `/opt/globe-demo`. Kein Lab-Dienst
veröffentlicht einen Port auf dem Host. Von außen ist nur die API erreichbar,
und zwar über den vorhandenen Caddy.

### Container

| Dienst   | Image                                   | Netzwerke                  | Host-Ports | Aufgabe                                    |
|----------|-----------------------------------------|----------------------------|------------|--------------------------------------------|
| `db`     | `postgres:18` (Tag und Digest in 3.3)   | `lab_internal`             | keine      | Datenbank, Volume `honeypot-lab_pgdata`    |
| `api`    | eigenes Image auf `python:3.12-slim` (gepinnt) | `lab_internal`, `lab_edge`, Alias `lab-api` | keine | Ingest, SSE-Stream, Statistik, Mitschnitte, LLM-Gateway (Port 8000 im Container) |
| `worker` | dasselbe Image wie `api`, anderer Befehl | `lab_internal`, `lab_egress` | keine    | IPinfo-Download, Aggregation, Aufräumen    |

### Docker-Netzwerke

| Netzwerk       | Art                                      | Mitglieder         | Zweck                                           |
|----------------|------------------------------------------|--------------------|-------------------------------------------------|
| `lab_internal` | `internal: true`, ohne Internetzugang    | db, api, worker    | Datenbankzugriff, db hat keinen Weg nach außen  |
| `lab_edge`     | eigenes Bridge-Netz, einmal von Hand angelegt, in beiden Projekten `external` | Caddy, api | Caddy erreicht nur die API. Die API erreicht darüber den LLM-Anbieter. |
| `lab_egress`   | Bridge-Netz des Lab-Projekts             | worker             | ausgehender Download der IPinfo-Datenbank       |

`gate` und die übrigen Dienste der Webseite sehen keinen Lab-Container, und
die Datenbank ist nur aus `lab_internal` erreichbar.

### Ports

- **Keine neuen Host-Ports.** Auf dem Host ändert sich an 22, 80 und 443
  nichts, und ufw braucht keine neue Regel.
- **Datenbank für Wartung:** über `docker compose exec db psql`. Nur falls
  nötig, zeitweise mit Bindung an `127.0.0.1` und SSH-Tunnel, nie auf
  `0.0.0.0`.
- **Interne Ports:** API 8000, PostgreSQL 5432, beide nur in Docker-Netzen.

### Ressourcenlimits

Budget auf 3,7 GiB RAM und 2 vCPU. Harte Grenzen verhindern, dass das Lab die
Webseite verdrängt. `cpu_shares` gibt der Webseite bei CPU-Knappheit doppeltes
Gewicht. `oom_score_adj` sorgt dafür, dass bei Speichermangel zuerst ein
Lab-Container beendet wird.

| Dienst   | `mem_limit` | `cpus` | `cpu_shares` | `oom_score_adj` | `pids_limit` | Erwartet im Betrieb |
|----------|-------------|--------|--------------|-----------------|--------------|---------------------|
| `db`     | 768 MiB     | 1.0    | 512          | 300             | 200          | 150 bis 300 MiB     |
| `api`    | 384 MiB     | 1.0    | 512          | 300             | 200          | 100 bis 200 MiB     |
| `worker` | 384 MiB     | 0.5    | 256          | 300             | 100          | 100 bis 250 MiB     |
| **Summe Lab** | **1,5 GiB** | | | | |                                  |

- **Rechnung:** Heute sind 683 MiB belegt. Mit dem Lab am Limit wären es rund
  2,2 GiB. Es bleiben etwa 1,5 GiB für den Page-Cache, den PostgreSQL und Caddy
  brauchen, dazu 2 GiB Swap als Reserve.
- **PostgreSQL passend zu 768 MiB:** `shared_buffers=192MB`,
  `effective_cache_size=512MB`, `work_mem=4MB`, `maintenance_work_mem=64MB`,
  `max_connections=40`.
- **Für alle Lab-Container:** Docker-Log-Rotation (`max-size 10m`,
  `max-file 3`), `no-new-privileges`, `cap_drop: ALL` (für `db` nur die nötigen
  Capabilities), `restart: unless-stopped`. `api` und `worker` laufen ohne Root
  und nach Möglichkeit schreibgeschützt.
- **Disk:** 31 GB frei. Roh-Events werden nach 90 Tagen gelöscht (Schritt 4.3),
  Backups kommen in Schritt 9.1.

### Anbindung an Caddy

Damit Caddy die API erreicht, müssen beide in einem gemeinsamen Docker-Netz
sein. Dafür gibt es zwei Wege.

**Variante A, gewählt: eigenes Netz `lab_edge`**

Die Änderung am Webseiten-Stack läuft über einen Pull Request in
`ClintonLel/Website-Demo`, nicht direkt auf dem Server. Die Reihenfolge ist
wichtig, denn Compose bricht ab, wenn ein als `external` markiertes Netz fehlt.

1. **DNS bei INWX** (erledigt am 2026-09-17): A-Eintrag `api` mit
   159.69.188.127 und AAAA-Eintrag `api` mit 2a01:4f8:c17:3201::1. Die Werte sind dieselben wie für
   `tomkaufmann.dev`. Erst weitermachen, wenn `dig +short api.tomkaufmann.dev`
   die IP liefert, sonst scheitert Caddys Zertifikatsanfrage.
2. **Netz auf dem Server anlegen**, einmalig und vor dem Merge:
   `docker network create lab_edge`.
3. **Pull Request in Website-Demo** (Schritt 3.2, gemerged am 2026-09-17:
   `ClintonLel/Website-Demo#13`, Branch `lab-api`):
   - In `docker-compose.yml` bekommt `caddy` die Netze `default` und
     `lab_edge`. `default` muss ausdrücklich dastehen, sonst verliert Caddy die
     Verbindung zu `gate`.
   - Unten kommt `lab_edge` mit `external: true` dazu.
   - Das Caddyfile bekommt einen Block `api.{$DOMAIN}`.
4. **Merge auf `main`:** Die Pipeline führt `git pull` und `up -d --build` aus.
   Weil sich die Compose-Konfiguration von `caddy` ändert, baut Compose den
   Container neu. Die Webseite ist dabei wenige Sekunden nicht erreichbar, die
   Zertifikate bleiben im Volume `caddy_data`, und der Smoke-Test prüft danach
   die Webseite.
5. **Bis das Lab läuft (Schritt 3.3)**, antwortet `api.tomkaufmann.dev` mit 502,
   hat aber schon ein gültiges Zertifikat.

Geplante Änderung an `docker-compose.yml` in Website-Demo:

```yaml
  caddy:
    # ... unverändert ...
    networks:
      - default
      - lab_edge

networks:
  lab_edge:
    external: true
```

- **Vorteile:** Caddy sieht nur die API. `docker compose down` in einem der
  Projekte blockiert das andere nicht. Die Trennung ist sauber.
- **Nachteil:** Eine kleine Änderung am Webseiten-Stack. Du hast sie mit der
  Wahl von Variante A ausdrücklich freigegeben.

**Variante B, nicht gewählt: API tritt `globe-demo_default` bei**

Die Compose-Datei der Webseite bleibt unverändert, nur der Site-Block kommt
dazu.

- **Nachteil:** Die API teilt sich das Netz mit `gate`.
- **Nachteil:** `docker compose down` von `globe-demo` kann das Netz nicht
  entfernen, solange die API daran hängt, und meldet einen Fehler. Das Lab
  greift damit in den Betrieb der Webseite ein.
- **Nachteil:** Die Anbindung hängt am internen Netznamen eines fremden
  Projekts.

**Site-Block, umgesetzt in Schritt 3.2** (Pull Request
`ClintonLel/Website-Demo#13`). Wie die bestehenden Blöcke nutzt er `{$DOMAIN}`:

```caddyfile
api.{$DOMAIN} {
	header {
		Strict-Transport-Security "max-age=31536000; includeSubDomains"
		-Server
	}

	request_body {
		max_size 1MB
	}

	@browser header Origin https://{$DOMAIN}
	header @browser {
		defer
		Access-Control-Allow-Origin "https://{$DOMAIN}"
		+Vary Origin
	}

	@preflight {
		method OPTIONS
		header Origin https://{$DOMAIN}
	}
	handle @preflight {
		header {
			Access-Control-Allow-Methods "GET, POST, OPTIONS"
			Access-Control-Allow-Headers "Content-Type"
			Access-Control-Max-Age "86400"
		}
		respond 204
	}

	handle /stream* {
		reverse_proxy lab-api:8000 {
			flush_interval -1
		}
	}

	handle {
		encode zstd gzip
		reverse_proxy lab-api:8000
	}
}
```

- **Zertifikat:** Caddy holt es selbst über die HTTP-Challenge auf Port 80,
  sobald der DNS-Eintrag steht. HSTS setzt der Block selbst, zusätzlich gilt
  `includeSubDomains` aus dem Hauptblock auch für `api`.
- **CORS:** nur `https://{$DOMAIN}`. Preflight-Anfragen beantwortet Caddy
  selbst, die API sieht keine `OPTIONS`. `defer` setzt den Header erst beim
  Schreiben der Antwort, damit keine zwei Werte nebeneinander stehen. Die API
  darf deshalb keine eigenen CORS-Header setzen (E-021).
- **Server-Sent Events:** `/stream` liegt in einem eigenen `handle` mit
  `flush_interval -1` und ohne `encode`; Kompression würde den Stream wieder
  puffern. Alle anderen Antworten werden komprimiert.
- **Request-Größe:** `max_size 1MB` gilt auch für `/ingest`. Vector muss seine
  Batches darunter halten (Schritt 4.2).
- **Optional:** `/ingest` und `/v1/chat/completions` zusätzlich auf die IP des
  Sensors beschränken (`remote_ip`). Das Token bleibt trotzdem Pflicht, weil
  sich die IP beim Neuaufbau des Sensors ändert.

### Deployment und Secrets

- **Ablage:** `/opt/honeypot-lab` mit `docker-compose.server.yml`, `server/` und
  `.env` (Rechte 600, Eigentümer root). Secrets laut `.env.example`,
  Abschnitt 1 und 2.
- **Übertragung:** vom Laptop per rsync, wie beim Sensor (E-017, gewählt).
  Das Lab ist damit unabhängig von der Pipeline der Webseite, und auf dem Server
  liegen keine Zugangsdaten zum Repo `honeypot-lab`.
- **Build:** Das API-Image wird auf dem Server gebaut (`docker compose build`).
  Basis-Images sind mit Tag und Digest gepinnt.

### Auswirkungen auf Webseite und Shop-Demo

| Bereich                                | Änderung                                      |
|----------------------------------------|-----------------------------------------------|
| `gate`, Inhalte der Webseite, Shop-/Globus-Demo | keine                                 |
| `docker-compose.yml` in Website-Demo   | Caddy bekommt die Netze `default` und `lab_edge`, per Pull Request |
| Caddyfile in Website-Demo              | neuer Block `api.{$DOMAIN}`, bestehende Blöcke bleiben (Schritt 3.2, mit Diff vorab) |
| Neustarts der Webseite                 | einmal beim Merge: Caddy wird in wenigen Sekunden neu aufgebaut, `gate` bleibt unberührt |
| Deployment-Pipeline, Smoke-Test        | keine                                         |
| ufw, Host-Ports                        | keine                                         |
| Last                                   | durch Limits begrenzt, Webseite hat Vorrang   |

## Geklärte Fragen

| Frage                                  | Antwort                                                    |
|----------------------------------------|------------------------------------------------------------|
| Caddy-Konfiguration und Zertifikate    | aus Website-Demo (`main`, `cf1d7e8`). Zertifikate liegen im Volume `caddy_data`. |
| Aufgabe von `gate`                     | liefert Startseite, Login und Globus-Demo aus               |
| DNS                                    | INWX, Werte siehe „DNS“                                     |
| Anbindung                              | Variante A, eigenes Netz `lab_edge`                         |
| Übertragung                            | rsync vom Laptop                                           |

**Vor Schritt 3.2 geprüft (2026-09-17):** Stimmt der Stand auf dem Server mit
`main` überein? Ja: leeres `git status`, HEAD `cc3bb5d` (aktueller `main`) und
die Prüfsummen `8828acf5…` (docker-compose.yml) und `3753238c…` (Caddyfile).
Derselbe Befehl prüft das jederzeit erneut, auf dem Hauptserver:

```bash
cd /opt/globe-demo && git status --short && git log -1 --oneline && sha256sum docker-compose.yml Caddyfile
```

## Schritt 3.2: Rollout und Prüfung

Alle Befehle laufen auf dem Hauptserver, sofern nicht anders vermerkt.

1. **Caddyfile des Branches prüfen, bevor er gemerged wird.** Ein Fehler im
   Caddyfile würde beim Deploy den Caddy-Container stoppen und die Webseite
   mitnehmen. Der Check lädt nur einen Ref, der Checkout bleibt sauber:

   ```bash
   cd /opt/globe-demo && git fetch --depth=1 origin lab-api && git show FETCH_HEAD:Caddyfile > /tmp/Caddyfile.lab
   ```

   ```bash
   docker run --rm -e DOMAIN=tomkaufmann.dev -e ACME_EMAIL=dummy@example.com -v /tmp/Caddyfile.lab:/etc/caddy/Caddyfile:ro caddy:2-alpine caddy validate --adapter caddyfile --config /etc/caddy/Caddyfile
   ```

   Erwartet: `Valid configuration`.

2. **Netz anlegen**, einmalig und vor dem Merge. Fehlt es, bricht
   `docker compose up -d` ab, weil `lab_edge` als `external` eingetragen ist:

   ```bash
   docker network create lab_edge
   ```

3. **Pull Request mergen.** Die Pipeline macht `git pull` und
   `docker compose up -d --build`. Caddy wird neu gebaut, `gate` bleibt stehen.

4. **Zertifikat und Antwort prüfen** (geht auch vom Laptop):

   ```bash
   curl -sS -o /dev/null -w 'HTTP %{http_code}, TLS-Pruefung %{ssl_verify_result}\n' https://api.tomkaufmann.dev/
   ```

   Erwartet: `HTTP 502` (die API kommt erst in Schritt 3.3) und
   `TLS-Pruefung 0`, also ein gültiges Zertifikat. Aussteller und Laufzeit:

   ```bash
   echo | openssl s_client -connect api.tomkaufmann.dev:443 -servername api.tomkaufmann.dev 2>/dev/null | openssl x509 -noout -subject -issuer -dates
   ```

5. **Webseite gegenprüfen:**

   ```bash
   curl -sS -o /dev/null -w '%{http_code}\n' https://tomkaufmann.dev/ https://www.tomkaufmann.dev/
   ```

6. **Netze von Caddy kontrollieren:**

   ```bash
   docker inspect -f '{{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{end}}' globe-demo-caddy-1
   ```

   Erwartet: `globe-demo_default lab_edge`.

### Ergebnis am 2026-09-17

Der Rollout ist durch, Schritt 3.2 ist abgeschlossen.

| Prüfung                         | Ergebnis                                                              |
|---------------------------------|-----------------------------------------------------------------------|
| Caddyfile des Branches          | `Valid configuration` (Caddy 2 im Wegwerf-Container)                  |
| Netz `lab_edge`                 | vorhanden, Caddy hängt in `globe-demo_default` und `lab_edge`          |
| Deploy nach dem Merge           | Workflow erfolgreich, Smoke-Test der Webseite grün                    |
| `https://api.tomkaufmann.dev/`  | HTTP 502, `ssl_verify_result 0`                                       |
| Zertifikat                      | `CN=api.tomkaufmann.dev`, Let's Encrypt, gültig bis 2026-12-16        |
| `https://tomkaufmann.dev/`      | HTTP 200, unverändert                                                 |
| CORS, erlaubte Herkunft         | Preflight von `https://tomkaufmann.dev` → 204 mit `Access-Control-Allow-Origin`, `-Methods`, `-Max-Age`, `Vary: Origin` |
| CORS, fremde Herkunft           | kein `Access-Control-Allow-Origin`                                    |
| HSTS                            | `max-age=31536000; includeSubDomains`                                 |

Anmerkungen:

- Das 502 ist der erwartete Zustand, solange das Lab nicht läuft. Caddy erreicht
  `lab-api:8000` noch nicht.
- Ein Preflight von fremder Herkunft trifft den Matcher nicht und geht an die
  API. Heute antwortet Caddy mit 502, später die API mit 405 — in beiden Fällen
  ohne CORS-Header.
- `notBefore` des Zertifikats liegt eine Stunde vor der Ausstellung. Das ist die
  übliche Rückdatierung von Let's Encrypt, kein Hinweis auf ein älteres
  Zertifikat.
- Vor dem Merge beendete Caddy den TLS-Handshake für `api.tomkaufmann.dev` mit
  `tlsv1 alert internal error`, weil es für diesen Namen weder Site-Block noch
  Zertifikat gab. Nach dem Merge war das weg.

## Schritt 3.3: Ergebnis am 2026-09-18

Lab-API, Datenbank und Worker laufen auf dem Hauptserver. Abgenommen mit:

| Prüfung                                | Ergebnis                                             |
|----------------------------------------|------------------------------------------------------|
| `docker compose ps`                    | `db` healthy, `api` und `worker` laufen, keine Host-Ports |
| Migration                              | `alembic upgrade head`, acht Tabellen (sieben plus `alembic_version`) |
| `https://api.tomkaufmann.dev/health`   | HTTP 200, `{"status":"ok","database":"ok"}`          |
| pytest im Container                    | 36 Tests grün, nichts übersprungen                   |
| PostgreSQL von außen                   | Port 5432 und 8000 vom Laptop aus nicht erreichbar   |
| Webseite                               | HTTP 200, unverändert                                |

Zwei Dinge sind dabei aufgefallen und behoben:

- **Der erste Testlauf hat den `IP_HMAC_KEY` ausgegeben.** Ein Test verglich
  gegen die Umgebung des ausführenden Rechners; im Container waren die
  Variablen gesetzt, der Vergleich schlug fehl, und pytest schreibt bei einem
  fehlgeschlagenen Vergleich beide Seiten in die Ausgabe. Der Schlüssel wurde
  am 2026-09-18 ersetzt, bevor das erste Event in der Datenbank war — zu
  diesem Zeitpunkt kostet ein Wechsel nichts (E-022). Der Test vergleicht jetzt
  nur noch einen Wahrheitswert, und `--tb=short` verhindert, dass lange
  Tracebacks den Verbindungsstring mit Passwort zeigen.
- **Die Datenbanktests verbanden sich mit einem Dummy-Passwort.** Eine Fixture
  hatte Testwerte direkt in `os.environ` gesetzt und nicht aufgeräumt. Jetzt
  übernimmt das `monkeypatch`.

Beides waren Fehler in den Tests, nicht im laufenden System.

## Freigabe

- [x] Plan freigegeben am 2026-09-17: Variante A (`lab_edge`), Übertragung per rsync
