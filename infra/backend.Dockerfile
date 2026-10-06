# syntax=docker/dockerfile:1.7
# Immagine di produzione del backend (GAP-J03): build multi-stage, dipendenze installate
# solo da lockfile con hash, utente non root, gunicorn, healthcheck senza curl.
# Le immagini base vanno fissate per digest in CI (vedi docs/runbooks/README e
# .github/dependabot.yml): ARG sovrascrivibili, default = tag.
ARG PYTHON_IMAGE=python:3.13-slim-bookworm

FROM ${PYTHON_IMAGE} AS build
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /build
COPY backend/requirements.txt .
# --require-hashes: qualunque pacchetto non presente nel lock o con hash diverso blocca la build.
RUN python -m venv /opt/venv \
 && /opt/venv/bin/pip install --require-hashes --no-deps -r requirements.txt

FROM ${PYTHON_IMAGE} AS runtime
ARG BUILD_VERSION=dev
LABEL org.opencontainers.image.title="ripetizioni-backend" \
      org.opencontainers.image.version="${BUILD_VERSION}" \
      org.opencontainers.image.licenses="proprietary"
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/opt/venv/bin:$PATH \
    DJANGO_SETTINGS_MODULE=config.settings_production \
    BUILD_VERSION=${BUILD_VERSION} \
    PROMETHEUS_MULTIPROC_DIR=/tmp/prometheus
RUN groupadd --system --gid 10001 app \
 && useradd --system --uid 10001 --gid app --home-dir /app --shell /usr/sbin/nologin app \
 && apt-get update && apt-get upgrade -y --no-install-recommends && rm -rf /var/lib/apt/lists/*
COPY --from=build /opt/venv /opt/venv
WORKDIR /app
COPY --chown=root:root backend/ /app/
COPY --chown=root:root infra/gunicorn.conf.py /app/gunicorn.conf.py
# collectstatic in build: nessuna scrittura a runtime (filesystem in sola lettura).
RUN DJANGO_SETTINGS_MODULE=config.settings DJANGO_SECRET_KEY=build-only-not-secret \
    USE_SQLITE_FOR_TESTS=1 python manage.py collectstatic --noinput --verbosity 0 \
 && rm -f /app/dev.sqlite3 && find /app -name '__pycache__' -prune -exec rm -rf {} + \
 && python -m compileall -q /app /opt/venv >/dev/null
# Dati privacy (export, registro): unica cartella scrivibile, montata come volume.
RUN mkdir -p /app/var/privacy/exports && chown -R 10001:10001 /app/var
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=20s --retries=3 \
  CMD ["python", "-c", "import sys,urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2).status == 200 else 1)"]
CMD ["gunicorn", "config.wsgi:application", "--config", "/app/gunicorn.conf.py"]
