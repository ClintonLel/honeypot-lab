# Methodik: Vorab-Registrierung des Experiments

Fassung 1 vom 2026-10-01 (Schritt 7.1). Bis zum Start von Variante B
änderbar, danach eingefroren.

Dieses Dokument legt fest, was das Experiment prüft und wie gemessen und
ausgewertet wird, **bevor Variante B Daten erhebt**. Was vorher feststeht,
lässt sich hinterher nicht an die Ergebnisse anpassen.

## Kurzfassung

- **Frage:** Verhalten sich Angreifer nach dem Login anders, wenn Cowries
  LLM-Backend die Shell spielt (B) statt der klassischen Shell (A)?
- **Zuteilung:** per Hash der Quell-IP, jede Adresse fest in A oder B.
  Gezählt wird je Quelle (`ip_hash`), nicht je Sitzung.
- **Primär (H2):** Bei Exec-Zugriffen unterscheidet sich der Anteil neuer
  Quellen, die binnen 24 Stunden nach ihrem ersten Befehl etwas Neues
  schicken (M1), zwischen B und A um weniger als 5 Prozentpunkte.
- **Sekundär (H3):** In B geben Exec-Clients bei langsamen Antworten häufiger
  vor der Antwort auf.
- **Explorativ:** H1 (interaktive Sitzungen, zu selten für einen Test) und H4
  (Verhalten nach Echtheitstests der Shell).
- **Laufzeit:** 42 Tage, einmal um 28 Tage verlängerbar, wenn weniger als
  1.000 Quellen je Variante zusammenkommen. Ausgewertet wird einmal am Ende.
- **Voraussetzung:** Cowries LLM-Backend loggt Exec-Befehle nicht. Ohne den
  Patch aus E-041 und die übrigen Pflichtpunkte aus Abschnitt 5 startet B
  nicht.

## 1. Status und Regeln für dieses Dokument

- Gilt ab dem Merge auf `main`. Bis zum Start von B darf es per Pull Request
  geändert werden, **danach nicht mehr** (AGENTS.md).
- Start und Ende ergeben sich aus den Daten (Abschnitt 4.3). Den genauen
  Startzeitpunkt und die Behandlungsparameter (Abschnitt 4.5) hält ein
  eigener Eintrag in `docs/decisions.md` fest, nicht dieses Dokument.
- Abweichungen nach dem Start kommen als eigener Eintrag in
  `docs/decisions.md` („Abweichung von method.md“, mit Datum und Grund) und in
  den Ergebnisbericht.
- Unmittelbar vor dem Start bekommt `main` den Git-Tag `vorab-b`. Er friert
  dieses Dokument ein und mit ihm den Code, der die Messgrößen bestimmt: die
  Einordnung interaktiv/Exec (`server/app/ingest.py`), die Normalisierung
  (`server/app/campaigns.py`), die ATT&CK-Regeln (`server/rules/attack.yml`)
  und die Regeln für Echtheitstests (V7). Die Auswertung rechnet mit diesem
  Stand, auch wenn sich die Regeln für `/lab` später ändern.
- Das Repo ist privat, sein Datum kann außen niemand prüfen. Wer das belegen
  will, legt zum Start eine datierte Kopie öffentlich ab, etwa bei einem
  Dienst für Vorab-Registrierungen. Optional.

## 2. Forschungsfrage

Verhalten sich Angreifer nach dem Login anders, wenn die Fake-Shell von einem
Sprachmodell gespielt wird (Cowrie-Backend `llm`) statt von Cowries
klassischer Shell?

Die Behandlung ist **diese Umsetzung**: Cowries LLM-Backend in der
eingesetzten Version mit dem Prompt aus `sensor/persona/prompt.md`, dem
gewählten Modell und den Parametern aus Abschnitt 4.5. Die Ergebnisse gelten
für sie, nicht für KI-Shells allgemein.

## 3. Ausgangslage aus Variante A

Seit 2026-09-17 läuft nur A. Diese Zahlen waren vor dem Start bekannt und
haben die Hypothesen geprägt. Konfirmatorisch zählen nur Daten ab dem Start
von B.

| Befund | Wert | Quelle |
|--------|------|--------|
| Sitzungen vom 2026-09-17 bis 2026-10-01 | 65.985 | `/stats/breakdown`, 2026-10-01 |
| davon mit Exec-Befehl | 20.549 | ebd. |
| davon interaktiv | 3, zwei davon eigene Persona-Tests von `127.0.0.1` | ebd., `server/README.md` |
| ohne Befehl | 45.433 | ebd. |
| verschiedene Befehlsfolgen | 64 bei 20.358 Sitzungen mit Befehlen, 99,7 % davon in Kampagnen | `docs/campaigns.md`, 2026-09-30 |
| größtes Werkzeug | 72 % der Sitzungen mit Befehlen, von 43 Quellen | ebd. |
| SSH-Key-Familie | kurz (2 Befehle): 3.219 Sitzungen von 570 Quellen; lang (18 Befehle): 78 Sitzungen, also rund 2,4 % | ebd. |
| Echtheitstests der Shell | rund 115 Befehle, davon 82 Prüfungen, ob ein Systemprogramm ein echtes Binary ist | `run attack --bericht`, 2026-09-29 |

Was daraus folgt:

1. **Interaktive Sitzungen sind zu selten für einen Test.** H1 aus dem
   Bauplan bleibt als Frage stehen, wird aber nur beschrieben.
2. **Fast alles ist Automatik.** Die meisten Bots laufen ein festes Skript.
   Prüfbar ist, ob einige auf die Ausgabe reagieren. „Kein Unterschied“
   braucht dafür eine vorher festgelegte Grenze.
3. **Der erste Exec-Befehl einer Quelle fällt vor jeder Ausgabe.** Bis dahin
   sehen A und B gleich aus: Banner, Host-Keys und Logins sind identisch
   (E-002, E-017). Erst was danach kommt, kann von der Shell abhängen.
4. **Wenige Werkzeuge stellen fast alle Sitzungen.** Gezählt wird deshalb je
   Quelle, und die Primärgröße nimmt nur Quellen, die vor dem Start nie da
   waren.
5. **Kampagnen trennen reagierende Bots über die Varianten**, weil der
   Fingerprint die ganze Befehlsfolge nimmt (`docs/campaigns.md`, „Grenzen“).
   Als Werkzeug einer Quelle gilt deshalb die Normalform ihres ersten Befehls.
6. **Varianten gibt es schon in A.** Die SSH-Key-Familie läuft mal mit 2, mal
   mit 18 Befehlen, obwohl A immer gleich antwortet. Ein Unterschied zeigt
   sich deshalb nur im Anteil der langen Variante.

## 4. Design

### 4.1 Varianten

|                     | A (Kontrolle)                    | B (Behandlung)                       |
|---------------------|----------------------------------|--------------------------------------|
| Shell               | klassisch (`backend shell`)      | Sprachmodell (`backend llm`)         |
| Image               | `cowrie/cowrie:3.0.14`, Digest gepinnt | dasselbe Image plus Patch aus E-041 |
| Port, `sensor_name` | 2222, `hp-a`                     | 2322, `hp-b`                         |

Gleich sind Banner, Host-Keys, `userdb.txt`, Hostname, Persona-Dateien und
`cowrie.cfg` (E-002, E-014, E-017).

Zur Behandlung gehört alles, was das LLM-Backend anders macht. Die Liste
steht in `sensor/persona/persona.md` („Bekannte Unterschiede“). Die
wichtigsten: Antworten kommen vom Modell und langsamer, B merkt sich nur die
letzten zehn Befehle, der Prompt zeigt immer `/`, SFTP und Weiterleitungen
gibt es in B nicht, und Cowrie begrenzt in B die Befehle je Adresse.
Unterschiede ohne Bezug zum Modell gleicht der Patch an: motd und Downloads
(E-041).

### 4.2 Zuteilung

nftables verteilt Port 22 per `jhash` der Quell-IPv4 modulo 2 mit festem
Startwert auf A und B (Schritt 7.4, E-004). Eine Adresse landet immer in
derselben Variante. Das ist kein echter Zufall, aber unabhängig davon, was ein
Angreifer tut. Ob die Zuteilung ausgewogen ist, prüfen N1, N2 und P1
(Abschnitt 7.6).

### 4.3 Zeiträume

- **Vorperiode:** 2026-09-17 bis T0, nur A.
- **T0, Start:** Beginn der ersten Sitzung mit `variant = 'b'`, die nicht
  ausgeschlossen ist (Abschnitt 8), also der erste fremde Zugriff auf B.
- **T1, Ende:** T0 + 42 Tage, verlängerbar nach Abschnitt 10.
- **Aufnahme:** Quellen, deren erster Befehl in [T0, T1 − 24 h) liegt. So hat
  jede Quelle volle 24 Stunden Beobachtung. Für S4 gilt [T0, T1 − 7 Tage).
- **Auswertung:** einmal, spätestens 14 Tage nach T1. Zahlen auf `/lab`
  während der Laufzeit sind Zwischenstände (Abschnitt 9.7).

### 4.4 Analyseeinheit

Die Quelle (`sessions.ip_hash`), weil die Zuteilung je Adresse erfolgt. Für
Größen je Sitzung oder je Aufruf werden ganze Quellen gezogen (Abschnitt 9.2).

### 4.5 Behandlungsparameter

Diese Werte stehen vor dem Start im Start-Eintrag in `docs/decisions.md` und
bleiben während der Laufzeit gleich:

- Cowrie-Version und Image-Digest von A und B, Commit des Patches
- Anbieter, Modell-ID, `temperature`, `max_tokens`
- Commit von `sensor/persona/prompt.md`
- Cowries Begrenzung je Adresse (`rate_limit_requests`, `rate_limit_window`)
- Grenzen des Gateways: Monatsbudget, Aufrufe je Minute, Zeitlimit
- Startwert des `jhash`

Vorgaben dazu:

- **`temperature` niedrig.** Eine echte Shell antwortet auf denselben Befehl
  gleich. Schwankende Antworten wären ein Merkmal von B, das sich mit einem
  Parameter vermeiden lässt.
- **`max_tokens` groß genug** für die längste Datei, die wörtlich im Prompt
  steht. Cowries Standard von 500 Tokens reicht dafür nicht, die feste Ausgabe
  von `dmesg` hat rund 2.600 Zeichen.
- **Begrenzung je Adresse oberhalb der Muster aus der Vorperiode.** Die lange
  Variante der SSH-Key-Familie schickt 18 Befehle in kurzer Folge, Cowries
  Standard sind 20 je Minute und Adresse. Jeder Treffer wird geloggt (V2).
- **Keine Änderung während der Laufzeit** an Persona, Prompt, Modell, Cowrie
  oder Zuteilung. Honeytokens (Phase 8) kommen erst nach dem Ende.

## 5. Voraussetzungen vor dem Start

B startet erst, wenn alle Pflichtpunkte erfüllt sind.

| Nr. | Was | Warum | Prüfung | Pflicht |
|-----|-----|-------|---------|---------|
| V1 | B loggt Exec-Befehle als `cowrie.command.input`, auch wenn die Begrenzung je Adresse greift (Patch, E-041) | Cowries LLM-Backend loggt Befehle nur in interaktiven Sitzungen. Ohne V1 hätten fast alle B-Sitzungen keine Befehle | auf dem Sensor `ssh -p 2322 root@localhost 'uname -a'`: Sitzung mit `variant = 'b'`, `interactive = false` und einem Befehl | ja |
| V2 | Zu jedem Befehl in B genau ein Ereignis `cowrie.llm.response` mit `status` (`ok`, `empty`, `error`, `rate_limited`, `client_gone`), `latency_ms`, `http_status` und `command_index`, der laufenden Nummer des Befehls in seiner Sitzung (ab 1, in der Reihenfolge der `cowrie.command.input`). `client_gone` gilt, wenn der Client bei Eintreffen der Antwort schon weg ist. Der Ingest nimmt das Ereignis an und legt die Felder zusätzlich in einer abgeleiteten Tabelle ab | H3, Ausfallzeiten und K1 bis K3 brauchen es. Antworten können in anderer Reihenfolge eintreffen als die Befehle, etwa bei parallelen Exec-Kanälen; nur `command_index` ordnet sie sicher zu. Roh-Events werden nach 90 Tagen gelöscht | ein Testaufruf liefert `ok` mit Antwortzeit, bei gestopptem Gateway `error`; zwei parallele Exec-Kanäle bekommen die richtige Nummer | ja |
| V3 | Das Gateway beantwortet Budget- und Limit-Stopps mit eigenem HTTP-Status (Vorschlag: 429) | nur so sind sie auf dem Sensor von anderen Fehlern zu trennen | Lasttest aus 7.2: `http_status` 429 im Ereignis | ja |
| V4 | Nach dem Login zeigen A und B dieselbe motd (E-015, E-041) | sonst sieht jede interaktive Sitzung sofort einen Unterschied | Login auf 2222 und 2322 vom Sensor, Ausgabe vergleichen | ja |
| V5 | B lädt Downloads mit `wget` und `curl` wirklich (E-041) | sonst sehen Angreifer an ihren eigenen Servern, dass B nie etwas abholt | Testdownload einer eigenen Datei, etwa von tomkaufmann.dev: `cowrie.session.file_download` in B | empfohlen, sonst Grenze 7 |
| V6 | Vector liest die Logs von B (E-025), das Prüfskript für die Zuteilung aus 7.4 liegt bereit | ohne das gibt es keine Daten von B | Testsitzung auf 2322 kommt in der Datenbank an | ja |
| V7 | Regeln für Echtheitstests in `server/rules/echtheit.yml`, entwickelt nur auf Daten der Vorperiode, mit Tests. Die Auswertung wendet sie selbst an (Abschnitt 7.1), ein Feld in der Datenbank gibt es dafür nicht | H4 braucht eine feste Definition | Tests mit erfundenen Beispielen | für H4 |
| V8 | Selbsttest-Kennung: `SELFTEST_PASSWORD` in der `.env` des Hauptservers, nur Buchstaben und Ziffern, mindestens 16 Zeichen. Jeder eigene Test von außen meldet sich damit an | eigene Sitzungen erkennen (Abschnitt 8) | – | ja |
| V9 | Tag `vorab-b` gesetzt, Start-Eintrag mit den Werten aus Abschnitt 4.5 vorbereitet | Abschnitt 1 | – | ja |

Fehlt V7 beim Start, wird H4 nicht ausgewertet.

## 6. Hypothesen

|    | Aussage | Rolle |
|----|---------|-------|
| H1 | Interaktive Sitzungen haben in B mehr Befehle als in A | explorativ |
| H2 | Exec-Zugriffe: Das Folgeverhalten neuer Quellen unterscheidet sich zwischen B und A um weniger als 5 Prozentpunkte | **primär** |
| H3 | In B geben Exec-Clients bei langsamen Antworten häufiger vor der Antwort auf | sekundär |
| H4 | Nach einem Echtheitstest machen Quellen in B anders weiter als in A | explorativ |

### H1: Interaktive Sitzungen (explorativ)

**Aussage:** In B schicken interaktive Sitzungen mehr Befehle als in A.

**Begründung:** So stand es im Bauplan als Kern des Experiments. In der
Vorperiode kam in 14 Tagen aber nur eine einzige interaktive Sitzung von
außen, für einen Test fehlen die Fälle. Berichtet werden Fallzahlen und I1
bis I3 (Abschnitt 7.5), Intervalle erst ab 20 interaktiven Sitzungen je
Variante.

### H2: Exec-Zugriffe (primär)

**Aussage:** Der Anteil neuer Exec-Quellen, die binnen 24 Stunden nach ihrem
ersten Befehl einen Befehl mit anderer Normalform schicken (M1, Abschnitt
7.2), unterscheidet sich zwischen B und A um weniger als 5 Prozentpunkte
(pp).

**Begründung:** Fast alle Zugriffe sind Skripte mit fester Folge (Abschnitt
3). Eine KI-Shell kann nur Bots beeinflussen, die auf Ausgaben reagieren.
„Kein Unterschied“ lässt sich nicht mit einem nicht signifikanten Test zeigen,
nur mit einer vorher festgelegten Grenze. Die Grenze liegt bei 5 pp: Ein
kleinerer Unterschied im Folgeverhalten von Bots wäre für den Betrieb eines
Honeypots kaum von Belang, und mit der erwarteten Fallzahl ist sie erreichbar
(Abschnitt 10).

**Entscheidung** mit Δ = M1(B) − M1(A):

| 90-%-Intervall von Δ ganz in (−5, +5) pp | 95-%-Intervall schließt 0 aus | Ergebnis |
|------|------|---------|
| ja   | nein | H2 bestätigt: gleichwertig innerhalb ±5 pp |
| ja   | ja   | Unterschied nachweisbar, aber kleiner als 5 pp; H2 bestätigt |
| nein | ja   | Unterschied, H2 widerlegt; Richtung und Größe werden berichtet |
| nein | nein | nicht entschieden |

Das 90-%-Intervall entspricht dem üblichen Äquivalenztest aus zwei einseitigen
Tests auf dem Niveau 5 %.

### H3: Antwortzeit (sekundär)

**Aussage:** In B geben Exec-Clients bei langsamen Antworten häufiger auf,
bevor die Antwort kommt, als bei schnellen Antworten auf denselben Befehl.

**Begründung:** B antwortet langsamer als A (E-008). Die Antwortzeit hängt vom
Anbieter ab und schwankt. Innerhalb desselben Befehls ist die Schwankung
weitgehend Zufall der Anbieterlast, der Vergleich innerhalb eines Befehls ist
deshalb fair. Damit wird die Fassung aus dem Bauplan („längere Antwortzeiten
erhöhen frühe Abbrüche“) messbar.

**Entscheidung:** H3 gilt als bestätigt, wenn das 95-%-Intervall von L1
(Abschnitt 7.4) ganz über 0 liegt, sonst als nicht bestätigt. Gibt es
insgesamt weniger als 50 Abbrüche, wird H3 nur beschrieben.

### H4: Echtheitstests (explorativ)

**Aussage:** Quellen, die prüfen, ob die Shell echt ist, machen danach in B
anders weiter als in A. Die Richtung ist offen.

**Begründung:** In der Vorperiode gab es rund 115 solche Befehle, vermutlich
von wenigen Quellen. Für eine konfirmatorische Aussage reicht das nicht.
Messgröße ist E1 (Abschnitt 7.5), nur mit den Regeln aus V7.

## 7. Messgrößen

### 7.1 Grundbegriffe

| Begriff | Definition |
|---------|------------|
| Quelle | `sessions.ip_hash` |
| neue Quelle | Quelle ohne Sitzung mit `started_at` vor T0 |
| Befehl | Zeile in `commands`, also ein `cowrie.command.input`. Befehle mit leerer Normalform zählen nicht |
| Normalform | Ergebnis von `normalize()` aus `server/app/campaigns.py` im Stand `vorab-b` |
| Reihenfolge | nach `commands.occurred_at`, dann `sessions.id`, dann `commands.sequence` |
| erster Befehl | erster Befehl einer Quelle ab T0 in dieser Reihenfolge, sein Zeitpunkt heißt t_q |
| Exec-Quelle | Quelle, deren erster Befehl in einer Sitzung mit `interactive = false` liegt |
| Werkzeug | Normalform des ersten Befehls einer Quelle |
| Aufruf | ein Ereignis `cowrie.llm.response` in B. Es gehört zu der Zeile in `commands` seiner Sitzung, die nach `occurred_at` und `sequence` an Stelle `command_index` steht; leere Befehle zählen dabei mit |
| Technik | Eintrag in `commands.techniques`, für die Auswertung neu berechnet mit `attack.yml` im Stand `vorab-b` |
| Echtheitstest | Befehl, auf dessen gespeicherten, entschärften Text (`commands.command`) mindestens eine Regel aus `server/rules/echtheit.yml` im Stand `vorab-b` zutrifft. Die Auswertung wendet die Regeln selbst an. Ein Eintrag in `commands.techniques` entsteht nicht, das Feld bleibt ATT&CK vorbehalten |

### 7.2 Primärgröße M1

**Grundgesamtheit:** neue Exec-Quellen mit t_q in [T0, T1 − 24 h), nicht
ausgeschlossen (Abschnitt 8).

**Wert je Quelle:** Y = 1, wenn die Quelle nach ihrem ersten Befehl (in der
Reihenfolge oben) und spätestens bei t_q + 24 h einen Befehl schickt, dessen
Normalform sich von der des ersten Befehls unterscheidet. Sonst Y = 0.

**M1** ist der Anteil der Quellen mit Y = 1, je Variante. Der Effekt ist
Δ = M1(B) − M1(A).

Lesart: Hat die Quelle nach der ersten Antwort mit etwas Neuem
weitergemacht? Wiederholungen desselben Befehls zählen nicht, die erfasst S1.

### 7.3 Sekundärgrößen zu H2

| Nr. | Name | Grundgesamtheit | Wert |
|-----|------|-----------------|------|
| S1 | Folgebefehl | wie M1 | wie M1, aber jeder weitere Befehl zählt, auch eine Wiederholung |
| S2 | Nachladen oder Festsetzen | wie M1, ohne Quellen, deren erster Befehl schon eine Technik aus P trägt | Y = 1, wenn bis t_q + 24 h ein Befehl mit einer Technik aus P = {T1105, T1098, T1098.004, T1053.003} folgt |
| S3 | lange Variante der SSH-Key-Familie | Sitzungen neuer Quellen ab T0, deren Folge (`normalized_sequence()`) mit den ersten beiden Einträgen der Folge von Kampagne `37fa39ae478f` beginnt | Y = 1, wenn die Folge mehr als diese zwei Einträge hat. Vorperiode: rund 2,4 % |
| S4 | Rückkehr | neue Exec-Quellen mit t_q in [T0, T1 − 7 Tage) | Y = 1, wenn eine weitere Sitzung frühestens 1 h und spätestens 7 Tage nach t_q beginnt |
| S5 | Befehle in 24 h | wie M1 | Zahl der Befehle von t_q bis t_q + 24 h, einschließlich des ersten; Mittelwert und Median |

S3 wird je Sitzung gezählt, alle anderen je Quelle. S5 hängt mechanisch an der
Antwortzeit: Wer auf Antworten wartet, schafft in B weniger Befehle. S5 wird
deshalb nur beschrieben.

### 7.4 Größen zu H3

**Grundgesamtheit:** Aufrufe in B zu Befehlen aus Exec-Sitzungen, außerhalb
von Ausfallzeiten, mit `status` `ok`, `empty` oder `client_gone` und
`latency_ms` unter 60.000. Nach 60 Sekunden beendet Cowrie eine Exec-Sitzung
selbst. Spätere Antworten zählen als Zeitüberschreitung, nicht als Abbruch,
und werden getrennt berichtet.

- **Abbruch:** `status = client_gone`.
- **L1:** Für jede Normalform mit mindestens 20 Aufrufen werden die Aufrufe am
  Median ihrer Antwortzeit geteilt; Aufrufe genau auf dem Median zählen zur
  schnellen Hälfte. L1 ist die Abbruchquote der langsamen minus die der
  schnellen Hälfte, gemittelt über die Normalformen und gewichtet mit ihrer
  Zahl an Aufrufen.
- **L2** (beschreibend): Abbruchquote je Viertel der Antwortzeit über alle
  Aufrufe.

### 7.5 Größen zu H1 und H4

| Nr. | Grundgesamtheit | Wert |
|-----|-----------------|------|
| I1 | interaktive Sitzungen ab T0, nicht ausgeschlossen | Zahl der Befehle |
| I2 | wie I1 | Dauer (`sessions.duration_ms`) |
| I3 | wie I1 | Anteil der Sitzungen mit höchstens zwei Befehlen |
| E1 | Quellen ab T0 mit mindestens einem Echtheitstest (Abschnitt 7.1); Zeitpunkt des ersten Tests t_e | Y = 1, wenn bis t_e + 1 h ein Befehl folgt, der kein Echtheitstest ist und dessen Normalform die Quelle bis zu diesem Befehl noch nie geschickt hat |
| E2 | wie M1 | Anteil der Quellen, deren Befehle bis t_q + 24 h einen Echtheitstest enthalten (beschreibend) |

### 7.6 Kontrollen

Kontrollen prüfen, ob Zuteilung, Logging und Behandlung funktionieren. Sie
sind keine Ergebnisse.

| Nr. | Was | Erwartung |
|-----|-----|-----------|
| N1 | Anteil der neuen Quellen in B | 95-%-Intervall enthält 50 % |
| N2 | Werkzeug-Mix der neuen Exec-Quellen: Werkzeuge mit mindestens 20 Quellen einzeln, der Rest als „Sonstige“, Chi-Quadrat-Statistik mit p-Wert per Permutation | kein Unterschied (p nicht unter 0,01), weil der erste Befehl vor jeder Ausgabe fällt |
| N3 | erste Sitzung neuer Quellen mit `cowrie.login.success`: Anteil mit mindestens einem Befehl | gleich in A und B. Ein Fehlbetrag in B deutet auf eine Lücke im Logging (V1) |
| N4 | Quellen mit Sitzungen in A und in B | keine |
| P1 | Placebo: Quellen, die vor und ab T0 Befehle schicken. M1 nur aus der Vorperiode (erster Befehl der Vorperiode, 24 h), verglichen nach der Variante, die sie ab T0 bekommen | 95-%-Intervall von Δ enthält 0 |
| K1 | Anteil der Aufrufe in B mit `status = ok`, außerhalb von Ausfallzeiten | mindestens 95 % |
| K2 | Antwortzeit in B: Median, 90. und 99. Perzentil | wird berichtet |
| K3 | Anteil der Aufrufe mit `rate_limited` oder `http_status` 429 | unter 1 % |

Verfehlt eine Kontrolle ihre Erwartung, wird die Primärauswertung trotzdem
berichtet, mit Warnhinweis und der gefundenen Ursache.

## 8. Ausschlüsse

Ausgeschlossen wird nur, was hier steht.

1. **Eigene Sitzungen**
   - Quellen, deren `ip_hash` dem Hash von `127.0.0.1` oder `::1` entspricht:
     Tests auf dem Sensor (E-024, E-025). Den Hash berechnet `hash_ip()` auf
     dem Hauptserver.
   - Alle Sitzungen einer Quelle, die sich mindestens einmal mit dem
     Selbsttest-Passwort angemeldet hat (`sessions.login_password`, V8).
2. **Ausfallzeiten.** Die Laufzeit wird in Fenster von 15 Minuten geteilt
   (UTC, ab :00). Ein Fenster ist eine Ausfallzeit, wenn
   - von keiner Variante ein Ereignis kommt (Sensor oder Pipeline aus),
   - eine Variante mindestens 20 Sitzungen hat und die andere keine (eine
     Variante aus), oder
   - B mindestens 5 Aufrufe hat und mindestens die Hälfte davon `error`
     (Gateway, Anbieter oder Budget).

   Quellen, deren erster Befehl in einer Ausfallzeit liegt, fallen aus allen
   Größen je Quelle. Aufrufe in Ausfallzeiten fallen aus H3.
3. **Quellen in beiden Varianten** (N4), falls es sie gibt.

**Nicht ausgeschlossen** werden Befehle, auf die B wegen der Begrenzung je
Adresse oder eines Limits im Gateway nicht geantwortet hat (`rate_limited`,
429). Sie gehören zur Behandlung, wie sie läuft. Wie stark das Ergebnis davon
abhängt, zeigen R5 und K3.

Der Bericht nennt je Grund und Variante, wie viele Quellen, Sitzungen und
Aufrufe herausfallen.

## 9. Auswertung

### 9.1 Schätzer

Bei Anteilen die Differenz B − A in Prozentpunkten, zur Einordnung auch das
Verhältnis B / A. Bei S5 die Differenz der Mittelwerte, Mediane nur
beschreibend.

### 9.2 Intervalle

Perzentil-Bootstrap mit 10.000 Wiederholungen. Gezogen werden Quellen, je
Variante getrennt. Bei Größen je Sitzung oder Aufruf (S3, L1, L2, I1 bis I3,
R6) kommt jede gezogene Quelle mit allen ihren Sitzungen und Aufrufen in die
Stichprobe. Startwert des Zufallsgenerators: 20261001.

### 9.3 Entscheidungsregeln

- Nur H2 ist konfirmatorisch, Regel in Abschnitt 6.
- H3 ist sekundär und hat eine eigene Regel (Abschnitt 6).
- Alle anderen Größen werden mit 95-%-Intervall berichtet und heißen
  explorativ. Für sie gibt es keine Korrektur für Mehrfachvergleiche und keine
  Aussage „bestätigt“.

### 9.4 Robustheit

Vorab festgelegt. Sie ändern die Entscheidung zu H2 nicht, stehen aber im
Bericht. Widerspricht eine der Primärauswertung, sagt der Bericht das.

| Nr. | Änderung gegenüber der Primärauswertung |
|-----|-----------------------------------------|
| R1 | geschichtet nach Werkzeug: Δ je Werkzeug mit mindestens 10 Quellen je Variante, der Rest als „Sonstige“, gewichtet mit der Zahl der Quellen |
| R2 | alle Quellen statt nur neue, erster Befehl ab T0 |
| R3 | ohne das Werkzeug mit den meisten Quellen |
| R4 | Fenster 1 h statt 24 h |
| R5 | ohne Quellen, bei denen B auf den ersten Befehl nicht mit `ok` oder `empty` geantwortet hat. Nur in B möglich und damit einseitig |
| R6 | je Sitzung: Anteil der Exec-Sitzungen neuer Quellen mit mindestens zwei verschiedenen Normalformen |

### 9.5 Je Werkzeug

M1 je Werkzeug mit mindestens 20 Quellen, je Variante, mit Intervall
(explorativ). Das zeigt, woher ein Unterschied kommt. Werkzeuge heißen im
Bericht nach Nummer oder Kampagnen-Präfix, nie nach dem Befehlstext.

### 9.6 Vorab-Prüfung der Auswertung (A/A)

Bevor jemand Ergebnisse von B ansieht, läuft das Auswertungsskript aus
Schritt 7.5 auf der Vorperiode. Grundgesamtheit wie bei M1, aber mit Quellen,
deren allererster Befehl in [2026-09-17, T0 − 24 h) liegt. Sie werden 500-mal
zufällig in zwei Hälften geteilt, M1 wird jeweils wie in der Hauptauswertung
berechnet (je 2.000 Bootstrap-Wiederholungen). Erwartet: Die Differenzen
liegen im Mittel bei 0, und mindestens 465 der 500 Intervalle (93 %) enthalten
die 0. Ein richtiges 95-%-Intervall besteht diese Prüfung mit rund 98 %
Wahrscheinlichkeit, eines mit nur 90 % Überdeckung mit rund 1 %. Fällt sie
durch, ist das Skript oder die Methode fehlerhaft und wird korrigiert, bevor B
ausgewertet wird. Das Ergebnis und die mittlere Breite der Intervalle kommen
in `docs/decisions.md`.

### 9.7 Zwischenstände und Abbruch

- `/lab` zeigt während der Laufzeit Zwischenstände mit Intervallen. Sie sind
  beschreibend. Entschieden wird einmal nach T1.
- Kein vorzeitiges Ende wegen eines Ergebnisses.
- Mitschnitte aus B (Schritte 6.3 und 6.4) erscheinen auf `/lab` erst nach
  T1, Mitschnitte aus A sofort. Sonst bekäme jeder, der die Seite beobachtet,
  während der Laufzeit eine Vorlage dafür, wie B antwortet (E-042).
- Ein Abbruch ist nur aus Betriebsgründen möglich (Sicherheit, Missbrauch,
  Kosten). Dann wird bis zum Abbruch ausgewertet und das Ergebnis als
  abgebrochen gekennzeichnet.

## 10. Fallzahl und Laufzeit

Wie genau M1 wird, hängt an der Zahl neuer Exec-Quellen je Variante. Im
ungünstigsten Fall (M1 bei 50 %) hat das Intervall für Δ ungefähr diese halbe
Breite:

| Quellen je Variante | 95 %    | 90 %    |
|---------------------|---------|---------|
| 500                 | ±6,2 pp | ±5,2 pp |
| 1.000               | ±4,4 pp | ±3,7 pp |
| 2.000               | ±3,1 pp | ±2,6 pp |

Für eine Aussage innerhalb ±5 pp braucht es also grob 1.000 Quellen je
Variante. Wie viele neue Exec-Quellen in 42 Tagen kommen, ist offen. In den
ersten 13 Tagen der Vorperiode brachte allein die Kampagne `37fa39ae478f`
570 Quellen. Wie viele Adressen danach neu dazukommen, zeigt erst die
Laufzeit.

**Regel:** Bei T1 wird nur gezählt, wie viele Quellen je Variante in M1
eingehen würden, ohne Y anzusehen. Hat die kleinere Variante weniger als
1.000, läuft das Experiment einmalig 28 Tage länger (T1 = T0 + 70 Tage). Die
Entscheidung steht mit Datum und Zahlen in `docs/decisions.md`. Danach wird
ausgewertet, auch mit weniger Quellen. Reicht die Fallzahl nicht, lautet das
Ergebnis eher „nicht entschieden“ als „gleichwertig“.

**Kosten:** Das Budget des Gateways muss die ganze Laufzeit samt Verlängerung
tragen. Ein vorzeitiges Budgetende erzeugt Ausfallzeiten und kann die
Auswertung kippen.

**Daten:** Roh-Events werden nach 90 Tagen gelöscht (E-022). Status und
Antwortzeit liegen deshalb zusätzlich in einer abgeleiteten Tabelle (V2). N3
braucht `cowrie.login.success` aus den Roh-Events. Die Auswertung läuft
deshalb spätestens 14 Tage nach T1, bei Verlängerung also bis T0 + 84 Tage.

## 11. Bekannte Grenzen

1. **Zuteilung je Adresse, nicht je Akteur.** Botnetze mit vielen Adressen
   landen in beiden Varianten. Beide Varianten haben dieselbe Ziel-IP: Wer die
   Ergebnisse seiner Bots zusammenführt, sieht unter einer Adresse zwei leicht
   verschiedene Maschinen. Das kann selbst ein Erkennungsmerkmal sein und wirkt
   dann auf beide Varianten. Unterschiede werden dadurch eher unterschätzt.
2. **Fast nur Automatik.** Die Aussagen gelten für Bots. Über Menschen sagt
   das Experiment kaum etwas (H1).
3. **Wenige Werkzeuge bestimmen viel.** Die Primärgröße zählt je neuer
   Quelle. Trotzdem hängt das Ergebnis am Werkzeug-Mix des Zeitraums. R1, R3
   und Abschnitt 9.5 zeigen, wie stark.
4. **Die Behandlung ist diese Umsetzung.** Cowries LLM-Backend in der
   eingesetzten Version: festes Verzeichnis `/` im Prompt, Gedächtnis von zehn
   Befehlen, kein SFTP, keine Weiterleitungen, Begrenzung je Adresse, dazu
   Modell und Prompt. Andere KI-Shells können anders wirken.
5. **Die Antwortzeit gehört zur Behandlung.** H2 kann Inhalt und
   Geschwindigkeit der Antworten nicht trennen. H3 beleuchtet nur den Teil
   „Abbruch vor der Antwort“.
6. **Antworten von B schwanken.** Auch mit niedriger `temperature` kann
   derselbe Befehl verschiedene Ausgaben bekommen. Das gehört zur Behandlung.
7. **Downloads.** Mit V5 laden beide Varianten wirklich, aber was der
   Angreifer danach sieht, kommt in B vom Modell. Ohne V5 holt B nie etwas ab,
   und das sehen Angreifer an ihren eigenen Servern.
8. **Erkennbar über `/lab`.** Die öffentliche Liste der letzten Befehle
   verrät den Sensor als Honeypot (E-030). Das betrifft beide Varianten gleich.
   Antworten von B zeigt `/lab` erst nach T1 (Abschnitt 9.7).
9. **Ein Sensor, eine Adresse, ein Zeitraum.** Ein Rechenzentrum in Nürnberg,
   nur IPv4, Herbst 2026. Andere Netze und Zeiten können anders aussehen.
10. **Wechsel am Start.** Quellen aus der Vorperiode, die B bekommen, sehen am
    Start einmal eine andere Shell. Die Primärgröße nimmt deshalb nur neue
    Quellen, R2 zeigt alle.
11. **Kampagnen taugen nicht für A/B.** Der Fingerprint über die ganze Folge
    teilt reagierende Bots über die Varianten (`docs/campaigns.md`). Als
    Werkzeug gilt deshalb der erste Befehl.
12. **Eigene Tests ohne Kennung** lassen sich nicht erkennen. V8 setzt
    Disziplin voraus.
13. **`jhash` ist kein Zufall.** Ausgewogenheit wird geprüft (N1, N2, P1),
    nicht vorausgesetzt.
14. **Viele Größen.** Nur H2 ist konfirmatorisch. Die Intervalle der übrigen
    Größen sind nicht für Mehrfachvergleiche korrigiert.
15. **Die Vorperiode hat die Hypothesen geprägt.** Konfirmatorisch zählen nur
    Daten ab T0. S3 und H4 bauen bewusst auf Befunden aus A auf.

## 12. Datenschutz und Sicherheit

- Ausgewertet wird nur mit `ip_hash`, Land und ASN, nie mit Adressen (E-009,
  E-022). Den Hash von `127.0.0.1` und `::1` berechnet der Hauptserver.
- Ergebnisse enthalten keine Befehle im Klartext. Werkzeuge und Familien
  heißen nach Nummer oder Kampagnen-Präfix.
- In B gehen die Befehle der Angreifer über das Gateway an den LLM-Anbieter,
  ohne die Adresse des Angreifers (`persona.md`, „Einbindung in Cowrie“). Der
  Abschnitt Methodik auf `/lab` nennt das.
- Die Auswertung läuft auf dem Hauptserver. Rohdaten und Berichte mit
  Angreifertext gehören nicht in den Kontext eines Coding-Agenten (CLAUDE.md,
  E-033).

## 13. Verweise

- `AGENTS.md`: Forschungsfrage und harte Regeln
- `docs/decisions.md`: E-002, E-004, E-008, E-009, E-014, E-015, E-017, E-022,
  E-024, E-025, E-030, E-039, E-040, E-041, E-042
- `sensor/persona/persona.md`: Persona und bekannte Unterschiede
- `docs/campaigns.md`: Kampagnen, Normalisierung und ihre Grenzen
