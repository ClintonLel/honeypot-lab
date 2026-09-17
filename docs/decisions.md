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
| E-016 | Echte Downloads in cowrie-b über Cowries Download-Code     | vorgeschlagen                                  |
| E-017 | Cowrie-Konfiguration und Betrieb von cowrie-a              | angenommen                                     |
| E-018 | Eigenes Dateisystem und erzeugte Persona-Dateien           | angenommen                                     |
| E-019 | Port 22 per eigener nftables-Tabelle auf cowrie-a umleiten | angenommen                                     |
| E-020 | Lab-Dienste auf dem Hauptserver neben der Webseite         | angenommen                                     |
| E-021 | Caddy-Block für die Lab-API auf `api.tomkaufmann.dev`      | angenommen                                     |

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

- Status: vorgeschlagen
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
  - Von außen landet `ssh root@195.201.127.108` in Cowrie, mit Honeypot-Host-Key,
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
