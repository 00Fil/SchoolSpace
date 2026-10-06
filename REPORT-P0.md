# Fase P0 — Produzione senza modalità sperimentali (guida v3.1)

## Fatto
- **T1 — flag di funzione per ambiente.** Nuovo modulo `backend/config/features.py`
  (`planning_enabled`, `calendar_enabled`, `lab_enabled`, codice `FEATURE_DISABLED`).
  Tutte le condizioni `DEBUG and EXPERIMENTAL_*` sono sostituite in: `api/calendar.py`,
  `api/calendar_ops.py`, `api/planning_data.py` (gate, readiness, run, proposte),
  `api/planning.py` (laboratorio), `api/portals_v2.py`, `api/views.py`,
  `apps/calendar/{scope,services,signals,tasks}.py`, comandi `propose_calendar_horizon`,
  `dispatch_pending_runs`, `simulate_plan`.
- **Impostazioni.** `settings.py`: `FEATURE_PLANNING`, `FEATURE_CALENDAR` (alias di lettura dei
  vecchi `EXPERIMENTAL_*` in sviluppo), `FEATURE_PLANNING_LAB` (default = DEBUG).
  `settings_production.py`: `FEATURE_PLANNING=1` e `FEATURE_CALENDAR=1` per default,
  laboratorio spento per default, `EXPERIMENTAL_*` restano vietati. `.env.example` aggiornato.
- **Stati sperimentali rimossi.** `PUBLISHED_EXPERIMENTAL` → `PUBLISHED`;
  `scope: EXPERIMENTAL_DATABASE` → `DATABASE`; `capabilities.reason_code` = `ENABLED` e
  `production_enabled` = valore reale; `confirm_experimental` nella pubblicazione diventa
  facoltativo e senza effetto (compatibilità con i client v0.8), eliminato `EXPERIMENTAL_CONFIRMATION`.
- **T5.** Menu: «Laboratorio» e «Decisioni» marcati `tech` e visibili solo in sviluppo o con
  build `VITE_TECH_ADMIN=1`; la notifica «decisioni aperte» segue la stessa regola.
  Messaggi: `FEATURE_DISABLED`, stato «Pubblicata».
- **Test.** Nuovo `tests/test_feature_flags_nodebug.py` (DEBUG=0). Aggiornati `test_calendar`,
  `test_planning_api`, `test_security_settings`, `test_database_planning`, `test_portals`,
  `test_portals_v2`, `frontend/tests/states.test.ts`.
- **Healthcheck di worker e beat:** già presenti in `compose.prod.yaml`, nessuna modifica.

## Restano DEBUG-only (voluto)
Login provvisorio (`api/views.login_view`), `/metrics` senza token, seed demo
(`seed_planning_demo`, `seed_portal_demo`).

## Da fare per chiudere P0
1. Eseguire la suite completa su PostgreSQL con `DJANGO_DEBUG=0` (in questa sessione le
   dipendenze Python/Node non erano installabili: verificata solo la compilazione dei file).
2. Rigenerare `contracts/openapi.yaml` e `frontend/src/api/schema.gen.ts` (enum `PUBLISHED`,
   `confirm_experimental` non più obbligatorio, `scope`).
3. Avviare `compose.prod.yaml` e verificare calendario, pianificazione e portali (criterio di uscita).
