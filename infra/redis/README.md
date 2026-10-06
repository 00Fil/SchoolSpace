# Redis privato (GAP-J04)

Trasporto per Celery e cache condivisa (rate limit): **non** è fonte di verità; job, outbox e
lease stanno in PostgreSQL e i reconciler li ricostruiscono dopo un riavvio o una perdita.

- `redis-tls.conf`: solo TLS (porta 6380, `port 0`), TLS 1.2+, nessuna persistenza,
  `maxmemory-policy noeviction` (memoria piena = errore visibile e alert, mai perdita silenziosa).
- `users.acl.example`: modello del file ACL. **Redis non accetta commenti nei file ACL**
  (avvio interrotto con "should start with user keyword"): il modello contiene solo righe `user`.
  - `default off`: nessun accesso anonimo;
  - `app` (web, worker, beat): tutto tranne `@dangerous` (FLUSHALL, CONFIG, KEYS, DEBUG, ...), più `INFO`;
  - `exporter` (redis_exporter): sola lettura delle metriche.
- `scripts/redis-acl.sh` genera `./secrets/redis-users.acl` con password casuali (salvate come
  SHA-256 nel file, mostrate una sola volta per il secret manager).

Redis gestito UE: stesse regole (TLS obbligatorio, AUTH/ACL, rete privata, nessuna eviction
delle chiavi del broker). URL applicative: `rediss://app:<password>@host:6380/0` (broker) e `/1`
(cache); CA privata via `REDIS_CA_PATH`.
