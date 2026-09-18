# Seitenaufbau von /lab

Übernommen aus dem Bauplan („Seitenaufbau von /lab“, Stand 2026-09-16). Die
Zahlen dort waren Beispielwerte, hier stehen stattdessen die Endpunkte, aus
denen die Seite ihre Daten holt. Gebaut wird die Seite im Repo Website-Demo
unter `lab/`, ausgeliefert von `gate` (E-020, E-030).

## Farben und Grundsätze

- Honiggelb steht überall für Variante A, Türkis für Variante B.
  Dunkler Hintergrund wie auf der Landingpage (`#0b1020`), Systemschriften.
- Angreifer-Texte (Befehle) nur als Text-Knoten einsetzen, nie als HTML
  (README „Harte Regeln“, E-029).
- Keine Klartext-IPs. Die API liefert keine, die Seite zeigt keine.
- Nichts von Dritten laden: keine Schriften, Karten, Texturen oder Skripte von
  fremden Servern. Verbindungen nur zur eigenen Seite und zu
  `api.tomkaufmann.dev`.
- `prefers-reduced-motion`: keine Rotation, keine laufenden Bögen.
- Mobil ab 360 px Breite, einspaltig.

## Abschnitte

| Nr. | Abschnitt | Inhalt | Daten | Stand |
|-----|-----------|--------|-------|-------|
| 1 | Kopf | Forschungsfrage in einem Satz, Live-Status des Sensors, heutige Sitzungen je Variante | `/stats/overview` alle 30 s | Schritt 5.2 |
| 2 | Live-Lage | Globus als eigene Instanz in dunkler Variante. Bögen vom Mittelpunkt des Herkunftslands nach Nürnberg. Daneben die letzten Befehle, entschärft und nur als Text | `/stats/countries?days=7` (Grundbögen), `/stats/recent` (Startliste), `/stream` (live) | Schritt 5.2 |
| 3 | Post-Login-Radar | Anteil Exec-Aufrufe und interaktive Shells, die größten Kampagnen mit ATT&CK-Techniken, Heatmap nach Wochentag und Uhrzeit | `/stats/breakdown?days=30`, `/stats/campaigns`, `/stats/heatmap?days=28` | Schritt 5.2, Kampagnen ab 6.2 |
| 4 | Session-Theater | Mitschnitte im asciinema-Player. Am stärksten: dasselbe Bot-Skript gegen A und B nebeneinander, mit ATT&CK-Marken | folgt | Phase 6/7 |
| 5 | Experiment | Kennzahlen je Variante mit Konfidenzintervallen und Stichprobengröße, getrennt nach interaktiven Sitzungen und Exec-Aufrufen, dazu die Verteilung der Antwortzeiten | folgt | Phase 7 |
| 6 | Methodik und Datenschutz | Vorab festgelegte Hypothesen, bekannte Grenzen, Architektur, Umgang mit IP-Adressen, Quellenhinweis IPinfo Lite | statisch | Kurzfassung im Footer ab 5.2, vollständig mit `docs/method.md` |

## Einzelheiten

### 1. Kopf

- Überschrift: „Merken Angreifer, ob ihnen eine KI antwortet?“
- Chip „Sensor online“, wenn `sensor.online` wahr ist (letztes Ereignis vor
  höchstens 15 Minuten), sonst „Sensor offline“ mit Zeitpunkt des letzten
  Ereignisses.
- Chip A: `today.a.sessions` Sitzungen heute (UTC).
- Chip B: `today.b.sessions`, solange `total.b.sessions` 0 ist aber
  „B · KI-Shell: noch nicht gestartet“.
- Darunter die Summe seit dem ersten Tag: Sitzungen, davon mit Login, Befehle.

### 2. Live-Lage

- Grundbögen: die häufigsten Herkunftsländer der letzten 7 Tage, schwach,
  Deckkraft nach Anteil. Unbekanntes Land (`??`) bekommt keinen Bogen.
- Live-Bögen: jedes `connect` aus dem Stream als kurzer, heller Bogen in der
  Farbe der Variante, der nach einigen Sekunden verblasst.
- Ziel aller Bögen: Nürnberg (49,45° N, 11,08° O), dort ein Punkt „Sensor“.
  Der Globus dreht sich nicht von selbst, sonst wanderte der Sensor aus dem
  Bild. Jede neue Verbindung lässt einen Ring um den Sensor laufen.
- Letzte Befehle: Startliste aus `/stats/recent`, danach jedes `command` aus
  dem Stream oben einfügen, höchstens 12 Einträge. Je Eintrag Uhrzeit,
  Variante (Farbpunkt), Land und der Befehl als Text.

### 3. Post-Login-Radar

- Balken: `exec` gegen `interactive` der letzten 30 Tage, als Prozent der
  Sitzungen mit Befehl. Darunter die Zahl der Sitzungen ohne Befehl.
- Kampagnen: bis Schritt 6.2 ein Hinweis, dass die Auswertung noch folgt.
- Heatmap: 7 Zeilen (Mo bis So) mal 24 Stunden, ausdrücklich in UTC
  beschriftet.

### Footer

- Quellenhinweis: Länder- und ASN-Daten von IPinfo Lite, CC BY-SA 4.0.
- Datenschutz in wenigen Sätzen: Angreifer-Adressen werden nur zum Anreichern
  genutzt und dann gehasht. Die Seite setzt keine Cookies und lädt nichts von
  Dritten. Das Rate-Limit der API nutzt einen Hash, der nur im Speicher liegt.

## Kachel im Projekt-Hub (Schritt 5.3)

Kleiner Globus-Ausschnitt, Titel „Honeypot-Lab“, eine Zeile Kontext
(„Feldexperiment: klassische Shell gegen KI-Shell“) und die heutige Zahl der
Sitzungen aus `/stats/overview`. Verlinkt auf /lab und bleibt ohne API
vollständig nutzbar.
