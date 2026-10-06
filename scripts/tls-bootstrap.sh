#!/usr/bin/env bash
# Primo rilascio del certificato Let's Encrypt (GAP-J08). Prerequisiti: record DNS A/AAAA
# di SERVER_NAME verso l'host, porta 80 raggiungibile, proxy avviato (senza certificato
# serve solo HTTP e la challenge ACME). Dopo il rilascio il servizio "acme" rinnova da solo
# e nginx ricarica i certificati ogni 6 h. Procedura: docs/infra/dns-tls-manutenzione.md
#
# Uso: SERVER_NAME=app.example.it ACME_EMAIL=ops@example.it scripts/tls-bootstrap.sh
#      ACME_STAGING=1 per provare contro l'ambiente di staging di Let's Encrypt.
set -Eeuo pipefail
. "$(dirname "$0")/lib/common.sh"
require_cmd docker curl
require_env SERVER_NAME ACME_EMAIL
compose=(docker compose -f compose.prod.yaml)
[[ $SERVER_NAME =~ ^[a-z0-9.-]+$ ]] || die "SERVER_NAME non valido"

# 1. La challenge deve essere raggiungibile dall'esterno prima di chiedere il certificato.
token="probe-$(head -c 8 /dev/urandom | od -An -tx1 | tr -d ' \n')"
"${compose[@]}" run --rm --no-deps --entrypoint sh acme -c \
  "mkdir -p /var/www/acme/.well-known/acme-challenge && echo ok > /var/www/acme/.well-known/acme-challenge/$token"
got=$(curl -fsS --max-time 10 "http://$SERVER_NAME/.well-known/acme-challenge/$token" || true)
"${compose[@]}" run --rm --no-deps --entrypoint sh acme -c "rm -f /var/www/acme/.well-known/acme-challenge/$token"
[ "$got" = ok ] || die "challenge HTTP-01 non raggiungibile: controllare DNS, firewall e proxy"

# 2. Rilascio.
staging=()
[ "${ACME_STAGING:-0}" = 1 ] && staging=(--staging)
"${compose[@]}" run --rm --no-deps --entrypoint certbot acme certonly --webroot \
  -w /var/www/acme -d "$SERVER_NAME" --email "$ACME_EMAIL" --agree-tos --non-interactive \
  --key-type ecdsa "${staging[@]}"

# 3. Il proxy rigenera la configurazione HTTPS all'avvio; HSTS parte da 1 h (paper §10.3).
"${compose[@]}" up -d --no-deps --force-recreate proxy
"${compose[@]}" --profile tls up -d acme
info "certificato attivo" server="$SERVER_NAME"
