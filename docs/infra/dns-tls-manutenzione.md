# DNS, TLS e pagina di manutenzione (GAP-J08)

## DNS

| Record | Valore | Note |
|---|---|---|
| `app.<dominio>` A/AAAA | IP pubblico dell'host proxy | TTL 300 s durante il go-live, poi 3600 s |
| `<dominio>` CAA | `0 issue "letsencrypt.org"` + `0 iodef "mailto:<ops>"` | solo la CA usata può emettere |
| SPF/DKIM/DMARC | dal provider email (s3) | `p=quarantine` poi `p=reject` dopo 30 giorni di report puliti |

DNSSEC se il registrar lo supporta. Il registrar e l'account DNS hanno MFA e due amministratori (D08).

## Certificati

- Primo rilascio: `SERVER_NAME=app.<dominio> ACME_EMAIL=<ops> scripts/tls-bootstrap.sh`
  (prima con `ACME_STAGING=1`). Verifica che la challenge HTTP-01 sia raggiungibile prima di chiedere il
  certificato, rilascia ECDSA, riavvia il proxy in HTTPS e avvia il servizio `acme`.
- Il proxy senza certificato serve solo HTTP (challenge ACME + app); con certificato attiva HTTPS, redirect
  301 da HTTP e HSTS (`HSTS_SECONDS`, default 1 h; portare a 1 anno dopo una settimana senza problemi su tutti
  i sottodomini; preload solo con decisione esplicita, s1).
- TLS 1.2/1.3, OCSP stapling, nessun protocollo legacy (`infra/nginx/conf.d/https.conf.template`).

### Rinnovo

Il servizio `acme` (profilo `tls`) esegue `certbot renew` ogni 12 h (rinnovo a 30 giorni dalla scadenza);
nginx ricarica i certificati ogni 6 h (`TLS_RELOAD_INTERVAL`). Alert `CertificatoTLSInScadenza` a 14 giorni
dal probe esterno (blackbox). Se scatta:

1. `docker compose -f compose.prod.yaml --profile tls logs --since 48h acme` (rate limit? challenge non raggiungibile? DNS cambiato?);
2. rinnovo forzato: `docker compose -f compose.prod.yaml --profile tls run --rm acme renew --force-renewal --webroot -w /var/www/acme`
   (con `--entrypoint certbot`), poi `docker compose -f compose.prod.yaml exec proxy nginx -s reload`;
3. verifica: `echo | openssl s_client -connect app.<dominio>:443 -servername app.<dominio> 2>/dev/null | openssl x509 -noout -enddate`.

Certificati privati (DB, Redis): conformi a `VERIFY_X509_STRICT` (Python 3.13: CA con keyUsage `keyCertSign`,
foglie con Authority/Subject Key Identifier e basicConstraints), altrimenti le connessioni falliscono con
"certificate unknown". Scadenze in calendario OPS 30 giorni prima.

## Pagina di manutenzione

`scripts/maintenance.sh on|off|status`: crea/rimuove il file `on` nel volume `maintenance`; il proxy risponde
503 con `maintenance.html` (senza dipendenze esterne, `Retry-After`) a tutte le richieste tranne la challenge
ACME. Usarla per restore, migrazioni lunghe, incidenti di sicurezza. Annunciarla alle famiglie (CEN) se
programmata: finestra consigliata fuori dagli orari di lezione (D06/D08).
