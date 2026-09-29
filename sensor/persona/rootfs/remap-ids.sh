#!/usr/bin/env bash
# Gleicht UIDs und GIDs im Image an honeyfs/etc/passwd und honeyfs/etc/group an.
#
# Pakete legen Systemkonten mit dynamischen IDs an. Die Persona legt die IDs in
# honeyfs fest. Ohne Angleichung zeigt `ls -l` in cowrie-a für Dateien dieser
# Konten falsche Namen. Umgezogen wird in zwei Durchgängen über einen
# Zwischenbereich ab 100000, damit sich getauschte IDs nicht überschreiben.
#
# Aufruf: remap-ids.sh <persona-passwd> <persona-group>
set -euo pipefail

readonly PASSWD_FILE="$1"
readonly GROUP_FILE="$2"
readonly OFFSET=100000

move_to_offset() {
  local kind="$1" database="$2" file="$3"
  local name id current
  while IFS=: read -r name _ id _; do
    current="$(getent "$database" "$name" | cut -d: -f3)" || continue
    if [[ -z "$current" || "$current" == "$id" ]]; then
      continue
    fi
    echo "$database $name: $current -> $id"
    if [[ "$kind" == uid ]]; then
      find / -xdev -uid "$current" -exec chown -h "$((OFFSET + id))" {} +
    else
      find / -xdev -gid "$current" -exec chgrp -h "$((OFFSET + id))" {} +
    fi
  done <"$file"
}

move_back() {
  local kind="$1" path id
  while IFS= read -r -d '' path; do
    if [[ "$kind" == uid ]]; then
      id="$(stat -c %u "$path")"
      chown -h "$((id - OFFSET))" "$path"
    else
      id="$(stat -c %g "$path")"
      chgrp -h "$((id - OFFSET))" "$path"
    fi
  done < <(find / -xdev -"$kind" +"$((OFFSET - 1))" -print0)
}

move_to_offset uid passwd "$PASSWD_FILE"
move_to_offset gid group "$GROUP_FILE"
move_back uid
move_back gid
