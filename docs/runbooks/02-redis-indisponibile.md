# 02 — Redis indisponibile

**Alert**: `RedisGiu` (SEV2), `RedisMemoriaAlta` (SEV3); spesso insieme a `HeartbeatWorkerAssente`.
**Impatto**: Redis è solo trasporto (broker Celery) e cache dei rate limit. Nessun dato perso:
run, outbox, consegne e lease sono in PostgreSQL. Durante il guasto: `/readyz` e `/api/v1/ready`
rispondono 503 (il proxy continua a servire l'app), i job restano in attesa, il login
**fallisce chiuso**: il rate limit (s1) usa la cache e, senza Redis, la richiesta di login termina in
errore 5xx invece di aggirare il limite. Le sessioni già aperte restano valide (sessioni nel DB).

## Diagnosi

```bash
docker compose -f compose.prod.yaml ps redis
docker compose -f compose.prod.yaml logs --since 30m redis | tail -50
docker compose -f compose.prod.yaml exec web python manage.py ops_check --checks cache,broker
```

Cause tipiche: memoria piena (`maxmemory 256mb`, `noeviction` → errori `OOM command not allowed`),
certificato TLS di Redis scaduto o non conforme (Python 3.13 richiede estensioni X.509 strette: AKI,
keyUsage della CA), file ACL non valido (Redis **non** accetta commenti nell'ACL e non parte), password ruotata
in una sola parte.

## Intervento

1. Riavvio: `docker compose -f compose.prod.yaml restart redis`. Web e worker si riconnettono da soli
   (verificato in `scripts/e2e_local.py`, scenario `redis_restart`): **non** riavviarli.
2. Memoria piena: individuare le code cresciute (`redis-cli --tls ... -n 0 LLEN solver`, `notifications`),
   risolvere il worker fermo che non consuma, poi aumentare `maxmemory` se serve. Mai `FLUSHALL` sul DB 0
   (broker): perdere i messaggi è comunque recuperabile (vedi 3), ma non necessario.
3. Dopo il ripristino i reconciler del beat rimettono in coda run e consegne non consegnate al broker
   (`apps.scheduling.tasks.reconcile`, `dispatch.reconcile` delle comunicazioni). Forzare subito, se serve:
   `docker compose -f compose.prod.yaml exec web python manage.py dispatch_communications`.
4. Verifica: `ops_check` verde, heartbeat di tutte le code < 60 s, backlog outbox in calo.
