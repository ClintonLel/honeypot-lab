"""Vergleicht die installierten Pakete mit requirements.lock (Schritt 7.3).

Läuft beim Bau des Images von cowrie-b. Das Lock nennt jede Distribution, die
Python im Image findet, mit Version, transitive eingeschlossen. Weicht etwas
ab, bricht der Bau ab und gibt die tatsächliche Liste aus, damit eine
gewollte Änderung (anderes Basis-Image) bewusst ins Lock wandert.

Die Bits selbst sichert der Digest des Basis-Images; das Lock macht den Stand
lesbar und prüfbar.

    python3 lockcheck.py requirements.lock
"""

from __future__ import annotations

import re
import sys
from importlib import metadata


def canonical(name: str) -> str:
    """Wie PEP 503: Groß/klein, Punkte und Unterstriche gleich."""
    return re.sub(r"[-_.]+", "-", name).lower()


def installed() -> dict[str, str]:
    found: dict[str, str] = {}
    for dist in metadata.distributions():
        name = dist.metadata["Name"]
        if name:
            found[canonical(name)] = dist.version
    return found


def read_lock(path: str) -> dict[str, str]:
    locked: dict[str, str] = {}
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.split("#", 1)[0].strip()
            if not line:
                continue
            name, sep, version = line.partition("==")
            if not sep or not name or not version:
                raise ValueError(f"Zeile ohne name==version: {line!r}")
            locked[canonical(name.strip())] = version.strip()
    return locked


def render(packages: dict[str, str]) -> str:
    return "\n".join(f"{name}=={version}" for name, version in sorted(packages.items()))


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("Aufruf: lockcheck.py <requirements.lock>", file=sys.stderr)
        return 2
    locked = read_lock(argv[0])
    actual = installed()
    if locked == actual:
        print(f"lock ok: {len(actual)} Pakete")
        return 0
    missing = sorted(set(locked) - set(actual))
    extra = sorted(set(actual) - set(locked))
    changed = sorted(n for n in set(locked) & set(actual) if locked[n] != actual[n])
    print("lock weicht ab", file=sys.stderr)
    print(f"  fehlt im Image: {missing}", file=sys.stderr)
    print(f"  nicht im Lock: {extra}", file=sys.stderr)
    print(f"  andere Version: {[(n, locked[n], actual[n]) for n in changed]}", file=sys.stderr)
    print("Tatsächlicher Stand:", file=sys.stderr)
    print(render(actual), file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
