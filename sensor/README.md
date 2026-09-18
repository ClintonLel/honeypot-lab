# sensor: Honeypots auf dem Sensor

Stand Schritt 2.3: `cowrie-a` mit klassischer Shell, Port 22 wird per nftables
auf `cowrie-a` umgeleitet. `cowrie-b`, die Zuteilung per Hash und Vector folgen in
späteren Schritten.

| Pfad im Repo                  | Inhalt                                                           |
|-------------------------------|------------------------------------------------------------------|
| `docker-compose.yml`          | Dienst `cowrie-a` (Image gepinnt, Host-Netzwerk, gehärtet)       |
| `cowrie/cowrie.cfg`           | gemeinsame Cowrie-Konfiguration für A und B                      |
| `cowrie/userdb.txt`           | angenommene Logins (`root` und `admin`)                          |
| `persona/`                    | Persona `bld-ci-03`, siehe `persona/persona.md`                  |
| `scripts/prepare-host.sh`     | Verzeichnisse und SSH-Host-Keys auf dem Sensor anlegen           |
| `scripts/build-fs-pickle.sh`  | `fs.pickle` der Persona auf dem Sensor bauen                     |
| `scripts/cleanup.sh`          | Rohlogs, Mitschnitte und Downloads nach 14 Tagen löschen         |
| `nftables/honeypot.nft`       | Umleitung von Port 22 auf `cowrie-a` (Schritt 2.3)               |
| `systemd/`                    | Aufräumen (Service und Timer) und Laden der nftables-Regel       |
| `tests/`                      | Prüfungen für Persona und Konfiguration                          |

Auf dem Sensor liegt dieser Ordner unter `/opt/honeypot-lab/sensor` und gehört
root. Laufzeitdaten liegen unter `/srv/honeypot`:

| Pfad auf dem Sensor               | Inhalt                                              | Eigentümer |
|-----------------------------------|-----------------------------------------------------|------------|
| `/srv/honeypot/a/var/log/cowrie`  | `cowrie.json` und rotierte Logs von cowrie-a        | 999:999    |
| `/srv/honeypot/a/var/lib/cowrie/tty` | tty-Mitschnitte                                  | 999:999    |
| `/srv/honeypot/a/var/lib/cowrie/downloads` | heruntergeladene und hochgeladene Dateien  | 999:999    |
| `/srv/honeypot/hostkeys`          | SSH-Host-Keys, gemeinsam für A und B                | 999:999    |
| `/srv/honeypot/persona/fs.pickle` | Dateisystem der Persona                             | root       |

## Lokal prüfen

Vor jeder Übertragung auf dem Laptop im Repo-Root:

```bash
python3 sensor/persona/build.py --check
```

```bash
python3 -m pytest sensor/tests
```

Fehlt pytest, installierst du es einmal mit `python3 -m pip install pytest`.

## Auf den Sensor übertragen

Übertragen wird per rsync vom Laptop. Auf dem Sensor liegen so keine
Zugangsdaten zum Repo. Der Sensor steht in `~/.ssh/config` als Host
`hp-sensor` (195.201.127.108, User `tom`, Port 22022, Schlüssel `hp_sensor`).
Mit der nackten IP greift dieser Block nicht, dann fehlen Port und Schlüssel.

Einmalig den Zielordner anlegen:

```bash
ssh hp-sensor 'sudo install -d -m 0755 /opt/honeypot-lab/sensor'
```

Übertragen, auch nach jeder Änderung:

```bash
rsync -rlptv --delete --exclude __pycache__ --rsync-path="sudo rsync" sensor/ hp-sensor:/opt/honeypot-lab/sensor/
```

## Vector einrichten (Schritt 4.2)

Vector liest die Cowrie-Logs und liefert sie an `https://api.tomkaufmann.dev/ingest`.
Er läuft mit derselben ID wie Cowrie (999), sieht nur die Logs und nur lesend,
und veröffentlicht keinen Port.

**1. Token auf den Sensor bringen.** Es ist dasselbe wie auf dem Hauptserver.
Dort auslesen (der Wert gehört in keine Chat-Nachricht und in kein Repo):

```bash
ssh globe 'sudo grep ^INGEST_TOKEN= /opt/honeypot-lab/.env'
```

Auf dem Sensor in `/srv/honeypot/.env` eintragen, Rechte 600, Eigentümer root.
Der Befehl wartet auf die Eingabe: Zeile `INGEST_TOKEN=‹Wert›` einfügen, dann
Strg-D:

```bash
ssh -t hp-sensor 'sudo sh -c "umask 077; cat > /srv/honeypot/.env" && sudo chown root:root /srv/honeypot/.env && sudo chmod 600 /srv/honeypot/.env && sudo ls -l /srv/honeypot/.env'
```

Vector liest das Token nicht aus der Umgebung, sondern aus einer eigenen Datei
(E-026). Sie entsteht aus der `.env`, ohne dass der Wert noch einmal getippt
oder angezeigt wird:

```bash
ssh -t hp-sensor 'sudo sh -c ". /srv/honeypot/.env; umask 077; printf %s \"\$INGEST_TOKEN\" > /srv/honeypot/secrets/ingest_token" && sudo chown 999:999 /srv/honeypot/secrets/ingest_token && sudo chmod 0400 /srv/honeypot/secrets/ingest_token && sudo ls -l /srv/honeypot/secrets/'
```

**2. Verzeichnis für Vector anlegen** (legt `prepare-host.sh` mit an, der
Aufruf ist gefahrlos wiederholbar):

```bash
ssh hp-sensor 'sudo /opt/honeypot-lab/sensor/scripts/prepare-host.sh'
```

**3. Starten:**

```bash
ssh hp-sensor 'cd /opt/honeypot-lab/sensor && sudo docker compose up -d vector && sudo docker compose ps'
```

**4. Nachsehen, ob er liefert:**

```bash
ssh hp-sensor 'sudo docker compose -f /opt/honeypot-lab/sensor/docker-compose.yml logs --tail 30 vector'
```

Erwartet werden Zeilen über die geöffnete Datei und keine Fehler mit `401`
(falsches Token) oder `422` (Format).

Auf dem Hauptserver muss die Zahl der Ereignisse wachsen:

```bash
ssh globe 'cd /opt/honeypot-lab && sudo docker compose -f docker-compose.server.yml exec -T db psql -U honeypot -d honeypot -c "SELECT count(*) AS ereignisse, count(DISTINCT cowrie_session) AS sitzungen FROM events;"'
```

### Wenn Vector Ereignisse verworfen hat

Antwortet die API mit 401 oder 422, gilt der Versuch für Vector als endgültig
gescheitert („Not retriable“): Die Ereignisse sind weg, und die Leseposition
rückt trotzdem vor. Genauso bei einer Antwort mit 200, in der die API alles
abgelehnt hat — das sieht nur das Log der API, Vector bleibt still (E-027):

```bash
ssh globe 'sudo docker logs honeypot-lab-api-1 --since 1h 2>&1 | grep "\"msg\": \"ingest\"" | tail -5'
```

Stehen dort `rejected` und `reasons`, liegt ein Formfehler vor. Nach so einem Fehler den Positionsmerker löschen, damit
Vector den Bestand noch einmal liest. Doppelte Ereignisse erkennt die API am
Inhalts-Hash (E-024), es entstehen also keine Duplikate:

```bash
ssh hp-sensor 'cd /opt/honeypot-lab/sensor && sudo docker compose stop vector && sudo find /srv/honeypot/vector -mindepth 1 -delete && sudo docker compose up -d vector'
```

`find` statt `rm -rf .../*`: Das Sternchen würde die Shell des angemeldeten
Users auflösen, und der darf das Verzeichnis mit Rechten 0700 nicht lesen. Es
bliebe stehen, `rm -f` täte stillschweigend nichts.

## Test: Rotation und Neustart (Schritt 4.2)

Cowrie rotiert `cowrie.json` täglich. Erkennt Vector die Datei am Namen statt
am Inhalt, entstehen dabei Lücken; ohne gemerkte Position liest er nach einem
Neustart alles noch einmal. `scripts/test-vector-rotation.sh` prüft beides in
einem eigenen Verzeichnis unter `/tmp`, mit erfundenen Ereignissen und einer
Datei als Ziel. Die echten Logs und die Datenbank bleiben unberührt.

```bash
ssh hp-sensor 'sudo /opt/honeypot-lab/sensor/scripts/test-vector-rotation.sh'
```

Der Test schreibt 10 Zeilen, rotiert die Datei, trägt 5 weitere Zeilen in die
rotierte und 10 in die neue Datei nach und startet Vector mit demselben
`data_dir` erneut. Erwartet: 25 Zeilen, jede genau einmal.

## Beispiel-Logs für die Tests erzeugen (Schritt 4.1)

`scripts/make-fixtures.py` wählt vollständige Sitzungen aus `cowrie.json` aus
und ersetzt dabei jede Adresse der Beteiligten durch eine aus dem
Dokumentationsbereich. Die Zusammenfassung auf stderr enthält nur Zahlen.

```bash
ssh hp-sensor 'sudo python3 /opt/honeypot-lab/sensor/scripts/make-fixtures.py > /tmp/fixtures.jsonl'
```

```bash
rsync -av hp-sensor:/tmp/fixtures.jsonl server/tests/fixtures/
```

Danach die Zwischendatei auf dem Sensor wieder löschen:

```bash
ssh hp-sensor 'rm -f /tmp/fixtures.jsonl'
```

## Einmalig vorbereiten

Die folgenden Befehle laufen auf dem Sensor.

Verzeichnisse und Host-Keys anlegen. Das Skript gibt am Ende die Fingerprints
der Honeypot-Host-Keys aus:

```bash
sudo /opt/honeypot-lab/sensor/scripts/prepare-host.sh
```

`fs.pickle` bauen. Das lädt Pakete von snapshot.debian.org und dauert einige
Minuten. Nach Änderungen an `persona/rootfs/` oder `persona/honeyfs/` wird
neu gebaut:

```bash
sudo /opt/honeypot-lab/sensor/scripts/build-fs-pickle.sh
```

## cowrie-a starten

```bash
cd /opt/honeypot-lab/sensor
```

Konfiguration prüfen:

```bash
sudo docker compose config --quiet
```

Starten:

```bash
sudo docker compose up -d cowrie-a
```

Startmeldungen ansehen:

```bash
sudo docker compose logs --tail 50 cowrie-a
```

Nach Änderungen an Konfiguration, Persona oder `fs.pickle` neu starten:

```bash
sudo docker compose up -d --force-recreate cowrie-a
```

## Aufräumen einrichten

```bash
sudo install -m 0644 /opt/honeypot-lab/sensor/systemd/honeypot-cleanup.service /opt/honeypot-lab/sensor/systemd/honeypot-cleanup.timer /etc/systemd/system/
```

```bash
sudo systemctl daemon-reload
```

```bash
sudo systemctl enable --now honeypot-cleanup.timer
```

Timer prüfen:

```bash
systemctl list-timers honeypot-cleanup.timer
```

Einmal von Hand laufen lassen und das Ergebnis ansehen:

```bash
sudo systemctl start honeypot-cleanup.service
```

```bash
journalctl -u honeypot-cleanup.service -n 10 --no-pager
```

## Testen (Abnahme Schritt 2.2)

Auf dem Sensor anmelden. Jedes Passwort außer `root` und `123456` funktioniert.
Der angezeigte Host-Key muss zu den Fingerprints aus `prepare-host.sh` passen.

```bash
ssh -p 2222 -o UserKnownHostsFile=/dev/null root@localhost
```

In der Sitzung zeigt sich die Persona, wenn:

- der Prompt `root@bld-ci-03:~#` lautet und die motd mit `bld-ci-03 - CI build worker` beginnt,
- `uname -a` den Kernel `6.12.107+deb13-amd64` zeigt,
- `cat /etc/os-release` Debian 13 (trixie) meldet,
- `ls -la /opt/ci-agent /srv/build/artifacts` die Dateien aus `persona.md` zeigt,
- `cat /proc/cpuinfo | grep name` zweimal `Common KVM processor` ausgibt,
- `df -h`, `lscpu` und `ps aux` zur Persona passen,
- `ssh -V` OpenSSH 10.0p2 meldet.

Mit `exit` abmelden. Ein Login mit einem anderen Benutzernamen muss scheitern:

```bash
ssh -p 2222 -o UserKnownHostsFile=/dev/null ubuntu@localhost
```

Das Log muss wachsen, mit Events wie `cowrie.login.success` und `cowrie.command.input`:

```bash
sudo tail -n 5 /srv/honeypot/a/var/log/cowrie/cowrie.json
```

Speicher des echten Sensors ablesen. `free` zeigt in cowrie-a diesen Wert.
Weicht er um mehr als 1 % von 3911744 kB ab, müssen `proc/meminfo`, `top` und der
Prompt angepasst werden:

```bash
grep MemTotal /proc/meminfo
```

## Port 22 umleiten (Schritt 2.3)

Eine eigene nftables-Tabelle `ip honeypot` leitet eingehende Verbindungen auf
Port 22 nach 2222 zu `cowrie-a` um. Die Tabelle ersetzt sich beim Laden selbst,
`flush ruleset` kommt nicht vor, Dockers Regeln bleiben also unberührt.
`nftables.service` bleibt aus, denn dessen `/etc/nftables.conf` würde alle Regeln
löschen. Stattdessen lädt `honeypot-nftables.service` die Regel beim Booten.

Einrichten auf dem Sensor, nach dem Übertragen von `sensor/`:

```bash
sudo nft -c -f /opt/honeypot-lab/sensor/nftables/honeypot.nft
```

```bash
sudo install -d -m 0755 /etc/nftables.d
```

```bash
sudo install -m 0644 /opt/honeypot-lab/sensor/nftables/honeypot.nft /etc/nftables.d/honeypot.nft
```

```bash
sudo install -m 0644 /opt/honeypot-lab/sensor/systemd/honeypot-nftables.service /etc/systemd/system/
```

```bash
sudo systemctl daemon-reload
```

```bash
sudo systemctl enable --now honeypot-nftables.service
```

Nach einer Änderung an der Regel die Datei erneut nach `/etc/nftables.d/`
kopieren und neu laden:

```bash
sudo systemctl reload honeypot-nftables.service
```

Umleitung vorübergehend abschalten. Das entfernt nur die Tabelle
`ip honeypot`:

```bash
sudo systemctl stop honeypot-nftables.service
```

### Testanleitung (Abnahme Schritt 2.3)

**1. Regel anzeigen** (auf dem Sensor). Erwartet wird die Kette `prerouting` mit
`tcp dport 22 redirect to :2222`:

```bash
sudo nft list table ip honeypot
```

**2. Verbindung auf Port 22 von außen** (auf dem Laptop). Der Host-Key ist der
Honeypot-Key aus `prepare-host.sh`, nicht der echte Key des Sensors. Er gehört
deshalb nicht in `known_hosts`. Jedes Passwort außer `root` und `123456`
funktioniert, danach erscheinen motd und Prompt `root@bld-ci-03:~#`:

```bash
ssh -o UserKnownHostsFile=/dev/null root@SENSOR_IP
```

Im Log muss die Sitzung mit `dst_port` 2222 und deiner eigenen IP als `src_ip`
auftauchen (auf dem Sensor):

```bash
sudo tail -n 5 /srv/honeypot/a/var/log/cowrie/cowrie.json
```

**3. Admin-Zugang auf 22022 weiterhin erreichbar** (auf dem Laptop):

```bash
ssh -i ~/.ssh/hp_sensor -p 22022 tom@SENSOR_IP sudo nft list tables
```

**4. Verhalten nach einem Neustart.** Sensor neu starten:

```bash
ssh -i ~/.ssh/hp_sensor -p 22022 tom@SENSOR_IP sudo systemctl reboot
```

Nach etwa 30 Sekunden müssen Unit und Container wieder laufen:

```bash
ssh -i ~/.ssh/hp_sensor -p 22022 tom@SENSOR_IP "systemctl is-active honeypot-nftables.service; sudo docker ps --format '{{.Names}} {{.Status}}'"
```

Danach Test 1 bis 3 wiederholen.

## Hinweise

- **Port 2222:** Er ist von außen nicht direkt erreichbar, weil die
  Hetzner-Firewall ihn nicht öffnet. Angreifer erreichen Cowrie nur über die
  Umleitung von Port 22.
- **Schreibgeschütztes Dateisystem:** `cowrie-a` läuft mit `read_only: true`.
  Bricht der Start mit einem Fehler zu einem schreibgeschützten Pfad ab, zeig mir
  die Ausgabe von `docker compose logs`.
- **Kein Crash-Reporter:** Cowrie 3.0.14 hat keinen, es gibt also nichts
  abzuschalten. `cowrie.cfg.dist` und `userdb.example` stecken im Image selbst.
  Das eingebundene `etc` enthält deshalb nur unsere Abweichungen.
- **`userdb.txt` nur ASCII:** Cowrie liest die Datei als ASCII. Ein Umlaut, auch
  in einem Kommentar, lässt jeden Login scheitern.
- **uutils-coreutils:** Ubuntu 26.04 bringt die Rust-coreutils mit. Deren
  `install -o/-g` nimmt keine numerischen IDs ohne passenden Host-User an. Die
  Skripte setzen Eigentümer deshalb mit `chown`.
- **Cowries eigene Befehle:** Kurzformen wie `head -4` kennt Cowrie nicht, nur
  `head -n 4`. Beim Testen deshalb die lange Form nutzen.
- **Erster Test am 2026-09-17:** Login, Persona, Logins, exec mit dem
  OpenSSH-Client, wachsendes `cowrie.json` und Aufräum-Timer waren in Ordnung.
  Nach Schritt 2.3 landete `ssh root@SENSOR_IP` von außen in Cowrie, auch nach
  einem Neustart. Port 22022 blieb erreichbar, und Port 2222 war von außen zu.
  paramiko meldet bei exec „Channel closed“, weil Cowrie den Kanal vor der
  Bestätigung schließt. OpenSSH stört das nicht.
