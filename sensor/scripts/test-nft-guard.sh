#!/usr/bin/env bash
# Prüft die nftables-Regeln aus nftables/honeypot.nft in zwei Netz-Namespaces
# (Schritt 7.3, E-044). Läuft in der CI, braucht root, nft, ip und python3.
# Fasst weder die Regeln des Hosts noch Docker an.
#
#   Namespace hp-srv: lädt honeypot.nft, lauscht auf 2222 und 2322
#   Namespace hp-cli: verbindet sich von außen über ein veth-Paar
#
# Erwartet:
#   von außen auf 2322        verworfen
#   von lo auf 2322           angenommen
#   von außen auf 22          per Umleitung bei 2222 (cowrie-a)
#   per Umleitung auf 2322    angenommen (ct status dnat), wie ab Schritt 7.4
#
# Aufruf: sudo sensor/scripts/test-nft-guard.sh [AUSGABEDATEI_FUER_NFT_JSON]
set -euo pipefail

readonly HERE="$(cd "$(dirname "$0")/.." && pwd)"
readonly RULES="$HERE/nftables/honeypot.nft"
readonly JSON_OUT="${1:-}"
readonly SRV=hp-srv CLI=hp-cli
readonly SRV_IP=10.99.0.2 CLI_IP=10.99.0.1

if [[ $EUID -ne 0 ]]; then
  echo "Bitte mit sudo ausführen." >&2
  exit 1
fi

cleanup() {
  ip netns pids "$SRV" 2>/dev/null | xargs -r kill 2>/dev/null || true
  ip netns del "$SRV" 2>/dev/null || true
  ip netns del "$CLI" 2>/dev/null || true
}
trap cleanup EXIT
cleanup

ip netns add "$SRV"
ip netns add "$CLI"
ip link add veth-cli netns "$CLI" type veth peer name veth-srv netns "$SRV"
ip -n "$CLI" addr add "$CLI_IP/24" dev veth-cli
ip -n "$SRV" addr add "$SRV_IP/24" dev veth-srv
for ns in "$SRV" "$CLI"; do
  ip -n "$ns" link set lo up
done
ip -n "$CLI" link set veth-cli up
ip -n "$SRV" link set veth-srv up

ip netns exec "$SRV" nft -f "$RULES"
if [[ -n "$JSON_OUT" ]]; then
  # Der Regelsatz, wie das Prüfskript ihn auf dem Sensor liest.
  ip netns exec "$SRV" nft -j list table ip honeypot >"$JSON_OUT"
fi
# Nur für diesen Test: eine Umleitung auf 2322, wie sie Schritt 7.4 bringt.
ip netns exec "$SRV" nft add rule ip honeypot prerouting tcp dport 2400 redirect to :2322

# Ein Lauscher je Port, der jede Verbindung annimmt und schließt.
for port in 2222 2322; do
  ip netns exec "$SRV" python3 -c "
import socket
s = socket.socket(); s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind(('0.0.0.0', $port)); s.listen(16)
while True:
    c, _ = s.accept(); c.close()
" &
done
sleep 1

connects() {  # Namespace, Ziel, Port -> 0 bei Verbindung
  ip netns exec "$1" python3 -c "
import socket, sys
try:
    socket.create_connection(('$2', $3), timeout=2).close()
except OSError:
    sys.exit(1)
"
}

failed=0
expect() {  # Beschreibung, erwartet (ja/nein), Namespace, Ziel, Port
  local got=nein
  if connects "$3" "$4" "$5"; then got=ja; fi
  if [[ "$got" == "$2" ]]; then
    echo "OK     $1"
  else
    echo "FEHLER $1 (verbunden: $got, erwartet: $2)"
    failed=1
  fi
}

expect "von außen auf 2322 verworfen" nein "$CLI" "$SRV_IP" 2322
expect "von lo auf 2322 angenommen" ja "$SRV" 127.0.0.1 2322
expect "von außen auf 22, umgeleitet auf 2222" ja "$CLI" "$SRV_IP" 22
expect "per Umleitung auf 2322 angenommen (ct status dnat)" ja "$CLI" "$SRV_IP" 2400
expect "von außen auf 2222 unverändert erreichbar" ja "$CLI" "$SRV_IP" 2222

exit "$failed"
