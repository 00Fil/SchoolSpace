# REPORT s8-solver

Branch `s8-solver`, base `a2fe972` (v0.7). Build solver 0.8.0, contratto pianificazione 0.5 (0.4 resta accettato con semantica storica, archiviato in `contracts/versions/`).

## GAP chiusi (codice + test)
- **D01** orizzonte fino a 6 settimane locali (`horizon_days` ≤ 42, ≤ 60.540 min con DST); limiti 0.5 di default 720 unità / 10 tutor / 120 studenti / 150.000 candidati, configurabili in `limits` (superamento → BLOCKED). Fixture `contracts/fixtures/planning-benchmark-720.json` (generata da `apps/scheduling/benchmark.py`). Bridge DB multi-settimana (`PlanningPolicy.horizon_weeks` 1–6).
- **D02** vettore lessicografico P0,P1,P2,F,C,R,P,G a fasi CP-SAT (fissa un livello solo dopo OPTIMAL, hint tra fasi); valutazione indipendente in `objectives.py` (discordanza → OBJECTIVE_MISMATCH); policy di equità versionata `fairness-default` v1 e ordine obiettivi marcati PENDING_APPROVAL (D03), riportati in `policy_approvals`/`warnings`.
- **D03** stabilità slot ricorrente: modello `LessonSeries` (migrazione 0003), `series` REQUIRED/PREFERRED nel DTO, obiettivo C, azione `POST /schedule-plans/{id}/derive-series/` con audit.
- **D04** H11: `family_constraints` SAME_START/SAME_INTERVAL/SAME_DAY/DIFFERENT_DAYS/NO_OVERLAP; H12: `sequences` curricolari ed `enrollments`; tutti verificati anche dal validatore.
- **D05** ripianificazione locale: `POST /schedule-runs` con `unlock:[{lesson_id,reason}]` autorizzato e registrato (PlanningAudit `authorize_unlock`), `previous_assignment`, obiettivo R; `propose_scope_expansion` produce `scope_expansion` solo come proposta.
- **D06** diagnostica: `hypotheses` MOVE_WITHIN_DECLARED vs REQUEST_NEW_AVAILABILITY (sempre `booking_allowed=false`, budget 3 s); `conflict_analysis` con sottomodelli isolati e `sufficient_assumptions` (non unsat core minimo).
- **D07** studente online dalla sede (finestra `location`, `student_space_id`), buffer studente e lezioni oltre mezzanotte modellati e validati (0.4 continua a rifiutarli esplicitamente).
- **D08** `manage.py benchmark_solver` (sottoprocesso per run, CPU/RSS da `wait4`, esiti); eseguito 20 run → `docs/evidence/v0.8-solver-benchmark.{md,json}`.
- **D09** `tests/test_solver_celery.py`: ordine soft<hard, soft limit → FAILED/SOFT_TIME_LIMIT, heartbeat fasi, hard kill riconquistato con fence, tentativi esauriti (3), perdita broker e recupero; test prefork reale con Redis skip senza `SOLVER_TEST_REDIS_URL`.
- **D10** `tests/test_solver_properties.py` (hypothesis): normalizzazione/sottrazione/intersezione intervalli, domini di inizio vs forza bruta, sweep di contenimento, proposta valida e riconciliazione domanda, idempotenza/hash, validatore che rifiuta proposte alterate.
- **Flaky** `test_real_cp_sat_demo_valid_complete`: budget 10 s e verifica che OPTIMAL sia raggiunto con `search_seconds` < budget; il budget in test dedicato usa un orologio finto. Il senso (prova di ottimalità sul demo) resta.

## Benchmark (20 run, 6 settimane, 720 unità, 1 worker, budget 30 s, macchina 2 CPU condivisa)
20/20 FEASIBLE con P0 OPTIMAL (~8 s) e P1 FEASIBLE a fine budget; 20/20 validatore PASSED; 0 obbligatorie non assegnate; 496 assegnate / 224 non assegnate (fixture volutamente sovraccarica); 122.616 candidati, ~155k variabili. Wall end-to-end min 44.4 / mediana 46.2 / p95 47.3 / max 49.1 s (20/20 entro 60 s); build 10.1–14.1 s; ricerca 30.8–32.4 s; diagnostica ~3.2 s; CPU mediana 45.2 s; RSS picco mediana 1.25 GB, max 1.26 GB.

## Parziali / rischi
- Ottimalità dell'intero vettore non provata entro 30 s sulla fixture 720 (solo P0): coerente con NFR04 ma da segnalare. La ricerca supera il budget di ~1–2 s (overhead di fase).
- F/C/R/P/G e posizione dell'equità sono politiche da approvare (D03); G è un proxy (giorni attivi per partecipante), non la frammentazione completa del paper.
- Pubblicazione nel calendario sintetico resta per una settimana (`active_week`, proprietà s2): una proposta multi-settimana va pubblicata settimana per settimana.
- Test Redis/prefork reale e test PostgreSQL non eseguiti qui (skip); RSS ~1.25 GB per run su 4 GB condivisi.
- Benchmark eseguito con altri agenti attivi (load 2–4): tempi indicativi.

## File fuori proprietà / configurazione
- Toccati fuori elenco: `docs/planner.md`, `docs/database-planning.md`, `docs/changelog.md`, `docs/evidence/v0.8-solver-benchmark.*`, `contracts/versions/*.v0.4.schema.json` (archivio), `REPORT-s8.md`.
- Nessuna modifica a settings e urls. Requirements: dichiarato `hypothesis>=6.100,<7` in `backend/requirements-dev.in` e fissati `hypothesis==6.168.3`, `sortedcontainers==2.4.0` in `requirements-dev.txt` (già installati in `/data/venv`, nessuna installazione eseguita). Nessuna dipendenza runtime nuova.

## Test
- Suite completa backend (SQLite): **300 passed, 9 skipped** in 76.6 s (skip: PostgreSQL reale, Redis/prefork reale).
- Nuovi: `test_solver_v05.py` 36, `test_planning_v05_db.py` 6, `test_solver_celery.py` 6 + 1 skip, `test_solver_properties.py` 7.
- `test_database_planning.py::test_config_strict_fields`: il valore fuori range passa da 30 a 31 (30 s ora ammesso, NFR04).
- `ruff check --select E9,F63,F7,F82` e `ruff format --check` puliti; `manage.py check` 0 problemi; `makemigrations --check` nessuna modifica.
