# Persona: bld-ci-03

Stand: 2026-09-17, abgeglichen mit Cowrie 3.0.14.

Diese Datei beschreibt die Maschine, die beide Honeypot-Varianten spielen. Sie
ist die Vorgabe für die zwei anderen Teile:

| Datei/Ordner | Wofür                                                                  | Genutzt von          |
|--------------|------------------------------------------------------------------------|----------------------|
| `honeyfs/`   | Dateiinhalte (`[honeypot] contents_path`), Banner vor dem Login         | cowrie-a und cowrie-b |
| `prompt.md`  | System-Prompt des LLM-Backends (`[llm] system_prompt`)                  | cowrie-b             |

`prompt.md` enthält jede Datei aus `honeyfs/` wörtlich. Wer eine Datei ändert,
ändert beide Stellen im selben Commit. Die Persona gehört zur Methode. Sobald
Variante B Daten erhebt, gilt jede Änderung für beide Varianten gleichzeitig
und steht mit Datum in `docs/decisions.md`, etwa Honeytokens aus Schritt 8.1.

## Namensregel

README.md verbietet reale Firmen-, Personen- und Markennamen in der Persona.
Umgesetzt ist die Regel so:

- **Frei erfunden:** Organisation, Rollen, Accounts, Hostnamen, Domain
  (`build.internal`, `.internal` ist für private Netze reserviert), Projekte,
  Artefakte, der Agent `ci-agent` und alle Tokens. Es gibt keinen
  Firmennamen, nur ein „build infrastructure team“.
- **Ausnahme:** Technische Kennungen, die jede Debian-VM ohnehin zeigt, bleiben
  drin. Dazu gehören Debian/GNU/Linux mit den URLs in `os-release`, die
  Kernel-Signatur in `/proc/version`, OpenSSH und die CPU-Vendor-ID
  `GenuineIntel`. Ohne sie wirkt die Maschine sofort unecht.
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
| Letzter Boot     | 2026-09-01 03:02 UTC (monatlicher Kernel-Neustart, erster Dienstag)         |
| Hardware         | KVM-VM, 2 vCPU („Common KVM processor“), 4 GB RAM, kein Swap, 40 GB Disk    |
| Netz             | `eth0`: öffentliche IP des Sensors, `eth1`: `10.20.4.13/16` (Build-Netz)    |
| Interne Hosts    | `git.build.internal` 10.20.1.10, `ci.build.internal` 10.20.1.20, `store-01.build.internal` 10.20.1.30, SSH-Gateway 10.20.0.5 |
| DNS              | 10.20.0.53, 10.20.0.54, Suchdomain `build.internal`                         |
| Zeitzone, Locale | `Etc/UTC`, `C.UTF-8`                                                        |
| Software         | bash 5.2.37, sudo 1.9.16p2, git 2.47.3, gcc 14.2.0, cmake 3.31.6, make 4.4.1, python3 3.13.5, rsync, curl, wget, ccache |
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

Alle Passwörter sind in `/etc/shadow` gesperrt, die Anmeldung läuft nur per Key.
Welche Logins Cowrie tatsächlich annimmt, legt später `userdb.txt` fest,
identisch für beide Varianten.

## Dienste

- **systemd-Units:** `ssh`, `cron`, `ci-agent.service` (User builder),
  `artifact-sync.timer` alle 15 Minuten (User release, rsync nach store-01),
  `unattended-upgrades`, `systemd-journald`, `-logind`, `-timesyncd`, `-udevd`,
  `dbus`, `getty@tty1`, `serial-getty@ttyS0`
- **Cron:** `/etc/cron.d/build-cleanup` löscht um 02:30 Workspaces, die älter als
  7 Tage sind
- **Prozessliste:** Die vollständige `ps aux`-Liste steht in `prompt.md`. Sie ist
  die Vorlage für ein eigenes `cmdoutput.json` in cowrie-a.

## Verzeichnisse

```text
/opt/ci-agent/                 root:root 755
  bin/ci-agent                 755, Python-Launcher
  etc/agent.ini                640 root:builder
  venv/                        Python-Umgebung mit Paket ci_agent
  README.txt, VERSION (2.14.3)
/srv/build/                    builder:builder 755
  workspace/job-48211, job-48213, job-48217   Git-Checkouts mit build/
  cache/ccache (ca. 9 GB), cache/pip (ca. 1,2 GB)
  artifacts/                   builder:release 2775
    svc-ingest-1.42.0-linux-amd64.tar.gz (38M)
    tool-cfgcheck-0.7.2-linux-amd64.tar.gz (4.1M)
/var/log/ci-agent/agent.log    builder:adm 640
/home/admin/                   .bash_history, .bashrc, .profile, runbook.txt
/home/builder/                 .bashrc, .cache/, .gitconfig, .profile
/home/release/                 .bashrc, .profile, .ssh/config
```

## Dateien in honeyfs

| Bereich     | Dateien                                                                         |
|-------------|---------------------------------------------------------------------------------|
| Identität   | `etc/hostname`, `etc/hosts`, `etc/issue`, `etc/issue.net`, `etc/motd`, `etc/debian_version`, `usr/lib/os-release`, `etc/resolv.conf` |
| Kernel, VM  | `proc/version`, `proc/cpuinfo`, `proc/mounts`                                   |
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
- Keine Datei enthält geschweifte Klammern (siehe `prompt.md` unten).

## Einbindung in Cowrie

Diese Werte gelten für cowrie-a und cowrie-b gleich:

| Abschnitt    | Option                | Wert                                                   |
|--------------|-----------------------|--------------------------------------------------------|
| `[honeypot]` | `hostname`            | `bld-ci-03`                                            |
| `[honeypot]` | `contents_path`       | eingebundener Ordner `honeyfs/`                        |
| `[shell]`    | `kernel_version`      | `6.12.107+deb13-amd64`                                 |
| `[shell]`    | `kernel_build_string` | `#1 SMP PREEMPT_DYNAMIC Debian 6.12.107-1 (2026-08-29)` |
| `[shell]`    | `hardware_platform`   | `x86_64`                                               |
| `[shell]`    | `operating_system`    | `GNU/Linux`                                            |
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
  eigenen IPs des Sensors) und sonst keine geschweiften Klammern. Die
  Angreifer-IP (`{client_ip}`) wird bewusst nicht an den LLM-Anbieter
  gegeben.
- **Automatische Ergänzungen:** Cowrie hängt selbst einen Schutz gegen
  Prompt-Injection sowie Hostname, User und Arbeitsverzeichnis an.
- **Größe:** Der Prompt hat rund 19.400 Zeichen (ca. 4.900 Tokens) und geht bei
  jedem Befehl mit (Entscheidung siehe „Prompt-Größe“).

## Banner

- **Vor dem Login: kein Banner.** Cowrie schickt `etc/issue.net` nur, wenn die
  Datei nicht leer ist. Ein echtes Debian zeigt standardmäßig ebenfalls kein
  Banner. Ein Warnhinweis würde gerade Menschen abschrecken, und ihre
  interaktiven Sitzungen sind für die Forschungsfrage am wertvollsten. Außerdem
  sieht ein leeres Banner vor der Anmeldung weniger von der Persona.
- **Nach dem Login: die motd aus `etc/motd`.** cowrie-a zeigt sie schon.
  cowrie-b gibt dagegen fest `Welcome to bld-ci-03` aus. Das soll derselbe
  kleine Cowrie-Patch ändern, der in cowrie-b auch echte Downloads ermöglicht
  (E-016). Kommt der Patch nicht, wird `etc/motd` auf genau
  `Welcome to bld-ci-03` gesetzt, damit beide Varianten dasselbe zeigen.

## Prompt-Größe

Der Prompt bleibt vollständig, mit rund 4.900 Tokens pro Befehl:

- **Wörtlicher Inhalt:** Nur so gibt cowrie-b bei `cat` denselben Text aus wie
  cowrie-a. Das gilt besonders für die Dateien, die Bots am häufigsten lesen
  (`/proc/cpuinfo`, `/etc/passwd`, `/etc/os-release`).
- **Nicht kürzbar:** Kürzen hieße, honeyfs-Dateien wegzulassen. Dann zeigt
  cowrie-a wieder Cowries alte Standardinhalte (User `phil`, Debian 12).
- **Kosten:** Der Prompt ist fast vollständig gleichbleibend. Die eigenen IPs
  sind pro Sensor fest, und Cowrie hängt die wechselnden Angaben ans Ende. Viele
  Anbieter speichern so einen gleichbleibenden Anfang zwischen und berechnen
  ihn günstiger. Das Gateway (Schritt 7.2) sollte das nutzen und die
  zwischengespeicherten Tokens mitloggen.
- **Latenz:** Ein langer Prompt kann die Antwortzeit von cowrie-b erhöhen. Das
  Gateway misst die Latenz ohnehin (`llm_usage`). Hypothese H3 aus Schritt 7.1
  (`docs/method.md`, noch nicht angelegt) behandelt sie.

## Bekannte Unterschiede zwischen den Varianten

Diese Unterschiede entstehen durch Cowrie und nicht durch die Persona. Sie
gehören in die Methodik.

| Stelle                   | cowrie-a (Shell)                            | cowrie-b (LLM)                                         |
|--------------------------|---------------------------------------------|--------------------------------------------------------|
| Nach dem Login           | Inhalt von `etc/motd`                       | fest eingebaut: `Welcome to bld-ci-03` (Patch geplant, E-016) |
| Start-Verzeichnis        | Home des Users                              | `/`                                                    |
| `w`, `who`, `last`       | echte Angreifer-IP                          | Gateway 10.20.0.5                                      |
| `uptime`, `date`         | echte Laufzeit bzw. Uhrzeit des Containers  | vom Modell geschätzt, Boot am 2026-09-01               |
| `ifconfig`               | nur `eth0` und `lo`                         | `eth0` und `eth1`                                      |
| `wget`, `curl`           | lädt wirklich herunter und speichert die Datei | simuliert nur, es entsteht keine Datei (Patch geplant, E-016) |
| `scp -t`, `tftp`, `ftpget` | nimmt Dateien an bzw. lädt herunter        | simuliert nur                                          |
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
  `/proc/cpuinfo` steht eine CPU von 2016.
- **Widersprüche:** `/etc/os-release` ist leer. `/usr/lib/modules` fehlt,
  obwohl ein Kernel angegeben ist. `/proc/modules` zeigt Module eines
  Container-Hosts. `/etc/resolv.conf` zeigt einen öffentlichen Resolver.
- **Bekannte Merkmale:** Hostname `svr04` und User `phil` gelten als
  Erkennungszeichen von Cowrie. `/opt`, `/srv` und `/home/phil` sind leer.
- **Zeitstempel:** Median 2024-02, dazu rund 17.500 `/sys`-Einträge von 2026-05.
- **Folge für die Persona:** Cowrie nutzt honeyfs-Inhalte nur für Pfade, die es
  im Dateisystem-Pickle gibt. Ohne eigenes `fs.pickle` sieht cowrie-a
  `/opt/ci-agent`, `/srv/build` und die Home-Verzeichnisse gar nicht.

## Offen

Diese Punkte gehören zu späteren Schritten, nicht zu Schritt 2.1.

- [ ] Schritt 2.2: eigenes `fs.pickle` per `createfs` aus einem Debian-13.7-Baum
- [ ] Schritt 2.2: `txtcmds` ersetzen (`dmesg`, `df`, `top`, `lscpu`, `nproc`, `mount`)
- [ ] Schritt 2.2: `cmdoutput.json` aus der Prozessliste in `prompt.md` erzeugen
- [ ] Schritt 2.2: `proc/modules` und `proc/meminfo` passend zur Persona
- [ ] Schritt 2.2: `userdb.txt` mit den angenommenen Logins, gleich für beide Varianten
- [ ] Schritt 2.2: Test, dass `prompt.md` alle honeyfs-Dateien wörtlich enthält
- [ ] Phase 7, vor Schritt 7.1: Cowrie-Patch für cowrie-b, echte Downloads und motd (E-016)
