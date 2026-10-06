# 01 — Solver bloccato o fallito

**Alert**: `HeartbeatWorkerAssente{queue="solver"}` (SEV2), `RunOltreLimiteHard` (SEV2),
`ValidatoreRespingeSolver` (SEV2), `CodaSolverFerma` (SEV3).
**Impatto**: nessuna nuova proposta di orario; calendario pubblicato e portali **non** toccati.

> In produzione la pianificazione è disattivata finché G3 non la abilita (`EXPERIMENTAL_DB_PLANNING`
> vietato da `config.settings_production`): fino ad allora questi alert indicano solo il worker fermo.

## Diagnosi (5 minuti)

```bash
docker compose -f compose.prod.yaml ps worker-solver beat
docker compose -f compose.prod.yaml logs --since 30m worker-solver | tail -50
docker compose -f compose.prod.yaml exec web python manage.py ops_check --checks broker,workers
```

- heartbeat assente su **tutte** le code → beat o broker fermi ([02](02-redis-indisponibile.md));
- solo `solver` → worker morto (OOM: `docker inspect --format '{{.State.OOMKilled}}'`), bloccato o in crash loop;
- `RunOltreLimiteHard` → un run supera il limite hard (90 s) ma il worker è vivo: probabile blocco nel
  processo figlio; `ValidatoreRespingeSolver` → il solver ha prodotto una soluzione invalida
  (bug: **non** ripubblicare a mano, aprire incidente con l'`id` del run dai log `error_code=VALIDATION_FAILED`).

## Intervento

1. Riavvio del worker (sicuro: `acks_late` + lease nel DB, il run interrotto torna in coda o va in
   `FAILED` con motivo, mai mezzo applicato):
   `docker compose -f compose.prod.yaml restart worker-solver`.
2. Se OOM ripetuti: alzare `deploy.resources.limits.memory` di `worker-solver` (benchmark G3) o
   ridurre l'orizzonte del run; tenere `--concurrency=1`.
3. Verificare il recupero: `ops_check --checks workers` verde entro 1-2 min; i run `QUEUED` riprendono
   (il reconciler `apps.scheduling.tasks.reconcile` del beat recupera i lease scaduti).
4. Run rimasti `RUNNING` oltre il limite dopo il riavvio: il reconciler li porta in `FAILED`
   (`LEASE_EXPIRED`); l'utente del centro riprova dalla UI.

## Chiusura

Alert rientrato, nessun run `RUNNING` più vecchio di 5 min, nota nel registro incidenti.
