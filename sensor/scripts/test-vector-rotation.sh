#!/usr/bin/env bash
# Prüft, dass Vector bei Log-Rotation und Neustart weder Zeilen verliert noch
# doppelt liefert (Schritt 4.2).
#
# Der Test läuft in einem eigenen Verzeichnis unter /tmp mit erfundenen
# Ereignissen und schreibt in eine Datei statt an die API. Die echten Logs und
# die Datenbank bleiben unberührt.
#
# Ablauf:
#   1. 10 Zeilen schreiben, Vector lesen lassen, beenden
#   2. Datei rotieren wie Cowrie es tut, 5 alte Zeilen in die rotierte Datei
#      nachtragen, 10 neue in die frische Datei
#   3. Vector mit demselben data_dir erneut starten
#   4. Zählen: 25 Zeilen, jede genau einmal
#
# Aufruf: sudo sensor/scripts/test-vector-rotation.sh
set -euo pipefail

readonly IMAGE="timberio/vector:0.58.0-alpine@sha256:5dcf67db0ee378caa87f3395cb9484ebe3e97bb0334d119f2ac33116e00c5773"
readonly WORK=/tmp/vector-rotation-test
readonly LOGS="$WORK/logs"
readonly DATA="$WORK/data"
readonly OUT="$WORK/out"

if [[ $EUID -ne 0 ]]; then
  echo "Bitte mit sudo ausführen." >&2
  exit 1
fi

rm -rf "$WORK"
mkdir -p "$LOGS" "$DATA" "$OUT"

# Erfundene Ereignisse im Format von cowrie.json. Adressen aus dem
# Dokumentationsbereich, nie echte.
schreibe_zeilen() {
  local datei="$1" von="$2" bis="$3"
  for i in $(seq "$von" "$bis"); do
    printf '{"eventid":"cowrie.session.connect","timestamp":"2026-09-18T10:%02d:00.000000Z","session":"test%08d","sensor":"hp-a","src_ip":"203.0.113.9","dst_ip":"198.51.100.1","message":"test %d"}\n' \
      $((i % 60)) "$i" "$i" >>"$datei"
  done
}

# Die Quelle ist dieselbe wie in vector/vector.yaml, nur das Ziel ist eine
# Datei statt der API.
cat >"$WORK/vector.yaml" <<'EOF'
data_dir: /data
sources:
  cowrie:
    type: file
    include:
      - /logs/cowrie.json*
    read_from: beginning
    fingerprint:
      strategy: checksum
      lines: 1
    oldest_first: true
sinks:
  datei:
    type: file
    inputs:
      - cowrie
    path: /out/gelesen.json
    encoding:
      codec: text
EOF

starte_vector() {
  local sekunden="$1"
  timeout "$sekunden" docker run --rm \
    -v "$WORK/vector.yaml:/etc/vector/vector.yaml:ro" \
    -v "$LOGS:/logs" \
    -v "$DATA:/data" \
    -v "$OUT:/out" \
    "$IMAGE" --config /etc/vector/vector.yaml --quiet || true
}

echo "1. Erster Durchlauf: 10 Zeilen"
schreibe_zeilen "$LOGS/cowrie.json" 1 10
starte_vector 15
nach_erstem=$(wc -l <"$OUT/gelesen.json")
echo "   gelesen: $nach_erstem"

echo "2. Rotation wie bei Cowrie, dann neue Zeilen"
mv "$LOGS/cowrie.json" "$LOGS/cowrie.json.2026-09-18"
# Fünf Zeilen landen noch in der rotierten Datei: Genau hier entstehen Lücken,
# wenn Vector die Datei am Namen statt am Inhalt erkennt.
schreibe_zeilen "$LOGS/cowrie.json.2026-09-18" 11 15
schreibe_zeilen "$LOGS/cowrie.json" 16 25

echo "3. Neustart mit demselben data_dir"
starte_vector 20

echo "4. Auswertung"
gesamt=$(wc -l <"$OUT/gelesen.json")
eindeutig=$(sort -u "$OUT/gelesen.json" | wc -l)
fehlend=""
for i in $(seq 1 25); do
  if ! grep -q "\"session\":\"test$(printf '%08d' "$i")\"" "$OUT/gelesen.json"; then
    fehlend="$fehlend $i"
  fi
done

echo "   Zeilen gesamt:   $gesamt"
echo "   davon eindeutig: $eindeutig"
echo "   fehlende:       ${fehlend:- keine}"

if [[ "$gesamt" -ne "$eindeutig" ]]; then
  echo "FEHLGESCHLAGEN: Vector hat Zeilen doppelt geliefert." >&2
  exit 1
fi
if [[ -n "$fehlend" ]]; then
  echo "FEHLGESCHLAGEN: Zeilen fehlen:$fehlend" >&2
  exit 1
fi
if [[ "$eindeutig" -ne 25 ]]; then
  echo "FEHLGESCHLAGEN: erwartet 25 Zeilen, gelesen $eindeutig." >&2
  exit 1
fi

echo
echo "BESTANDEN: 25 Zeilen, jede genau einmal, über Rotation und Neustart hinweg."
echo "Aufräumen mit: sudo rm -rf $WORK"
