#!/usr/bin/env bash
# Rigenera i lockfile con hash (GAP-J06): installazione con `pip install --require-hashes`.
# Uso: scripts/lock-deps.sh [--upgrade]   (richiede pip-tools >= 7.4, Python 3.13 linux)
set -euo pipefail
cd "$(dirname "$0")/../backend"
COMPILER=${PIP_TOOLS_COMPILE:-pip-compile}  # (non usare PIP_*: pip lo leggerebbe come opzione)
args=(--generate-hashes --allow-unsafe --strip-extras --resolver=backtracking --quiet --no-header)
if [[ "${1:-}" == "--upgrade" ]]; then args+=(--upgrade); fi
"$COMPILER" "${args[@]}" --output-file requirements.txt requirements.in
"$COMPILER" "${args[@]}" --output-file requirements-dev.txt requirements-dev.in
echo "lockfile aggiornati: backend/requirements.txt, backend/requirements-dev.txt"
