#!/usr/bin/env bash
# Esegue la suite backend su PostgreSQL come la CI (job "pytest su PostgreSQL").
# Uso (dalla cartella principale del progetto, anche da Git Bash su Windows):
#   bash scripts/test-backend.sh                 # tutta la suite
#   bash scripts/test-backend.sh tests/test_p6_privacy.py -x   # solo alcuni file
# L'ambiente dei test e pulito (env -i): le impostazioni del .env (FEATURE_*, canali,
# preavviso, ...) NON entrano nei test, che usano config.test_settings.
set -euo pipefail
export MSYS_NO_PATHCONV=1
if pwd -W >/dev/null 2>&1; then ROOT="$(pwd -W)"; else ROOT="$(pwd)"; fi
ARGS="${*:-}"
docker compose up -d db >/dev/null
docker compose run --rm -u root -v "$ROOT":/src -w /src/backend backend sh -c '
  set -e
  /opt/venv/bin/pip install -q --require-hashes -r requirements-dev.txt
  mkdir -p /tmp/prometheus
  exec env -i PATH=/opt/venv/bin:/usr/local/bin:/usr/bin:/bin HOME=/tmp LANG=C.UTF-8 \
    DJANGO_SETTINGS_MODULE=config.test_settings USE_SQLITE_FOR_TESTS=0 EXPERIMENTAL_DB_PLANNING=1 \
    POSTGRES_DB="$POSTGRES_DB" POSTGRES_USER="$POSTGRES_USER" POSTGRES_PASSWORD="$POSTGRES_PASSWORD" \
    DB_HOST="${DB_HOST:-db}" DB_PORT="${DB_PORT:-5432}" \
    pytest -q -p no:cacheprovider -rfE --tb=short \
      --ignore=tests/test_infra_nginx.py --ignore=tests/test_ops_scripts.py '"$ARGS"'
'
