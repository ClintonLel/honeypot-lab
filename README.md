# Honeypot-Lab

## Ziel
Forschungs-Honeypot mit Live-Visualisierung unter tomkaufmann.dev/lab.
Forschungsfrage: Verhalten sich Angreifer nach dem Login anders, wenn die
Fake-Shell von einem Sprachmodell gespielt wird (Cowrie-Backend "llm")
statt von Cowries klassischer Shell?

## Architektur (verbindlich)
- Sensor: Hetzner Cloud CX23, Ubuntu 26.04, eigenes Hetzner-Projekt.
  - cowrie-a: klassische Shell, tcp:2222, sensor_name hp-a
  - cowrie-b: backend llm, tcp:2322, sensor_name hp-b
  - beide mit network_mode host; nftables verteilt Port 22 per jhash der Quell-IP
  - Vector liest cowrie.json und sendet per HTTPS + Bearer-Token an /ingest
- Hauptserver (bestehend): Reverse Proxy, FastAPI (Ingest, SSE-Stream,
  Statistik, Mitschnitte, LLM-Gateway), PostgreSQL, Worker.
- Daten fließen nur vom Sensor zum Hauptserver. Der Hauptserver verbindet
  sich nie zum Sensor.
- Der echte LLM-API-Key liegt nur auf dem Hauptserver. Der Sensor kennt nur
  das Gateway-Token.

## Harte Regeln
- Keine Klartext-IPs speichern oder ausgeben: anreichern (IPinfo Lite),
  dann HMAC-SHA256-Hash, Klartext verwerfen.
- Angreifer-Eingaben sind feindlich: validieren, Längen begrenzen, im
  Frontend nur per textContent rendern.
- URLs und IPs in allen öffentlichen Ausgaben entschärfen (hxxp://, [.]).
- Cowrie: forward_redirect und forward_tunnel bleiben aus, Telnet bleibt aus.
- Keine echten Firmen-, Personen- oder Markennamen in der Persona.
- Secrets nur über .env; nie committen, nie loggen, nie in Beispiele.
- Die bestehende Webseite und die Shop-/Globus-Demo nur ändern, wenn ich
  es ausdrücklich verlange.
- Image-Tags pinnen, kein :latest.
- docs/method.md wird nach dem Start von Variante B nicht mehr geändert.

## Stack
Python 3.12, FastAPI, SQLAlchemy 2, Alembic, pytest, PostgreSQL, Vector,
Docker Compose, nftables. Frontend: bestehender Stack von tomkaufmann.dev,
Globus-Komponente als eigene Instanz wiederverwenden.

## Arbeitsweise
- Jede Aufgabe erst planen, Plan zeigen, dann umsetzen.
- Kleine Schritte; nach jedem Schritt Tests laufen lassen.
- Entscheidungen mit Begründung in docs/decisions.md festhalten.
- Befehle für die Server als Anleitung ausgeben, nicht selbst ausführen.

## Befehle
- Tests: cd server && pytest
- Sensor-Tests: python3 -m pytest sensor/tests
- Persona-Dateien erzeugen: python3 sensor/persona/build.py
- Lokal starten: docker compose -f docker-compose.server.yml up
