# Image für Lab-API und Worker.
#
# Tag und Digest sind gepinnt (E-010). Der Container läuft ohne Root und mit
# schreibgeschütztem Dateisystem; beschreibbar ist nur /tmp als tmpfs.
FROM python:3.12-slim@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Feste UID, damit sich Rechte auf dem Host nicht mit anderen Diensten beißen.
RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin lab

# Mountpunkt für die IPinfo-Datenbank. Ein neues Volume übernimmt beim ersten
# Einhängen Eigentümer und Rechte von hier. Ohne das gehörte es root, und der
# Worker (uid 10001) könnte die Datei nicht ablegen (Schritt 4.3).
RUN install -d -o lab -g lab -m 0755 /data

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY alembic.ini ./
COPY app ./app
COPY worker ./worker
# ATT&CK-Regeln, geladen von app/attack.py (Schritt 6.1).
COPY rules ./rules

# Build-Ziel für Tests: docker build --target test -t honeypot-lab-api:test server/
FROM base AS test
COPY requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements-dev.txt
COPY pytest.ini ./
COPY tests ./tests
USER lab
CMD ["pytest"]

# Laufzeit. Letzte Stufe, also das Standardziel von "docker compose build".
FROM base AS runtime
USER lab
EXPOSE 8000
# --no-access-log: Uvicorns Access-Log enthält die Adresse jedes Clients (E-009).
# --no-server-header: die Antwort soll nicht verraten, was hinter Caddy läuft.
CMD ["uvicorn", "app.main:create_app", \
     "--factory", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--no-access-log", \
     "--no-server-header"]
