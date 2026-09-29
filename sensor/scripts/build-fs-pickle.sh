#!/usr/bin/env bash
# Baut Cowries fs.pickle für die Persona bld-ci-03. Läuft auf dem Sensor als root.
#
# 1. Image aus sensor/persona/rootfs/Dockerfile bauen (Debian 13.7)
# 2. Dateisystem exportieren und Spuren des Containers entfernen
# 3. /proc, /sys und /dev als Platzhalter anlegen, damit Cowrie diese Pfade kennt
# 4. createfs aus dem gepinnten Cowrie-Image per chroot ausführen
#
# /proc, /sys und /dev werden nicht eingebunden. So landen keine Daten des
# Sensors im Pickle. Ergebnis: /srv/honeypot/persona/fs.pickle (nicht im Repo).
#
# Aufruf: sudo sensor/scripts/build-fs-pickle.sh [ziel]
set -euo pipefail

SENSOR_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly SENSOR_DIR
readonly OUT="${1:-/srv/honeypot/persona/fs.pickle}"
readonly BUILD_TAG="honeypot-persona-rootfs:build"
readonly EXPORT_NAME="honeypot-persona-export"
readonly CREATEFS_NAME="honeypot-cowrie-createfs"
# Zeitpunkte aus persona.md
readonly PERSONA_NOW="2026-09-17 09:00:00 UTC"
readonly INSTALLED_AT="2026-02-10 16:04:00 UTC"
readonly BOOTED_AT="2026-09-01 03:02:05 UTC"

if [[ $EUID -ne 0 ]]; then
  echo "Bitte mit sudo ausführen." >&2
  exit 1
fi

cowrie_image="$(sed -n 's/^ *image: *\(cowrie\/cowrie:[^ ]*\) *$/\1/p' "$SENSOR_DIR/docker-compose.yml" | head -n 1)"
if [[ -z "$cowrie_image" ]]; then
  echo "Cowrie-Image nicht in docker-compose.yml gefunden." >&2
  exit 1
fi

work="$(mktemp -d /var/tmp/persona-fs.XXXXXX)"
cleanup() {
  docker rm -f "$EXPORT_NAME" "$CREATEFS_NAME" >/dev/null 2>&1 || true
  rm -rf --one-file-system "${work:?}"
}
trap cleanup EXIT

echo "1/4 Image bauen (lädt Pakete vom Debian-Snapshot, dauert einige Minuten)"
docker build --tag "$BUILD_TAG" --file "$SENSOR_DIR/persona/rootfs/Dockerfile" "$SENSOR_DIR/persona"

echo "2/4 Dateisystem exportieren"
rootfs="$work/rootfs"
install -d -m 0755 "$rootfs"
docker create --name "$EXPORT_NAME" "$BUILD_TAG" >/dev/null
docker export "$EXPORT_NAME" | tar -x -C "$rootfs" --numeric-owner
docker rm "$EXPORT_NAME" >/dev/null
rm -f "${rootfs:?}/.dockerenv"
# Docker ersetzt diese Dateien beim Anlegen des Containers durch eigene.
for file in etc/hostname etc/hosts etc/resolv.conf; do
  install -m 0644 -o root -g root "$SENSOR_DIR/persona/honeyfs/$file" "$rootfs/$file"
  touch -d "2026-02-10 16:05:00 UTC" "$rootfs/$file"
done

# Alles, was beim Bauen nach dem Stand der Persona entstanden ist, bekommt den
# Zeitpunkt der Installation. Sonst zeigt `ls -la /` einen frisch gebauten Server.
find "$rootfs" -xdev -newermt "$PERSONA_NOW" -exec touch -h -d "$INSTALLED_AT" {} +
# unattended-upgrades läuft täglich
for path in var/lib/dpkg var/lib/dpkg/status var/lib/apt/lists; do
  touch -h -d "2026-09-17 06:25:00 UTC" "$rootfs/$path"
done

echo "3/4 Platzhalter für /proc, /sys und /dev anlegen"
rm -rf --one-file-system "${rootfs:?}/proc" "${rootfs:?}/sys" "${rootfs:?}/dev"
install -d -m 0555 "$rootfs/proc" "$rootfs/proc/1" "$rootfs/proc/net" "$rootfs/proc/sys"
ln -s 1 "$rootfs/proc/self"
# Leer wie im echten /proc. Die Inhalte liefert Cowrie aus honeyfs.
for file in cpuinfo meminfo modules mounts version; do
  install -m 0444 /dev/null "$rootfs/proc/$file"
done
install -d -m 0555 "$rootfs/sys"
for dir in block bus class dev devices firmware fs hypervisor kernel module power; do
  install -d -m 0755 "$rootfs/sys/$dir"
done
install -d -m 0755 "$rootfs/dev" "$rootfs/dev/pts" "$rootfs/dev/mqueue" "$rootfs/dev/hugepages" "$rootfs/dev/disk"
install -d -m 1777 "$rootfs/dev/shm"
while read -r name type major minor mode; do
  mknod -m "$mode" "$rootfs/dev/$name" "$type" "$major" "$minor"
done <<'NODES'
null c 1 3 666
zero c 1 5 666
full c 1 7 666
random c 1 8 666
urandom c 1 9 666
kmsg c 1 11 644
tty c 5 0 666
console c 5 1 600
ptmx c 5 2 666
tty0 c 4 0 620
tty1 c 4 1 620
ttyS0 c 4 64 660
vda b 254 0 660
vda1 b 254 1 660
vda14 b 254 14 660
vda15 b 254 15 660
NODES

find "$rootfs/proc" "$rootfs/sys" "$rootfs/dev" -exec touch -h -d "$BOOTED_AT" {} +

echo "4/4 createfs aus $cowrie_image"
docker create --name "$CREATEFS_NAME" "$cowrie_image" >/dev/null
docker cp "$CREATEFS_NAME:/cowrie/cowrie-git/src/cowrie/scripts/createfs.py" "$rootfs/cowrie-createfs.py"
docker rm "$CREATEFS_NAME" >/dev/null
# createfs überspringt alle Pfade mit "cowrie" im Namen, also auch Skript und Ausgabe.
install -d -m 0755 "$rootfs/cowrie-out"
touch -h -d "$INSTALLED_AT" "$rootfs"
chroot "$rootfs" /usr/bin/python3 /cowrie-createfs.py -p -l / -o /cowrie-out/fs.pickle

install -d -m 0755 "$(dirname "$OUT")"
install -m 0644 -o root -g root "$rootfs/cowrie-out/fs.pickle" "$OUT.new"
mv -f "$OUT.new" "$OUT"
echo "Fertig: $OUT ($(du -h "$OUT" | cut -f 1))"
