#!/usr/bin/env bash
# Dopo ogni "migrate": riapplica privilegi e trigger append-only di infra/postgres (s4) e
# fallisce se 04_verify.sql trova non conformità. Connessione: variabili libpq del
# migratore (PGUSER=app_migrator, PGOPTIONS="-c role=app_owner", PGSSLMODE=verify-full).
# Uso: scripts/pg-privileges.sh   (PSQL="docker run ... postgres:17 psql" per usare un container)
set -Eeuo pipefail
. "$(dirname "$0")/lib/common.sh"
ROOT=$(repo_root)
read -r -a psql_cmd <<<"${PSQL:-psql}"
run_sql() { "${psql_cmd[@]}" -X -q -v ON_ERROR_STOP=1 "$@"; }
run_sql -f - <"$ROOT/infra/postgres/02_privileges.sql" >/dev/null
run_sql -f - <"$ROOT/infra/postgres/03_append_only_triggers.sql" >/dev/null
problems=$("${psql_cmd[@]}" -X -At -v ON_ERROR_STOP=1 -f - <"$ROOT/infra/postgres/04_verify.sql")
if [ -n "$problems" ]; then
  log ERROR "verifica privilegi fallita" problems="$problems"
  exit 1
fi
info "privilegi e trigger append-only conformi"
