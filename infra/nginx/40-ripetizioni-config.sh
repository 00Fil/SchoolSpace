#!/bin/sh
# Genera la configurazione runtime di nginx (eseguito da /docker-entrypoint.sh).
# Variabili: SERVER_NAME, TLS_CERT, TLS_KEY, CSP_MODE (enforce|report-only),
# CSP_REPORT_URI, HSTS_SECONDS, ADMIN_ALLOW_CIDRS (lista separata da spazi/virgole),
# TRUST_UPSTREAM_PROTO=1 dietro un proxy TLS fidato (Traefik di Dokploy).
set -eu

SERVER_NAME=${SERVER_NAME:-_}
TLS_CERT=${TLS_CERT:-/etc/nginx/tls/fullchain.pem}
TLS_KEY=${TLS_KEY:-/etc/nginx/tls/privkey.pem}
CSP_MODE=${CSP_MODE:-report-only}
HSTS_SECONDS=${HSTS_SECONDS:-3600}
CONF=/etc/nginx/conf.d
RUNTIME=$CONF/runtime
SRC=/etc/nginx/templates-src
mkdir -p "$RUNTIME"

case "$SERVER_NAME" in *[!A-Za-z0-9._\ -]*) echo "SERVER_NAME non valido" >&2; exit 1;; esac

# v0.10 videolezioni: VIDEO_ORIGIN (es. https://meet.esempio.it) è l'unica origine che può
# essere incorniciata e ricevere camera/microfono/condivisione schermo. Vuoto = nessuna.
VIDEO_ORIGIN=${VIDEO_ORIGIN:-}
case "$VIDEO_ORIGIN" in ""|https://*) ;; *) echo "VIDEO_ORIGIN deve iniziare con https://" >&2; exit 1;; esac
case "$VIDEO_ORIGIN" in *[!A-Za-z0-9.:/-]*|*/*/*/*) echo "VIDEO_ORIGIN non valido (solo https://host[:porta])" >&2; exit 1;; esac

hashes=$(cat /etc/nginx/csp-script-hashes.txt 2>/dev/null || true)
if [ -n "$VIDEO_ORIGIN" ]; then frame="frame-src ${VIDEO_ORIGIN}"; else frame="frame-src 'none'"; fi
csp="default-src 'self'; script-src 'self' ${hashes}; style-src 'self'; img-src 'self' data:; font-src 'self'; connect-src 'self'; ${frame}; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'; manifest-src 'self'; worker-src 'self'"
if [ -n "${CSP_REPORT_URI:-}" ]; then csp="$csp; report-uri ${CSP_REPORT_URI}"; fi
if [ "$CSP_MODE" = "enforce" ]; then header="Content-Security-Policy"; else header="Content-Security-Policy-Report-Only"; fi
printf 'add_header %s "%s" always;\n' "$header" "$csp" > "$RUNTIME/csp.inc"

if [ -n "$VIDEO_ORIGIN" ]; then
  media="camera=(\\\"${VIDEO_ORIGIN}\\\"), microphone=(\\\"${VIDEO_ORIGIN}\\\"), display-capture=(\\\"${VIDEO_ORIGIN}\\\"), fullscreen=(self \\\"${VIDEO_ORIGIN}\\\")"
else
  media="camera=(), microphone=(), display-capture=()"
fi
printf 'add_header Permissions-Policy "%s, geolocation=(), payment=(), usb=()" always;\n' "$media" > "$RUNTIME/permissions.inc"

: > "$RUNTIME/admin-allow.inc"
for cidr in $(echo "${ADMIN_ALLOW_CIDRS:-}" | tr ',' ' '); do
  case "$cidr" in *[!0-9a-fA-F:./]*) echo "CIDR non valido: $cidr" >&2; exit 1;; esac
  printf 'allow %s;\n' "$cidr" >> "$RUNTIME/admin-allow.inc"
done

if [ -s "$TLS_CERT" ] && [ -s "$TLS_KEY" ]; then
  printf 'add_header Strict-Transport-Security "max-age=%s; includeSubDomains" always;\n' "$HSTS_SECONDS" > "$RUNTIME/hsts.inc"
  # shellcheck disable=SC2016  # variabili nginx, non della shell
  body='  location / { return 308 https://$host$request_uri; }'
  sed -e "s|__SERVER_NAME__|$SERVER_NAME|g" -e "s|__TLS_CERT__|$TLS_CERT|g" -e "s|__TLS_KEY__|$TLS_KEY|g" \
    "$SRC/https.conf.template" > "$CONF/https.conf"
  # Rinnovo automatico (certbot nel servizio "acme"): reload periodico per caricare il nuovo certificato.
  # TLS_RELOAD_INTERVAL=0 disattiva il ciclo (test).
  interval=${TLS_RELOAD_INTERVAL:-21600}
  if [ "$interval" != "0" ]; then
    ( while sleep "$interval"; do nginx -s reload || true; done ) >/dev/null 2>&1 &
  fi
  echo "nginx: TLS attivo per $SERVER_NAME (HSTS ${HSTS_SECONDS}s, CSP $CSP_MODE)"
else
  : > "$RUNTIME/hsts.inc"   # niente HSTS senza TLS
  body='  include /etc/nginx/snippets/app-locations.conf;'
  rm -f "$CONF/https.conf"
  echo "nginx: certificato assente, solo HTTP su 8080 (sviluppo/e2e o primo rilascio ACME)"
fi
awk -v body="$body" '{ if ($0 == "__HTTP_BODY__") print body; else print }' \
  "$SRC/http.conf.template" | sed -e "s|__SERVER_NAME__|$SERVER_NAME|g" > "$CONF/http.conf"

# Dietro Traefik (Dokploy) TLS è terminato a monte: si inoltra il protocollo originale,
# altrimenti Django vedrebbe "http" e andrebbe in loop di redirect.
if [ "${TRUST_UPSTREAM_PROTO:-0}" = "1" ]; then
  sed -i 's|set $forwarded_proto http;|set $forwarded_proto $http_x_forwarded_proto;|' "$CONF/http.conf"
  echo "nginx: X-Forwarded-Proto dal proxy a monte"
fi
