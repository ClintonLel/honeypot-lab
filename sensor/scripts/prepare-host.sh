#!/usr/bin/env bash
# Legt auf dem Sensor Verzeichnisse und SSH-Host-Keys für die Honeypots an.
#
# Kann mehrfach laufen: Vorhandene Keys bleiben erhalten, Rechte werden
# nachgezogen. Der Container-User von Cowrie ist 999:999.
#
# Aufruf: sudo sensor/scripts/prepare-host.sh
set -euo pipefail

readonly ROOT=/srv/honeypot
readonly COWRIE_ID=999

if [[ $EUID -ne 0 ]]; then
  echo "Bitte mit sudo ausführen." >&2
  exit 1
fi

# Verzeichnis für den Container-User anlegen. install -o/-g der uutils-coreutils
# in Ubuntu 26.04 akzeptiert keine numerischen IDs ohne passenden Host-User.
cowrie_dir() {
  local mode="$1" dir="$2"
  mkdir -p "$dir"
  chown "$COWRIE_ID:$COWRIE_ID" "$dir"
  chmod "$mode" "$dir"
}

install -d -m 0755 -o root -g root "$ROOT" "$ROOT/persona"

# Laufzeitdaten je Variante: Logs, tty-Mitschnitte, Downloads. Nur der
# Container-User darf lesen, denn GID 999 gehört auf dem Host zu systemd-journal.
for variant in a b; do
  for dir in var var/log var/log/cowrie var/lib var/lib/cowrie var/lib/cowrie/tty \
    var/lib/cowrie/downloads var/lib/cowrie/snapshots var/run; do
    cowrie_dir 0700 "$ROOT/$variant/$dir"
  done
done

# Gemeinsame Host-Keys, damit A und B vor dem Login gleich aussehen (E-002)
cowrie_dir 0700 "$ROOT/hostkeys"
for type in rsa ecdsa ed25519; do
  key="$ROOT/hostkeys/ssh_host_${type}_key"
  if [[ ! -f "$key" ]]; then
    ssh-keygen -q -t "$type" -N "" -C "" -f "$key"
    echo "Host-Key erzeugt: $key"
  fi
  chown "$COWRIE_ID:$COWRIE_ID" "$key" "$key.pub"
  chmod 0600 "$key"
  chmod 0644 "$key.pub"
done

echo "Fingerprints der Honeypot-Host-Keys:"
for type in rsa ecdsa ed25519; do
  ssh-keygen -l -f "$ROOT/hostkeys/ssh_host_${type}_key.pub"
done
