# Entscheidungen

Hier stehen die Entscheidungen des Projekts, jeweils mit Begründung.

Regeln für dieses Dokument:

- Einträge werden fortlaufend nummeriert (E-001, E-002, …) und nur angehängt.
- Eine Entscheidung wird nicht umgeschrieben. Ändert sie sich, kommt ein neuer
  Eintrag dazu. Der alte bekommt den Status „ersetzt durch E-0xx“.
- Jeder Eintrag enthält Status, Datum, Quelle, Entscheidung, Begründung und
  Konsequenzen.

E-001 bis E-010 übernehmen die verbindlichen Vorgaben aus README.md. README.md
nennt die Entscheidungen, aber meist nicht ihre Gründe. Die Begründungen wurden
bei der Übernahme ausformuliert.

## Übersicht

| Nr.   | Entscheidung                                               | Status                                         |
|-------|------------------------------------------------------------|------------------------------------------------|
| E-001 | Sensor als eigener Hetzner-Server in eigenem Projekt       | angenommen, Ubuntu-Version ersetzt durch E-012 |
| E-002 | Zwei Cowrie-Varianten auf demselben Sensor                 | angenommen                                     |
| E-003 | Cowrie-Container mit `network_mode: host`                  | angenommen                                     |
| E-004 | Zuteilung von Port 22 per nftables-jhash der Quell-IP      | angenommen                                     |
| E-005 | Vector liefert cowrie.json per HTTPS an /ingest            | angenommen                                     |
| E-006 | Komponenten auf dem bestehenden Hauptserver                | angenommen                                     |
| E-007 | Verbindungen nur vom Sensor zum Hauptserver                | angenommen                                     |
| E-008 | LLM-Zugriff nur über das Gateway auf dem Hauptserver       | angenommen                                     |
| E-009 | Quell-IPs anreichern, per HMAC hashen, Klartext verwerfen  | angenommen                                     |
| E-010 | Technologie-Stack                                          | angenommen                                     |
| E-011 | Grundeinrichtung des Sensors per cloud-init                | angenommen                                     |
| E-012 | Ubuntu 26.04 statt 24.04 auf dem Sensor                    | angenommen                                     |
| E-013 | Sensor-Infrastruktur mit OpenTofu                          | vorgeschlagen                                  |
| E-014 | Persona bld-ci-03 für beide Varianten                      | angenommen                                     |
| E-015 | Kein Banner vor dem Login, vollständiger Persona-Prompt    | angenommen                                     |
| E-016 | Echte Downloads in cowrie-b über Cowries Download-Code     | ersetzt durch E-041                            |
| E-017 | Cowrie-Konfiguration und Betrieb von cowrie-a              | angenommen                                     |
| E-018 | Eigenes Dateisystem und erzeugte Persona-Dateien           | angenommen                                     |
| E-019 | Port 22 per eigener nftables-Tabelle auf cowrie-a umleiten | angenommen                                     |
| E-020 | Lab-Dienste auf dem Hauptserver neben der Webseite         | angenommen                                     |
| E-021 | Caddy-Block für die Lab-API auf `api.tomkaufmann.dev`      | angenommen                                     |
| E-022 | Fester HMAC-Schlüssel statt monatlicher Rotation            | angenommen                                     |
| E-023 | Grundgerüst von API, Schema und Worker                      | angenommen                                     |
| E-024 | Ingest: Prüfung, Idempotenz und Umgang mit Adressen         | angenommen                                     |
| E-025 | Vector auf dem Sensor: Quelle, Stapel und Puffer            | angenommen, Token-Weg ersetzt durch E-026      |
| E-026 | Ingest-Token über Vectors Secrets-Backend                   | angenommen                                     |
| E-027 | Stapelform, rotierte Dateien, NUL-Bytes, Savepoints         | angenommen                                     |
| E-028 | Worker: IPinfo-Download, Tagesstatistik, Aufräumen          | angenommen                                     |
| E-029 | Live-Stream und Statistik-Endpunkte                         | angenommen                                     |
| E-030 | Seite /lab: eigenes Projekt in Website-Demo, eigene Globus-Instanz | angenommen                              |
| E-031 | Startseite als Projektseite mit Live-Karte des Labs         | angenommen                                     |
| E-032 | Regeln für Coding-Agenten in AGENTS.md                      | angenommen, Sperrlisten ergänzt durch E-033 und E-035 |
| E-033 | Rohdaten und weitere .env-Dateien für Agenten sperren       | angenommen, Sperrlisten ergänzt durch E-034 und E-035 |
| E-034 | OpenTofu-State und -Variablen für Agenten sperren           | angenommen, `*.tfplan` ersetzt durch E-035     |
| E-035 | Sperrlisten an .gitignore angleichen, auch `*.tfplan`       | angenommen                                     |
| E-036 | CI mit Tests gegen PostgreSQL und gitleaks, ohne Deploy     | angenommen                                     |
| E-037 | ATT&CK-Regeln als Daten, Zuordnung beim Ingest              | angenommen, Regeln ergänzt durch E-038         |
| E-038 | ATT&CK-Regeln erweitert, T1083 enger als bei MITRE          | angenommen                                     |
| E-039 | Kampagnen über normalisierte Befehlsfolgen, Labels als Daten | angenommen                                     |
| E-040 | Vorab-Registrierung des Experiments in `docs/method.md`     | angenommen                                     |
| E-041 | Patch für cowrie-b ist Voraussetzung für den Start          | angenommen, Ereignisfelder ersetzt durch E-044 |
| E-042 | Mitschnitte von B erst nach dem Ende der Laufzeit öffentlich | angenommen                                     |
| E-043 | LLM-Gateway: Grenzen, Herkunftsprüfung und Kosten           | angenommen, Grenzen ergänzt durch E-044        |
| E-044 | Patch für cowrie-b: Ereignis, Abgleich, EOF, Image          | angenommen                                     |

---

## E-001: Sensor als eigener Hetzner-Server in eigenem Projekt

- Status: angenommen, Ubuntu-Version ersetzt durch E-012
- Datum: 2026-09-17
- Quelle: README.md, „Architektur (verbindlich)“

**Entscheidung:** Der Sensor läuft auf einem Hetzner Cloud CX23 mit Ubuntu
24.04 in einem eigenen Hetzner-Projekt, getrennt vom Hauptserver.

**Begründung:**

- Ein Honeypot soll angegriffen werden. Es ist damit zu rechnen, dass er
  irgendwann kompromittiert wird. Ein eigenes Projekt trennt API-Tokens,
  Firewalls, Netzwerke und Snapshots von der übrigen Infrastruktur.
- Missbrauchsmeldungen, Sperren oder das Löschen des Servers betreffen nur
  das Sensor-Projekt.
- Zwei Cowrie-Container und Vector brauchen wenig Ressourcen. Eine kleine,
  günstige Instanz reicht.
- Ubuntu 24.04 ist eine LTS-Version mit langem Support-Zeitraum.

**Konsequenzen:**

- Der Sensor sollte sich jederzeit reproduzierbar neu aufsetzen lassen
  (Konfiguration in `infra/` und `sensor/`).
- Die echte SSH-Administration kann nicht auf Port 22 laufen, weil Port 22 an
  die Honeypots geht (E-004).

---

## E-002: Zwei Cowrie-Varianten auf demselben Sensor

- Status: angenommen
- Datum: 2026-09-17
- Quelle: README.md, „Ziel“ und „Architektur (verbindlich)“

**Entscheidung:** Auf dem Sensor laufen zwei Cowrie-Instanzen:

| Instanz  | Shell-Backend    | Port     | sensor_name |
|----------|------------------|----------|-------------|
| cowrie-a | klassische Shell | tcp:2222 | hp-a        |
| cowrie-b | `llm`            | tcp:2322 | hp-b        |

**Begründung:**

- Die Forschungsfrage vergleicht das Verhalten nach dem Login zwischen beiden
  Shells. Laufen beide gleichzeitig auf demselben Host hinter derselben
  öffentlichen IP, sind Zeitraum, Netz, Provider und Sichtbarkeit in Scannern
  gleich. Der einzige gewollte Unterschied ist das Shell-Backend.
- cowrie-a ist die Kontrollgruppe, cowrie-b die Variante mit Sprachmodell.
- `sensor_name` kennzeichnet jedes Event mit seiner Variante. Die Zuordnung
  muss nicht aus Ports oder Containernamen rekonstruiert werden.

**Konsequenzen:**

- Alles vor dem Login sollte bei beiden Instanzen gleich aussehen:
  SSH-Banner, Host-Keys, Hostname, akzeptierte Zugangsdaten. Sonst können
  Angreifer mit mehreren Quell-IPs die Varianten unterscheiden, und
  Verhaltensunterschiede lassen sich nicht mehr allein der Shell zuschreiben.
- Beide Konfigurationen sollten aus einer gemeinsamen Basis entstehen und sich
  nur in Backend, Port und `sensor_name` unterscheiden.

---

## E-003: Cowrie-Container mit `network_mode: host`

- Status: angenommen
- Datum: 2026-09-17
- Quelle: README.md, „Architektur (verbindlich)“

**Entscheidung:** cowrie-a und cowrie-b laufen in Docker mit
`network_mode: host` und lauschen direkt auf den Host-Ports 2222 und 2322.

**Begründung:**

- Ohne Dockers Port-Publishing gibt es keine zusätzliche NAT-Schicht und
  keinen userland-proxy zwischen Angreifer und Cowrie. Cowrie sieht die echte
  Quell-IP. Die Zuteilung (E-004) und die Anreicherung (E-009) brauchen sie.
- Für veröffentlichte Ports erzeugt Docker eigene Firewall-Regeln. Mit
  host-Netzwerk liegt die gesamte Weiterleitung in der eigenen
  nftables-Konfiguration und ist dort nachvollziehbar.

**Konsequenzen:**

- Die Container teilen den Netzwerk-Stack des Hosts. Ihre Ports müssen sich
  unterscheiden und dürfen nicht mit anderen Diensten kollidieren.
- Die Netzwerkisolation durch Docker entfällt. Umso wichtiger sind die
  übrigen Schutzmaßnahmen: Container ohne Root-Rechte, `forward_redirect` und
  `forward_tunnel` aus, Telnet aus (README.md, „Harte Regeln“).

---

## E-004: Zuteilung von Port 22 per nftables-jhash der Quell-IP

- Status: angenommen
- Datum: 2026-09-17
- Quelle: README.md, „Architektur (verbindlich)“

**Entscheidung:** nftables leitet eingehende Verbindungen auf Port 22 abhängig
von einem jhash der Quell-IP entweder auf Port 2222 (cowrie-a) oder auf Port
2322 (cowrie-b) um.

**Begründung:**

- Die Zuteilung ist deterministisch. Dieselbe Quell-IP landet immer bei
  derselben Variante. Wiederkehrende Angreifer sehen keine wechselnde Shell,
  und ihre Sessions verteilen sich nicht auf beide Gruppen.
- Die Verteilung ist ungefähr gleichmäßig und zufallsähnlich, ohne Zustand und
  ohne Liste bereits gesehener IPs.
- Die Umleitung geschieht im Kernel vor den Containern. Es gibt keinen
  zusätzlichen Proxy, der die Quell-IP verdecken oder selbst angreifbar sein
  könnte.

**Konsequenzen:**

- Zugeteilt wird pro Quell-IP, nicht pro Angreifer. Ein Botnetz mit vielen IPs
  verteilt sich auf beide Varianten. Die Auswertung muss das berücksichtigen.
- Die Ports 2222 und 2322 sollten von außen nicht direkt erreichbar sein, sonst
  lässt sich die Zuteilung umgehen.
- IPv6 braucht eine eigene Regel oder wird bewusst ausgeschlossen. Das ist
  noch offen.

---

## E-005: Vector liefert cowrie.json per HTTPS an /ingest

- Status: angenommen
- Datum: 2026-09-17
- Quelle: README.md, „Architektur (verbindlich)“

**Entscheidung:** Vector liest auf dem Sensor die `cowrie.json` beider
Instanzen und sendet die Events per HTTPS mit Bearer-Token an den Endpunkt
`/ingest` des Hauptservers.

**Begründung:**

- Cowrie schreibt bereits strukturiertes JSON, ein Event pro Zeile. Auf dem
  Sensor ist dafür kein eigener Code nötig, nur Konfiguration.
- Vector merkt sich die Leseposition und wiederholt fehlgeschlagene
  Sendungen. Kurze Ausfälle des Hauptservers kosten keine Events.
- HTTPS schützt die Events auf dem Transport. Ein Bearer-Token ist einfach zu
  prüfen und bei Verdacht schnell zu wechseln.
- Der Sensor baut nur ausgehende Verbindungen auf (E-007).

**Konsequenzen:**

- Wer das Token hat, kann beliebige Events einliefern, auch ein
  kompromittierter Sensor. `/ingest` behandelt deshalb jedes Event als
  feindliche Eingabe: Schema prüfen, Längen begrenzen.
- `INGEST_TOKEN` liegt auf Sensor und Hauptserver (`.env.example`).

---

## E-006: Komponenten auf dem bestehenden Hauptserver

- Status: angenommen
- Datum: 2026-09-17
- Quelle: README.md, „Ziel“ und „Architektur (verbindlich)“

**Entscheidung:** Auf dem bestehenden Hauptserver laufen ein Reverse Proxy,
eine FastAPI-Anwendung (Ingest, SSE-Stream, Statistik, Mitschnitte,
LLM-Gateway), PostgreSQL und ein Worker. Die Visualisierung ist unter
tomkaufmann.dev/lab erreichbar.

**Begründung:**

- Der Server betreibt bereits tomkaufmann.dev. Es entsteht kein weiterer Host,
  der betrieben und abgesichert werden muss.
- Eine FastAPI-Anwendung für alle Endpunkte hält Deployment,
  Authentifizierung und Datenmodell an einer Stelle.
- Für die Live-Visualisierung fließen Daten nur vom Server zum Browser. Dafür
  reicht SSE. Es ist einfacher als WebSockets, läuft über normales HTTP durch
  den Reverse Proxy und verbindet sich im Browser automatisch neu.
- PostgreSQL passt zu zusammenhängenden Daten (Sessions, Befehle, Varianten)
  und zu Aggregationen für die Statistik.
- Der Worker übernimmt Arbeit, die nicht im Request-Pfad laufen muss, damit
  `/ingest` schnell antwortet.

**Konsequenzen:**

- Die bestehende Webseite und die Shop-/Globus-Demo bleiben unverändert
  (README.md, „Harte Regeln“). Das Lab bekommt eigene Routen und eine eigene
  Instanz der Globus-Komponente.
- Der Reverse Proxy muss für den SSE-Stream die Pufferung abschalten und lange
  offene Verbindungen erlauben.
- Feindliche Daten werden auf demselben Server verarbeitet, der auch die
  Webseite ausliefert. Eingabevalidierung und Trennung der Dienste
  (Container, eigener Datenbank-Benutzer) sind deshalb besonders wichtig.

---

## E-007: Verbindungen nur vom Sensor zum Hauptserver

- Status: angenommen
- Datum: 2026-09-17
- Quelle: README.md, „Architektur (verbindlich)“

**Entscheidung:** Daten fließen nur vom Sensor zum Hauptserver. Der
Hauptserver baut nie eine Verbindung zum Sensor auf. Antworten auf Anfragen
des Sensors (z.B. vom LLM-Gateway) sind davon nicht betroffen.

**Begründung:**

- Der Hauptserver hält die wertvolleren Daten und Secrets (Datenbank,
  `LLM_API_KEY`, `IP_HMAC_KEY`). Gegenüber dem Sensor tritt er nur als Server
  auf, der Anfragen prüft. Er verarbeitet nie als Client die Antworten eines
  möglicherweise kompromittierten Sensors und hält keine Zugangsdaten für ihn
  vor.
- Auf dem Sensor sind außer den Honeypot-Ports und der Admin-SSH keine
  eingehenden Dienste nötig.
- Alle benötigten Datenwege gehen ohnehin vom Sensor aus: Events (E-005) und
  LLM-Anfragen (E-008).

**Konsequenzen:**

- Der Hauptserver fragt keine Metriken, Logs oder Health-Checks beim Sensor
  ab. Einen Ausfall des Sensors erkennt er nur daran, dass keine Daten mehr
  ankommen, oder an einem Lebenszeichen, das der Sensor selbst sendet.
- Änderungen am Sensor laufen per Admin-SSH von außen, nicht vom Hauptserver
  aus. Die Befehle werden als Anleitung dokumentiert (README.md,
  „Arbeitsweise“).

---

## E-008: LLM-Zugriff nur über das Gateway auf dem Hauptserver

- Status: angenommen
- Datum: 2026-09-17
- Quelle: README.md, „Architektur (verbindlich)“

**Entscheidung:** cowrie-b spricht nicht direkt mit dem LLM-Anbieter, sondern
mit dem LLM-Gateway der FastAPI-Anwendung. Nur der Hauptserver kennt den
echten LLM-API-Key. Der Sensor kennt nur das Gateway-Token.

**Begründung:**

- Secrets auf dem Sensor gelten als verloren, sobald er kompromittiert ist. Ein
  gestohlener Anbieter-Key verursacht direkte Kosten und lässt sich beliebig
  missbrauchen. Ein Gateway-Token funktioniert nur gegen das eigene Gateway
  und lässt sich sperren, ohne beim Anbieter etwas zu ändern.
- Am Gateway lassen sich Kosten- und Rate-Limits, Längenbegrenzung der
  Angreifer-Eingaben, ein festes Modell und die Persona durchsetzen, ohne dem
  Sensor dafür vertrauen zu müssen.
- Ein Wechsel von Anbieter oder Modell betrifft nur den Hauptserver.

**Konsequenzen:**

- cowrie-b hängt von der Erreichbarkeit des Hauptservers ab. Ausfälle des
  Gateways sind für Angreifer sichtbar.
- cowrie-b antwortet langsamer als cowrie-a. Dieser Unterschied zwischen den
  Varianten gehört in die Methodik und in die Auswertung.
- Prompts und Antworten dürfen keine internen Informationen des Hauptservers
  enthalten, denn die Antworten gehen direkt an Angreifer.
- `LLM_API_KEY` steht nur in der `.env` des Hauptservers,
  `LLM_GATEWAY_TOKEN` in beiden.

---

## E-009: Quell-IPs anreichern, per HMAC hashen, Klartext verwerfen

- Status: angenommen
- Datum: 2026-09-17
- Quelle: README.md, „Harte Regeln“

**Entscheidung:** Quell-IPs werden nie im Klartext gespeichert oder
ausgegeben. Jede IP wird zuerst mit IPinfo Lite angereichert und dann mit
HMAC-SHA256 gehasht. Danach wird der Klartext verworfen.

**Begründung:**

- IP-Adressen können personenbezogene Daten sein, auch bei Angriffen. Oft
  stammen sie von gekaperten Geräten Unbeteiligter. Ohne Klartext ist eine
  Veröffentlichung oder ein Datenleck weit weniger heikel.
- Aus einem Hash lässt sich nichts mehr ableiten. Deshalb muss die
  Anreicherung vorher passieren.
- HMAC mit geheimem Schlüssel statt eines einfachen Hashes: Der
  IPv4-Adressraum ist so klein, dass sich einfache SHA-256-Hashes vollständig
  durchprobieren lassen. Ohne den Schlüssel geht das nicht.
- Der Hash bleibt für dieselbe IP gleich. Wiederkehrende Angreifer und die
  Zuteilung zu Varianten bleiben auswertbar.

**Konsequenzen:**

- `IP_HMAC_KEY` und `IPINFO_TOKEN` liegen auf dem Hauptserver. Ein Wechsel des
  Schlüssels macht alte und neue Hashes unvergleichbar.
- `.mmdb`-Dateien werden nicht committet, sondern per Token geladen.
- Offen: Cowrie schreibt die Klartext-IP selbst in `cowrie.json` auf dem
  Sensor, und Vector überträgt sie an `/ingest`. Wie lange diese Rohdaten auf
  dem Sensor liegen dürfen und an welcher Stelle genau gehasht wird, ist noch
  festzulegen.

---

## E-010: Technologie-Stack

- Status: angenommen
- Datum: 2026-09-17
- Quelle: README.md, „Stack“ und „Harte Regeln“

**Entscheidung:** Python 3.12, FastAPI, SQLAlchemy 2, Alembic, pytest,
PostgreSQL, Vector, Docker Compose, nftables. Das Frontend nutzt den
bestehenden Stack von tomkaufmann.dev und eine eigene Instanz der
Globus-Komponente.

**Begründung:**

- Eine fest vorgegebene Python-Version sorgt dafür, dass lokal, in Tests und
  im Container dieselbe Version läuft. Cowrie ist selbst in Python
  geschrieben.
- FastAPI ist asynchron, das hilft bei vielen gleichzeitig offenen
  SSE-Verbindungen. Eingaben werden über Pydantic-Modelle geprüft, was zur
  Regel „Angreifer-Eingaben sind feindlich“ passt.
- SQLAlchemy 2 und Alembic liefern typisierte Modelle und versionierte,
  wiederholbare Schema-Migrationen.
- pytest ist der Standard im Python-Umfeld. Tests laufen mit
  `cd server && pytest`.
- Docker Compose reicht für jeweils einen Host (Sensor, Hauptserver) ohne den
  Aufwand einer Orchestrierung.
- Der bestehende Frontend-Stack erspart einen zweiten Build-Prozess. Eine
  eigene Globus-Instanz lässt die bestehende Demo unberührt.

**Konsequenzen:**

- Image-Tags werden gepinnt, kein `:latest`. So ändern sich Sensor und Server
  während der Datenerhebung nicht unbemerkt.

---

## E-011: Grundeinrichtung des Sensors per cloud-init

- Status: angenommen
- Datum: 2026-09-17
- Quelle: Vorgabe beim Anlegen von `infra/cloud-init.yaml`

**Entscheidung:** Der Sensor wird beim ersten Start über
`infra/cloud-init.yaml` eingerichtet:

- Admin-User `tom` mit sudo und dem Public Key `hp_sensor.pub`
- Admin-SSH auf Port 22022, nur per Key und nur für `tom`
- Root- und Passwort-Login aus
- unattended-upgrades aktiv
- Docker Engine und Compose-Plugin aus dem offiziellen Docker-Repository
- nftables installiert
- Zeitzone UTC

**Begründung:**

- Die Einrichtung ist versioniert und läuft bei jedem Neuaufsetzen gleich ab
  (E-001).
- Port 22 gehört den Honeypots (E-004), deshalb läuft Admin-SSH auf 22022. Der
  Server ist ab der ersten Minute Angriffen ausgesetzt. Deshalb gibt es nur
  Key-Login und kein Passwort, das sich erraten ließe.
- `tom` hat kein Passwort. sudo läuft deshalb ohne Passwortabfrage.
- Das offizielle Docker-Repository ist der Installationsweg, den Docker selbst
  dokumentiert. Engine und Compose-Plugin kommen dort aus derselben Quelle.
- Mit UTC lassen sich die Zeitstempel von Sensor, Cowrie und Hauptserver ohne
  Umrechnung vergleichen.
- unattended-upgrades spielt Sicherheitsupdates des Betriebssystems ohne
  manuellen Eingriff ein.

**Konsequenzen:**

- Ubuntu 26.04 (E-012) startet sshd standardmäßig über `ssh.socket`. Den Port
  übernimmt dort ein systemd-Generator aus der sshd-Konfiguration, wirksam erst
  nach `systemctl daemon-reload` und `systemctl restart ssh.socket`. Auf dem
  ersten, von Hand eingerichteten Sensor lief sshd dagegen als `ssh.service`.
  Das Skript prüft deshalb beim ersten Start, welcher Weg aktiv ist. Es meldet
  einen Fehler, wenn 22022 nicht lauscht oder 22 belegt bleibt.
- Wer den Key `hp_sensor` verliert, kommt nicht mehr per SSH auf den Server.
  Dann bleibt nur das Hetzner-Rescue-System.
- nftables ist installiert, hat aber noch kein Regelwerk. Die mitgelieferte
  `/etc/nftables.conf` beginnt mit `flush ruleset` und würde beim Laden auch
  Dockers Regeln löschen. Das eigene Regelwerk (E-004) muss das
  berücksichtigen.
- unattended-upgrades installiert standardmäßig nur Sicherheitsupdates aus den
  Ubuntu-Quellen. Es aktualisiert Docker nicht und startet den Server nicht
  neu. Docker-Updates und Neustarts nach Kernel-Updates bleiben manuell.

---

## E-012: Ubuntu 26.04 statt 24.04 auf dem Sensor

- Status: angenommen
- Datum: 2026-09-17
- Quelle: Entscheidung nach der Prüfung des ersten, von Hand angelegten Sensors

**Entscheidung:** Der Sensor läuft auf Ubuntu 26.04 LTS (resolute), Hetzner-Image
`ubuntu-26.04`. Das ersetzt die Ubuntu-Version aus E-001. Alle anderen Teile
von E-001 gelten weiter.

**Begründung:**

- Der erste Sensor lief bereits mit 26.04. Docker Engine aus dem offiziellen
  Repository, Compose-Plugin, nftables und unattended-upgrades funktionierten
  dort.
- 26.04 ist ebenfalls eine LTS-Version und wird zwei Jahre länger unterstützt
  als 24.04.
- Cowrie und Vector laufen in Containern. Die Version des Host-Systems betrifft
  sie kaum.

**Konsequenzen:**

- README.md und `infra/cloud-init.yaml` nennen 26.04.
  Anleitungen, die 24.04 nennen, sind veraltet.
- 26.04 ist jünger als 24.04, und Anleitungen für 24.04 passen nicht immer.
  Zum Beispiel startete sshd auf dem ersten Sensor als `ssh.service` und nicht
  über `ssh.socket` (E-011).

---

## E-013: Sensor-Infrastruktur mit OpenTofu

- Status: vorgeschlagen, noch nicht entschieden
- Datum: 2026-09-17
- Quelle: Vorgabe beim Anlegen von `infra/*.tf`

**Entscheidung:** OpenTofu baut Server, Firewall und SSH-Key des Sensors mit dem
hcloud-Provider aus `infra/`. `tofu apply` baut `hp-sensor-01`, `tofu destroy`
entfernt ihn wieder. `cloud-init.yaml` wird als User Data übergeben. Das
Hetzner-API-Token kommt nur aus der Umgebungsvariable `HCLOUD_TOKEN`.

**Begründung:**

- Der erste Sensor wurde von Hand angelegt. Seine User Data war leer, seine
  SSH-Konfiguration wich vom Repo ab, und in der Firewall fehlte zuerst die
  Regel für 22022. Mit OpenTofu ist der ganze Aufbau im Repo beschrieben und
  wiederholbar (E-001).
- Die Firewall gehört zum Code. Sie hängt schon beim Anlegen am Server, es gibt
  also kein Zeitfenster mit offenen Ports.
- OpenTofu ist Open Source, der hcloud-Provider wird von Hetzner selbst
  gepflegt.
- Für das Token gibt es weder Variable noch Argument. So kann es nicht in
  `*.tfvars`, im Repo oder im State landen.
- Der Admin-Key wird auch als Hetzner-SSH-Key angelegt. Hetzner erzeugt dann
  kein Root-Passwort, und das Rescue-System ist mit demselben Key erreichbar.
  Der Key wird aus `cloud-init.yaml` gelesen und steht nur an dieser Stelle.

**Konsequenzen:**

- Eingehend erlaubt die Firewall nur ICMP, TCP 22 und TCP 22022. TCP 22022 ist
  über `admin_source_ips` einschränkbar. 2222 und 2322 bleiben zu (E-004).
  Ausgehender Verkehr ist nicht beschränkt. Ob das so bleibt, ist noch offen.
- Jede Änderung an `cloud-init.yaml` baut den Server neu, und er bekommt eine
  neue IP. Ob der Sensor für die Datenerhebung eine feste IP braucht
  (Primary IP als eigene Ressource), ist offen.
- Der State liegt nur lokal in `infra/` und wird nicht committet. Geht er
  verloren, müssen die Ressourcen in der Console von Hand gelöscht werden.
- Provider-Version (`~> 1.69`) und Prüfsummen sind über `.terraform.lock.hcl`
  festgelegt, analog zur Regel „Image-Tags pinnen“.
- Standort ist `nbg1`. Hetzner-Backups und Löschschutz sind aus, weil der
  Sensor keine Daten hält, die nicht auch beim Hauptserver ankommen.

---

## E-014: Persona bld-ci-03 für beide Varianten

- Status: angenommen
- Datum: 2026-09-17
- Quelle: Vorgabe beim Anlegen von `sensor/persona/`

**Entscheidung:** Beide Varianten spielen denselben fiktiven CI-Build-Worker
`bld-ci-03` mit Debian GNU/Linux 13.7. Die Maschine ist in
`sensor/persona/persona.md` beschrieben. Die Dateiinhalte liegen in
`sensor/persona/honeyfs/`, und `sensor/persona/prompt.md` enthält alle diese
Dateien wörtlich als System-Prompt für cowrie-b.

**Begründung:**

- Die Forschungsfrage verlangt, dass sich die Varianten nur in der Shell
  unterscheiden (E-002). Deshalb beschreiben eine Persona, ein Satz Dateien und
  ein Prompt dieselben Fakten.
- Die Standard-Persona von Cowrie (`svr04`, User `phil`) ist bekannt und in
  sich widersprüchlich: Debian 12.5 an der Oberfläche, darunter Ausgaben von
  2009 bis 2016.
- Ein Build-Server ist ein plausibles, lohnendes Ziel und kommt ohne
  Kundendaten, Web-Frontend oder Produktnamen aus.
- Debian statt eines Firmen-Betriebssystems und erfundene Namen für
  Organisation, Accounts, Domain und Agent erfüllen die Namensregel.
  Technische Kennungen jeder Debian-VM bleiben als Ausnahme drin (Auslegung in
  `persona.md`).
- Hardware und Speicher entsprechen dem echten Sensor, weil Cowries `free` die
  echten Werte des Hosts zeigt.

**Konsequenzen:**

- Eine Änderung an einer honeyfs-Datei muss im selben Commit auch in
  `prompt.md` landen. Nach dem Start der Datenerhebung gilt jede Änderung für
  beide Varianten gleichzeitig und wird mit Datum festgehalten.
- Beide Container brauchen `contents_path`. `etc/issue.net` ist das Banner vor
  dem Login und muss in beiden Varianten gleich sein.
- In cowrie-a sind die Dateien unter `/opt`, `/srv` und `/home` erst sichtbar,
  wenn es ein eigenes `fs.pickle` mit diesen Pfaden gibt.
- Einige Unterschiede zwischen den Varianten legt Cowrie selbst fest, zum
  Beispiel die Ausgabe nach dem Login, das Start-Verzeichnis, `w` und `wget`.
  Sie sind in `persona.md` aufgelistet und gehören in die Methodik.
- Die Namensregel gilt als erfüllt, solange die Abnahme von Schritt 2.1
  erfüllt ist: `persona.md` beschreibt die Maschine vollständig, und honeyfs
  und `prompt.md` passen zueinander.
- Der Prompt hat rund 5.000 Tokens und geht bei jedem Befehl mit. Kosten und
  Caching betreffen das LLM-Gateway (E-008).

---

## E-015: Kein Banner vor dem Login, vollständiger Persona-Prompt

- Status: angenommen
- Datum: 2026-09-17
- Quelle: Entscheidung nach Schritt 2.1, vom User an Claude übertragen

**Entscheidung:**

- `etc/issue.net` bleibt leer, damit Cowrie vor dem Login kein Banner zeigt.
- Nach dem Login zeigen beide Varianten die motd aus `etc/motd`, cowrie-b über
  den Patch aus E-016. Kommt der Patch nicht, wird `etc/motd` auf genau
  `Welcome to bld-ci-03` gesetzt. Das gibt cowrie-b fest aus.
- `prompt.md` enthält weiterhin alle honeyfs-Dateien wörtlich (rund 4.900
  Tokens pro Befehl).

**Begründung:**

- Ein echtes Debian zeigt standardmäßig kein Banner vor dem Login. Ein
  Warnhinweis könnte gerade Menschen abschrecken, deren interaktive Sitzungen
  für die Forschungsfrage am meisten zählen.
- Was nach dem Login erscheint, sieht jede interaktive Sitzung sofort. Ein
  Unterschied an dieser Stelle wäre ein offensichtliches Merkmal der Variante
  (E-002).
- Nur mit wörtlichem Inhalt liefert cowrie-b bei `cat` denselben Text wie
  cowrie-a. Weglassen ist keine Option, weil cowrie-a dann wieder Cowries alte
  Standardinhalte zeigt.
- Der Prompt ist bis auf die angehängten Angaben gleichbleibend. Viele Anbieter
  speichern so einen Anfang zwischen und berechnen ihn günstiger.

**Konsequenzen:**

- Das Gateway (Schritt 7.2) sollte das Zwischenspeichern beim Anbieter nutzen
  und zwischengespeicherte Tokens in `llm_usage` mitloggen.
- Mehr Prompt kann die Antwortzeit von cowrie-b erhöhen. Die Latenz wird
  gemessen und in der Methodik berücksichtigt (H3).

---

## E-016: Echte Downloads in cowrie-b über Cowries eigenen Download-Code

- Status: ersetzt durch E-041
- Datum: 2026-09-17
- Quelle: Wunsch des Users nach Schritt 2.1

**Entscheidung:** Ein kleiner Patch am LLM-Backend von Cowrie erkennt `wget` und
`curl` in den Befehlen von cowrie-b. Er lädt die Datei im Hintergrund wirklich
herunter und schreibt dieselben Events wie cowrie-a
(`cowrie.session.file_download`, `.failed`). Die Terminalausgabe liefert
weiterhin das Sprachmodell. Derselbe Patch gibt nach dem Login `etc/motd` aus
statt des fest eingebauten `Welcome to bld-ci-03`.

**Begründung:**

- Ohne Patch sammelt cowrie-b keine Malware-Proben. Das Artifact führt das in
  Schritt 7.1 bisher als bekannte Grenze.
- Cowrie 3.0.14 bündelt die Download-Logik in `cowrie/core/download.py`:
  `fetch` mit Sperre für private und nicht routbare Adressen und
  Weiterleitungsprüfung, `capture_download` und `report_download_failure`.
  `capture_download` kommt ohne Fake-Dateisystem aus, wenn es keine Zieldatei
  gibt. Der Patch kann also dieselben Grenzen und Events wie cowrie-a nutzen,
  statt eigene zu bauen.
- Die Alternativen sind schlechter. Ein Zusatzdienst, der die Logs von
  cowrie-b ausliest, bräuchte eigenen Download-Code auf dem Sensor. Downloads
  über das Gateway würden den Hauptserver mit Angreifer-Servern verbinden
  (E-007).
- In Cowrie gibt es dazu bisher weder Issue noch Pull Request. Der Patch eignet
  sich als Beitrag ans Cowrie-Projekt.

**Konsequenzen:**

- cowrie-b läuft mit einem eigenen Image, das auf dem fest gepinnten
  Cowrie-Image aufbaut und den Patch enthält. Beide Varianten nutzen dieselbe
  Basisversion.
- Zunächst nur `wget` und `curl`. Uploads per `scp -t` sowie `tftp` und
  `ftpget` bleiben in cowrie-b simuliert und stehen als Grenze in der Methodik.
- Download-Limit, Rate-Limits und eine spätere Ausgangssperre (Schritt 9.2)
  gelten für beide Varianten gleich.
- Die Umsetzung muss vor Schritt 7.1 stehen. Die Liste der Grenzen in
  `docs/method.md` hängt davon ab.

---

## E-017: Cowrie-Konfiguration und Betrieb von cowrie-a

- Status: angenommen
- Datum: 2026-09-17
- Quelle: Schritt 2.2, Entscheidungen des Users zu SFTP, Logins und Übertragung

**Entscheidung:**

- `sensor/cowrie/cowrie.cfg` ist die gemeinsame Konfiguration für A und B. Was
  nur eine Variante betrifft (`sensor_name`, Port, Backend), steht als
  Umgebungsvariable in `sensor/docker-compose.yml`.
- Beide Varianten nutzen dieselben SSH-Host-Keys aus `/srv/honeypot/hostkeys`.
- `userdb.txt` nimmt nur `root` und `admin` an, mit jedem Passwort außer dem
  eigenen Benutzernamen und `123456`.
- SFTP und SSH-Weiterleitung (direct-tcpip) bleiben in cowrie-a an, wie im
  Cowrie-Standard. Weiterleitungen werden nur protokolliert, nie ausgeführt.
- cowrie-a nutzt das Image `cowrie/cowrie:3.0.14` mit Digest und läuft mit
  `network_mode: host` nur auf `tcp:2222`. Die Laufzeitdaten liegen unter
  `/srv/honeypot/a/var`.
- Härtung: `no-new-privileges`, `cap_drop: ALL`, schreibgeschütztes
  Dateisystem, 512 MB RAM, Prozesslimit, Rotation der Docker-Logs.
- `sensor/` kommt per rsync vom Laptop auf den Sensor, nach
  `/opt/honeypot-lab/sensor`, Eigentümer root.

**Begründung:**

- Eine gemeinsame Datei verhindert, dass A und B bei Persona, Limits oder
  Sicherheitseinstellungen auseinanderlaufen (E-002).
- Eigene Host-Keys je Instanz würden die Varianten schon vor dem Login
  unterscheidbar machen.
- Die Persona kennt nur diese Konten mit Login-Shell. Andere Benutzernamen
  müssten beide Varianten improvisieren. `root` und `admin` probieren Bots am
  häufigsten.
- SFTP und Weiterleitungsversuche liefern in A zusätzliche Daten. Die
  Entscheidung dafür hat der User bewusst getroffen, obwohl B beides nicht kann.
- In Cowrie 3.0.14 stecken `cowrie.cfg.dist` und `userdb.example` im
  Python-Paket. Anders als im Artifact beschrieben, muss man sie nicht mehr in
  das eingebundene `etc` kopieren. Einen Crash-Reporter gibt es nicht.
- rsync braucht keine Zugangsdaten zum Repo auf einem Server, der als
  kompromittierbar gilt.

**Konsequenzen:**

- SFTP-Uploads und direct-tcpip-Kanäle sind ein bekannter Unterschied zwischen
  den Varianten. Er steht in `persona.md` und gehört in die Methodik.
  Auswertungen, die nur Shell-Sitzungen vergleichen, klammern ihn aus.
- `sensor/tests/test_cowrie_config.py` prüft Konfiguration, Logins und
  Einbindungen gegen die Persona.
- Das schreibgeschützte Dateisystem funktioniert mit Cowrie 3.0.14. Das hat der
  Start auf dem Sensor am 2026-09-17 bestätigt.
- Cowrie liest `userdb.txt` als ASCII. Umlaute in Kommentaren brechen jeden
  Login, ein Test prüft das jetzt.
- Ubuntu 26.04 nutzt die uutils-coreutils. Deren `install -o/-g` nimmt keine
  numerischen IDs ohne passenden Host-User an. Die Skripte setzen Eigentümer
  deshalb mit `chown`. Auf dem Host gehört GID 999 zu `systemd-journal`, die
  Datenverzeichnisse sind deshalb `0700`.

---

## E-018: Eigenes Dateisystem und erzeugte Persona-Dateien

- Status: angenommen
- Datum: 2026-09-17
- Quelle: Schritt 2.2, Vorschlag aus Schritt 2.1, Entscheidung des Users zum Bauort

**Entscheidung:**

- `sensor/scripts/build-fs-pickle.sh` baut `fs.pickle` auf dem Sensor. Grundlage
  ist `sensor/persona/rootfs/Dockerfile`: gepinntes Debian-13-Image, Pakete vom
  Debian-Snapshot `20260917T000000Z`, Konten, Verzeichnisse, honeyfs-Dateien
  und Zeitstempel der Persona.
- Das Skript exportiert das Dateisystem und legt leere Platzhalter für `/proc`,
  `/sys` und `/dev` an. Dann führt es `createfs` aus dem gepinnten Cowrie-Image
  per `chroot` aus. `fs.pickle` bleibt auf dem Sensor und kommt nicht ins Repo.
- `sensor/persona/build.py` erzeugt aus den Quellen `prompt.template.md`,
  `honeyfs/`, `txtcmds/` und `ps.txt` die Dateien `prompt.md`,
  `cmdoutput.json` sowie die Ausgaben von `mount` und `lsmod`.
- Feste Ausgaben für `df`, `dmesg`, `lscpu`, `nproc` und `top` stehen wörtlich
  im Prompt. `mount` und `lsmod` beschreibt der Prompt als abgeleitet.

**Begründung:**

- Ohne eigenes Pickle sieht cowrie-a die Verzeichnisse der Persona nicht, und
  Cowries Standard wirkt veraltet und widersprüchlich (Befund in `persona.md`).
- Bei einem `chroot` ohne eingebundenes `/proc`, `/sys` und `/dev` gelangen
  keine Daten des Sensors ins Pickle. `createfs` läuft dabei mit `/` als Wurzel,
  sodass auch absolute Links erhalten bleiben.
- Der Snapshot hält den Paketstand fest, damit spätere Neubauten zur Persona
  passen.
- Auf dem Sensor ist Docker schon installiert, lokal musst du nichts einrichten.
  Das Pickle wird ohnehin nur dort geladen, deshalb entsteht kein zusätzliches
  Vertrauensproblem.
- Mit einem Generator und Tests kann `prompt.md` nicht unbemerkt von honeyfs und
  den festen Ausgaben abweichen.

**Konsequenzen:**

- Der Prompt wächst auf rund 7.400 Tokens. Die Begründung aus E-015 gilt
  unverändert.
- Pakete legen Systemkonten mit anderen IDs an als die Persona. `remap-ids.sh`
  gleicht sie an, damit `ls -l` in cowrie-a passende Namen zeigt.
- Größen im Pickle stammen von echten Dateien. Große Caches beschreibt die
  Persona deshalb nicht mit Zahlen, die `du` widerlegen würde.
- Bau und `chroot` laufen auf dem Sensor in rund zwei Minuten durch, sobald die
  Pakete im Build-Cache liegen. Das Pickle hat rund 33.800 Einträge (1,5 MB)
  und keine Spuren von Docker.
- Beim Bauen entstandene Zeitstempel setzt `build-fs-pickle.sh` auf die
  Installation im Februar zurück, `/proc`, `/sys` und `/dev` auf den letzten
  Boot. Sonst zeigt `ls -la /` einen frisch gebauten Server. Dateien und Ordner
  aus honeyfs bekommen im Dockerfile feste Zeitstempel und hängen nicht von
  lokalen Änderungszeiten ab.

---

## E-019: Port 22 per eigener nftables-Tabelle auf cowrie-a umleiten

- Status: angenommen
- Datum: 2026-09-17
- Quelle: Schritt 2.3 im Bauplan

**Entscheidung:** Die Tabelle `ip honeypot` in `sensor/nftables/honeypot.nft`
leitet eingehende TCP-Verbindungen auf Port 22 nach 2222 zu cowrie-a um. Sie
hängt mit Priorität -110 (`dstnat - 10`) im Hook `prerouting`. Auf dem Sensor
liegt sie unter `/etc/nftables.d/honeypot.nft`, und
`honeypot-nftables.service` lädt sie beim Booten (oneshot, nach
`network.target`). Die Umleitung gilt nur für IPv4.

**Begründung:**

- Die Tabelle ersetzt sich beim Laden selbst (`table`, `delete table`, neu
  anlegen). Ohne `flush ruleset` bleiben Dockers Tabellen `ip nat` und
  `ip filter` unberührt.
- `nftables.service` bleibt aus. Dessen `/etc/nftables.conf` beginnt mit
  `flush ruleset` (E-011). Eine eigene Unit lädt nur die eigene Datei, und
  `systemctl stop` entfernt nur die eigene Tabelle.
- REDIRECT ändert nur das Ziel. Cowrie sieht weiter die echte Quell-IP (E-003).
- Der Bauplan (Schritt 1.4) sieht den Honeypot nur für IPv4 vor. Damit ist der
  offene Punkt zu IPv6 aus E-004 vorerst beantwortet: Auf Port 22 über IPv6
  lauscht nichts.

**Konsequenzen:**

- Getestet am 2026-09-17:
  - Von außen landet `ssh root@SENSOR_IP` in Cowrie, mit Honeypot-Host-Key,
    Persona und `dst_port` 2222 im Log.
  - Port 22022 bleibt erreichbar, Port 2222 ist von außen zu.
  - Nach einem Neustart waren Regel, cowrie-a und Aufräum-Timer nach etwa 30
    Sekunden wieder aktiv.
- Schritt 7.4 ersetzt die Regel durch die Zuteilung per jhash auf cowrie-a und
  cowrie-b.
- `sensor/tests/test_nftables.py` prüft, dass kein `flush ruleset` vorkommt,
  dass die Umleitung auf den Port von cowrie-a zeigt und dass die Unit die Regel
  lädt.

---

## E-020: Lab-Dienste auf dem Hauptserver neben der Webseite

- Status: angenommen
- Datum: 2026-09-17
- Quelle: Schritt 3.1, `docs/server-inventory.md`, Entscheidung des Users für Variante A und rsync

**Entscheidung:**

- `db`, `api` und `worker` laufen als eigenes Compose-Projekt `honeypot-lab` in
  `/opt/honeypot-lab` auf dem Hauptserver. Keiner der Dienste veröffentlicht
  einen Port auf dem Host.
- Netze: `lab_internal` (ohne Internet) für die Datenbank, `lab_edge` nur für
  Caddy und API, `lab_egress` für den Worker.
- Der vorhandene Caddy aus Website-Demo tritt `lab_edge` bei und bekommt einen
  Block `api.{$DOMAIN}`. Die Änderung läuft per Pull Request in Website-Demo.
- Speichergrenzen: `db` 768 MiB, `api` 384 MiB, `worker` 384 MiB. Dazu
  niedrigere `cpu_shares` und ein höherer `oom_score_adj` als bei der
  Webseite.
- Übertragung vom Laptop per rsync.

**Begründung:**

- Docker umgeht ufw. Ohne veröffentlichte Ports entsteht kein Weg ins Lab an
  Caddy vorbei.
- Ein eigenes Netz statt `globe-demo_default` hält `gate` und das Lab getrennt.
  `docker compose down` des einen Projekts blockiert das andere nicht.
- `/opt/globe-demo` wird per Pipeline mit `git pull` aktualisiert. Direkte
  Änderungen auf dem Server würden den nächsten Deploy gefährden.
- 3,7 GiB RAM reichen für beides nur mit harten Grenzen, und die Webseite soll
  Vorrang haben.

**Konsequenzen:**

- Reihenfolge für Schritt 3.2: DNS für `api` bei INWX, dann
  `docker network create lab_edge` auf dem Server, dann Merge in Website-Demo.
  Beim Merge baut die Pipeline Caddy einmal neu, die Webseite ist wenige
  Sekunden weg.
- Reine Caddyfile-Änderungen übernimmt die bestehende Pipeline nicht, sie
  brauchen `docker compose restart caddy`.
- Die Seite `/lab` (Schritt 5.2) liefert `gate` aus. Sie entsteht deshalb im
  Repo Website-Demo.


---

## E-021: Caddy-Block für die Lab-API auf `api.tomkaufmann.dev`

- Status: angenommen
- Datum: 2026-09-17
- Quelle: Schritt 3.2, Pull Request `ClintonLel/Website-Demo#13`

**Entscheidung:**

- Der vorhandene Caddy aus Website-Demo bekommt die Netze `default` und
  `lab_edge` und einen Site-Block `api.{$DOMAIN}`. Die Änderung läuft über einen
  Pull Request, nicht direkt auf dem Server.
- Der Block enthält: HSTS und `-Server` wie der Hauptblock, automatisches TLS,
  `request_body { max_size 1MB }`, CORS ausschließlich für `https://{$DOMAIN}`
  (mit `defer` und einem eigenen `handle` für Preflight-Anfragen), `/stream` in
  einem eigenen `handle` mit `flush_interval -1` und ohne `encode`, alles andere
  mit `encode zstd gzip` an `lab-api:8000`.
- Reihenfolge: `docker network create lab_edge` auf dem Server, dann Merge.

**Begründung:**

- TLS holt Caddy selbst über die HTTP-Challenge auf Port 80. Die Zertifikate
  liegen im Volume `caddy_data` und überleben einen Neuaufbau des Containers.
- Server-Sent Events vertragen weder Puffer noch Kompression. `flush_interval
  -1` schiebt jedes Ereignis sofort raus, deshalb steht `/stream` in einem
  eigenen `handle` ohne `encode`. Statistik-Antworten werden weiter komprimiert.
- Das Größenlimit greift, bevor die API den Body liest. 1 MB reicht für die
  Batches des Sensors.
- CORS gehört in den Proxy, nicht in die Anwendung: eine Stelle, und die API
  muss die Domain der Webseite nicht kennen. `defer` setzt den Header erst beim
  Schreiben der Antwort, sonst könnten zwei Werte nebeneinander stehen.

**Konsequenzen:**

- Die FastAPI-App aus Schritt 3.3 setzt **keine** eigenen CORS-Header.
- Der API-Container muss im Netz `lab_edge` den Alias `lab-api` tragen und im
  Container auf Port 8000 lauschen.
- Vector muss seine Batches (Schritt 4.2) unter 1 MB halten.
- Weitere Endpunkte laufen über den allgemeinen `handle`-Block. Ein zweiter
  Pfad mit Streaming braucht einen eigenen `handle` mit `flush_interval -1`.
- Bis das Lab läuft, antwortet `api.tomkaufmann.dev` mit 502, hat aber schon ein
  gültiges Zertifikat.

---

## E-022: Fester HMAC-Schlüssel statt monatlicher Rotation

- Status: angenommen
- Datum: 2026-09-17
- Quelle: Schritt 3.3, Entscheidung des Users. Weicht bewusst vom Bauplan ab,
  der dort einen „monatlich rotierenden Schlüssel“ verlangt.

**Entscheidung:** `IP_HMAC_KEY` bleibt über die gesamte Laufzeit der Studie
konstant. Es gibt keine Rotation. E-009 gilt unverändert weiter.

**Begründung:**

- Ohne Klartext-IP lässt sich ein Hash nach einem Schlüsselwechsel nicht neu
  berechnen. Wiederkehrende Angreifer, die Zuordnung zu Kampagnen (Schritt 6.2)
  und der Vergleich der Varianten über die Laufzeit (Phase 7) brechen damit
  genau an der Stelle, an der die Auswertung ansetzt.
- Die geprüfte Alternative wäre eine stabile `actor_id` gewesen, die beim
  Ingest über den vorherigen Schlüssel weitergereicht wird. Sie verzerrt aber
  die Kennzahl „wiederkehrende Angreifer“ systematisch: Wer länger pausiert als
  eine Rotationsperiode, zählt als neuer Akteur.
- Der Schlüssel liegt auf demselben Host wie die Datenbank. Wer ihn erbeutet,
  hat in aller Regel auch die Daten. Die Rotation hätte also weniger geschützt,
  als sie an Auswertbarkeit gekostet hätte.

**Konsequenzen:**

- Kompensation statt Rotation: mindestens 32 zufällige Bytes, nur in
  `/opt/honeypot-lab/.env` (Rechte 600, Eigentümer root), nie in Logs, nie in
  Beispielen. Roh-Events werden nach 90 Tagen gelöscht (Schritt 4.3), danach
  existieren Hashes nur noch in `sessions` und `campaigns`.
- Ein Test stellt sicher, dass keine Tabelle eine Klartext-IP aufnehmen kann.
- Soll später doch rotiert werden, braucht das eine neue Entscheidung, eine
  Spalte `actor_id` und eine Migration. Ein stiller Wechsel des Schlüssels
  macht alte und neue Hashes unvergleichbar.
- `docs/method.md` beschreibt das Verfahren ohne Rotation.

---

## E-023: Grundgerüst von API, Schema und Worker

- Status: angenommen
- Datum: 2026-09-17
- Quelle: Schritt 3.3

**Entscheidung:**

- **Asynchron mit psycopg 3.** FastAPI, SQLAlchemy 2 und Alembic laufen über
  `postgresql+psycopg`. Derselbe Treiber bedient synchrone und asynchrone
  Verbindungen, es ist also nur einer im Image.
- **Die App ist eine Factory** (`app.main:create_app --factory`). Der Import
  des Moduls liest keine Einstellungen.
- **Kein Access-Log von Uvicorn** (`--no-access-log`). Es enthielte die Adresse
  jedes Clients. Stattdessen loggt eine eigene Middleware Methode, Pfad, Status
  und Dauer als JSON.
- **Kein CORS in der Anwendung.** Das macht Caddy (E-021).
- **Keine öffentliche Schema-Seite** im Betrieb: `/docs` und `/openapi.json`
  sind aus, solange `ENVIRONMENT=production`.
- **Start bricht ab**, wenn `POSTGRES_PASSWORD`, `IP_HMAC_KEY` oder
  `INGEST_TOKEN` fehlen, zu kurz sind oder noch `CHANGE_ME` enthalten.
- **`daily_stats` ist schmal:** `(tag, variante, metrik, dimension) -> wert`.
- **`events.dedup_hash` ist eindeutig**, das trägt die Idempotenz in 4.1.
- **Tests in zwei Stufen:** ohne Datenbank überall, mit Datenbank im Container
  gegen eine eigene Datenbank `honeypot_test`.

**Begründung:**

- Die Regeln aus README.md („keine Klartext-IPs ausgeben“) greifen nur, wenn
  auch das Logging sie einhält. Uvicorns Access-Log wäre die einfachste Lücke.
- Ein fehlender Schlüssel darf nicht dazu führen, dass die API mit einem
  Standardwert weiterläuft und stillschweigend falsche Hashes schreibt.
- Eine schmale Statistik-Tabelle spart Migrationen: Für jede neue Kennzahl in
  Phase 5 und 6 kommt eine Zeile dazu, keine Spalte.
- Die Datenbanktests fahren das Schema hoch und wieder herunter. Sie brauchen
  deshalb eine eigene Datenbank, sonst wären die erhobenen Daten weg.

**Konsequenzen:**

- `server/tests/test_schema.py` lehnt jede Spalte ab, deren Name nach einer
  Adresse aussieht, und jeden Postgres-Typ `inet` oder `cidr`. Neue Tabellen
  müssen daran vorbei.
- Das Laufzeit-Image enthält kein pytest. Tests laufen über das Build-Ziel
  `test` im Dockerfile.
- Die Testdatenbank `honeypot_test` muss auf dem Server existieren.
- Lokal läuft eine andere Python-Version als im Container. Maßgeblich ist der
  Lauf im Container (E-010).

---

## E-024: Ingest: Prüfung, Idempotenz und Umgang mit Adressen

- Status: angenommen
- Datum: 2026-09-18
- Quelle: Schritt 4.1, Auswertung der echten Beispiel-Logs in
  `server/tests/fixtures/fixtures.jsonl`

**Entscheidung:**

- **Idempotenz über einen Inhalts-Hash.** `events.dedup_hash` ist ein SHA-256
  über das Ereignis ohne die Felder, die erst auf dem Transportweg dazukommen
  (`host`, `file`, `offset`, …). Cowries `uuid` taugt dafür nicht: Sie
  kennzeichnet die Cowrie-Instanz, nicht das Ereignis, und ist in allen 175
  Beispielzeilen dieselbe.
- **Eine kaputte Zeile wirft nicht den Stapel weg.** Ungültige Ereignisse
  werden gezählt und mit Grund zurückgemeldet, der Rest wird gespeichert.
- **Adressen der Beteiligten werden ersetzt, nicht entschärft.** Cowrie
  schreibt die Quell-IP auch in Freitexte („New connection: 192.0.2.4:59386“).
  Dort steht künftig `<src>` beziehungsweise `<dst>`. Entschärfen allein
  genügte nicht: `1[.]2[.]3[.]4` ist weiterhin die Adresse.
- **Fremde Adressen und URLs in Befehlen bleiben**, aber entschärft
  (`hxxp://`, `[.]`). Sie sind Gegenstand der Untersuchung.
- **Interaktiv gegen Exec** entscheidet `cowrie.client.size`: Wer eine
  Terminalgröße meldet, hat ein Pseudoterminal angefordert. Sitzungen mit
  Befehlen ohne Terminalgröße sind Exec-Aufrufe, Sitzungen ohne Befehle
  bleiben unentschieden (`NULL`).
- **Ohne IPinfo-Datenbank läuft der Ingest weiter**, die Sitzung bekommt dann
  kein Land.
- **Grenzen:** höchstens 500 Ereignisse je Anfrage (Caddy begrenzt zusätzlich
  den Body auf 1 MB), Freitexte werden gekürzt statt abgelehnt.

**Begründung:**

- Die Beispiel-Logs zeigen, womit zu rechnen ist: ein „Client“, der sich mit
  `CONNECT …:80 HTTP/1.0` als Version meldet, Sitzungen ohne Login, Sitzungen
  ohne jede Version. Strenge Prüfung mit Zählung statt Abbruch hält die
  Pipeline trotzdem am Laufen.
- `cowrie.session.params` kam in den Beispielen bei interaktiven Sitzungen und
  bei Exec-Aufrufen vor und taugt deshalb nicht zur Unterscheidung.
  `cowrie.client.size` trennt die beiden Gruppen sauber.
- Ein zu langer Befehl ist ein Befund. Ihn wegzuwerfen hieße, gerade das
  Auffällige zu verlieren.

**Konsequenzen:**

- Vector muss seine Batches unter 500 Ereignissen und 1 MB halten (Schritt 4.2).
- `docs/method.md` beschreibt die Klassifikation so, wie sie hier steht. Ändert
  sie sich nach dem Start von Variante B nicht mehr (README).
- Die Sitzungen unserer eigenen Tests sind an `127.0.0.1` erkennbar und werden
  in Schritt 7.1 ausgeschlossen.

---

## E-025: Vector auf dem Sensor: Quelle, Stapel und Puffer

- Status: angenommen, Token-Weg ersetzt durch E-026
- Datum: 2026-09-18
- Quelle: Schritt 4.2

**Entscheidung:**

- `timberio/vector:0.58.0-alpine`, Tag und Digest gepinnt. Der Container läuft
  als 999:999 wie Cowrie, schreibgeschützt, ohne Capabilities und ohne Port.
- Er sieht nur `/srv/honeypot/a/var/log/cowrie`, und das nur lesend. Host-Keys
  und `fs.pickle` bleiben außen vor.
- Das Ingest-Token kommt aus `/srv/honeypot/.env` (Rechte 600, root) und steht
  als `${INGEST_TOKEN}` in der Konfiguration, nie im Klartext.
- Die Datei wird am Inhalt erkannt (`fingerprint.strategy: checksum`), die
  Position liegt in `/srv/honeypot/vector`.
- Ein Stapel geht als JSON-Array raus, höchstens 250 Ereignisse und 512 KiB.
- Fällt der Hauptserver aus, puffert Vector auf der Platte (256 MiB, `block`).

**Begründung:**

- Cowrie rotiert `cowrie.json` täglich. Am Dateinamen erkannt, verlöre Vector
  die Zeilen, die nach dem Umbenennen noch in die alte Datei laufen. Am Inhalt
  erkannt, liest er sie zu Ende.
- Die gemerkte Position verhindert, dass ein Neustart alles noch einmal
  schickt. Gegen den Rest hilft die Idempotenz der API (E-024) — beides
  zusammen, weil eines allein jeweils nur die halbe Zusage ist.
- 250 Ereignisse und 512 KiB liegen mit Abstand unter den Grenzen von API und
  Caddy (500 Ereignisse, 1 MB).
- `when_full: block` hält lieber Vector an, als Ereignisse zu verwerfen. Auf
  dem Sensor liegen die Logs ohnehin 14 Tage.

**Konsequenzen:**

- `scripts/test-vector-rotation.sh` prüft Rotation und Neustart in einem
  eigenen Verzeichnis, ohne die echten Daten anzufassen.
- Die API nimmt neben dem Array auch NDJSON und ein einzelnes Objekt an, damit
  eine geänderte Einstellung auf dem Sensor den Ingest nicht anhält.
- Variante B bekommt in Phase 7 einen zweiten Pfad in `include` und einen
  eigenen Mount.
- Beim ersten Start liefert Vector den gesamten vorhandenen Bestand nach
  (`read_from: beginning`), auch unsere eigenen Testsitzungen. Sie sind an
  `127.0.0.1` erkennbar und werden in Schritt 7.1 ausgeschlossen.

---

## E-026: Ingest-Token über Vectors Secrets-Backend

- Status: angenommen
- Datum: 2026-09-18
- Quelle: Schritt 4.2, Fehlersuche nach 401 beim ersten Start

**Entscheidung:** Vector holt das Ingest-Token über den Secrets-Backend
`directory` aus `/srv/honeypot/secrets/ingest_token` (Rechte 0400, Eigentümer
999). In der Konfiguration steht `SECRET[lab.ingest_token]`. Der Container
bekommt keine `env_file` mehr. Ersetzt den Weg über `${INGEST_TOKEN}` aus
E-025.

**Begründung:**

- Vector 0.57 hat die automatische Ersetzung von `${VAR}` in der
  Konfiguration entfernt. Vector schickte den Platzhalter deshalb wörtlich als
  Token, und die API antwortete mit 401. Die Meldung im Log der API
  (`laenge 15`, `sieht_aus_wie_platzhalter true`) hat das gezeigt.
- Die angebotenen Wege sind `--dangerously-allow-env-var-interpolation`, ein
  Vorverarbeiten mit envsubst oder der Secrets-Backend. Vector empfiehlt für
  Zugangsdaten ausdrücklich den Secrets-Backend.
- Nebeneffekt: Das Token steht nicht mehr in der Umgebung des Containers.
  `docker inspect` und `/proc/1/environ` zeigen es damit nicht mehr.

**Konsequenzen:**

- `prepare-host.sh` legt `/srv/honeypot/secrets` an. Der Inhalt kommt von Hand,
  abgeleitet aus `/srv/honeypot/.env`.
- Ein falsches oder fehlendes Token führt bei Vector zu „Not retriable“: Die
  Ereignisse werden **verworfen**, nicht erneut versucht, und die Leseposition
  rückt trotzdem vor. Nach so einem Fehler muss der Positionsmerker in
  `/srv/honeypot/vector` gelöscht werden, damit Vector den Bestand noch einmal
  liest. Die Idempotenz der API (E-024) macht das gefahrlos.
- Die API protokolliert bei 401 die Form des Headers, nie den Wert.

---

## E-027: Stapelform, rotierte Dateien, NUL-Bytes, Savepoints

- Status: angenommen
- Datum: 2026-09-18
- Quelle: Schritt 4.2, Fehlersuche nach 0 Ereignissen trotz laufendem Vector

**Befund:** Nach der Umstellung auf den Secrets-Backend (E-026) lief Vector
ohne Fehlermeldung, in der Datenbank kam aber nichts an. Das Log der API zeigte
je Anfrage `accepted 0, rejected 1, kein Objekt`. Mit `codec: json` und Komma
als Trenner baut Vector das Array selbst. `payload_prefix: "["` und
`payload_suffix: "]"` legten eine zweite Klammer darum, es kam `[[e1, e2, …]]`
an: eine Liste mit einem einzigen Element, das kein Objekt ist. Die API
antwortete 200, Vector hielt das für Erfolg und rückte weiter.

**Entscheidung:**

- **Keine `payload_prefix`/`payload_suffix` in Vector.** Vector schickt ein
  schlichtes Array.
- **Die API entpackt eine zweite Array-Hülle** (eine Ebene tief), damit dieselbe
  Fehleinstellung nicht noch einmal unbemerkt Daten kostet.
- **Der Ablehnungsgrund nennt den Typ** (`kein Objekt (list)`). Damit wäre der
  Fehler im ersten Log sofort erkennbar gewesen.
- **Vector liest `cowrie.json*`**, also auch die rotierten Dateien. Was nach
  Mitternacht UTC noch in die alte Datei läuft, ginge sonst verloren, und
  ältere Tage würden nie gelesen. Doppelt liest Vector nichts, er erkennt eine
  umbenannte Datei am Inhalt (E-025).
- **NUL-Bytes werden durch „␀“ ersetzt.** PostgreSQL speichert sie weder in
  `text` noch in `jsonb`, Angreifer schicken sie trotzdem.
- **Jedes Ereignis bekommt einen eigenen Savepoint.** Scheitert eines an der
  Datenbank, zählt es als `datenbankfehler`, der Rest des Stapels bleibt.

**Begründung:**

- E-024 versprach, dass eine kaputte Zeile nicht den Stapel wegwirft. Das galt
  nur für Prüffehler. Ein Datenbankfehler (etwa durch ein NUL-Byte) hätte mit
  500 geendet, Vector hätte fünf Minuten wiederholt und dann 250 Ereignisse
  verworfen, während alles dahinter wartet.
- Eine Antwort mit 200 und lauter Ablehnungen ist für Vector ein Erfolg. Solche
  Fehler fallen nur im Log der API auf, nicht bei Vector.

**Konsequenzen:**

- Nach dem Einspielen muss der Positionsmerker auf dem Sensor gelöscht werden,
  damit Vector den Bestand ab 2026-09-17 noch einmal liest. Duplikate
  verhindert der Inhalts-Hash (E-024).
- Zur Kontrolle des Ingest gehört künftig immer auch das Log der API
  (`"msg": "ingest"` mit `rejected` und `reasons`), nicht nur das von Vector.

---

## E-028: Worker: IPinfo-Download, Tagesstatistik, Aufräumen

- Status: angenommen
- Datum: 2026-09-18
- Quelle: Schritt 4.3

**Entscheidung:**

- Drei Jobs in einer Zeitplanschleife: `ipinfo` täglich, `statistik`
  stündlich, `aufraeumen` täglich. Die im Bauplan vorgesehene monatliche
  Rotation des HMAC-Schlüssels entfällt (E-022).
- **IPinfo:** erst die Prüfsumme abfragen, nur bei Änderung laden. Die Datei
  landet als `.part` im selben Volume, wird gegen die Prüfsumme geprüft und
  probeweise geöffnet, erst dann per `os.replace` an ihren Platz gebracht. Nach
  einem Neustart lädt der Worker nur, wenn die Datei fehlt oder älter als ein
  Tag ist.
- **Statistik:** heute, gestern und jeder Tag ohne Zeile in `daily_stats`,
  jeweils komplett neu (löschen und schreiben in einer Transaktion). Grundlage
  sind `sessions` und `commands`. Nur die Logins kommen aus `events`.
- **Aufräumen:** erst fehlende Statistik nachrechnen, dann Roh-Events älter als
  90 Tage in Portionen löschen.

**Begründung:**

- IPinfo erlaubt 10 Downloads am Tag je IP, die Prüfsumme zählt nicht mit. Ein
  Worker, der bei jedem Neustart lädt, würde in einer Neustartschleife das
  Limit reißen.
- Die API liest die Datei in jedem Moment. Mit `os.replace` sieht sie immer
  eine vollständige Datei, alt oder neu.
- Die Statistik muss sich auch nach dem Löschen der Roh-Events nachrechnen
  lassen. Deshalb stützt sie sich auf die abgeleiteten Tabellen.
- Die URL enthält das Token. Fehlermeldungen des Downloads nennen deshalb nur
  den Status, fremde Ausnahmen im Log nur ihren Typ.

**Konsequenzen:**

- Die 14.178 Ereignisse vom 17. und 18.09. kamen ohne IPinfo-Datenbank an. Ihre
  Sitzungen bekommen ein Land nur durch ein einmaliges Neueinlesen vom Sensor,
  solange die Rohlogs dort liegen (14 Tage).
- Kennzahlen in `daily_stats`: `sessions`, `logins`, `sessions_interactive`,
  `sessions_exec`, `commands`, `sources`, dazu `sessions_by_country` und
  `sessions_by_hour` als Dimensionen. Je Tag gibt es Zeilen für `a`, `b` und
  `all`. Sitzungen ohne Land zählen unter `??`.
- Unsere eigenen Testsitzungen sind noch mitgezählt. Sie fallen in Schritt 7.1
  heraus.

---

## E-029: Live-Stream und Statistik-Endpunkte

- Status: angenommen
- Datum: 2026-09-18
- Quelle: Schritt 5.1

**Entscheidung:**

- **Stream über einen Verteiler im Speicher.** Der Ingest meldet jedes neu
  gespeicherte Ereignis nach dem Commit. Jeder Client hat eine eigene
  Warteschlange mit 100 Plätzen, bei Überlauf fällt die älteste Meldung weg.
  Höchstens 200 Clients insgesamt.
- **Meldung:** `ts`, `variant`, `country`, `event` und bei Befehlen `command`,
  eine Vorschau von höchstens 80 Zeichen. Keine Sitzungs-ID, kein Hash.
  Gestreamt werden nur Verbindung, Login, fehlgeschlagener Login, Befehl,
  Download und Sitzungsende.
- **„Ohne IPs“** heißt: Die Adresse des Angreifers erscheint nie, auch nicht
  entschärft. Adressen Dritter in Befehlen erscheinen nur entschärft.
- **Statistik aus `daily_stats`**, nur „heute“ in der Übersicht live aus
  `sessions`. Jede Antwort 30 Sekunden im Speicher und mit
  `Cache-Control: public, max-age=30`.
- **Rate-Limit:** 60 Statistik-Anfragen pro Minute und höchstens 3 offene
  Streams je Client. Der Client wird über den ersten Eintrag in
  `X-Forwarded-For` erkannt, das Caddy selbst setzt. Als Schlüssel dient ein
  Hash mit einem Zufallswert je Prozess, nie die Adresse.

**Begründung:**

- Ein Verteiler im Speicher ist das Einfachste, das trägt. Die API läuft als
  ein einziger uvicorn-Prozess, und der Stream muss keine Geschichte liefern,
  nur das, was ab jetzt passiert.
- Die Warteschlange je Client entkoppelt: Ein langsamer Browser bremst weder
  den Ingest noch andere Besucher.
- Erst nach dem Commit zu melden heißt, dass nichts im Stream erscheint, was
  nicht auch in der Datenbank steht. Dubletten beim Neueinlesen erscheinen
  nicht, sie werden ja nicht gespeichert.
- Auch Besucheradressen sind IPs (E-009). Der Hash mit Zufallswert erlaubt ein
  Limit pro Client, ohne dass eine Adresse irgendwo stehen bleibt.

**Konsequenzen:**

- Läuft die API einmal mit mehreren Prozessen, muss PostgreSQL
  `LISTEN/NOTIFY` den Verteiler ersetzen. Heute steht im Dockerfile kein
  `--workers`.
- Nach einem Neustart der API verbinden sich Browser selbst neu (`retry:
  5000`). Was in der Zwischenzeit geschah, sehen sie im Stream nicht, nur in
  der Statistik.
- Die Seite `/lab` muss Befehle ausschließlich per `textContent` einsetzen
  (README „Harte Regeln“, Schritt 5.2). Entschärft heißt nicht harmlos für
  HTML.
- Unsere eigenen Testsitzungen zählen in der Statistik noch mit (Schritt 7.1).

---

## E-030: Seite /lab: eigenes Projekt in Website-Demo, eigene Globus-Instanz

- Status: angenommen
- Datum: 2026-09-18
- Quelle: Schritt 5.2, `docs/wireframe.md`, Pull Request in `ClintonLel/Website-Demo`

**Entscheidung:**

- **Eigenes Vite-Projekt `lab/` in Website-Demo**, neben `globe-demo/`.
  Gleicher Stack (React 19.2.4, globe.gl 2.45.0, three 0.182.0), aber eigener
  Build unter `/lab/` in einer eigenen Stufe des Dockerfiles. `gate` liefert
  `/lab` öffentlich aus, ohne Login.
- **Eigene Globus-Komponente `LabGlobe`** statt `useGlobeScene` aus der Demo.
  Dunkel, ohne Klicks, ohne Rotation. Bögen vom Mittelpunkt des Herkunftslands
  (Beschriftungspunkte aus Natural Earth) nach Nürnberg.
- **Nichts von Dritten.** Länderumrisse aus dem npm-Paket `world-atlas`,
  Mittelpunkte als Tabelle im Repo, Ländernamen per `Intl.DisplayNames`,
  Systemschriften.
- **Content-Security-Policy auf `/lab`:** Skripte nur von der eigenen
  Herkunft, Verbindungen nur dorthin und zu `https://api.<DOMAIN>`, kein
  Einbetten. `style-src` erlaubt `'unsafe-inline'`, weil globe.gl drei kleine
  `<style>`-Tags einfügt.
- **Angreifer-Texte nur als Text:** ESLint verbietet jeden Weg zu HTML aus
  einem String (auch die Tooltip-Accessoren von globe.gl), ein Test rendert
  feindliche Befehle. Die Seite prüft auch Meldungen der eigenen API noch
  einmal (Felder, Länge, Steuer- und Richtungszeichen).
- **Neuer Endpunkt `GET /stats/recent`:** die letzten 12 Befehle in der Form
  der Stream-Meldungen, 30 Sekunden gecacht.
- **Vorerst nur Deutsch.**

**Begründung:**

- `globe-demo` wird unter `/demo/` hinter dem Login gebaut. Eine zweite Seite
  im selben Build bräuchte einen anderen Basis-Pfad und würde die Demo ändern.
  Ein eigenes Projekt lässt die Demo unberührt (README „Harte Regeln“). Die
  Aussage aus E-010, der bestehende Stack erspare einen zweiten
  Build-Prozess, gilt damit nur noch für den Stack, nicht für den Build.
- `useGlobeScene` ist mit dem Shop verdrahtet (Japan-Flagge, Klick öffnet den
  Shop, Intro-Text) und lädt Länder und Textur zur Laufzeit von GitHub und
  unpkg. Diese Server sähen sonst die Adresse jedes Besuchers.
- Der Bloom aus der Demo (`GlobePostProcessingEffect.js`) wird nicht
  übernommen: Er ruft `composer.removeAllPasses()` auf, das three.js'
  `EffectComposer` nicht kennt, und bleibt deshalb auch in der Demo still
  wirkungslos.
- Der Globus dreht sich nicht, weil fast alle Bögen in Nürnberg enden und der
  Sensor sonst aus dem Bild wandert. Auf Touch-Geräten ist nur das Drehen
  gesperrt, nicht die Controls: Ohne `controls.update()` zeigt die Kamera
  nicht mehr auf den Erdmittelpunkt.
- Ohne `/stats/recent` bliebe „Letzte Befehle“ nach dem Laden minutenlang
  leer. Befehle kommen im Schnitt nur etwa alle zwei Minuten.

**Konsequenzen:**

- Wer die Seite findet, kann einen eigenen Befehl eingeben und sehen, ob er
  dort erscheint. So lässt sich der Sensor als Honeypot erkennen. Das betrifft
  A und B gleich und gehört als Grenze in `docs/method.md`.
- Ein Tab im Hintergrund hält keinen Stream offen und lädt Statistik nur
  einmal. So bleiben die 200 Plätze des Verteilers (E-029) für sichtbare
  Seiten.
- Die Seite nennt den Standort des Sensors (Nürnberg), nie seine Adresse.
- Änderungen an `/lab` laufen wie die am Caddy-Block per Pull Request in
  Website-Demo. Die Pipeline dort baut und prüft `lab/` mit (Lint, Tests,
  Build) und fragt nach jedem Deploy `/lab` samt CSP ab.

---

## E-031: Startseite als Projektseite mit Live-Karte des Labs

- Status: angenommen
- Datum: 2026-09-18
- Quelle: Schritt 5.3, Wunsch des Users, Pull Request `ClintonLel/Website-Demo#15`

**Entscheidung:**

- **Statt einer Kachel wird die Startseite eine Projektseite.** Oben eine
  Karte je Projekt, darunter ein Abschnitt je Projekt. Die Texte zur Globe
  Demo bleiben wörtlich erhalten, das Lab bekommt einen eigenen Abschnitt.
  Alles auf einer Seite, auf Deutsch und Englisch.
- **Die Karte des Labs ist live:**
  - ein kleiner Globus als SVG, ohne three.js
  - Sensorstatus und Sitzungen heute aus `/stats/overview`
  - „zuletzt: Land, vor x s“ und ein Bogen je neuer Verbindung aus `/stream`
- **Nur Zahlen und Ländercodes, keine Befehle.** Angreifer-Texte bleiben
  auf `/lab`.
- **Alles Live-Hafte steht mit `hidden` im HTML** und wird erst mit Daten
  sichtbar.
- **Derselbe Ländermittelpunkt wie auf `/lab`:** ein Test hält beide
  Tabellen gleich.
- **Die Content-Security-Policy von `/lab` gilt jetzt auch für die
  Startseite.**

**Begründung:**

- Der Bauplan ging von einem bestehenden Projekt-Hub aus. Die Startseite war
  aber eine Seite nur über die Globe Demo. Der User wollte, dass sie alle
  Projekte zeigt und beide interaktiv bewirbt.
- **Eine Seite statt Unterseiten:**
  - Sprachumschaltung und QR-Code-Link bleiben unverändert.
  - Das Gate braucht keine neuen Routen.
  - Werden es mehr Projekte, lassen sich die langen Texte später auslagern.
- **Kein Framework und kein Build für die Startseite.** Sie wird oft über
  den QR-Code im Mobilfunknetz geöffnet. Ein ES-Modul von wenigen KB und ein
  SVG von 11 kB (komprimiert) halten sie schnell.
- **Keine Befehle auf der Startseite:** Die Regel „Angreifer-Texte nur als
  Text“ muss dann nur eine Seite einhalten, und die Startseite braucht keine
  eigene Prüfung dafür.

**Konsequenzen:**

- **Stream-Plätze:** Die Startseite belegt nur einen Platz des Verteilers
  (E-029), solange die Lab-Karte zu sehen und der Tab offen ist.
- **Quellenhinweis:** IPinfo Lite und Natural Earth stehen jetzt auch im
  Footer der Startseite.
- **Neue Projekte:** Ein neues Projekt bekommt eine weitere Karte und einen
  Abschnitt, in beiden Sprachfassungen (`docs/DEPLOYMENT.md` in Website-Demo).

---

## E-032: Regeln für Coding-Agenten in AGENTS.md

- Status: angenommen, Sperrlisten ergänzt durch E-033 und E-035
- Datum: 2026-09-29
- Quelle: Wunsch des Users

**Entscheidung:**

- **Die Vorgaben stehen in `AGENTS.md`.** Ziel, Architektur, harte Regeln,
  Stack, Arbeitsweise und Befehle sind wörtlich aus README.md übernommen.
  README.md behält Titel und Ziel und verweist auf `AGENTS.md`.
- **`CLAUDE.md` bindet `AGENTS.md` per `@AGENTS.md` ein.** Darunter stehen
  nur Hinweise, die allein für Claude Code gelten.
- **`.cursorignore`** hält Secrets, `.mmdb`-Dateien, Datenbank-Dumps,
  `node_modules` und `dist` von Cursor fern.
- **`.claude/settings.json`** verbietet Claude Code das Lesen von
  `.env`-Dateien (`Read(.env)`, `Read(**/.env)`).
- **`docs/workflow-log.md`** hält je Aufgabe fest, welches Werkzeug sie
  erledigt hat und was von Hand nachgearbeitet wurde.

**Begründung:**

- Neben Claude Code sollen auch andere Coding-Agenten wie Cursor im Repo
  arbeiten. `AGENTS.md` ist die Datei, die solche Werkzeuge von sich aus
  lesen. Die Regeln stehen damit an einer Stelle und laufen nicht
  auseinander.
- Claude Code liest `CLAUDE.md`, nicht `AGENTS.md`. Der Import bindet die
  Regeln ein, ohne sie zu kopieren.
- Die Bauplan-Vorlage hieß `CLAUDE.md`, lag im Repo aber als README.md. Die
  Regeln richten sich an Agenten, README.md richtet sich an Leser auf GitHub.
- Was ein Agent liest, kann im Kontext eines Modells und damit beim Anbieter
  landen. Die Regel „Secrets nur über .env; nie committen, nie loggen“ soll
  deshalb auch für Agenten gelten.

**Konsequenzen:**

- Neue Regeln für alle Agenten kommen in `AGENTS.md`, nicht in `CLAUDE.md`
  oder README.md.
- Verweise auf README-Abschnitte in E-001 bis E-010, E-012, E-023, E-024,
  E-029 und E-030 meinen jetzt den gleichnamigen Abschnitt in `AGENTS.md`.
  Die Einträge bleiben unverändert. Verweise in Code, Tests und Doku zeigen
  jetzt auf `AGENTS.md`.
- Die Deny-Regeln gelten nur für Claude Codes Read-Tool. Ein `cat .env` über
  die Shell verhindern sie nicht, darauf weist `CLAUDE.md` hin. Dateien wie
  `.env.local` erfassen sie nicht.
- Offen: `.cursorignore` enthält die Rohdaten des Honeypots (`cowrie.json*`,
  `tty/`, `downloads/`) noch nicht. Sie stehen bisher nur in `.gitignore`.

---

## E-033: Rohdaten und weitere .env-Dateien für Agenten sperren

- Status: angenommen, Sperrlisten ergänzt durch E-034 und E-035
- Datum: 2026-09-29
- Quelle: Wunsch des Users, offener Punkt aus E-032

**Entscheidung:**

- `.cursorignore` enthält zusätzlich die Rohdaten des Honeypots:
  `cowrie.json*`, `tty/` und `downloads/`.
- `.claude/settings.json` verbietet zusätzlich `Read(**/.env.local)`,
  `Read(**/.env.production)`, `Read(**/cowrie.json*)`, `Read(**/tty/**)` und
  `Read(**/downloads/**)`.
- `.gitignore` enthält jetzt auch `dist/`. Damit steht alles, was
  `.cursorignore` und die Deny-Regeln sperren, auch in `.gitignore`.

**Begründung:**

- `cowrie.json` enthält Klartext-IPs, tty-Mitschnitte enthalten
  Angreifer-Eingaben, `downloads/` enthält Malware. Liest ein Agent sie, landen
  Klartext-IPs beim Anbieter des Modells, und das verletzt die erste harte
  Regel.
- Rohdaten gehören nicht auf den Laptop: `sensor/scripts/make-fixtures.py`
  läuft auf dem Sensor und ersetzt die Adressen der Beteiligten, bevor
  Beispiele nach `server/tests/fixtures` kommen. Liegt trotzdem eine Kopie im
  Repo-Ordner, soll kein Agent sie lesen.

**Konsequenzen:**

- Agenten können echte Rohdaten nicht mehr per Read-Tool lesen. Wer
  Beispiele braucht, nimmt die Fixtures in `server/tests/fixtures` oder
  erzeugt neue auf dem Sensor (sensor/README.md).
- Weiter offen: Die Deny-Regeln gelten nur für das Read-Tool, nicht für die
  Shell (E-032).

---

## E-034: OpenTofu-State und -Variablen für Agenten sperren

- Status: angenommen, `*.tfplan` ersetzt durch E-035
- Datum: 2026-09-29
- Quelle: Wunsch des Users, nach dem Commit der OpenTofu-Dateien (E-013)

**Entscheidung:** `.cursorignore` und die Deny-Regeln in
`.claude/settings.json` sperren zusätzlich `*.tfstate`, `*.tfstate.*`,
`*.tfvars` und `*.tfvars.json`. In `.gitignore` stehen diese Muster bereits
(E-013).

**Begründung:**

- Der State enthält IDs, die IPs des Sensors und die komplette User Data aus
  `cloud-init.yaml` (`infra/README.md`). `*.tfstate.*` erfasst auch
  `terraform.tfstate.backup` mit demselben Inhalt.
- In `*.tfvars` stehen lokale Werte wie die Admin-Adressen aus
  `admin_source_ips`.
- Die Sensor-IP soll nicht beim Anbieter eines Modells landen. Aus demselben
  Grund ersetzt `make-fixtures.py` sie in den Beispiel-Logs.

**Konsequenzen:**

- Agenten können `.tf`-Dateien, `infra/README.md` und `.terraform.lock.hcl`
  weiter lesen, den State nicht. Fragen zum aktuellen Aufbau beantwortet
  `tofu output` oder `tofu state list` im Terminal, nicht ein Agent.
- Nicht gesperrt sind gespeicherte Pläne (`*.tfplan`) und der Ordner
  `.terraform/`. Beide stehen nur in `.gitignore`.

---

## E-035: Sperrlisten an .gitignore angleichen, auch `*.tfplan`

- Status: angenommen
- Datum: 2026-09-29
- Quelle: Review von PR #2 durch Antigravity, Auftrag des Users

**Entscheidung:**

- `.cursorignore` und die Deny-Regeln in `.claude/settings.json` sperren
  zusätzlich `*.pem`, `*.key`, `.env.*` (außer `.env.example`), `*.log` und
  `*.tfplan`. Die Deny-Regeln sperren außerdem die Datenbank-Dumps
  (`*.sql`, `*.sql.gz`, `*.dump`, `*.pgdump`, `*.backup`, `dumps/`,
  `backups/`), die bisher nur `.cursorignore` enthielt.
- `.env.example` bleibt lesbar: in `.cursorignore` per `!.env.example`, in
  `.claude/settings.json` per `Read(!**/.env.example)` direkt nach
  `Read(**/.env.*)`. Die Einzelregeln für `.env.local` und `.env.production`
  aus E-033 entfallen, `.env.*` erfasst sie.
- `server/.env` entfällt aus `.cursorignore`. `.env` ohne Schrägstrich greift
  dort in jedem Ordner, auch in `server/` und `sensor/`.
- `CLAUDE.md` nennt alle gesperrten Gruppen und beschreibt genauer, wo die
  Deny-Regeln greifen.
- Das ersetzt den letzten Punkt von E-034: `*.tfplan` ist jetzt gesperrt.
  `.terraform/` bleibt frei.

**Begründung:**

- Mit E-032 bis E-034 sperrten `.cursorignore` und die Deny-Regeln
  unterschiedliche Teilmengen von `.gitignore`. Was Git von GitHub fernhält,
  soll auch kein Agent einem Modell zeigen. Alle Muster aus `.gitignore` für
  Secrets, Klartext-IPs und Angreiferdaten stehen jetzt in beiden Listen.
  Nur in `.cursorignore` stehen `*.mmdb`, `node_modules/` und `dist/`: Sie
  enthalten nichts davon und sollen nur nicht indexiert werden.
- Ein gespeicherter Plan enthält den bisherigen State, die Werte der
  Variablen und die Konfiguration im Klartext, also dieselben Daten wie
  `*.tfstate` und `*.tfvars` (Sensor-IP, `admin_source_ips`, User Data).
  `infra/` nutzt keine State- oder Plan-Verschlüsselung von OpenTofu.
  `.terraform/` enthält bei lokalem Backend nur Provider und Module.
- `.env.*` statt einzelner Namen: Eine `.env.staging` oder
  `sensor/.env.local` wäre sonst lesbar.
- `*.log`: Cowrie und Vector können Logs mit Klartext-IPs schreiben;
  `.gitignore` führt `*.log` deshalb unter den Rohdaten.
- Laut Doku von Claude Code gelten Read-Deny-Regeln auch für Grep und Glob
  sowie für Shell-Befehle, die Dateien beim Namen nennen (`cat`, `head`,
  `tail`, `sed`, Umleitungen). Sie gelten nicht für `grep -r` ohne
  Dateinamen und nicht für Programme, die Dateien selbst öffnen. E-032 und
  E-033 („nur für das Read-Tool“) waren zu eng formuliert.
- Muster wie `**/cowrie.json*` greifen auch im Repo-Root, Dateinamen ohne
  Schrägstrich in jeder Tiefe. Mit dem Read-Tool an nicht vorhandenen
  Pfaden geprüft (die Sperre meldet sich vor „Datei fehlt“): `cowrie.json`,
  `x.tfplan`, `a.log`, `tty/…` und `dumps/…` im Root, `infra/sensor.key` und
  `sensor/.env.staging` sind gesperrt, `.env.example` ist lesbar.

**Konsequenzen:**

- Agenten können `.env.example` weiter lesen und ändern, echte `.env`-Dateien
  in keinem Ordner.
- `tofu show` auf einen gespeicherten Plan zeigt dessen Inhalt trotzdem. Das
  gehört ins Terminal, nicht in einen Agenten (E-034).
- Die SSH-Host-Keys des Sensors heißen `ssh_host_*_key` und liegen unter
  `/srv/honeypot/hostkeys` auf dem Sensor. `*.key` erfasst sie nicht; sie
  gehören nicht ins Repo.
- Weiter offen: Gegen Shell-Zugriffe, die die Deny-Regeln nicht erkennen,
  hilft nur die Sandbox von Claude Code oder Disziplin (`CLAUDE.md`).

## E-036: CI mit Tests gegen PostgreSQL und gitleaks, ohne Deploy

- Status: angenommen
- Datum: 2026-09-29
- Quelle: Auftrag des Users

**Entscheidung:**

- `.github/workflows/ci.yml` läuft bei Pull Requests, Pushes auf `main` und
  von Hand. Drei Jobs: `server` (pytest mit PostgreSQL als Service-Container),
  `sensor` (pytest mit PyYAML) und `secrets` (gitleaks über die ganze
  Historie). Kein Deploy-Job.
- Übersprungene Tests lassen `server` und `sensor` scheitern.
- Actions sind auf Commit-Hashes gepinnt, `permissions: contents: read`.
- gitleaks läuft als Binary mit fester Version und geprüftem SHA-256, wie im
  Website-Demo-Repo. `.gitleaks.toml` erlaubt nur den erfundenen
  `registration_token` der Persona, und zwar nur genau diesen Wert.

**Begründung:**

- Ohne Datenbank überspringt pytest 58 Server-Tests, darunter Migration,
  Ingest und Worker. Der Service-Container nutzt dasselbe Image mit Digest wie
  `docker-compose.server.yml`.
- Ohne die Prüfung auf übersprungene Tests bliebe der Job grün, wenn die
  Datenbank einmal nicht erreichbar ist. Ohne PyYAML übersprängen 19
  Sensor-Tests.
- Ein Tag wie `v7` lässt sich verschieben, ein Commit-Hash nicht.
- Kein Deploy, weil der Code per rsync auf den Hauptserver kommt (E-017)
  und GitHub dafür keinen Zugang bekommen soll.
- gitleaks 8.30.1 meldet den Köder-Token in `agent.ini` und `prompt.md` als
  `generic-api-key`. Eine Ausnahme mit `paths` überspringt in dieser Version
  die ganze Datei, auch mit `condition = "AND"`. Lokal geprüft: Ein anderer
  Wert in `agent.ini` fiel damit nicht mehr auf. Die Ausnahme hängt deshalb
  nur am exakten Wert.

**Konsequenzen:**

- Die Datenbanktests laufen jetzt bei jedem PR, nicht nur im Container auf
  dem Hauptserver. Maßgeblich für den Betrieb bleibt der Lauf dort.
- Ändert sich der Köder-Token in der Persona, muss `.gitleaks.toml` mit.
- Neue Action-Versionen kommen nur durch bewusstes Nachziehen der Hashes.

## E-037: ATT&CK-Regeln als Daten, Zuordnung beim Ingest

- Status: angenommen
- Datum: 2026-09-29
- Quelle: Auftrag des Users, Schritt 6.1

**Entscheidung:**

- Die Regeln stehen in `server/rules/attack.yml`: je Technik ID, Name,
  Taktiken, kurze Begründung und reguläre Ausdrücke. Oben steht die
  ATT&CK-Version, **Enterprise v19.2** (2026-04-28). IDs, Namen und Taktiken
  wurden am 2026-09-29 auf attack.mitre.org nachgesehen.
- Startset: T1082, T1033, T1098.004, T1222.002, T1105. Aus der Bauanleitung
  dazu T1057, T1053.003 und T1070.003. T1496 (Miner) bleibt draußen.
- Die Zuordnung läuft **beim Ingest** (`add_command` schreibt
  `commands.techniques`). Stream und `/stats/recent` geben die Techniken als
  zusätzliches Feld `techniques` aus, alle anderen Felder bleiben gleich.
- Der Worker-Job `attack` taggt alle gespeicherten Befehle neu. Er läuft nur
  von Hand, nicht im Zeitplan. `run attack --bericht` gibt danach die
  100 häufigsten Befehle ohne Technik im Terminal aus, nicht ins Log.
- Die Muster laufen auf dem gespeicherten Text, also entschärft (`hxxp://`,
  `[.]`). `{cmd}` und `{end}` in der Datei grenzen Befehlswörter ab, damit
  `apt-get install wget` oder `cat ~/.ssh/id_rsa.pub` nichts treffen.
- ReDoS: Eingabe auf 4096 Zeichen gekürzt, Muster höchstens 512 Zeichen.
  Der Loader zerlegt jedes Muster mit Pythons Regex-Parser und lehnt
  verschachtelte Wiederholungen und Rückverweise ab. Die API startet dann
  nicht. Nach dem Review ist die Prüfung strenger: In einer Wiederholung
  mit Obergrenze über 1 (`+`, `*`, `{n,m}`) sind nur noch Literale und
  Zeichenklassen erlaubt, also keine Alternativen, keine optionalen Teile
  und keine weiteren Wiederholungen, damit auch Muster wie `(a|a)+` und
  `(a?a)+` abgelehnt werden.

**Begründung:**

- Die Spalte `commands.techniques` gab es seit dem Grundschema, eine
  Migration war nicht nötig. Beim Ingest kostet die Zuordnung einmal
  Mikrosekunden. Danach lässt sich in SQL nach Technik filtern, für
  Kampagnen (6.2) und den Report.
- Die Bauanleitung sah das Tagging im Worker vor. Dann bekäme der Stream die
  Techniken aber erst bis zu einer Stunde später. Der Worker bleibt fürs
  Nachtaggen zuständig. Stündlich alle Befehle zu prüfen lohnt nicht, weil
  sich das Ergebnis nur mit den Regeln ändert, und die ändern sich nur mit
  einem neuen Build.
- In v19 gibt es die Taktik „Defense Evasion“ nicht mehr. Sie ist in
  **Stealth (TA0005)** und **Defense Impairment (TA0112)** aufgegangen.
  T1222.002 heißt jetzt „Linux and Mac Permissions“ und gehört zu Defense
  Impairment, T1070.003 zu Stealth. Der Loader kennt nur die 15 Taktiken
  von v19.
- Bewusst eng: T1222.002 nur für `chmod`/`chattr` an `.ssh`, wie im Auftrag.
  `chmod +x x.sh` bleibt ohne Tag. `curl` zählt als T1105 nur mit
  Ausgabedatei (`-o`, `-O`, `--output`) oder Pipe in eine Shell, sonst ist es
  meist eine Abfrage. `crontab -l` und `crontab -r` sind kein T1053.003.
- T1496 über Miner-Begriffe liefert viele Fehltreffer, etwa bei `pgrep -f
  xmrig`, das eher Discovery ist. Das lässt sich über Kampagnen in 6.2
  besser zuordnen.
- Die Testbefehle in `server/tests/fixtures/attack_commands.yml` sind von
  Hand geschrieben: Dokumentationsadressen, entschärft, Schlüssel nur als
  Platzhalter. Rohdaten fließen nicht in die Tests.
- Der Report enthält Angreifertext. Deshalb geht er nicht ins Log, und
  Steuerzeichen erscheinen escaped, damit sie das Terminal nicht steuern.

**Konsequenzen:**

- Neue Befehle tragen ihre Techniken sofort. Ältere erst nach
  `run attack` auf dem Hauptserver.
- Jede Regeländerung braucht einen Build und danach `run attack`.
- Bei einem Wechsel der ATT&CK-Version müssen `attack_version`, die
  Taktikliste in `app/attack.py` und die Namen in der Regeldatei mit.
- `re._parser` ist eine interne API von Python. Ändert sie sich mit einer
  neuen Python-Version, schlagen die Tests in `tests/test_attack.py` an.
- Neue Abhängigkeit im Server-Image: `pyyaml==6.0.3`.

## E-038: ATT&CK-Regeln erweitert, T1083 enger als bei MITRE

- Status: angenommen
- Datum: 2026-09-29
- Quelle: Auftrag des Users, Folge-PR zu Schritt 6.1

**Entscheidung:**

- Neue Regeln in `server/rules/attack.yml`: **T1049** (Netzverbindungen
  auflisten), **T1016** (Adressen, Schnittstellen und Routen abfragen),
  **T1098** (Passwort ohne Rückfrage setzen, über das Werkzeug für
  Passwortlisten oder über eine Pipe in das Passwortprogramm) und **T1083**
  (Dateien suchen, Systemverzeichnisse auflisten). IDs, Namen und Taktiken
  am 2026-09-29 auf attack.mitre.org gegen v19.2 geprüft: T1049, T1016 und
  T1083 gehören zu Discovery, T1098 zu Persistence und Privilege Escalation.
- T1082 umfasst jetzt auch Rechnername, Laufzeit, Speicher- und
  Plattenbelegung, geladene Kernelmodule, Systemkonstanten und das Lesen der
  Release-Dateien unter `/etc`. Umgebung und Einhängepunkte zählen nur, wenn
  der Befehl ohne Argumente läuft. Mit Argumenten führt er etwas aus oder
  hängt etwas ein, das ist keine Abfrage. T1033 umfasst jetzt auch die
  Befehle, die angemeldete Benutzer zeigen.
- `{cmd}` erkennt Pfade mit `/./` zwischen den Teilen. Hinter jedem
  Schrägstrich des festen Pfads dürfen bis zu drei `./` stehen. Die
  Wiederholung enthält nur Literale und ist nach oben beschränkt, die
  Prüfung in `_check_structure` bleibt unverändert.
- Neuer Platzhalter `{pipe}`: Befehlsanfang direkt hinter einer einfachen
  Pipe, nicht hinter `||`. Damit zählt das Passwortprogramm nur, wenn es
  sein Passwort aus einer Pipe liest, und nicht, wenn jemand es interaktiv
  aufruft.
- **T1083 bewusst enger als bei MITRE.** MITRE zählt jedes Auflisten und
  Suchen von Dateien. Hier zählen nur die Dateisuche und das Auflisten der
  Wurzel und der üblichen Systemverzeichnisse (`/`, `/etc`, `/home`,
  `/root`, `/var`, `/usr`, `/opt`, `/tmp`), und zwar nur das Verzeichnis
  selbst, keine Unterverzeichnisse.
- **Bewusst ohne Tag bleiben:** vorhandene Cron-Einträge nur lesen, die
  Version des SSH-Clients abfragen, das aktuelle Verzeichnis ausgeben, die
  Befehlshistorie nur anzeigen, Befehle für andere Plattformen (Windows,
  Router und andere Netzgeräte) und Aufräumskripte, die konkurrierende
  Prozesse beenden oder fremde Dateien löschen.

**Begründung:**

- Fast jede interaktive Sitzung listet irgendwann ein Verzeichnis auf. Trüge
  jede davon T1083, sagte das Tag nichts mehr über die Sitzung aus und
  verdrängte in Auswertungen die seltenen Techniken. Das gezielte Umsehen
  in Systemverzeichnissen und die Dateisuche dagegen sind echte Aufklärung.
- Nur lesen ist bei Cron und Historie keine Technik: E-037 zählt erst das
  Anlegen eines Cron-Eintrags und das Löschen der Historie. Die
  Versionsabfrage des SSH-Clients und das aktuelle Verzeichnis sagen über
  das Ziel des Angreifers zu wenig aus.
- Befehle für andere Plattformen laufen auf dem Linux-Honeypot ins Leere.
  Sie zeigen, dass ein Skript blind läuft, aber keine Technik auf diesem
  System.
- Aufräumskripte mischen mehrere Techniken und lassen sich einzeln schlecht
  sauber zuordnen. Über Kampagnen in 6.2 geht das besser.
- Eine Wiederholung aus Literalen verbraucht je Durchlauf eine feste Zahl
  Zeichen. Die Obergrenze hält auch die Zahl der Versuche je Stelle klein.
  Die Tests prüfen feindliche Eingaben mit vielen `/./`, Pipes und
  Auflistungen gegen dieselbe Zeitgrenze wie bisher.

**Konsequenzen:**

- Nach dem Deploy auf dem Hauptserver `run attack` ausführen, damit ältere
  Befehle die neuen Tags bekommen (Anleitung in `server/README.md`).
- Je neue Regel gibt es in `server/tests/fixtures/attack_commands.yml`
  Treffer und Beinahe-Treffer, von Hand geschrieben.
- Ob T1083 zu eng ist, zeigt der Bericht von `run attack --bericht` über
  Befehle ohne Technik. Eine Lockerung braucht einen neuen Eintrag.

## E-039: Kampagnen über normalisierte Befehlsfolgen, Labels als Daten

- Status: angenommen
- Datum: 2026-09-30
- Quelle: Auftrag des Users, Schritt 6.2

**Entscheidung:**

- Sitzungen mit gleicher **normalisierter Befehlsfolge** bilden eine
  Kampagne. Die Normalisierung in `server/app/campaigns.py` ersetzt
  entschärfte URLs und IPs, Passwörter in `user:pw`-Form, Hex ab 16 Zeichen,
  Token aus Buchstaben und Ziffern ab 8 Zeichen und freistehende Zahlen
  durch Platzhalter und vereinheitlicht Leerraum. SSH-Public-Keys werden zu
  `<KEY:…>` mit den ersten 12 Hex von SHA-256 über den Body.
- **Fingerprint** = SHA-256 über die Art der Sitzung (`exec` oder
  `interactive`) und die Folge der normalisierten Befehle, direkte
  Wiederholungen einmal. Sitzungen ohne Befehl haben keinen.
- Eine Kampagne entsteht erst ab **5 Sitzungen** (`MIN_SESSIONS`).
- Der Worker-Job `campaigns` baut alles stündlich neu auf, schreibt nur
  Änderungen, löscht verschwundene Fingerprints und setzt
  `sessions.campaign_id`. Alles in einer Transaktion mit
  `SET LOCAL lock_timeout = '5s'`; die Sitzungen werden nach `id` sortiert
  und nur bei Änderung aktualisiert.
- Migration **0002** ergänzt `campaigns.sources`, `campaigns.asns` und
  `campaigns.median_interval_s`.
- **Labels als Daten** in `server/rules/campaigns.yml`: Fingerprint-Präfix
  (12 Hex) → Label (höchstens 64 Zeichen, eindeutig) und Beschreibung. In der
  Datenbank kommen beide nur von dort.
- `/stats/campaigns` zeigt nur Kampagnen **mit Label** und ergänzt `sources`,
  `asns` und `median_interval_s`. Alle bisherigen Felder bleiben.
- `run campaigns --bericht` zeigt die 20 größten Kampagnen im Terminal, mit
  Präfix, `p3` (erste 6 Hex von SHA-256 über die ersten drei normalisierten
  Befehle), Länge der Folge und den ersten drei Befehlen. `p3` steht nur im
  Bericht.

**Begründung:**

- `commands.command_hash` ist der Hash des rohen Befehls. Jede
  `chpasswd`-Zeile mit neuem Zufallspasswort hätte einen eigenen Hash, und
  aus einem Bot würden tausende Ein-Sitzungs-Kampagnen.
- SSH-Schlüssel gehören einem bestimmten Angreifer. Ein gemeinsamer
  Platzhalter würde fremde Akteure zusammenwerfen, nur weil sie dasselbe
  Skript nutzen.
- **Art im Fingerprint:** `fingerprint` ist eindeutig und `kind` eine Spalte.
  Dieselben Befehle per Exec und in einer Shell kommen in der Praxis von
  verschiedenen Werkzeugen; zusammen hätte die Kampagne keine eindeutige Art.
- **Ganze Folge statt der ersten N Befehle:** So bleiben Skripte getrennt,
  die gleich beginnen und verschieden enden. Der Preis: Bots, die auf die
  Ausgabe der Shell reagieren, können sich über Variante A und B auf
  getrennte Kampagnen verteilen. `p3` im Bericht macht das sichtbar, ohne die
  Befehle vergleichen zu müssen. Zeigt es sich häufig, braucht ein Wechsel
  auf ein Präfix einen neuen Eintrag.
- Die Mindestgröße verhindert zehntausende Kampagnen aus Einzelsitzungen,
  die niemand ansehen kann.
- Verschiedene Download-Adressen werden zu `<URL>`. Eine Kampagne soll ein
  Werkzeug beschreiben, nicht die Infrastruktur, die es gerade nutzt.
- Labels im Repo sind nachvollziehbar, durchlaufen ein Review und überleben
  jeden Neuaufbau. Von Hand gesetzte Werte in der Datenbank wären beim
  nächsten Lauf weg oder, schlimmer, ungeprüft öffentlich.
- Nur gelabelte Kampagnen sind öffentlich: Ein Label heißt, dass jemand die
  Kampagne angesehen hat. Das Frontend nutzt das Label als Anzeigename und
  React-Key, deshalb muss es eindeutig sein.
- Der `lock_timeout` hält einen hängenden Lauf davon ab, den Ingest zu
  blockieren. Sortierte Updates sperren immer in derselben Reihenfolge.
- Die Muster folgen den Regeln aus E-037 gegen ReDoS und werden mit derselben
  Strukturprüfung getestet.

**Konsequenzen:**

- Nach dem Deploy: `alembic upgrade head`, dann `run campaigns` von Hand
  (Anleitung in `server/README.md`). Danach hält der Zeitplan alles aktuell.
- `/stats/campaigns` bleibt leer, bis das erste Label in
  `server/rules/campaigns.yml` steht und ausgerollt ist.
- Ändert sich die Normalisierung, ändern sich Fingerprints. Die Kampagnen
  entstehen neu, die Präfixe in `campaigns.yml` müssen dann neu vergeben
  werden (`labels_ohne_kampagne` im Log zeigt die verwaisten).
- `commands.command_hash` bleibt unverändert und wird für Kampagnen nicht
  genutzt.
- Der Job hält je Sitzung mit Befehlen ein paar Felder im Speicher. Bei
  zehntausenden Sitzungen sind das wenige MB; wächst das deutlich, braucht
  es eine Aggregation in SQL.

## E-040: Vorab-Registrierung des Experiments in `docs/method.md`

- Status: angenommen
- Datum: 2026-10-01
- Quelle: Schritt 7.1, Entwurf von Claude (Projekt), Review durch Antigravity.
  Grenze ±5 Prozentpunkte, Schwelle von 1.000 Quellen, Laufzeit 42 plus
  einmal 28 Tage und echte Downloads in B als Empfehlung (V5) vom User am
  2026-10-01 bestätigt

**Entscheidung:**

- `docs/method.md` legt Hypothesen, Messgrößen, Ausschlüsse, Auswertung,
  Laufzeit und Grenzen fest, bevor B Daten erhebt. Ab dem Start wird es nicht
  mehr geändert (AGENTS.md).
- **Primär ist H2**, eine Äquivalenzhypothese für Exec-Zugriffe: Der Anteil
  neuer Quellen, die binnen 24 Stunden nach ihrem ersten Befehl einen Befehl
  mit anderer Normalform schicken (M1), unterscheidet sich zwischen B und A um
  weniger als 5 Prozentpunkte. H3 (Antwortzeit) ist sekundär, H1 (interaktive
  Sitzungen) und H4 (Echtheitstests) sind explorativ.
- **Analyseeinheit ist die Quelle** (`ip_hash`). Die Primärgröße nimmt nur
  Quellen, die vor dem Start nie da waren. Intervalle per Bootstrap über
  Quellen.
- **Laufzeit 42 Tage**, einmal um 28 Tage verlängerbar, wenn weniger als 1.000
  Quellen je Variante zusammenkommen. Entschieden wird nur nach der Fallzahl.
- **Start und Ende ergeben sich aus den Daten.** Startzeitpunkt und
  Behandlungsparameter kommen in einen eigenen Eintrag hier, nicht in
  `method.md`. Der Git-Tag `vorab-b` friert `method.md` und den Code ein, der
  die Messgrößen bestimmt.

**Begründung:**

- Der Bauplan sah H1 (mehr Befehle je interaktiver Sitzung) als Kern vor. In
  den ersten 14 Tagen gab es drei interaktive Sitzungen, zwei davon eigene
  Tests. H1 ist in vertretbarer Laufzeit nicht prüfbar.
- „Kein Unterschied bei Exec“ (H2 im Bauplan) lässt sich nur mit einer vorher
  festgelegten Grenze zeigen, nicht mit einem nicht signifikanten Test.
- Der erste Exec-Befehl einer Quelle fällt, bevor die Shell etwas ausgegeben
  hat. Was danach kommt, kann von der Shell abhängen, und genau das misst M1.
- Nur neue Quellen: Das schließt den einmaligen Wechsel von A nach B für
  Quellen aus der Vorperiode aus und nimmt das Werkzeug heraus, das 72 % der
  Sitzungen stellt und dessen 43 Quellen schon in der Vorperiode aktiv waren.
- Der Bauplan verlangt in Schritt 7.4 das Startdatum in `method.md`,
  AGENTS.md verbietet Änderungen nach dem Start. Ein Startzeitpunkt aus den
  Daten und ein eigener Eintrag hier lösen den Widerspruch.

**Konsequenzen:**

- Vor dem Start von B müssen die Pflichtpunkte aus `method.md`, Abschnitt 5,
  erfüllt sein, darunter der Patch aus E-041.
- Die Auswertung (Schritt 7.5) setzt die Definitionen aus `method.md` um und
  läuft zuerst als A/A-Prüfung auf der Vorperiode.
- `/lab` zeigt während der Laufzeit nur Zwischenstände. Entschieden wird
  einmal nach dem Ende.
- Abweichungen nach dem Start kommen als eigener Eintrag hierher.

## E-041: Patch für cowrie-b ist Voraussetzung für den Start

- Status: angenommen, Ereignisfelder (Punkt 2) ersetzt durch E-044
- Datum: 2026-10-01
- Quelle: Schritt 7.1, Prüfung des Quellcodes von Cowrie 3.0.14 und 3.0.15
  durch Claude (Projekt). Ersetzt E-016 und erweitert es.

**Befund** im LLM-Backend von Cowrie 3.0.14 (`cowrie/llm/protocol.py`, in
3.0.15 unverändert):

- `cowrie.command.input` entsteht nur in interaktiven Sitzungen
  (`lineReceived`). Ein Exec-Befehl geht ohne Ereignis direkt ans Modell. In A
  loggt die klassische Shell jeden Exec-Befehl.
- Cowrie begrenzt in B die Befehle je Adresse (Standard 20 je 60 Sekunden)
  und antwortet darüber mit leerer Ausgabe. Das steht nur im Textlog, nicht in
  `cowrie.json`. Für Fehler des Anbieters und Antwortzeiten gibt es ebenfalls
  kein Ereignis.
- Nach dem Login schreibt B fest `Welcome to <hostname>`. Das Verzeichnis im
  Prompt bleibt immer `/`, auch nach `cd`.
- `wget` und `curl` laden in B nichts herunter (E-016).

**Entscheidung:** cowrie-b läuft mit einem eigenen Image auf Basis des
gepinnten Cowrie-Images von A, mit einem Patch am LLM-Backend:

1. Exec-Befehle erzeugen `cowrie.command.input` wie in A, und zwar vor der
   Begrenzung je Adresse.
2. Jeder Befehl erzeugt genau ein Ereignis `cowrie.llm.response` mit `status`
   (`ok`, `empty`, `error`, `rate_limited`, `client_gone`), `latency_ms`,
   `http_status`, der Länge der Ausgabe und `command_index`, der laufenden
   Nummer des Befehls in seiner Sitzung. Antworten können in anderer
   Reihenfolge eintreffen als die Befehle, etwa bei parallelen Exec-Kanälen;
   nur die Nummer ordnet sie sicher zu. Der Ingest nimmt das Ereignis an und
   legt die Felder zusätzlich in einer abgeleiteten Tabelle ab.
3. Nach dem Login gibt B die motd aus `etc/motd` aus (E-015).
4. `wget` und `curl` laden über Cowries Download-Code wirklich herunter und
   schreiben dieselben Ereignisse wie A. Begründung, Grenzen und Ablauf wie in
   E-016.

Punkte 1 bis 3 sind Pflicht vor dem Start von B. Punkt 4 ist empfohlen; fehlt
er beim Start, gilt Grenze 7 in `method.md` (V5).

Bewusst nicht im Patch: das Verzeichnis im Prompt, das Gedächtnis von zehn
Befehlen, SFTP und Weiterleitungen. Sie gehören zur Behandlung „Cowries
LLM-Backend“ und stehen als Grenze in `method.md`.

**Begründung:**

- Ohne Punkt 1 hätten fast alle Sitzungen von B in der Datenbank keine
  Befehle. Jeder Vergleich mit A wäre ein Artefakt des Loggings.
- Ohne Punkt 2 sind H3, die Ausfallzeiten und die Prüfung, ob B überhaupt
  geantwortet hat, nicht messbar. Nach dem Start nachgerüstet, fehlten diese
  Daten für den Anfang der Laufzeit.
- Punkte 3 und 4 entfernen Unterschiede, die nichts mit dem Sprachmodell zu
  tun haben.
- Punkt 1 ist eine Lücke in Cowrie selbst und eignet sich wie E-016 als
  Beitrag ans Cowrie-Projekt.

**Konsequenzen:**

- Die Schritte 7.2 und 7.3 setzen den Patch um, mit Tests für alle vier
  Punkte. Der Bauplan nennt ihn dort noch nicht.
- `server/app/events.py` bekommt `cowrie.llm.response` in `KNOWN_EVENTIDS`,
  dazu eine Migration für die abgeleitete Tabelle.
- Das Gateway beantwortet Budget- und Limit-Stopps mit eigenem HTTP-Status,
  damit `http_status` sie zeigt.
- Ein Rate-Limit je IP-Hash im Gateway (Bauplan, Schritt 7.2) geht nicht:
  Cowrie schickt die Adresse des Angreifers bewusst nicht mit (`persona.md`).
  Das übernimmt Cowries Begrenzung je Adresse auf dem Sensor. Soll das Gateway
  je Sitzung begrenzen oder Kosten Sitzungen zuordnen
  (`llm_usage.session_id`), muss der Patch die Sitzungs-ID mitschicken, etwa
  als eigenen Header. Für `method.md` ist das nicht nötig.
- E-016 hat den Status „ersetzt durch E-041“.

## E-042: Mitschnitte von B erst nach dem Ende der Laufzeit öffentlich

- Status: angenommen
- Datum: 2026-10-01
- Quelle: Vorschlag von Claude (Projekt) bei der Planung von 6.3 und 6.4, vom
  User angenommen

**Entscheidung:** Das Session-Theater auf `/lab` (Schritt 6.4) zeigt
Mitschnitte aus A sofort, Mitschnitte aus B erst nach dem Ende der Laufzeit
(T1 in `method.md`). Damit erscheinen auch die Paare aus A und B mit gleicher
Eingabe erst danach. Die Regel steht in `method.md`, Abschnitt 9.7.

**Begründung:**

- Ein Mitschnitt enthält die Antworten der Shell. Während der Laufzeit wären
  die Antworten von B eine Vorlage für jeden, der `/lab` beobachtet, um B zu
  erkennen. Das könnte das Verhalten in B verändern, ohne dass es an der Shell
  selbst liegt.
- Nach dem Ende kostet die Veröffentlichung nichts mehr. Die Paare aus A und B
  eignen sich dann als Auflösung des Experiments.

**Konsequenzen:**

- Schritt 6.3 lädt Mitschnitte aus B trotzdem während der Laufzeit hoch, denn
  auf dem Sensor liegen sie nur 14 Tage. Bis zur Freigabe gibt die API sie
  nicht aus.
- Die Freigabe ist eine Einstellung auf dem Hauptserver, die Tom nach T1 von
  Hand setzt. Ohne sie bleiben Mitschnitte aus B verborgen; ein Fehler in der
  Einstellung darf sie nicht vorzeitig öffentlich machen.

## E-043: LLM-Gateway: Grenzen, Herkunftsprüfung und Kosten

- Status: angenommen, Gesamtgrenze und Kürzung der Antworten ergänzt durch E-044
- Datum: 2026-10-01
- Quelle: Schritt 7.2, Plan von Claude Code, vom User mit Änderungen
  freigegeben. Grundlage: Quellcode von Cowrie 3.0.14
  (`cowrie/llm/llm.py`, `cowrie/llm/protocol.py`). Nachgebessert nach dem
  Review von #13 (Antigravity, Gegenprüfung Claude): Kosten bei Abbrüchen,
  Zeichenmengen der Herkunftsprüfung, 503 statt 429 beim Budgetstopp,
  Status `upstream_limited`.

**Entscheidung:**

- **Endpunkt** `POST /v1/chat/completions` im OpenAI-Format, Anbieter OpenAI,
  über Basis-URL, Modell und Preise austauschbar. Reihenfolge: Token
  konfiguriert (sonst 503), Token gültig (sonst 401, keine Zeile), Schalter
  und Konfiguration (sonst 503, Status `disabled`), Anfrage (400 oder 413,
  `rejected`), Budget (503 `budget_exceeded`), Minutengrenze (429
  `rate_limited`), Anbieter (504 `timeout`; 502 `upstream_limited` bei einem
  429 des Anbieters, 502 `upstream_error` bei jedem anderen Fehler; 200
  `ok`). 429 entsteht nur an der Minutengrenze. Fehler im OpenAI-Format mit
  neutralem Text, nie mit Details vom Anbieter; `upstream_limited` und
  `upstream_error` haben für den Sensor denselben Rumpf.
- **Die Anfrage gilt als feindlich.** Erlaubt sind nur die Felder, die Cowrie
  schickt (`model`, `messages`, `max_tokens`, `temperature`); die drei Werte
  außer `messages` werden ignoriert, alles andere abgelehnt. `content` muss
  ein String sein. Grenzen, abgeleitet aus Cowrie 3.0.14 und dem Prompt:

  | Grenze | Wert | Herleitung |
  |--------|------|------------|
  | Nachrichten | 12 | 1 System + 10 Verlauf + 1 Reserve |
  | System | 48.000 Zeichen | Persona 29.641 + rund 600 von Cowrie + Befehl 4.096, plus 40 % |
  | user | 8.192 | Cowrie kürzt Befehle auf 4.096 |
  | assistant | 32.768 | frühere Antworten, begrenzt durch die Ausgabegrenze |
  | gesamt | 131.072 Zeichen | realistisch höchstens rund 95.000 |
  | Rumpf | 1 MiB | wie Caddy (E-021) |

- **Herkunftsprüfung:** Der System-Prompt muss Cowries Form haben: Persona,
  dann Cowries Satz gegen Prompt-Injection, dann der Satz mit Hostname,
  Benutzer und Verzeichnis, bei Exec zuletzt der Befehl. Getrennt wird am
  ersten Vorkommen des Satzes; der Befehl ist Angreifertext und darf den Satz
  oder das Hostname-Muster selbst enthalten. Hostname, Benutzer und
  Verzeichnis sind auf feste ASCII-Zeichenmengen beschränkt, ohne
  Anführungszeichen und Leerzeichen:

  | Feld | Erlaubt | Was Cowrie 3.0.14 dort einsetzt |
  |------|---------|---------------------------------|
  | Hostname | 1 bis 64 Zeichen aus `A-Z a-z 0-9 . -` | `hostname` aus `cowrie.cfg` (`bld-ci-03`) |
  | Benutzer | 1 bis 32 Zeichen aus `A-Z a-z 0-9 . _ -` | den Login-Namen; laut `sensor/cowrie/userdb.txt` nur `root` oder `admin`, Cowrie vergleicht exakt |
  | Verzeichnis | beginnt mit `/`, 1 bis 1.024 Zeichen aus `A-Z a-z 0-9 . _ - /` | `/`; `self.cwd` ändert sich im LLM-Backend nie |

  Feste Mengen statt `str.isalnum()`, das auch Unicode-Buchstaben
  durchlässt. Der SHA-256 des Teils davor
  (`prompt_sha256`) steht in jeder Logzeile und lässt sich in
  `LLM_PROMPT_SHA256` pinnen. Zerlegt wird mit `str.find`, nicht mit einem
  regulären Ausdruck.
- **Modell, Ausgabegrenze und `temperature`** kommen aus der Konfiguration.
  Die Nachrichten gehen unverändert weiter, damit der Anbieter den
  gleichbleibenden Anfang zwischenspeichert (E-015). Das Feld für die
  Ausgabegrenze ist einstellbar (`max_completion_tokens` bei OpenAI,
  `max_tokens` bei anderen).
- **Budget** für Kalendermonat und -tag in UTC, im Speicher des Prozesses.
  Beim ersten Aufruf nach dem Start aus `llm_usage` geladen; ohne lesbaren
  Stand ruft das Gateway den Anbieter nicht. Geprüft wird vor dem Aufruf, ohne
  Reservierung. Kosten zählen, sobald die Antwort da ist, für den Tag, an dem
  die Anfrage begann.
- **Minutengrenze** als gleitendes 60-Sekunden-Fenster über alle Aufrufe.
- **Kosten** in Mikro-Euro mit eigenem Preis für zwischengespeicherte Tokens,
  aufgerundet. Ohne `usage` und bei jedem Abbruch nach dem
  Verbindungsaufbau eine obere Schätzung (Zeichen / 3 als Eingabe ohne
  Cache, volle Ausgabe): Zeitüberschreitung, Lese- und Schreibfehler,
  abgebrochene Verbindung (`RemoteProtocolError`), kaputte Kodierung, zu
  große Antwort, `OSError`. 0, wenn keine Verbindung zustande kam
  (`ConnectError`, `ConnectTimeout`, `PoolTimeout`), und bei einer
  Fehlerantwort des Anbieters (Status außer 200, auch 429).
- **Neue Spalte** `llm_usage.cached_tokens` (Migration 0003), neue Status
  `disabled` und `upstream_limited` (429 des Anbieters, etwa sein hartes
  Monatslimit). `session_id` bleibt leer (E-041).
- **Konfiguration** nur über die `.env`. Kein Wert des Gateways verhindert den
  Start der API; Platzhalter und zu kurze Secrets gelten als fehlend
  (Maßstab wie E-023). Ein Schalter `LLM_GATEWAY_ENABLED`, Vorgabe aus.
- **Netz:** Die API hängt zusätzlich in `lab_egress`.
- **HTTP-Client** `httpx2` (bisher nur für Tests) wandert in die
  Laufzeit-Abhängigkeiten; `truststore` und `idna`, die es ohne feste Version
  verlangt, sind exakt gepinnt (E-010).

**Begründung:**

- Ein gestohlenes Gateway-Token soll kein allgemeiner Zugang zu einem Modell
  sein. Mit der Herkunftsprüfung ist der einzige freie Text im System-Prompt
  der Platz des Befehls, also genau das, was jeder SSH-Angreifer auf
  cowrie-b ohnehin eingeben kann, und jeder Aufruf trägt den ganzen
  Persona-Prompt. Wer den Sensor übernimmt, hat allerdings auch den Prompt;
  die eigentliche Sicherung bleiben Budget und Minutengrenze.
- Der gepinnte Hash ist zugleich ein Fingerabdruck des Prompts. Eine Änderung
  während der Laufzeit, die `method.md` 4.5 ausschließt, fällt sofort auf.
- Budget im Speicher statt einer Summe je Anfrage aus der Datenbank: kein
  Zugriff je Aufruf, und gleichzeitige Anfragen sehen Kosten sofort. Ohne
  Reservierung können parallele Anfragen das Budget überschreiten, aber nur
  um die gerade laufenden. Weil das Zeitlimit unter 60 Sekunden liegt, laufen
  höchstens `LLM_CALLS_PER_MINUTE` gleichzeitig.
- Ein gleitendes Fenster statt eines Token-Buckets wie in `ratelimit.py`: Es
  lässt in keinen 60 Sekunden mehr als die Grenze durch, und daraus folgt die
  Schranke für gleichzeitige Anfragen.
- Ein Anbieter rechnet auch Antworten ab, auf die das Gateway nicht mehr
  wartet oder deren Verbindung nach dem Senden abbricht. Ohne Schätzung
  könnte ein langsamer oder wackliger Anbieter das Budget unbemerkt leeren.
  Kam dagegen gar keine Verbindung zustande, rechnet niemand ab; eine
  Schätzung dort würde bei einem Ausfall des Anbieters das Tagesbudget
  leeren und B für den Rest des Tages stumm machen.
- **Budgetstopp 503 statt 429:** `method.md` behandelt beides verschieden.
  Ein Budgetstopp ist ein Ausfall (Abschnitt 8, Punkt 2), die Minutengrenze
  gehört zur Behandlung („Nicht ausgeschlossen“ in Abschnitt 8). Der Sensor
  sieht nur `http_status`, deshalb hat jede Seite ihren eigenen Code (V3).
  Ein 429 des Anbieters wird aus demselben Grund nicht weitergereicht.
- `upstream_limited` als eigener Status: Greift das harte Limit bei OpenAI,
  ist das in `llm_usage` sofort von anderen Fehlern zu unterscheiden.
- Zeichenmengen für Hostname, Benutzer und Verzeichnis: Nur so stimmt die
  Zusage, dass der Befehl der einzige freie Text im System-Prompt ist.
- `disabled` statt keiner Zeile: Jede Anfrage mit gültigem Token soll in
  `llm_usage` stehen, auch wenn das Gateway aus ist.
- Felder wie `stream` oder `tools` ablehnen statt ignorieren: Cowrie schickt
  sie nie, wer sie schickt, ist nicht cowrie-b.
- `lab_edge` wurde ohne `--internal` angelegt (E-021), die API käme also auch
  darüber hinaus. Das Netz gehört aber nicht dem Lab allein und wird in
  Website-Demo verwaltet; wird es je zur Härtung intern, bliebe das Gateway
  sonst ohne Weg zum Anbieter. Kein `gw_priority`: Beide Netze gehen über
  dieselbe Adresse des Hosts hinaus, und es entfiele die Abhängigkeit von
  Docker 28.
- `httpx2` statt `urllib`: asynchron, ohne die Ereignisschleife zu blockieren,
  mit Gesamtzeitlimit und Keep-Alive. Ohne Keep-Alive stünde in jeder
  Antwortzeit von B ein TLS-Handshake (H3). Dieselbe Bibliothek nutzt schon
  Starlettes TestClient.

**Konsequenzen:**

- Lasttest (`tests/test_llm_load.py`): Bei einem Budget für 10 Aufrufe
  gingen mit 8 parallelen Schleifen 16 Aufrufe durch, mit 24 gleichzeitig
  gestarteten Anfragen 24. Beides liegt innerhalb der Schranke „laufende
  Anfragen“. Danach gab es nur noch 503 ohne Aufruf beim Anbieter, auch für
  einen neuen Prozess, der das Budget aus `llm_usage` liest.
- Lässt `userdb.txt` je beliebige Benutzernamen zu (`*` oder ein regulärer
  Ausdruck als Benutzer), muss die Prüfung des Benutzernamens mitwachsen.
  Sonst bekommt B für solche Logins keine Antwort, A schon.
- Für 7.3: Der Hash hängt an den eigenen Adressen des Sensors (`{ip}`,
  `{ip6}` im Prompt) und setzt voraus, dass `system_prompt` und
  `system_prompt_exec` denselben Prompt bekommen. Der Patch aus E-041 darf
  den Teil von Cowrie, der den System-Inhalt baut, nicht verändern, sonst
  schlägt die Herkunftsprüfung an. `server/tests/cowrie_llm.py` bildet
  Cowrie 3.0.14 nach.
- Ein Anbieter, der Anfragen ohne `user`-Nachricht ablehnt, scheidet aus:
  Fast der ganze Verkehr ist Exec, und Exec schickt nur die
  System-Nachricht. Die Probeaufrufe in `server/README.md` prüfen beide
  Formen.
- Die Werte der Grenzen und `LLM_PROMPT_SHA256` gehören in den Start-Eintrag
  (`method.md` 4.5). Das Tagesbudget großzügig ansetzen: Ein greifendes
  Tageslimit macht B für den Rest des Tages stumm (Ausfallzeiten).
- Uvicorn muss bei einem Prozess bleiben. Mit mehreren hätte jeder sein
  eigenes Budget.
- Beim Herausziehen der Token-Prüfung (`app/auth.py`) fiel auf, dass
  `/ingest` bei Nicht-ASCII-Zeichen im Token mit 500 statt 401 antwortete
  (`hmac.compare_digest` auf Strings). Der Vergleich läuft jetzt auf Bytes.
- Bewusst nicht enthalten: Grenze je IP-Hash oder Sitzung (E-041),
  Wiederholungen beim Anbieter, eine Sperre in Caddy auf die Adresse des
  Sensors und eine Liste erlaubter Ziele für den Ausgang. Die letzten beiden
  wären eine Änderung an Website-Demo bzw. eine spätere Härtung.

## E-044: Patch für cowrie-b: Ereignis, Abgleich, EOF, Image

- Status: angenommen
- Datum: 2026-10-02
- Quelle: Schritt 7.3, Plan von Claude Code, vom User mit Änderungen
  freigegeben. Grundlage: Quellcode von Cowrie 3.0.14 (Tag `v3.0.14`,
  `src/cowrie/llm/`, `src/cowrie/shell/`), End-zu-End-Läufe mit A, B und dem
  ungepatchten LLM-Backend. Ergänzt E-041 und E-043.

**Entscheidung:**

1. **Ereignis `cowrie.llm.response`** je Befehl in B, statt der Felder aus
   E-041 Punkt 2: `command_index`, `outcome`, `http_status`, `latency_ms`,
   `output_chars`, `client_gone`, `input_sha256`. Kein Prompt, keine Antwort.

   | `outcome` | Entsteht | `http_status` |
   |-----------|----------|---------------|
   | `ok` | 200 mit lesbarem `content`, auch leer (`output_chars` 0) | 200 |
   | `rate_limited` | Minutengrenze des Gateways, gehört zur Behandlung | 429 |
   | `unavailable` | Budgetstopp oder Gateway aus, ein Ausfall | 503 |
   | `upstream_error` | Fehler beim Anbieter, auch Caddy ohne API | 502 |
   | `timeout` | Zeitlimit des Gateways oder eigenes Zeitlimit von Cowrie | 504 bzw. leer |
   | `local_rate_limit` | Cowries Begrenzung je Adresse, kein Aufruf | leer |
   | `error` | alles andere: 400, 401, 413, 500, 200 mit unlesbarem Rumpf, keine Verbindung | Code bzw. leer |

   Gegenüber E-041 heißt das Feld `outcome` statt `status`. `empty` ist
   `ok` mit `output_chars` 0, `client_gone` ein eigenes Feld, und
   `rate_limited` meint jetzt die 429 des Gateways; Cowries Begrenzung heißt
   `local_rate_limit`. `method.md` ist darauf umgestellt (V2, 7.1, 7.4, 8,
   K1, K3, R5). H3 rechnet nur mit `ok`, alle Größen je Quelle nehmen jede
   zugeteilte Quelle (7.4, „Geltungsbereich“).
2. **`command_index`**: ein Zähler je SSH-Verbindung am Transport, den alle
   Kanäle teilen, ab 1, vergeben in derselben Reactor-Runde wie das
   `cowrie.command.input`. B schreibt `command.input` an denselben Stellen
   wie A: einmal je Exec mit dem ganzen, ungekürzten Befehl, vor der
   Begrenzung je Adresse, und einmal je Enter, auch bei leerer Zeile, nie
   für Strg-D. Jede Zeile ruft das Gateway auf, auch eine leere (Behandlung).
3. **Abgleich über `input_ref`.** Der Ingest bildet aus dem rohen `input`
   eines `command.input` (A und B) und aus `input_sha256` eines Aufrufs
   denselben Wert `HMAC-SHA256(IP_HMAC_KEY, "cmd-input\0" + sha256)` und
   speichert ihn in `commands.input_ref` bzw. `llm_responses.input_ref`.
   `input_sha256` selbst wird nicht gespeichert, auch nicht im Roh-Event.
   `python -m app.llm_check` zählt Aufrufe, die an ihrer Stelle passen, nicht
   passen oder keinen Befehl haben.
4. **Zeitlimit und Verbindungsfehler**: `[llm] request_timeout` = 58 s,
   länger als das Gateway (höchstens 55 s), kürzer als Cowries 60 s für
   Exec. Ohne HTTP-Antwort meldet Cowries Client Status 0 statt einer
   erfundenen 500. Was der Client sieht, bleibt wie ohne Patch.
5. **EOF bei Exec**: Ein Exec-Kanal wartet nach dem EOF des Clients auf die
   laufende Antwort, deren Handler ihn dann beendet; höchstens bis zum
   Zeitlimit.
6. **Gateway**: Es kürzt den zurückgegebenen `content` auf 16.384 Zeichen
   und 65.536 Byte als JSON mit `ensure_ascii` (`finish_reason` `length`,
   Logzeile `gekuerzt`). `MAX_TOTAL_CHARS` steigt von 131.072 auf 163.840.
7. **Image**: Basis ist das Image von A (Tag und Digest wie in Compose),
   dazu die zwei gepatchten Dateien. Der Bau prüft die Originaldateien per
   SHA-256, wendet den Patch mit GNU patch `--fuzz=0` an und vergleicht die
   installierten Pakete mit `requirements.lock` (58 Pakete). Das Image heißt
   `localhost/honeypot-lab/cowrie-b:3.0.14-lab.1`, `pull_policy: build`.
   `lab/launch.py` setzt beide System-Prompts aus derselben `prompt.md` und
   das Gateway-Token aus `/srv/honeypot/secrets-b`.
8. **Netz**: cowrie-b lauscht wie A auf `0.0.0.0`, Port 2322. Neben der
   Hetzner-Firewall nimmt nftables 2322 nur von `lo` oder nach Umleitung
   (`ct status dnat`) an und verwirft alles andere. Die Sperre steht in der
   Tabelle `ip honeypot` und deckt nur IPv4 ab; das genügt, weil A und B
   nur auf IPv4 lauschen (`tcp:…:interface=0.0.0.0`, kein `tcp6`). Ein
   Test in `sensor/tests/test_cowrie_b.py` hält das fest.
9. **Bekannte Unterschiede im Backend**, nicht angeglichen: Befehle auf
   stdin einer Exec-Shell (`ssh host sh < skript`) führt A Zeile für Zeile
   aus und loggt sie, B nicht. Eingaben an Programme, die stdin lesen (`cat`
   ohne Datei), sind in A kein Befehl, in B schon.
10. **V5** (echte Downloads) kommt als eigener Schritt 7.3b vor dem Start.

**Begründung:**

- Die Namen aus 7.2 trennen auf dem Sensor, was `method.md` trennen muss:
  Ausfall (`unavailable`, `upstream_error`, `timeout`, `error`) und
  Behandlung (`rate_limited`, `local_rate_limit`). Mit dem alten `status`
  stand `rate_limited` für Cowries Limit und `error` für alles, was die
  Ausfallregel erst über `http_status` wieder aufteilen musste.
- `commands.sequence` entsteht am Server in Eingangsreihenfolge. Wird ein
  `command.input` abgelehnt (Prüfung, Datenbankfehler), rutschen alle
  späteren Nummern der Sitzung. Ohne Abgleich fiele das nicht auf.
- Warum nicht `sha256(commands.command)`: Der gespeicherte Befehl ist
  gekürzt, die Adressen der Beteiligten sind durch `<src>`/`<dst>` ersetzt,
  und er ist entschärft; bei jeder URL oder IP passte der Hash nie. Und ein
  einfacher SHA-256 ließe sich zurückrechnen: Man setzt für `<src>` alle
  IPv4-Adressen ein und vergleicht. Das wäre die Quell-IP (E-009). Der HMAC
  braucht den Schlüssel; der vorhandene genügt, mit eigener Domain.
- Status 0: Eine erfundene 500 wäre in `http_status` nicht von einer echten
  500 des Gateways zu unterscheiden.
- EOF: Gos `x/crypto/ssh` schickt bei `session.Run()` ohne Stdin sofort EOF,
  ebenso `ssh -n`. Cowries LLM-Backend beendete den Kanal dann, bevor die
  Antwort da war: Diese Clients sahen von B nie eine Ausgabe, von A schon.
  Das hat nichts mit dem Modell zu tun, wie motd und Downloads in E-041.
  Ohne die Änderung wäre H3 von EOF-Clients bestimmt, nicht von der
  Antwortzeit.
- Gateway: Die größte Anfrage, die Cowrie bauen kann (Persona bis 32.000
  Zeichen, fünf Befehle à 4.096, fünf Antworten), hatte 134.885 Zeichen und
  passte nicht unter 131.072; das Gateway hätte sie mit 400 abgelehnt. Ohne
  Kürzung konnte es außerdem Antworten liefern, die es im nächsten Aufruf
  selbst ablehnt oder die den Rumpf über Caddys 1 MB treiben. Mit Kürzung
  liegt der schlimmste Fall bei 134.885 Zeichen und 606.772 Byte (Zeichen
  außerhalb der BMP, 12 Byte je Zeichen). Bei `LLM_MAX_TOKENS` 2.048 greift
  die Kürzung praktisch nie.
- Image von A als Basis statt eines eigenen Builds aus den Quellen:
  `method.md` 4.1 verlangt dasselbe Image plus Patch. Das Lock macht den
  Stand lesbar und prüfbar, die Bits sichert der Digest.
- `localhost/` und `pull_policy: build`: Ein gleichnamiges Image auf Docker
  Hub könnte sonst bei `docker compose pull` das eigene ersetzen.
- Die Unterschiede in Punkt 9 nachzubilden hieße, B Programme oder eine
  zweite Shell beizubringen. Das wäre eine Änderung der Behandlung.

**Konsequenzen:**

- Server und Migration 0004 gehen vor cowrie-b live, sonst lehnt `/ingest`
  die neuen Ereignisse ab und Vector verwirft sie (E-027).
- Für den Start-Eintrag (V9, `method.md` 4.5) offen: `LLM_PROMPT_SHA256`
  (nach dem Prüfskript aus dem Log des Gateways, `sensor/README.md`),
  `rate_limit_requests` und `rate_limit_window`, `request_timeout`, die ID
  des gebauten Images von cowrie-b.
- Ändert sich das Basis-Image, ändern sich `upstream.sha256`, der Patch und
  das Lock mit. Der Bau scheitert sonst, und das ist gewollt.
- `cowrie-b.patch` eignet sich wie E-016 als Beitrag ans Cowrie-Projekt:
  Exec-Logging, Antwort-Ereignis, motd, Status 0 und EOF sind Lücken in
  Cowrie selbst.
