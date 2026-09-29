#!/usr/bin/env bash
# Löscht Rohlogs, tty-Mitschnitte und Downloads der Honeypots nach 14 Tagen.
#
# Die aktuelle cowrie.json bleibt, gelöscht werden nur rotierte Logdateien
# (cowrie.json.<datum>). Läuft täglich über honeypot-cleanup.timer.
#
# Aufruf: sudo sensor/scripts/cleanup.sh
set -euo pipefail

readonly ROOT=/srv/honeypot
readonly MAX_AGE_DAYS="${MAX_AGE_DAYS:-14}"
readonly MAX_AGE_MINUTES=$((MAX_AGE_DAYS * 24 * 60))

remove_old() {
  local label="$1" dir="$2"
  shift 2
  if [[ ! -d "$dir" ]]; then
    return
  fi
  local count
  count="$(find "$dir" -type f "$@" -mmin +"$MAX_AGE_MINUTES" -print -delete | wc -l)"
  echo "$label: $count Datei(en) gelöscht"
}

for variant_dir in "$ROOT"/a "$ROOT"/b; do
  [[ -d "$variant_dir" ]] || continue
  variant="$(basename "$variant_dir")"
  remove_old "$variant logs" "$variant_dir/var/log/cowrie" -name 'cowrie.json.*'
  remove_old "$variant tty" "$variant_dir/var/lib/cowrie/tty"
  remove_old "$variant downloads" "$variant_dir/var/lib/cowrie/downloads"
done
