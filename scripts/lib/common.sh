# shellcheck shell=bash
# Funzioni comuni degli script operativi (GAP-L01..L04, J07). Da includere con:
#   . "$(dirname "$0")/lib/common.sh"
# Log su stderr in JSON (una riga per evento), mai segreti: le URL di connessione non
# vengono stampate, solo host e database.

ts() { date -u +%Y-%m-%dT%H:%M:%SZ; }
epoch() { date -u +%s; }

log() { # log <livello> <messaggio> [chiave=valore ...]
  local level=$1 msg=$2 extra="" kv
  shift 2
  for kv in "$@"; do
    extra+=$(printf ',"%s":"%s"' "${kv%%=*}" "$(json_escape "${kv#*=}")")
  done
  printf '{"ts":"%s","level":"%s","script":"%s","msg":"%s"%s}\n' \
    "$(ts)" "$level" "${0##*/}" "$(json_escape "$msg")" "$extra" >&2
}
info() { log INFO "$@"; }
warn() { log WARNING "$@"; }
die() { log ERROR "$@"; exit 1; }

json_escape() { # escape minimo per stringhe JSON
  local s=${1//\\/\\\\}
  s=${s//\"/\\\"}
  s=${s//$'\n'/\\n}
  s=${s//$'\t'/\\t}
  printf '%s' "$s"
}

require_cmd() {
  local c
  for c in "$@"; do
    command -v "$c" >/dev/null 2>&1 || die "comando richiesto assente: $c"
  done
}

require_env() {
  local v
  for v in "$@"; do
    [ -n "${!v:-}" ] || die "variabile richiesta assente: $v"
  done
}

sha256_of() { sha256sum "$1" | cut -d' ' -f1; }

file_size() { stat -c %s "$1"; }

# Scrittura atomica: write_atomic <file> (contenuto da stdin).
write_atomic() {
  local target=$1 tmp
  tmp=$(mktemp "${target}.XXXXXX")
  cat >"$tmp"
  chmod 0644 "$tmp"
  mv -f "$tmp" "$target"
}

repo_root() { cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd; }
