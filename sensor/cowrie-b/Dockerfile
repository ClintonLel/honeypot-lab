# Honeypot-Lab: Image von cowrie-b (Schritt 7.3, E-041, E-044)
#
# Dasselbe Cowrie-Image wie cowrie-a (method.md 4.1) plus der Patch am
# LLM-Backend aus cowrie-b.patch. Build-Kontext ist sensor/cowrie-b/, gebaut
# auf dem Sensor mit `docker compose build cowrie-b` und in der CI.
#
# Der Bau bricht ab, wenn
# - die Originaldateien im Image nicht genau die sind, gegen die der Patch
#   geschrieben ist (upstream.sha256),
# - der Patch nicht ohne Unschärfe passt (--fuzz=0),
# - die installierten Pakete vom Lock abweichen (requirements.lock).

# Tag und Digest wie cowrie-a in docker-compose.yml. Ein Test prüft, dass
# beide gleich bleiben (sensor/tests/test_cowrie_b.py).
FROM cowrie/cowrie:3.0.14@sha256:f6ea2e847a1837794cd570322a25a9da819824c70a718600fa6de4c1eba66626 AS upstream

# --- Patch anwenden ------------------------------------------------------------
# Das Cowrie-Image ist distroless, ohne Shell und ohne patch. Angewendet wird
# deshalb in einer eigenen Stufe mit GNU patch aus einem festen
# Debian-Snapshot, wie in persona/rootfs/Dockerfile (E-018).
FROM debian:trixie-20260824@sha256:f324c7ff54321e8d9c588493a20244965938ce0aa50bbd1022d38010e9ffc4b1 AS patch

ARG SNAPSHOT=20260917T000000Z
SHELL ["/bin/bash", "-euo", "pipefail", "-c"]
ENV DEBIAN_FRONTEND=noninteractive

RUN printf '%s\n' \
      "Types: deb" \
      "URIs: http://snapshot.debian.org/archive/debian/${SNAPSHOT}" \
      "Suites: trixie" \
      "Components: main" \
      "Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg" \
      >/etc/apt/sources.list.d/debian.sources \
 && apt-get -o Acquire::Check-Valid-Until=false -o Acquire::Retries=5 update \
 && apt-get -o Acquire::Retries=5 -y install --no-install-recommends patch \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /work
COPY --from=upstream /cowrie/cowrie-git/src/cowrie/llm/protocol.py /cowrie/cowrie-git/src/cowrie/llm/llm.py src/cowrie/llm/
COPY upstream.sha256 cowrie-b.patch ./
RUN sha256sum --strict --check upstream.sha256 \
 && patch -p1 --dry-run --fuzz=0 --batch --forward --reject-file=- -i cowrie-b.patch \
 && patch -p1 --fuzz=0 --batch --forward --no-backup-if-mismatch --reject-file=- -i cowrie-b.patch

# --- Laufzeit ------------------------------------------------------------------
FROM cowrie/cowrie:3.0.14@sha256:f6ea2e847a1837794cd570322a25a9da819824c70a718600fa6de4c1eba66626

COPY --from=patch --chown=999:999 /work/src/cowrie/llm/protocol.py /work/src/cowrie/llm/llm.py /cowrie/cowrie-git/src/cowrie/llm/
# Starter, Lock-Prüfung und Testclient gehören root, Cowrie liest sie nur.
COPY --chown=0:0 lab/ /cowrie/lab/
COPY --chown=0:0 requirements.lock /cowrie/lab/requirements.lock

# Bytecode vorab: Zur Laufzeit ist das Dateisystem schreibgeschützt.
USER 0:0
RUN ["/cowrie/cowrie-env/bin/python3", "-m", "compileall", "-q", "/cowrie/cowrie-git/src/cowrie/llm", "/cowrie/lab"]
RUN ["/cowrie/cowrie-env/bin/python3", "/cowrie/lab/lockcheck.py", "/cowrie/lab/requirements.lock"]
USER 999:999

# Wie im Image von Cowrie: python3 als ENTRYPOINT, twistd als CMD. Dazwischen
# setzt launch.py Prompt und Gateway-Token (E-044).
ENTRYPOINT [ "/cowrie/cowrie-env/bin/python3", "/cowrie/lab/launch.py" ]
CMD [ "/cowrie/cowrie-env/bin/twistd", "-n", "--umask=0022", "--pidfile=", "--logger", "cowrie.python.logfile.stdoutLogger", "cowrie" ]
