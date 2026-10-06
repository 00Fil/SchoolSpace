# REPORT s5-infra — esercizio, osservabilità, backup/restore, CI/CD

Branch `s5-infra` (merge di `main` 6bad967 con s1/s3/s4 incluso). Tutte le decisioni D08/D09 sono
parametri **da approvare** (valori di default prudenti).

## GAP chiusi

| GAP | Cosa | Evidenza |
|---|---|---|
| J03 | Immagini multi-stage (`infra/backend.Dockerfile` da `requirements.txt --require-hashes`, utente 10001, gunicorn, healthcheck; `infra/frontend.Dockerfile` nginx non root con CSP a hash), `compose.prod.yaml` (read-only, cap_drop ALL, no-new-privileges, limiti, job `migrate` separato, worker `solver` e `notifications,default`, beat singolo, Redis TLS+ACL, ACME), `scripts/deploy.sh` | `tests/test_infra_config.py`, `tests/test_infra_nginx.py` (nginx reale), `docker compose config` |
| J06 + I04 | Lock con hash, `scripts/check-lock.py` (freschezza semantica), pip-audit e npm audit bloccanti, bandit (baseline), gitleaks (storia completa, eccezioni solo sintetiche), Trivy, SBOM CycloneDX, Dependabot, Actions fissate per SHA | pip-audit 0 vuln, npm audit 0, gitleaks "no leaks", bandit 0 nuovi |
| J07 | `scripts/e2e_local.py` (senza Docker, eseguito) e `scripts/e2e-compose.sh` (CI): PG17 TLS verify-full + Redis TLS/ACL + gunicorn `settings_production` + Celery + nginx HTTPS; broker giù all'avvio, riavvio Redis, kill -9 worker (rilevato in 44 s), manutenzione, log redatti, minimo privilegio DB | `docs/evidence/e2e-local-20261002T192629Z.json` (12/12 ok) |
| K01 (+I07) | Log JSON redatti con correlation_id (anche Celery e `django.request`), actor pseudonimo, route template, niente query string | test ops, scenario `logs_redacted` |
| K02/K03 | `/metrics` protetto (HTTP, dominio, solver, heartbeat, backup, capacità DB, outbox/consegne), 27 regole Prometheus (registrazione + alert) con runbook e test promtool, Alertmanager | `promtool test rules` SUCCESS, `amtool check-config` |
| K04 | Probe esterno `/api/v1/ready` anonimo, blackbox, `docs/infra/uptime-monitor.md` | — |
| L01 | `scripts/backup.sh`: pg_dump -Fc, verifica TOC, SHA-256, cifratura age a chiave pubblica, manifest, upload, retention, stato + textfile metric, ruolo `app_backup` | `tests/test_ops_scripts.py` (stub + reale) |
| L02 | PITR del fornitore documentato con procedura e obiettivi RPO 15 min/RTO 4 h | `docs/runbooks/06-restore.md#pitr` |
| L03 | `scripts/restore-drill.sh` (rifiuto prod, DB nuovo, ruoli/privilegi/trigger s4, `04_verify`, invarianti SQL, `post_restore_reconcile` dry-run, RPO/RTO) + `post_restore_reconcile` integrato con identity, privacy (s4), communications (s3), calendario | drill reale PG 17.10: `docs/evidence/restore-drill-20261002T185536Z.json` |
| L04 | Runbook (ruoli, SEV, 6 scenari, rilascio/rollback, controlli periodici), art. 33 72 h | `docs/runbooks/` |
| M01 | `scripts/loadtest/locustfile.py` (25 utenti, soglia p95 500 ms, exit≠0) | e2e locale: 2063 letture, 0 errori, p50 13 ms, **p95 28 ms** (login escluso) |
| J08 | DNS/CAA, `scripts/tls-bootstrap.sh`, rinnovo ACME, `scripts/maintenance.sh` | `docs/infra/dns-tls-manutenzione.md` |
| J04 | PG17 gestito (rete privata, verify-full, btree_gist pre-creato, ruoli s4) e Redis privato TLS/ACL | `docs/infra/database-redis.md`, `infra/redis/README.md` |

## Parziali / non verificabili qui

- `scripts/e2e-compose.sh`, build immagini, Trivy, SBOM e workflow GitHub **non eseguiti** (niente Docker/Actions nella sandbox): validati con `docker compose config`, YAML e test statici. Lo stesso percorso è stato eseguito senza Docker (`e2e_local.py`).
- Pianificazione/solver disattivati in produzione (flag sperimentali vietati da s1): kill del worker *durante un run* e carico sulle viste di pianificazione non provati; coperti dai test di lease/reconcile esistenti.
- Error tracking (K01): solo requisiti (`docs/infra/observability.md`), servizio da scegliere (D08). Ruoli/contatti dei runbook da assegnare (D08).
- CD: `deploy.sh` testato con docker finto (successo, backup vecchio bloccante, rollback su smoke e su healthcheck); deploy reale non provato.

## File fuori proprietà s5 toccati

- `backend/config/settings.py`: blocco `# --- s5-infra ---` (app ops, middleware in testa, LOGGING, OPS_*, heartbeat beat).
- `backend/config/settings_production.py` (s1): blocco s5 in coda (DEPLOY_ENVIRONMENT, BUILD_VERSION, OPS_METRICS_TOKEN, SECURE_REDIRECT_EXEMPT per probe, CA Redis, code/route Celery, heartbeat). `check --deploy` resta a 0 avvisi (test).
- `backend/config/urls.py`: `path("", include("apps.ops.urls"))`.
- `backend/requirements*.in/.txt`: aggiunte `prometheus-client==0.26.0` (runtime) e `PyYAML==6.0.3` (dev) con hash.
- `.gitignore` (`.e2e/`), `.gitleaks.toml`, `.shellcheckrc`; `.github/workflows/core.yml` sostituito da `ci.yml` + `cd.yml`.
- `backend/tests/test_infra_nginx.py`: harness spostato in `infra/nginx/local_layout.py` (riuso e2e).
- Nessuna modifica a `infra/postgres/` (s4): usati in CI, compose e drill.

## Nuove dipendenze

Runtime: `prometheus-client`. Dev: `PyYAML`. Installati additivamente in `/data/venv`: prometheus-client, PyYAML (gunicorn già presente). Strumenti solo in `/tmp` (non nel repo): pip-tools, bandit, shellcheck-py, locust, age, promtool/amtool, docker-compose, gitleaks; pacchetti di sistema nginx, postgresql17, redis6 (per i test reali).

## Risultati dei test

- Suite completa SQLite: **568 passed, 16 skipped, 2 failed** (167 s). I 2 falliti sono `tests/test_families_api.py::test_invitation_single_use_and_secret_never_audited` e `::test_expired_and_revoked_invitations`: **falliscono identici su `main` 6bad967** (risposta 400 `INVALID_TOKEN` invece di 200/410) → s1/s4.
- Suite su PostgreSQL 17.10 reale: 546 passed, 17 skipped, gli stessi 2 falliti.
- ruff check/format, `manage.py check`, `makemigrations --check`: puliti. shellcheck pulito. promtool/amtool SUCCESS.

## Rischi e segnalazioni

1. **Redis non accetta commenti nei file ACL**: il vecchio modello avrebbe impedito l'avvio in produzione (corretto; trovato dall'e2e).
2. **Python 3.13 VERIFY_X509_STRICT**: CA private di Redis/DB senza AKI/keyUsage falliscono ("certificate unknown"); requisito documentato.
3. s1: senza Redis il login risponde 5xx (throttle non gestisce errori di cache): fail-closed ma poco leggibile; valutare 503 esplicito.
4. s3: bandit B310 su `apps/communications/providers.py` (urlopen da URL di configurazione) in baseline: validare lo schema https e motivare `nosec`.
5. s4: `app_readonly` non legge le sequenze → pg_dump fallisce: aggiunto `app_backup` (`scripts/sql/backup-role.sql`, `pg_read_all_data`).
6. Rate limit proxy API 20 r/s per IP: 25 utenti dietro un NAT con poco tempo di attesa possono raggiungerlo; login 10/min per IP. Tarare in staging.
7. CI non ancora eseguita su GitHub: il primo run può richiedere aggiustamenti (pacchetti apt, permessi, SHA delle Actions verificati il 2026-10-02).
8. s6: lo sprite SVG usa `style` inline via innerHTML (violazione CSP `style-src`, innocua ma rumorosa nei report).
