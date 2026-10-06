# Osservabilità (GAP-K01, K02, K03)

## Log

- JSON su stdout (`apps.ops.logs.JsonFormatter`), una riga per evento: `ts`, `level`, `logger`, `message`,
  `correlation_id`, `actor_id` (pseudonimo HMAC, non l'id reale), `build`, `env` e campi specifici.
- Access log applicativo (`ops.access`, `http.request`): metodo, **route template** (mai il path con id né la
  query string), stato, durata, esito. L'access log di gunicorn è disattivato; nginx registra `$uri` senza query
  (il token ICS `?token=ics_...` non finisce mai nei log).
- Redazione (`RedactFilter`) su messaggi e campi: email, bearer/JWT, `token=`, segreti opachi ≥ 32 caratteri,
  `ics_...`, codici fiscali, IBAN, telefoni, URL ridotte all'host; chiavi sensibili (`password`, `secret`,
  `authorization`, `cookie`, ...) sostituite da `[REDACTED]`. Verificato end-to-end (`e2e_local.py`, scenario
  `logs_redacted`).
- Correlazione: `X-Request-ID` dal proxy (o generato), propagato ai task Celery (header del messaggio) e ai
  log del worker.
- Conservazione: driver `json-file` con rotazione (10 MB × 5) sull'host; spedizione a un archivio log UE con
  retention 30 giorni (D09) — **da scegliere** (D08): Loki self-hosted o SaaS UE.

## Metriche

`/metrics` (solo rete interna, `Authorization: Bearer $OPS_METRICS_TOKEN`; 404 dal proxy): HTTP per route,
domain events, run del solver, heartbeat per coda, backup, capacità DB, outbox e consegne. Regole e test:
`infra/monitoring/` (`promtool test rules`). Stack opzionale: `infra/monitoring/compose.monitoring.yaml`.

## Error tracking (parziale)

Non integrato nel codice: la scelta del servizio (Sentry self-hosted o SaaS con dati nell'UE) è D08. Requisiti
per l'integrazione: `send_default_pii=False`, scrubbing con le stesse regole di `apps.ops.logs.redact_text`,
nessun corpo di richiesta, release = `BUILD_VERSION`, ambiente = `DEPLOY_ENVIRONMENT`, campionamento delle
transazioni ≤ 10 %. Fino ad allora gli errori 5xx sono nei log JSON (`level=ERROR`) e nell'alert
`ErroriServer5xx`.
