# Honeypot-Lab: Verzeichnisbaum der Persona bld-ci-03 (Debian 13.7)
#
# Nur Vorlage für Cowries fs.pickle, läuft nie als Dienst.
# Gebaut und umgewandelt von sensor/scripts/build-fs-pickle.sh auf dem Sensor.
# Build-Kontext ist sensor/persona/.

FROM debian:trixie-20260824@sha256:f324c7ff54321e8d9c588493a20244965938ce0aa50bbd1022d38010e9ffc4b1

# Paketstand der Persona: Debian-Snapshot vom Stand der Persona (E-018)
ARG SNAPSHOT=20260917T000000Z

SHELL ["/bin/bash", "-euo", "pipefail", "-c"]
ENV DEBIAN_FRONTEND=noninteractive

# Docker-spezifische Einstellungen des Basis-Images entfernen, damit Dokumentation
# installiert wird und keine Spuren eines Containers im Dateisystem bleiben.
RUN rm -f /etc/apt/apt.conf.d/docker-* /etc/dpkg/dpkg.cfg.d/docker* \
 && printf '%s\n' \
      "Types: deb" \
      "URIs: http://snapshot.debian.org/archive/debian/${SNAPSHOT}" \
      "Suites: trixie trixie-updates" \
      "Components: main" \
      "Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg" \
      "" \
      "Types: deb" \
      "URIs: http://snapshot.debian.org/archive/debian-security/${SNAPSHOT}" \
      "Suites: trixie-security" \
      "Components: main" \
      "Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg" \
      >/etc/apt/sources.list.d/debian.sources \
 && apt-get -o Acquire::Check-Valid-Until=false -o Acquire::Retries=5 update \
 && apt-get -o Acquire::Retries=5 -y upgrade \
 && apt-get -o Acquire::Retries=5 -y install --no-install-recommends \
      apparmor bash-completion build-essential ca-certificates ccache cmake cron \
      curl dbus git iproute2 iputils-ping kmod less linux-image-amd64 man-db nano \
      openssh-client openssh-server procps python3 python3-venv rsync sudo systemd \
      systemd-sysv systemd-timesyncd unattended-upgrades vim-tiny wget \
 && apt-get clean \
 && printf '%s\n' \
      "Types: deb" \
      "URIs: http://deb.debian.org/debian" \
      "Suites: trixie trixie-updates" \
      "Components: main" \
      "Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg" \
      "" \
      "Types: deb" \
      "URIs: http://security.debian.org/debian-security" \
      "Suites: trixie-security" \
      "Components: main" \
      "Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg" \
      >/etc/apt/sources.list.d/debian.sources

# Konten der Persona (honeyfs/etc/passwd und honeyfs/etc/group)
RUN groupadd --gid 1000 admin \
 && useradd --uid 1000 --gid admin --groups sudo,adm,systemd-journal --create-home \
      --shell /bin/bash --comment "Build Admin,,," admin \
 && groupadd --gid 1001 builder \
 && useradd --uid 1001 --gid builder --create-home --shell /bin/bash \
      --comment "CI Build Agent,,," builder \
 && groupadd --gid 1002 release \
 && useradd --uid 1002 --gid release --groups builder --create-home --shell /bin/bash \
      --comment "Release Publisher,,," release

# IDs der Systemkonten an die Persona angleichen
COPY rootfs/remap-ids.sh /usr/local/sbin/persona-remap-ids
COPY honeyfs/etc/passwd /tmp/persona/passwd
COPY honeyfs/etc/group /tmp/persona/group
RUN persona-remap-ids /tmp/persona/passwd /tmp/persona/group \
 && rm -rf /tmp/persona /usr/local/sbin/persona-remap-ids

# Verzeichnisse und Dateien, die persona.md beschreibt
RUN install -d -m 0755 /opt/ci-agent/bin /opt/ci-agent/etc \
 && python3 -m venv /opt/ci-agent/venv \
 && pkg=/opt/ci-agent/venv/lib/python3.13/site-packages/ci_agent \
 && install -d "$pkg" \
 && touch "$pkg/__init__.py" "$pkg/main.py" "$pkg/coordinator.py" "$pkg/jobs.py" "$pkg/artifacts.py" \
 && install -d -o builder -g builder -m 0755 \
      /srv/build /srv/build/workspace /srv/build/cache /srv/build/cache/ccache /srv/build/cache/pip \
      /home/builder/.cache \
 && for dir in 0 1 2 3 4 5 6 7 8 9 a b c d e f; do \
      install -d -o builder -g builder -m 0755 "/srv/build/cache/ccache/$dir"; \
    done \
 && install -d -o builder -g release -m 2775 /srv/build/artifacts \
 && for job in 48211 48213 48217; do \
      ws="/srv/build/workspace/job-$job"; \
      install -d "$ws/src" "$ws/build"; \
      git -c init.defaultBranch=main init -q "$ws"; \
      printf 'cmake_minimum_required(VERSION 3.25)\n' >"$ws/CMakeLists.txt"; \
      printf 'Build workspace for job %s\n' "$job" >"$ws/README.md"; \
      chown -R builder:builder "$ws"; \
    done \
 && head -c 39845888 /dev/zero >/srv/build/artifacts/svc-ingest-1.42.0-linux-amd64.tar.gz \
 && head -c 4296704 /dev/zero >/srv/build/artifacts/tool-cfgcheck-0.7.2-linux-amd64.tar.gz \
 && chown builder:release /srv/build/artifacts/*.tar.gz \
 && install -d -o builder -g adm -m 2750 /var/log/ci-agent \
 && printf '%s\n' \
      "2026-09-17T08:33:12Z INFO job 48213 finished status=success duration=287s" \
      "2026-09-17T08:35:47Z INFO job 48217 started pool=linux-amd64" \
      "2026-09-17T08:41:02Z INFO job 48217 finished status=success duration=312s" \
      >/var/log/ci-agent/agent.log \
 && chown builder:adm /var/log/ci-agent/agent.log \
 && chmod 0640 /var/log/ci-agent/agent.log \
 && install -d -o release -g release -m 0700 /home/release/.ssh \
 && touch /etc/ssh/ssh_known_hosts

# Dateiinhalte aus honeyfs (ohne /proc, das build-fs-pickle.sh anlegt)
COPY honeyfs/etc/ /etc/
COPY honeyfs/usr/ /usr/
COPY honeyfs/opt/ /opt/
COPY honeyfs/home/ /home/
RUN chown -R admin:admin /home/admin \
 && chown -R builder:builder /home/builder \
 && chown -R release:release /home/release \
 && chmod 0600 /home/admin/.bash_history /home/release/.ssh/config \
 && chmod 0755 /opt/ci-agent/bin/ci-agent \
 && chown root:builder /opt/ci-agent/etc/agent.ini \
 && chmod 0640 /opt/ci-agent/etc/agent.ini \
 && chown root:shadow /etc/shadow \
 && chmod 0640 /etc/shadow \
 && chmod 0440 /etc/sudoers.d/90-admin

# policy-rc.d verhindert im Docker-Image nur das Starten von Diensten beim
# Installieren und gehört nicht auf einen echten Server.
# Plausible Zeitstempel: Installation im Februar, Betrieb bis zum Stand der Persona.
# /etc/hostname, /etc/hosts und /etc/resolv.conf sind beim Bauen schreibgeschützt
# eingebunden, deren Zeitstempel setzt build-fs-pickle.sh nach dem Export.
COPY honeyfs/ /tmp/persona-honeyfs/
RUN rm -f /usr/sbin/policy-rc.d \
 && stamp() { local when="$1"; shift; touch -h -d "$when" "$@"; } \
 && (cd /tmp/persona-honeyfs && find . -mindepth 1 ! -path './proc' ! -path './proc/*' \
      ! -path './etc/hostname' ! -path './etc/hosts' ! -path './etc/resolv.conf' -print0) \
    | while IFS= read -r -d '' file; do stamp "2026-02-10 16:08:00 UTC" "/${file#./}"; done \
 && rm -rf /tmp/persona-honeyfs \
 && stamp "2026-02-10 16:05:00 UTC" /etc/issue /etc/issue.net \
 && stamp "2026-02-10 16:12:00 UTC" /etc/sudoers.d/90-admin \
 && stamp "2026-02-11 09:40:00 UTC" /etc/systemd/system/ci-agent.service \
      /etc/systemd/system/artifact-sync.service /etc/systemd/system/artifact-sync.timer \
 && stamp "2026-02-11 09:41:00 UTC" /etc/cron.d/build-cleanup \
 && stamp "2026-02-11 09:45:00 UTC" /home/builder/.gitconfig \
 && stamp "2026-02-11 09:46:00 UTC" /home/release/.ssh/config /home/release/.ssh \
 && find /opt/ci-agent -exec touch -h -d "2026-08-12 10:24:00 UTC" {} + \
 && stamp "2026-09-02 14:05:00 UTC" /opt/ci-agent/etc/agent.ini \
 && stamp "2026-09-02 14:12:00 UTC" /home/admin/runbook.txt \
 && stamp "2026-09-16 17:48:00 UTC" /home/admin/.bash_history \
 && find /srv/build/workspace/job-48211 -exec touch -h -d "2026-09-16 11:02:00 UTC" {} + \
 && find /srv/build/workspace/job-48213 -exec touch -h -d "2026-09-16 15:37:00 UTC" {} + \
 && find /srv/build/workspace/job-48217 -exec touch -h -d "2026-09-17 08:41:00 UTC" {} + \
 && stamp "2026-09-17 08:35:00 UTC" /srv/build/workspace \
 && stamp "2026-09-17 08:33:00 UTC" /srv/build/artifacts/tool-cfgcheck-0.7.2-linux-amd64.tar.gz \
 && stamp "2026-09-17 08:41:00 UTC" /srv/build/artifacts/svc-ingest-1.42.0-linux-amd64.tar.gz \
      /srv/build/artifacts /var/log/ci-agent/agent.log
