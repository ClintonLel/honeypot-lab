# infra: Sensor mit OpenTofu

OpenTofu baut den Sensor `hp-sensor-01` in Hetzner Cloud. Beim ersten Start
richtet `cloud-init.yaml` den Server ein. Hintergrund: `docs/decisions.md`,
E-011 bis E-013.

| Ressource        | Name                 | Inhalt                                                                  |
|------------------|----------------------|-------------------------------------------------------------------------|
| `hcloud_ssh_key` | `hp-sensor-01-admin` | Public Key von `tom` aus `cloud-init.yaml`                              |
| `hcloud_firewall`| `hp-sensor-01`       | eingehend: ICMP, TCP 22 nur IPv4 (Honeypot), TCP 22022 (Admin, `admin_source_ips`) |
| `hcloud_server`  | `hp-sensor-01`       | CX23, `ubuntu-26.04`, `nbg1`, IPv4 + IPv6, User Data `cloud-init.yaml`  |

Alle Befehle laufen im Ordner `infra/`.

## Voraussetzungen

- OpenTofu ab 1.12, z.B. per Homebrew:

  ```bash
  brew install opentofu
  ```

- Der private Schlüssel `~/.ssh/hp_sensor`
- Ein API-Token des Hetzner-Sensor-Projekts mit Lese- und Schreibrecht

## Token setzen

Das Token kommt nur aus der Umgebungsvariable `HCLOUD_TOKEN`. Es gehört in
keine Datei, auch nicht in `.env` oder `*.tfvars`. So setzt du es, ohne dass
es in der Shell-History landet (die Eingabe bleibt unsichtbar):

```bash
read -rs HCLOUD_TOKEN && export HCLOUD_TOKEN
```

Die Variable gilt nur im aktuellen Terminal. Wenn du fertig bist:

```bash
unset HCLOUD_TOKEN
```

## Einmalig: von Hand angelegte Ressourcen aufräumen

Der erste Sensor wurde von Hand angelegt. Servernamen sind pro Projekt
eindeutig. Solange es ihn gibt, bricht `tofu apply` ab.

1. In der Hetzner Cloud Console den Server `hp-sensor-01` löschen. Seine IP
   `195.201.127.108` geht dabei verloren, der neue Server bekommt eine andere.
2. Die von Hand angelegte Firewall löschen.
3. Hetzner lehnt denselben Public Key ein zweites Mal ab. Liegt `hp_sensor.pub`
   schon als SSH-Key im Projekt, löschst du ihn dort oder übernimmst ihn mit
   seiner ID aus der Console nach dem `tofu init`:

   ```bash
   tofu import hcloud_ssh_key.admin SSH_KEY_ID
   ```

## Aufbauen

```bash
tofu init
```

```bash
tofu plan
```

```bash
tofu apply
```

`tofu apply` zeigt den Plan noch einmal und fragt nach `yes`. Danach steht der
Server, und cloud-init braucht noch einige Minuten für Updates und Docker.

## Prüfen

Den Login-Befehl mit der neuen IP gibt OpenTofu aus:

```bash
tofu output -raw ssh
```

Auf dem Server wartet dieser Befehl, bis cloud-init fertig ist, und zeigt
Fehler an:

```bash
sudo cloud-init status --wait --long
```

SSH darf nur auf 22022 lauschen, auf 22 nichts:

```bash
sudo ss -tlnp
```

Docker und Compose-Plugin:

```bash
sudo docker compose version
```

Den Host-Key-Fingerprint vergleichst du beim ersten Login mit der Ausgabe in
`/var/log/cloud-init-output.log` oder in der Hetzner-Konsole.

## Ändern

- **`cloud-init.yaml` geändert:** `tofu plan` zeigt einen Neuaufbau des
  Servers (`-/+`). Der Server bekommt dabei eine neue IP, alle Daten darauf
  sind weg.
- **Admin-SSH nur von bestimmten Adressen erlauben:** Lege eine Datei
  `admin.auto.tfvars` an. Sie wird nicht committet, und OpenTofu liest sie
  automatisch. Die Firewall wird dann ohne Neuaufbau angepasst:

  ```hcl
  admin_source_ips = ["203.0.113.4/32"]
  ```

- **Alter Host-Key nach einem Neuaufbau mit derselben IP:** Den alten Eintrag
  entfernst du so:

  ```bash
  ssh-keygen -R "[IP]:22022"
  ```

## Abbauen

```bash
tofu destroy
```

Das entfernt Server, Firewall und SSH-Key. Die Daten auf dem Sensor sind
danach weg, das ist so gewollt (E-001).

## State

- `terraform.tfstate` liegt nur lokal in `infra/` und wird nicht committet.
  Er enthält IDs, IPs und die User Data, aber kein Token.
- Geht der State verloren, kennt OpenTofu die Ressourcen nicht mehr. Dann musst
  du Server, Firewall und SSH-Key in der Console von Hand löschen.
- `.terraform.lock.hcl` wird committet. Sie legt Provider-Version und
  Prüfsummen fest, damit jeder Aufbau denselben Provider nutzt.
