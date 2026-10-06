# REPORT — stream s3-comunicazioni

Branch `s3-comunicazioni` (worktree `/data/work/s3-comunicazioni`). Documentazione tecnica
completa: `docs/communications.md`.

## GAP chiusi (codice completo + test)

| GAP | Cosa | Test principali |
|---|---|---|
| **F01** | `OutboxEvent` + `Delivery` scritti da `services.emit()` nella transazione di dominio (rifiuta chiamate fuori da `atomic`); accodamento Celery solo `on_commit` (coda `notifications`); reconciler periodico (beat 30 s) + `manage.py dispatch_communications [--inline]`; chiave UQ `event+recipient+channel`; retry con backoff esponenziale ed equal jitter (30 s→1 h, max 6); stati `PENDING/SENDING/SENT/AMBIGUOUS/DEAD/SKIPPED/CANCELLED`, dead-letter con risoluzione manuale del centro; lease per worker morti; `DeliveryAttempt` append-only; replay idempotente (stessa chiave = nessun effetto, payload diverso = `OutboxConflict`). **T22**: crash dopo commit prima di accodare → recuperato (unitario e con pubblicazione reale). Broker giù → obbligo persistente. | `test_communications_outbox.py` (25 + 2 PG) , `test_t22_*` in entrambi i file |
| **F02** | Astrazione provider (`sink`/`smtp`/`api`) da env; backend reali rifiutati fuori da `COMMUNICATIONS_ENV=production` (runtime + system check E002); mappatura errori transitori/permanenti/ambigui; un destinatario per messaggio, `Message-ID` dalla chiave, `Idempotency-Key` per API; template italiani (pubblicata/spostata/annullata + generico, orari Europe/Rome, DST testato). **T23**: risposta persa → `AMBIGUOUS` → lookup → `SENT` senza reinvio; esito ignoto e provider non idempotente → dead-letter "da verificare" (nessuna falsa exactly-once); policy `retry` esplicita e configurabile. SPF/DKIM/DMARC documentati. | `test_communications_email.py` (32) |
| **F03** | Notifiche interne deduplicate (UQ `event+recipient`); `GET /notifications` (solo proprie, filtri, `unread_count`, consegne email pendenti), `POST /notifications/{id}/read`, `/read-all`; `GET/PUT /notifications/preferences` (servizio in-app obbligatorio); categoria `MARKETING` separata e disabilitata. | `test_notifications_api_*`, `test_preferences_*`, `test_marketing_*` |
| **F04** | Token ICS `ics_…` mostrato una volta, salvato solo come SHA-256, revocabile, a scadenza, max 3; `GET /calendar.ics?token=` minimizzato con perimetro ricalcolato a ogni richiesta (revoca delega/account immediata); `GET /occurrences/{id}/meeting`: 404 fuori perimetro, solo online pubblicate, finestra −15 min → fine, `expires_at`, `no-store`; mai nell'ICS. Modello `MeetingLink` (per lezione o canale) gestito in admin. | `test_ics_*`, `test_meeting_*` |
| **F05** | Guardia sui payload (niente elenchi di persone, recapiti, link, oggetti annidati); contesto per destinatario solo con i propri studenti; test end-to-end che nessun payload/contesto/notifica/email contenga il link video o nomi di studenti altrui. | `test_payload_guard_*`, `test_f05_*`, `test_recipients_get_only_their_own_students` |

API pubblica per gli altri stream: `apps.communications.services.emit(event_type, payload,
recipients, *, idempotency_key, category="SERVICE", channels=(...), subject_ref="")`
con `Recipient(account, context)`; vedi esempio in `docs/communications.md`.

## GAP parziali / cosa manca
- F02: scelta del fornitore UE, DNS SPF/DKIM/DMARC reali e contratto art. 28 (D08/H03) —
  solo requisiti documentati. Gestione webhook bounce/complaint non implementata.
- F04: scadenza effettiva del link lato provider video (stanze per lezione) dipende da D08;
  il backend lo limita solo in consegna. Nessun audit degli accessi a `/meeting`.
- Retention consegne/notifiche (proposta 90 gg, D09) senza job di purge (coordinare con s4/H04).
- OpenAPI (`contracts/openapi.yaml`) e UI frontend per notifiche/preferenze/ICS non aggiornati.

## File toccati fuori dalla mia proprietà
- `backend/apps/calendar/services.py`: import + 2 chiamate `notify_lesson(...)` (dopo ogni
  `CalendarEvent` di pubblicazione e di spostamento/cancellazione). Nessun'altra modifica;
  le risposte dei comandi sono invariate (`notifications_sent: False` resta vero: l'invio è asincrono).
- `docs/communications.md` (nuovo file).

## Settings / urls / requirements
- `config/settings.py`: blocco `# --- s3-comunicazioni ---` in coda (INSTALLED_APPS,
  `COMMUNICATIONS_*`, beat `communications-reconcile` su coda `notifications`).
- `config/urls.py`: 1 import + 10 path nel blocco `# --- s3-comunicazioni ---`.
- Requirements: invariati. **Nessuna nuova dipendenza** (smtplib/urllib della stdlib).

## Test
- Suite completa (SQLite): **316 passed, 10 skipped, 1 failed** in 4 min 44 s; l'unico
  fallimento è il noto flaky `test_solver.py::test_real_cp_sat_demo_valid_complete`
  (FEASIBLE vs OPTIMAL sotto carico). In un run precedente è fallito una volta anche
  `test_calendar.py::test_normal_sqlite_publication_disabled` in `plan_for` (solver sotto
  carico, nessun codice comunicazioni coinvolto): da solo passa.
- Nuovi: 72 test comunicazioni (+2 PG-only skipped: emit concorrente con stessa chiave,
  worker concorrenti → una sola notifica).
- `ruff check --select E9,F63,F7,F82` ok, `ruff format --check` ok, `manage.py check` ok,
  `makemigrations --check` nessuna modifica; migrazione `communications 0001` reversibile
  (migrate → zero → migrate verificato).

## Rischi / punti aperti (da approvare)
- **Deploy**: il worker Compose consuma solo `solver`; serve un worker
  `celery -A config worker -Q notifications` (container separato) — file infra non miei (s5).
- D07: email agli account studente spenta di default; D08: policy esito ambiguo `verify`
  (default) vs `retry`; email solo a indirizzi verificati (`COMMUNICATIONS_REQUIRE_VERIFIED_EMAIL`).
- Il token ICS viaggia in query string: escludere `/api/v1/calendar.ics` dai log del proxy.
- ~~Delega revocata dopo l'emissione~~: risolto in fase 2 (ricontrollo → `REVOKED`).
- Una pubblicazione genera un evento per lezione (nessun riepilogo aggregato).

## Integrazione (fase 2)
- `git merge main` (6bad967), poi commit d6a7478.
- **Inviti e reset password di s1 passano dall'outbox**. Il token in chiaro vive solo nel
  corpo dell'email. A riposo è un `SealedSecret` cifrato con Fernet (MultiFernet, chiavi
  `COMMUNICATIONS_SEAL_KEYS` oppure HKDF da `SECRET_KEY` e fallback). Il segreto viene
  cancellato quando la consegna arriva a uno stato terminale e il reconcile elimina quelli
  scaduti. Messaggi `essential`: ignorano preferenze e verifica email. Scelta e alternative
  scartate sono in `docs/communications.md`.
- **Ricontrollo dell'autorizzazione prima dell'invio** (in-app ed email), con un registro
  di autorizzatori che nel dubbio nega: `calendar.lesson`, `identity.invitation`,
  `identity.password_reset`. Se l'autorizzazione manca → `REVOKED`
  (`RECIPIENT_NOT_AUTHORIZED`); se il segreto manca o è scaduto → `EXPIRED`.
- Migrazione `communications 0002`, reversibile. Check W002 (manca la chiave seal in
  produzione) ed E004 (chiave non valida).
- `contracts/openapi.yaml`: 10 path e 8 schemi s3. I test di contratto validano le
  risposte reali.
- **Nuova dipendenza**: `cryptography==50.0.2`, con hash in requirements.txt.
- **File fuori proprietà toccati**:
  - `apps/identity/delivery.py`: i sender con `transactional=True` vengono chiamati dentro
    la transazione;
  - `apps/identity/services.py`: `deliver(..., ref=...)`;
  - `tests/test_identity_invitations.py`: fixture che fissa il sender diretto di s1, perché
    quei test leggono `mail.outbox`;
  - `config/settings.py`: `IDENTITY_MESSAGE_SENDER`; requirements; `contracts/openapi.yaml`.
- **Test**: 493 passed, 15 skipped, 3 failed. Oltre al flaky del solver noto, falliscono
  `test_families_api.py::test_invitation_single_use_and_secret_never_audited` e
  `::test_expired_and_revoked_invitations`. **Falliscono anche su main e non dipendono da
  s3**: la rotta s1 `api/v1/invitations/accept` in `config/urls.py` viene registrata prima
  di quella di s4 (`api/families.py`) e risponde 400. Va deciso chi rinomina la rotta
  (s1 o s4).
- **Rischi**:
  - il reset password ora scrive nel DB solo per gli account esistenti: possibile
    differenza di tempi di risposta (enumerazione degli account);
  - `settings_production` eredita `IDENTITY_MESSAGE_SENDER`;
  - serve ancora il worker della coda `notifications` (compito di s5).
