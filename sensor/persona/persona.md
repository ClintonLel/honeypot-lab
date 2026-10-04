# Persona: bld-ci-03

Stand: 2026-09-17, abgeglichen mit Cowrie 3.0.14.

Diese Datei beschreibt die Maschine, die beide Honeypot-Varianten spielen. Alle
anderen Dateien in diesem Ordner setzen sie um:

| Datei/Ordner          | Wofür                                                           | Genutzt von           |
|-----------------------|-----------------------------------------------------------------|-----------------------|
| `honeyfs/`            | Dateiinhalte (`[honeypot] contents_path`)                       | cowrie-a und cowrie-b |
| `txtcmds/`            | feste Befehlsausgaben (`[honeypot] txtcmds_path`)               | cowrie-a              |
| `ps.txt`              | Prozessliste, Quelle für `cmdoutput.json` und den Prompt        | –                     |
| `cmdoutput.json`      | Prozessliste für `ps` (`[shell] processes`), erzeugt            | cowrie-a              |
| `prompt.template.md`  | Text des System-Prompts mit Platzhaltern für die Dateien        | –                     |
| `prompt.md`           | System-Prompt des LLM-Backends (`[llm] system_prompt`), erzeugt | cowrie-b              |
| `rootfs/`             | Debian-13-Baum als Vorlage für `fs.pickle` (`[shell] filesystem`) | cowrie-a            |
| `build.py`            | erzeugt `prompt.md`, `cmdoutput.json`, `txtcmds/usr/bin/mount` und `txtcmds/usr/sbin/lsmod` | – |

Erzeugte Dateien nie von Hand ändern. Nach jeder Änderung an den Quellen:

```bash
python3 sensor/persona/build.py
```

Die Tests in `sensor/tests/` prüfen, dass alles zusammenpasst. Die Persona
gehört zur Methode. Sobald Variante B Daten erhebt, gilt jede Änderung für beide
Varianten gleichzeitig und steht mit Datum in `docs/decisions.md`, etwa
Honeytokens aus Schritt 8.1.

## Namensregel

AGENTS.md verbietet reale Firmen-, Personen- und Markennamen in der Persona.
Umgesetzt ist die Regel so:

- **Frei erfunden:** Organisation, Rollen, Accounts, Hostnamen, Domain
  (`build.internal`, `.internal` ist für private Netze reserviert), Projekte,
  Artefakte, der Agent `ci-agent` und alle Tokens. Es gibt keinen
  Firmennamen, nur ein „build infrastructure team“.
- **Ausnahme:** Technische Kennungen, die jede Debian-VM ohnehin zeigt, bleiben
  drin. Dazu gehören Debian/GNU/Linux mit den URLs in `os-release`, die
  Kernel-Signatur in `/proc/version`, OpenSSH, OpenSSL, QEMU/KVM und EDK II in
  `dmesg` sowie die CPU-Vendor-ID `GenuineIntel`. Ohne sie wirkt die Maschine
  sofort unecht.
- **Bewusst vermieden:** Produkt- und Anbieternamen wie CI-Systeme,
  Container-Runtimes, Cloud-Anbieter und Chat-Tools. Die CPU heißt „Common KVM
  processor“, nicht nach einem Prozessormodell.

Die Auslegung gilt, solange die Abnahme von Schritt 2.1 erfüllt ist:
`persona.md` beschreibt die Maschine vollständig, und `honeyfs/` und
`prompt.md` passen zueinander.

## Steckbrief

| Merkmal          | Wert                                                                        |
|------------------|-----------------------------------------------------------------------------|
| Hostname / FQDN  | `bld-ci-03` / `bld-ci-03.build.internal`                                    |
| Rolle            | CI-Build-Worker im Pool `linux-amd64`, einer von vier (`bld-ci-01` bis `-04`) |
| Betriebssystem   | Debian GNU/Linux 13.7 (trixie), x86_64, installiert Februar 2026            |
| Kernel           | `6.12.107+deb13-amd64`, `#1 SMP PREEMPT_DYNAMIC Debian 6.12.107-1 (2026-08-29)` |
| SSH-Banner       | `SSH-2.0-OpenSSH_10.0p2 Debian-7+deb13u4`                                   |
| `ssh -V`         | `OpenSSH_10.0p2 Debian-7+deb13u4, OpenSSL 3.5.7 9 Jun 2026`                 |
| Letzter Boot     | 2026-09-01 03:02 UTC (monatlicher Kernel-Neustart, erster Dienstag)         |
| Hardware         | KVM-VM, 2 vCPU („Common KVM processor“), 4 GB RAM (`MemTotal` 3911744 kB), kein Swap, 40 GB Disk (`/dev/vda1`, 61 % belegt) |
| Netz             | `eth0`: öffentliche IP des Sensors, `eth1`: `10.20.4.13/16` (Build-Netz)    |
| Interne Hosts    | `git.build.internal` 10.20.1.10, `ci.build.internal` 10.20.1.20, `store-01.build.internal` 10.20.1.30, SSH-Gateway 10.20.0.5 |
| DNS              | 10.20.0.53, 10.20.0.54, Suchdomain `build.internal`                         |
| Zeitzone, Locale | `Etc/UTC`, `C.UTF-8`                                                        |
| Software         | bash 5.2.37, sudo 1.9.16p2, git 2.47.3, gcc 14.2.0, cmake 3.31.6, make 4.4.1, python3 3.13.5, systemd 257.13, rsync, curl, wget, ccache |
| Nicht vorhanden  | Container-Runtimes, Web-, Datenbank- und Mailserver, Toolchains außer C, C++ und Python |

Die Versionen entsprechen dem Paketstand von Debian 13 am 2026-09-17. Die
Hardware entspricht absichtlich dem echten Sensor (CX23). Cowries `free` liest
nämlich das echte `/proc/meminfo` des Hosts.

## Nutzer

| Account   | UID  | Gruppen                            | Zweck                                   |
|-----------|------|------------------------------------|-----------------------------------------|
| `root`    | 0    | root                               | keine Crontab, Home nur mit `.bashrc` und `.profile` |
| `admin`   | 1000 | admin, sudo, adm, systemd-journal  | Betreuung, sudo ohne Passwort           |
| `builder` | 1001 | builder                            | führt `ci-agent` aus                    |
| `release` | 1002 | release, builder                   | führt `artifact-sync` aus               |

In `/etc/shadow` sind alle Passwörter gesperrt, laut Persona läuft die Anmeldung
nur per Key. Cowrie nimmt trotzdem Passwörter an (`sensor/cowrie/userdb.txt`,
gleich für beide Varianten). `root` und `admin` kommen mit jedem Passwort
hinein, außer mit dem eigenen Benutzernamen und `123456`. Andere Benutzernamen
werden abgewiesen.

## Dienste

- **systemd-Units:** `ssh`, `cron`, `ci-agent.service` (User builder),
  `artifact-sync.timer` alle 15 Minuten (User release, rsync nach store-01),
  `unattended-upgrades`, `systemd-journald`, `-logind`, `-timesyncd`, `-udevd`,
  `dbus`, `getty@tty1`, `serial-getty@ttyS0`
- **Cron:** `/etc/cron.d/build-cleanup` löscht um 02:30 Workspaces, die älter als
  7 Tage sind
- **Prozessliste:** `ps.txt` im Format von `ps aux`, dazu `top` in
  `txtcmds/usr/bin/top` mit denselben Prozessen

## Verzeichnisse

```text
/opt/ci-agent/                 root:root 755
  bin/ci-agent                 755, Python-Launcher
  etc/agent.ini                640 root:builder
  venv/                        Python-Umgebung mit Paket ci_agent
  README.txt, VERSION (2.14.3)
/srv/build/                    builder:builder 755
  workspace/job-48211, job-48213, job-48217   Git-Checkouts mit src/ und build/
  cache/ccache/0 bis f, cache/pip
  artifacts/                   builder:release 2775
    svc-ingest-1.42.0-linux-amd64.tar.gz (38M)
    tool-cfgcheck-0.7.2-linux-amd64.tar.gz (4.1M)
/var/log/ci-agent/agent.log    builder:adm 640
/home/admin/                   .bash_history, .bash_logout, .bashrc, .profile, runbook.txt
/home/builder/                 .bash_logout, .bashrc, .cache/, .gitconfig, .profile
/home/release/                 .bash_logout, .bashrc, .profile, .ssh/config
```

Dieser Baum entsteht in `rootfs/Dockerfile` samt Rechten und Zeitstempeln.

## Dateien in honeyfs

| Bereich     | Dateien                                                                         |
|-------------|---------------------------------------------------------------------------------|
| Identität   | `etc/hostname`, `etc/hosts`, `etc/issue`, `etc/issue.net`, `etc/motd`, `etc/debian_version`, `usr/lib/os-release`, `etc/resolv.conf` |
| Kernel, VM  | `proc/version`, `proc/cpuinfo`, `proc/meminfo`, `proc/modules`, `proc/mounts`   |
| Accounts    | `etc/passwd`, `etc/group`, `etc/shadow`, `etc/sudoers.d/90-admin`               |
| Dienste     | `etc/systemd/system/ci-agent.service`, `artifact-sync.service`, `artifact-sync.timer`, `etc/cron.d/build-cleanup` |
| Anwendungen | `opt/ci-agent/README.txt`, `VERSION`, `bin/ci-agent`, `etc/agent.ini`           |
| Home        | `home/admin/.bash_history`, `home/admin/runbook.txt`, `home/builder/.gitconfig`, `home/release/.ssh/config` |

- `etc/issue.net` ist absichtlich leer, damit es kein Banner vor dem Login
  gibt (siehe „Banner“).
- `os-release` liegt unter `usr/lib/`, weil `/etc/os-release` im Dateisystem ein
  Link ist. Cowrie übernimmt Inhalte nur für echte Dateien.
- `registration_token` in `agent.ini` ist ein erfundener Köder ohne Funktion.
  Andere Tokens, Schlüssel oder Passwort-Hashes gibt es nicht.
- Keine Datei enthält geschweifte Klammern (siehe „Einbindung in Cowrie“).

## Feste Befehlsausgaben

Cowrie sucht feste Ausgaben unter dem aufgelösten Pfad des Befehls, in Debian 13
also meist unter `usr/bin/`. Die mitgelieferten Dateien unter `bin/` greifen
dort nicht mehr, und einige waren falsch.

| Datei in `txtcmds/` | Inhalt                                                  | Im Prompt       |
|---------------------|---------------------------------------------------------|-----------------|
| `usr/bin/df`        | Ausgabe von `df -h`                                     | wörtlich        |
| `usr/bin/dmesg`     | Anfang des Boot-Logs                                    | wörtlich        |
| `usr/bin/lscpu`     | 2 vCPU, KVM                                             | wörtlich        |
| `usr/bin/nproc`     | `2`                                                     | wörtlich        |
| `usr/bin/top`       | Momentaufnahme wie `top -bn1`                           | wörtlich        |
| `usr/bin/mount`     | erzeugt aus `proc/mounts`                               | als Regel       |
| `usr/sbin/lsmod`    | erzeugt aus `proc/modules`                              | als Regel       |
| `usr/bin/getconf`   | `64` (Cowrie gab `32` aus)                              | nein            |
| `usr/bin/nano`      | Terminal-Fehler (Cowrie gab eine vim-Meldung aus)       | nein            |
| `usr/bin/stty`, `usr/bin/sync` | keine Ausgabe                                | nein            |

## Einbindung in Cowrie

Die Werte stehen in `sensor/cowrie/cowrie.cfg` und gelten für cowrie-a und
cowrie-b gleich. `sensor/tests/test_cowrie_config.py` prüft sie gegen diese
Persona.

| Abschnitt    | Option                | Wert                                                   |
|--------------|-----------------------|--------------------------------------------------------|
| `[honeypot]` | `hostname`            | `bld-ci-03`                                            |
| `[honeypot]` | `contents_path`       | `/cowrie/persona/honeyfs`                              |
| `[honeypot]` | `txtcmds_path`        | `/cowrie/persona/txtcmds`                              |
| `[shell]`    | `filesystem`          | `/cowrie/fs.pickle`, gebaut von `sensor/scripts/build-fs-pickle.sh` |
| `[shell]`    | `processes`           | `/cowrie/persona/cmdoutput.json`                       |
| `[shell]`    | `kernel_version`      | `6.12.107+deb13-amd64`                                 |
| `[shell]`    | `kernel_build_string` | `#1 SMP PREEMPT_DYNAMIC Debian 6.12.107-1 (2026-08-29)` |
| `[shell]`    | `ssh_version`         | `OpenSSH_10.0p2 Debian-7+deb13u4, OpenSSL 3.5.7 9 Jun 2026` |
| `[ssh]`      | `version`             | `SSH-2.0-OpenSSH_10.0p2 Debian-7+deb13u4`              |

- **`contents_path` auch für cowrie-b:** Cowrie liest `etc/issue.net` für
  das Banner vor dem Login in beiden Varianten. cowrie-b bekommt denselben
  honeyfs-Ordner, sonst greift dort der Standardinhalt.
- **Nur cowrie-b:** `prompt.md` wird zu `[llm] system_prompt` und zu
  `system_prompt_exec`, dem Prompt für Befehle ohne interaktive Shell. Am
  besten übergibt man ihn als Umgebungsvariable `COWRIE_LLM_SYSTEM_PROMPT`
  (bzw. `_EXEC`). In `cowrie.cfg` würde configparser die Einrückungen
  entfernen.
- **Klammern im Prompt:** Cowrie setzt den Prompt per `str.format_map` ein.
  Deshalb enthält `prompt.md` nur die Platzhalter `{ip}` und `{ip6}` (die
  eigenen IPs des Sensors) und sonst keine geschweiften Klammern. `build.py`
  bricht ab, wenn andere Felder auftauchen. Die Angreifer-IP (`{client_ip}`)
  wird bewusst nicht an den LLM-Anbieter gegeben.
- **Automatische Ergänzungen:** Cowrie hängt selbst einen Schutz gegen
  Prompt-Injection sowie Hostname, User und Arbeitsverzeichnis an.
- **Was beim Modell ankommt (E-045):** Bei Exec trennt das Gateway den Befehl
  vom System-Prompt und schickt ihn als user-Nachricht, wie in einer
  interaktiven Sitzung. Der System-Prompt ist dadurch in jeder Anfrage
  gleich. Anbieter ist Google (Gemini-API, bezahlte Stufe).
- **Größe:** Der Prompt hat rund 29.600 Zeichen (ca. 7.400 Tokens) und geht bei
  jedem Befehl mit (Entscheidung siehe „Prompt-Größe“).

## Banner

- **Vor dem Login: kein Banner.** Cowrie schickt `etc/issue.net` nur, wenn die
  Datei nicht leer ist. Ein echtes Debian zeigt standardmäßig ebenfalls kein
  Banner. Ein Warnhinweis würde gerade Menschen abschrecken, und ihre
  interaktiven Sitzungen sind für die Forschungsfrage am wertvollsten. Außerdem
  sieht ein leeres Banner vor der Anmeldung weniger von der Persona.
- **Nach dem Login: die motd aus `etc/motd`.** cowrie-a zeigt sie von
  Haus aus, cowrie-b seit dem Patch statt des fest eingebauten `Welcome to
  bld-ci-03` (E-041, E-044). Beide schreiben dieselben Bytes; das prüfen die
  CI (Job `cowrie-b`) und das Prüfskript auf dem Sensor.

## Prompt-Größe

Der Prompt bleibt vollständig (E-015). Mit den festen Befehlsausgaben aus
Schritt 2.2 sind das rund 7.400 Tokens pro Befehl:

- **Wörtlicher Inhalt:** Nur so gibt cowrie-b bei `cat` und bei den typischen
  Erkundungsbefehlen denselben Text aus wie cowrie-a. Das gilt besonders für die
  Dateien, die Bots am häufigsten lesen (`/proc/cpuinfo`, `/etc/passwd`,
  `/etc/os-release`), und für `lscpu`, `nproc`, `df -h` und `top`.
- **Nicht kürzbar:** Kürzen hieße, honeyfs-Dateien oder feste Ausgaben
  wegzulassen. Dann zeigt cowrie-a wieder Cowries alte Standardinhalte (User
  `phil`, Debian 12, Kernel von 2009).
- **Kosten:** Der Prompt ist fast vollständig gleichbleibend. Die eigenen IPs
  sind pro Sensor fest, und Cowrie hängt die wechselnden Angaben ans Ende. Viele
  Anbieter speichern so einen gleichbleibenden Anfang zwischen und berechnen
  ihn günstiger. Das Gateway (Schritt 7.2) sollte das nutzen und die
  zwischengespeicherten Tokens mitloggen.
- **Latenz:** Ein langer Prompt kann die Antwortzeit von cowrie-b erhöhen. Das
  Gateway misst die Latenz ohnehin (`llm_usage`). Hypothese H3 in
  `docs/method.md` behandelt sie.

## Bekannte Unterschiede zwischen den Varianten

Diese Unterschiede entstehen durch Cowrie und nicht durch die Persona. Sie
gehören in die Methodik.

| Stelle                   | cowrie-a (Shell)                            | cowrie-b (LLM)                                         |
|--------------------------|---------------------------------------------|--------------------------------------------------------|
| Nach dem Login           | Inhalt von `etc/motd`                       | gleich, seit dem Patch (E-041, E-044); ohne Patch fest `Welcome to bld-ci-03` |
| Start-Verzeichnis        | Home des Users                              | `/`                                                    |
| Verzeichnis im Prompt    | folgt `cd`                                  | bleibt immer `/`, Cowrie setzt es nie neu              |
| Exec-Befehle im Log      | `cowrie.command.input`                      | gleich, seit dem Patch (E-041, E-044); dazu je Befehl `cowrie.llm.response` |
| Exec mit EOF gleich nach dem Befehl | Ausgabe                          | gleich, seit dem Patch; ohne Patch keine Ausgabe (E-044) |
| stdin einer Exec-Shell (`ssh host sh < skript`) | jede Zeile ein eigener Befehl, im Log | nur `sh` geht ans Modell, stdin bleibt ungelesen (E-044) |
| Eingabe an Programme, die stdin lesen (`cat` ohne Datei) | Eingabe des Programms, kein Befehl | jede Zeile ein eigener Befehl (E-044) |
| Leere Zeile (interaktiv) | neuer Prompt                                | das Gateway antwortet leer, ohne Modell (E-045); vorher meist leer vom Modell |
| Unbekannte Befehle im Log | `cowrie.command.failed`                    | kein Ereignis, das Modell antwortet auf alles          |
| Befehle je Adresse       | unbegrenzt                                  | höchstens 20 je Minute (Cowrie-Standard), darüber leere Ausgabe und `cowrie.llm.response` mit `local_rate_limit` (E-044) |
| Länge der Ausgabe        | vollständig                                 | höchstens `LLM_MAX_TOKENS` des Gateways und 16.384 Zeichen (E-043, E-044) |
| `w`, `who`, `last`       | echte Angreifer-IP                          | Gateway 10.20.0.5                                      |
| `uptime`, `date`         | echte Laufzeit bzw. Uhrzeit des Containers  | vom Modell geschätzt, Boot am 2026-09-01               |
| `top`                    | feste Momentaufnahme mit „up 16 days“       | vom Modell, passend zur aktuellen Session              |
| Feste Befehlsausgaben    | gleich, egal mit welchen Optionen           | passend zu den Optionen, aus denselben Daten           |
| `ps`                     | Cowries eigenes Spaltenformat, Sitzungsprozess mit festem Startdatum `Jul22` | Format von `ps aux`             |
| Befehle ohne Umsetzung in Cowrie (z.B. `lsblk`, `ip`) | `cannot execute binary file: Exec format error` | plausible Ausgabe                   |
| Eigenheiten von Cowries Befehlen | z.B. `head -4` unbekannt (nur `head -n 4`), `ls -l` zeigt Datum als `2026-09-17 08:41` | Verhalten wie GNU coreutils |
| `ifconfig`               | nur `eth0` und `lo`                         | `eth0` und `eth1`                                      |
| `wget`, `curl`           | lädt wirklich herunter und speichert die Datei | simuliert nur, es entsteht keine Datei (Patch folgt mit Schritt 7.3b, V5) |
| `scp -t`, `tftp`, `ftpget` | nimmt Dateien an bzw. lädt herunter        | simuliert nur                                          |
| SFTP                     | an, Uploads werden gespeichert (E-017)      | nicht vorhanden, Anfrage wird abgelehnt                |
| SSH-Weiterleitung (direct-tcpip) | an, wird protokolliert, nicht ausgeführt (E-017) | nicht vorhanden, Kanal wird abgelehnt |
| Gedächtnis               | Dateisystem der Session                     | nur die letzten 10 Befehle                             |
| Nicht hinterlegte Dateien | leer                                       | plausibler Debian-Standardinhalt                       |

## Befund: Cowries Standard-Dateisystem

Stand Cowrie 3.0.14, ausgewertet am 2026-09-17:

- **Oberfläche:** Debian 12.5 mit Kernel 6.1.0-21 (Mai 2024) und OpenSSH 9.2p1.
  Debian 12 ist seit August 2025 „oldstable“. Der Stand 12.5 stammt von Anfang
  2024, alle späteren Point-Releases fehlen.
- **Darunter deutlich älter:** `dmesg` zeigt Kernel 2.6.26 aus Debian 5 (2009,
  32 Bit). `df` zeigt ein 4,7-GB-rootfs mit `/run/shm`. Die Prozessliste für
  `ps` stammt etwa aus 2014 (Erlang erts-6.2, VirtualBox-Gastdienst, exim4,
  mysqld). `top` gibt eine Fehlermeldung des Editors vim aus. In
  `/proc/cpuinfo` steht eine CPU von 2016. `ssh -V` meldet OpenSSH 7.9 von 2018.
- **Widersprüche:** `/etc/os-release` ist leer. `/usr/lib/modules` fehlt,
  obwohl ein Kernel angegeben ist. `/proc/modules` zeigt Module eines
  Container-Hosts. `/etc/resolv.conf` zeigt einen öffentlichen Resolver.
  `getconf` gibt auf x86_64 `32` aus.
- **Bekannte Merkmale:** Hostname `svr04` und User `phil` gelten als
  Erkennungszeichen von Cowrie. `/opt`, `/srv` und `/home/phil` sind leer.
- **Zeitstempel:** Median 2024-02, dazu rund 17.500 `/sys`-Einträge von 2026-05.
- **Folge für die Persona:** Cowrie nutzt honeyfs-Inhalte nur für Pfade, die es
  im Dateisystem-Pickle gibt. Ohne eigenes `fs.pickle` sieht cowrie-a
  `/opt/ci-agent`, `/srv/build` und die Home-Verzeichnisse gar nicht.

## Offen

- [x] Schritt 2.2 auf dem Sensor: `fs.pickle` gebaut, Persona in cowrie-a
      geprüft (2026-09-17)
- [x] Schritt 2.2 auf dem Sensor: `MemTotal` des echten Sensors ist 3906284 kB,
      0,14 % unter der Persona, keine Anpassung nötig
- [x] Schritt 7.3: Patch für cowrie-b (E-041, E-044): Exec-Befehle loggen,
      Antwort-Ereignis je Befehl, motd, EOF bei Exec
- [ ] Schritt 7.3b, vor dem Start von B: echte Downloads in cowrie-b (V5)
