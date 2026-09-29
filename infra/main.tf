locals {
  # Feste Vorgaben aus docs/decisions.md (E-001, E-012). Absichtlich keine
  # Variablen, damit jeder Aufbau gleich aussieht.
  name        = "hp-sensor-01"
  server_type = "cx23"
  image       = "ubuntu-26.04"
  location    = "nbg1"

  cloud_init = file("${path.module}/cloud-init.yaml")

  # Einzige Quelle für den Admin-Key ist der User tom in cloud-init.yaml.
  admin_public_key = [
    for user in yamldecode(local.cloud_init).users : user.ssh_authorized_keys[0]
    if user.name == "tom"
  ][0]

  labels = {
    project = "honeypot-lab"
    role    = "sensor"
  }
}

# Admin-Key auch bei Hetzner hinterlegen. Dann erzeugt Hetzner kein
# Root-Passwort, und das Rescue-System ist mit demselben Key erreichbar.
# Root-Login per SSH bleibt trotzdem gesperrt (cloud-init.yaml).
resource "hcloud_ssh_key" "admin" {
  name       = "${local.name}-admin"
  public_key = local.admin_public_key
  labels     = local.labels
}

# Eingehend nur ICMP, Honeypot-SSH und Admin-SSH. Die Cowrie-Ports 2222 und
# 2322 bleiben zu, sonst ließe sich die Zuteilung umgehen (E-004).
# Ohne Regeln für "out" erlaubt Hetzner jeden ausgehenden Verkehr.
resource "hcloud_firewall" "sensor" {
  name   = local.name
  labels = local.labels

  rule {
    description = "ICMP"
    direction   = "in"
    protocol    = "icmp"
    source_ips  = ["0.0.0.0/0", "::/0"]
  }

  # Honeypot nur über IPv4, wie im Bauplan (Schritt 1.4).
  rule {
    description = "Honeypot-SSH, per nftables auf cowrie-a und cowrie-b verteilt"
    direction   = "in"
    protocol    = "tcp"
    port        = "22"
    source_ips  = ["0.0.0.0/0"]
  }

  rule {
    description = "Admin-SSH"
    direction   = "in"
    protocol    = "tcp"
    port        = "22022"
    source_ips  = var.admin_source_ips
  }
}

resource "hcloud_server" "sensor" {
  name        = local.name
  server_type = local.server_type
  image       = local.image
  location    = local.location
  labels      = local.labels

  ssh_keys     = [hcloud_ssh_key.admin.id]
  firewall_ids = [hcloud_firewall.sensor.id]
  user_data    = local.cloud_init

  public_net {
    ipv4_enabled = true
    ipv6_enabled = true
  }

  # Der Sensor hält keine Daten, die nicht auch beim Hauptserver ankommen
  # (E-001). Backups und Löschschutz sind deshalb aus, "tofu destroy" räumt
  # ohne Zwischenschritt ab.
  backups                  = false
  delete_protection        = false
  rebuild_protection       = false
  shutdown_before_deletion = true
}
