#!/usr/bin/env bash
# Smoke test post-deploy (GAP-J03/J07, usato da deploy.sh e dalla CD). Solo richieste
# anonime e idempotenti: nessun dato creato, nessuna credenziale (lo staff ha MFA
# obbligatoria, quindi un login automatico non è previsto).
#
# Uso: scripts/smoke.sh https://app.example.it
# Variabili:
#   SMOKE_INSECURE=1        accetta certificati non pubblici (solo e2e con CA locale)
#   SMOKE_CACERT=<file>     CA da usare per la verifica TLS (alternativa a INSECURE)
#   SMOKE_RETRIES           tentativi per la readiness (default 30, 2 s l'uno)
set -Eeuo pipefail
. "$(dirname "$0")/lib/common.sh"

base=${1:-${SMOKE_BASE_URL:-}}
[ -n "$base" ] || die "uso: smoke.sh <https://host[:porta]>"
base=${base%/}
require_cmd curl
curl_opts=(--silent --show-error --max-time 10 --proto '=https,http')
[ "${SMOKE_INSECURE:-0}" = 1 ] && curl_opts+=(--insecure)
[ -n "${SMOKE_CACERT:-}" ] && curl_opts+=(--cacert "$SMOKE_CACERT")
failures=0
body=$(mktemp)
headers=$(mktemp)
trap 'rm -f "$body" "$headers"' EXIT

fetch() { # fetch <path> [opzioni curl] -> stampa lo status
  local path=$1
  shift
  curl "${curl_opts[@]}" -o "$body" -D "$headers" -w '%{http_code}' "$@" "$base$path" || echo 000
}
check() { # check <descrizione> <condizione...>
  local what=$1
  shift
  if "$@"; then
    info "ok: $what"
  else
    log ERROR "FALLITO: $what"
    failures=$((failures + 1))
  fi
}
header() { grep -i "^$1:" "$headers" | head -1 | cut -d: -f2- | tr -d '\r' | sed 's/^ *//'; }
has_header() { [ -n "$(header "$1")" ]; }
header_matches() { header "$1" | grep -Eq "$2"; }

# 1. Readiness pubblica (dipendenze interne), con attesa per il rollout.
status=000
for _ in $(seq "${SMOKE_RETRIES:-30}"); do
  status=$(fetch /api/v1/ready)
  [ "$status" = 200 ] && break
  sleep 2
done
check "readiness /api/v1/ready = 200 (ultimo $status)" test "$status" = 200

# 2. Pagina dell'app e header di sicurezza.
status=$(fetch /)
check "index = 200" test "$status" = 200
check "CSP presente" has_header content-security-policy
check "CSP senza unsafe-inline negli script" \
  bash -c "! grep -i '^content-security-policy:' '$headers' | grep -Eo \"script-src[^;]*\" | grep -q unsafe-inline"
check "X-Content-Type-Options nosniff" header_matches x-content-type-options nosniff
check "Referrer-Policy" has_header referrer-policy
check "X-Request-ID restituito" has_header x-request-id
if [[ $base == https://* ]]; then
  check "HSTS su HTTPS" has_header strict-transport-security
fi
check "nessuna versione del server esposta" bash -c "! grep -Eiq '^server: .*[0-9]' '$headers'"

# 3. Superfici interne non esposte dal proxy.
for p in /metrics /readyz /healthz; do
  status=$(fetch "$p")
  check "$p non esposto (404, ottenuto $status)" test "$status" = 404
done
# Admin: 404 se spento, 403 dal proxy fuori dall'allowlist (ADMIN_ALLOW_CIDRS).
status=$(fetch /admin/)
check "/admin/ chiuso (403/404, ottenuto $status)" bash -c "[ '$status' = 404 ] || [ '$status' = 403 ]"

# 4. API: senza sessione nessun dato, risposta JSON coerente.
status=$(fetch /api/v1/me)
check "/api/v1/me anonimo = 401/403 (ottenuto $status)" bash -c "[ '$status' = 401 ] || [ '$status' = 403 ]"
status=$(fetch /api/v1/auth/login -X POST -H 'Content-Type: application/json' --data '{}')
check "login senza CSRF rifiutato (ottenuto $status)" bash -c "[ '$status' = 403 ] || [ '$status' = 400 ]"
status=$(fetch '/api/v1/calendar.ics?token=ics_smoke_invalid')
check "feed ICS con token non valido rifiutato (ottenuto $status)" \
  bash -c "[ '$status' = 404 ] || [ '$status' = 401 ] || [ '$status' = 403 ]"

# 5. Redirect HTTP -> HTTPS (se il servizio è su HTTPS sulla porta standard).
if [[ $base == https://* ]] && [[ ! $base =~ :[0-9]+$ ]]; then
  http_base="http://${base#https://}"
  code=$(curl "${curl_opts[@]}" -o /dev/null -w '%{http_code} %{redirect_url}' "$http_base/" || echo 000)
  check "HTTP reindirizza a HTTPS ($code)" bash -c "[[ '$code' =~ ^30[18]\ https:// ]]"
fi

if [ "$failures" -gt 0 ]; then
  die "smoke test fallito" failures="$failures" base="$base"
fi
info "smoke test superato" base="$base"
