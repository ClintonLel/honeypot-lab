# Abuse-Meldungen zum Sensor

Vorlage und Checkliste für Abuse-Meldungen, die Hetzner zum Sensor
`hp-sensor-01` weiterleitet. Erst die Checkliste abarbeiten, dann antworten.
Antworten nur mit Aussagen, die die Prüfung bestätigt hat.

## Was der Sensor tut und was nicht

Diese Punkte stützen die Antwort. Stimmt einer davon nicht mehr, muss die
Vorlage angepasst werden.

- **Cowrie:** Auf Port 22 läuft ein Forschungs-Honeypot. Er emuliert eine Shell,
  Befehle von Angreifern werden nicht auf dem System ausgeführt.
- **Weiterleitungen:** `forward_redirect` und `forward_tunnel` sind aus.
  SSH-Weiterleitungen werden nur protokolliert, nie ausgeführt. Telnet ist aus.
- **Keine Angriffe:** Der Sensor scannt nicht und greift nichts an.
- **Ausgehende Verbindungen:** Updates, später Vector zum eigenen Hauptserver,
  und Downloads. Verlangt ein Angreifer per `wget` oder `curl` eine Datei, lädt
  cowrie-a sie zur Analyse herunter (höchstens 10 MB, keine privaten Adressen).
- **Logs:** `cowrie.json` mit Zeitstempeln in UTC, 14 Tage aufbewahrt.

## Checkliste bei einer Meldung

1. **Meldung lesen:** Zeitpunkt (in UTC umrechnen), gemeldete IP und Ports, Art
   des Vorwurfs (Scan, Brute Force, Malware, Spam) und die Antwortfrist notieren.
2. **Laufende ausgehende Verbindungen prüfen.** Normal sind Verbindungen von
   Port 22022 (Admin) und 2222 (Honeypot) sowie kurze Downloads:

   ```bash
   sudo ss -tnp state established | grep -v -e ':22022 ' -e ':2222 '
   ```

3. **Konfiguration bestätigen.** Unter `[ssh]` müssen `forward_redirect` und
   `forward_tunnel` `false` sein, unter `[telnet]` muss `enabled` `false` sein:

   ```bash
   grep -E '^\[|^(forward_redirect|forward_tunnel|enabled) ' /opt/honeypot-lab/sensor/cowrie/cowrie.cfg
   ```

4. **Log für den gemeldeten Zeitraum lesen.** `‹JJJJ-MM-TTTHH›` durch Datum und
   Stunde ersetzen. `direct-tcpip` zeigt Weiterleitungsversuche (nur
   protokolliert), `file_download` zeigt Downloads, die der Sensor ausgeführt
   hat:

   ```bash
   sudo grep '"timestamp":"‹JJJJ-MM-TTTHH›' /srv/honeypot/a/var/log/cowrie/cowrie.json | grep -E 'direct-tcpip|file_download'
   ```

5. **Host auf Kompromittierung prüfen:** unbekannte Prozesse, Logins auf 22022,
   laufende Container:

   ```bash
   ps aux --sort=-%cpu | head -n 15
   ```

   ```bash
   sudo journalctl -u ssh --since "7 days ago" --no-pager | grep Accepted
   ```

   ```bash
   sudo docker ps --format '{{.Names}} {{.Image}} {{.Status}}'
   ```

6. **Bei begründetem Verdacht sofort stoppen**, Logs bleiben erhalten. Honeypot
   anhalten:

   ```bash
   cd /opt/honeypot-lab/sensor && sudo docker compose stop
   ```

   Umleitung von Port 22 entfernen:

   ```bash
   sudo systemctl stop honeypot-nftables.service
   ```

   Ist der Host selbst kompromittiert, den Server in der Hetzner Console
   ausschalten und aus dem Repo neu aufbauen (E-001).
7. **Antworten** innerhalb der Frist, mit der passenden Vorlage unten. Bestätigt
   die Prüfung einen echten Missbrauch, das offen sagen und die ergriffenen
   Maßnahmen nennen.
8. **Festhalten:** Datum, Vorwurf, Ergebnis und Maßnahmen kurz in
   `docs/decisions.md` eintragen, wenn sich am Betrieb etwas ändert.

## Vorlage Deutsch

> Guten Tag,
>
> vielen Dank für Ihre Meldung zu ‹SENSOR_IP› vom ‹DATUM›.
>
> Auf diesem Server läuft ein Forschungs-Honeypot (Cowrie) für eine Studie zum
> Verhalten von Angreifern nach einem SSH-Login. Die Shell ist emuliert.
> Befehle von Angreifern werden nicht auf dem System ausgeführt.
>
> Wir haben die Meldung geprüft:
>
> - Der Server führt keine Scans oder Angriffe aus. SSH-Weiterleitungen
>   (Port-Forwarding und Tunnel) sind deaktiviert, entsprechende Anfragen
>   werden nur protokolliert. Telnet ist deaktiviert.
> - ‹ERGEBNIS DER PRÜFUNG, z.B.: Im gemeldeten Zeitraum gab es keine ausgehende
>   Verbindung zu der genannten Adresse.›
> - Protokolle mit Zeitstempeln (UTC) liegen für diesen Zeitraum vor und können
>   bei Bedarf bereitgestellt werden.
>
> ‹OPTIONAL: Ergriffene Maßnahmen›
>
> Ansprechpartner: ‹NAME›, ‹E-MAIL›
>
> Mit freundlichen Grüßen
> ‹NAME›

## Vorlage Englisch

> Hello,
>
> thank you for your report regarding ‹SENSOR_IP› from ‹DATE›.
>
> This server runs a research honeypot (Cowrie) for a study of attacker behaviour
> after an SSH login. The shell is emulated. Commands entered by attackers are
> not executed on the system.
>
> We have reviewed the report:
>
> - The server does not perform scans or attacks. SSH forwarding (port
>   forwarding and tunnels) is disabled, such requests are only logged. Telnet
>   is disabled.
> - ‹RESULT OF THE REVIEW, e.g.: During the reported period there was no
>   outgoing connection to the address mentioned.›
> - Logs with timestamps (UTC) are available for this period and can be
>   provided on request.
>
> ‹OPTIONAL: Actions taken›
>
> Contact: ‹NAME›, ‹EMAIL›
>
> Kind regards
> ‹NAME›
