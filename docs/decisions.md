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

| Nr.   | Entscheidung                                              | Status     |
|-------|-----------------------------------------------------------|------------|
| E-001 | Sensor als eigener Hetzner-Server in eigenem Projekt      | angenommen |
| E-002 | Zwei Cowrie-Varianten auf demselben Sensor                | angenommen |
| E-003 | Cowrie-Container mit `network_mode: host`                 | angenommen |
| E-004 | Zuteilung von Port 22 per nftables-jhash der Quell-IP     | angenommen |
| E-005 | Vector liefert cowrie.json per HTTPS an /ingest           | angenommen |
| E-006 | Komponenten auf dem bestehenden Hauptserver               | angenommen |
| E-007 | Verbindungen nur vom Sensor zum Hauptserver               | angenommen |
| E-008 | LLM-Zugriff nur über das Gateway auf dem Hauptserver      | angenommen |
| E-009 | Quell-IPs anreichern, per HMAC hashen, Klartext verwerfen | angenommen |
| E-010 | Technologie-Stack                                         | angenommen |

---

## E-001: Sensor als eigener Hetzner-Server in eigenem Projekt

- Status: angenommen
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
