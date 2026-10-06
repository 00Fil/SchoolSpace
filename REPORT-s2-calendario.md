# REPORT s2-calendario

Branch `s2-calendario`, worktree `/data/work/s2-calendario`. `main` integrato (s1, s3, s4) con `git merge main`; conflitti risolti in `config/settings.py` e `config/urls.py` (tenuti entrambi i lati; rimossa una route `admin/` incondizionata lasciata dal merge, che rompeva `test_security_settings`).

## GAP chiusi (codice + test)
| GAP | Implementazione | Test |
|---|---|---|
| **E01** serie | `LessonSeries` + `recurrence.py` (WEEKLY/INTERVAL/BYDAY/UNTIL, resto → `RRULE_UNSUPPORTED`), chiavi stabili `series:<root>/<data>`, EXDATE, override "solo questa", split "questa e successive" (`carried`), DST/`INVALID_LOCAL_TIME`, proiezione come lock nella generazione, collegamento alla pubblicazione, limite `sessions_per_week` | `test_calendar_recurrence.py` (T12, proprietà hypothesis), `test_calendar_series.py` (T13 nessun duplicato, T14 split) |
| **E02** spostamenti | `operations.py`: move tra settimane, modify (tutor/spazio/modalità/video), swap atomico; validatore indipendente per ogni settimana toccata, unità sintetiche | `test_calendar_moves.py` |
| **E03** recuperi | `RecoveryObligation` canonico per lezione d'origine, makeup unico, cancellare il makeup riapre lo stesso obbligo, waive, gruppi parziali, minuti a catalogo | `test_calendar_recovery.py` (T40) |
| **E04** presenze | `Attendance` per partecipante, `AttendanceRevision` append-only, COMPLETED (makeup → FULFILLED), correzione amministrativa confermata e auditata | `test_calendar_attendance.py` (T30) |
| **E05** pratiche | `ConflictCase` automatiche (segnali post-commit + comando/endpoint detect), risoluzione solo centro (CANCEL/RESCHEDULE/CONFIRM rivalidata), `ChangeRequest` con scope (404 fuori scope), decide/apply atomico, withdraw; warnings in `/calendar/` | `test_calendar_conflicts.py` (T41) |
| **E06** orizzonte | `HorizonProposal` BLOCKED/COVERED/PROPOSED, idempotente per (settimana, revisione), job Celery beat + management command + endpoint; mai pubblicazione | `test_calendar_lifecycle.py` |
| **E07** stato piano | `PlanReview` esterno a `SchedulePlan` (immutato, `apps/scheduling` non toccato): DRAFT→VALIDATED/STALE/REJECTED→PUBLISHED, validate/reject/lifecycle, setting validazione esplicita | `test_calendar_lifecycle.py` |
| **C07** | `apps/availability/effective.py` + `GET /availability/effective` con diagnostica e scope | `test_calendar_availability_effective.py` |

Trasversali: ogni comando ha CommandReceipt (idempotenza), `expected_version`, motivo, CalendarAudit append-only (ORM + trigger PG), CalendarEvent, notifiche outbox s3 (`apps/calendar/notifications.py`: `lesson.rescheduled/cancelled` via `notify_lesson`, `lesson.makeup_scheduled`, `lesson.completed`, `attendance.corrected`, `recovery.created/waived`, `conflict.opened` e `change_request.submitted` agli account CENTER, `change_request.decided` al richiedente; payload senza membri né link video; chiamate di s3 in `services.py` conservate). PG: migrazione `0005_postgres_protection_v2` (trigger esteso per COMPLETED/makeup, `calendar_completed_immutable`, append-only per audit e revisioni presenze; reversibile).

## GAP parziali / limiti
- Cambio di modalità limitato agli `allowed_modes` della richiesta; tutor del makeup tra gli `allowed_tutors` della richiesta d'origine.
- Recupero parziale di minuti solo per durate a catalogo; nessun saldo multiplo per obbligo.
- RRULE solo settimanale; solo Europe/Rome. Override solo su istanze non materializzate (per quelle materializzate si usa move/modify).
- Rilevazione automatica: i `QuerySet.update` non emettono segnali → coperti dal job orario `calendar-conflicts` e da `/conflict-cases/detect/`.
- Lo staff reale passa dal gate MFA di s1; i test usano `force_authenticate` (DRF) come `tests/test_calendar.py`, quindi non esercitano il gate.

## File toccati fuori ownership
- `backend/config/urls.py` (blocco `# --- s2-calendario ---` + 2 import), `backend/config/settings.py` (blocco `# --- s2-calendario ---`).
- `backend/api/calendar.py`: `LessonSerializer` aggiunge `series`, `recurrence_key`, `recovery`, `warnings`; annotazioni Count nel queryset di `CalendarView`.
- `backend/tests/calendar_helpers.py` (helper condivisi dei nuovi test, nessun test).
- `docs/calendar.md` (sezione aggiunta in coda), `backend/apps/calendar/README.md`.

## Settings / URL / requirements
- Settings (default prudenziali, **da approvare**): `CALENDAR_REQUIRE_EXPLICIT_VALIDATION=0`, `CALENDAR_HORIZON_WEEKS=6`, `CALENDAR_RECOVERY_POLICY="EXPLICIT_ONLY"` (D06), `CALENDAR_AUTO_CONFLICT_DETECTION=1`, `CALENDAR_TUTOR_RECORDS_ATTENDANCE=1`, `CALENDAR_HORIZON_ACTOR=""` (job disabilitato se vuoto); beat `calendar-horizon` (giornaliero), `calendar-conflicts` (orario).
- URL: `occurrences/swap|{id}/move|modify|recovery|attendance|complete|admin-correction`, `recovery-obligations/…`, `lesson-series/…`, `conflict-cases/…`, `change-requests/…`, `schedule-plans/{id}/validate|reject|lifecycle`, `calendar/horizon/`, `availability/effective`.
- Requirements: nessuna modifica, **nessuna nuova dipendenza** (hypothesis già in requirements-dev).

## Risultati test
- Nuovi file: 62 funzioni di test → 80 casi su SQLite + 4 PG-only (skipped su SQLite).
- SQLite, suite completa: **563 passed, 19 skipped, 2 failed** (5:35). I 2 falliti sono `tests/test_families_api.py` e falliscono identici su `main` (vedi rischi). Il flaky noto `test_solver` è passato.
- **PostgreSQL 17 reale** (cluster temporaneo locale in /tmp, socket): `tests/test_calendar.py` 47 passed (inclusi i test GiST/trigger/concorrenza baseline con la 0005 installata); `tests/test_calendar_*.py` 79 passed; `tests/test_calendar_pg.py` 4 passed; `tests/test_privacy_postgres.py` passed.
- `ruff check --select E9,F63,F7,F82 .` e `ruff format --check .` puliti; `manage.py check` senza problemi; `makemigrations --check` nessuna modifica.

## Rischi / punti aperti
- Pre-esistenti su `main` (non dipendono da s2): `tests/test_families_api.py::test_invitation_single_use_and_secret_never_audited` e `::test_expired_and_revoked_invitations` falliscono anche su `main` (400 invece di 200/410).
- Su PostgreSQL reale `tests/test_communications_calendar.py::test_meeting_link_only_authorized_and_in_window` (s3) fallisce: il test forza con `QuerySet.update` una lezione IN_PERSON a ONLINE senza canale video e il trigger **baseline** 0002 (`Lesson inconsistent with canonical snapshot unit`) lo rifiuta; su SQLite passa. Da correggere in s3 (usare una lezione online coerente).
- D06 (politica recuperi), validazione esplicita obbligatoria, permesso presenze ai tutor, orizzonte di 6 settimane: decisioni aperte, default prudenziali.
- Il job orizzonte crea run di bozza (`submit_run`) che richiedono un worker: in assenza di Redis restano QUEUED (come i run manuali).
- Le unità sintetiche (lezioni spostate tra settimane/makeup) dipendono dallo snapshot d'origine: se la richiesta esce dal periodo → `OUTSIDE_REQUEST_PERIOD`.
