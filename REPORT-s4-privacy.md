# REPORT — stream s4-privacy

Branch `s4-privacy`. Lingua: italiano per documenti e messaggi, inglese per gli identificatori.
Tutte le durate e azioni legate a D07/D09 sono **configurabili e "da approvare"**: nessuna è presentata come termine legale.

## GAP chiusi (codice + test)

| GAP | Cosa è stato fatto | Test |
|---|---|---|
| **B06** | `api/families.py`: API del centro per famiglie, studenti, deleghe GuardianLink (creazione non verificata → verifica con metodo → permessi → revoca immediata), inviti monouso (solo hash del token, scadenza, revoca, accettazione anonima con risposta uniforme e throttling). Versione attesa e motivo obbligatori; payload rigidi; una delega attiva per coppia (lock + verifica). Audit unificato `governance.AuditEvent` (append-only via ORM e trigger PG) per famiglie, deleghe, inviti, export, import, privacy, retention e **azioni dell'admin Django** (signal su `LogEntry`). Redazione dei segreti (`governance/audit.py`). | `tests/test_families_api.py` (12) |
| **H04** | Matrice D09 in DB (`RetentionPolicy`, seed da migrazione con stato PROPOSED e valori della guida); modifica/approvazione via API con audit (ogni modifica torna "da approvare"). Job `privacy_retention` / `POST /privacy/retention-runs`: dry-run di default, esecuzione solo per categorie APPROVED, ricevuta `RetentionRun` con SHA-256, audit e voce nel ledger esterno. Handler: chiavi di idempotenza, inviti, file degli export (+ file orfani), report di import, account revocati (pseudonimizzazione), audit (minimizzazione solo come owner PG), conteggi per snapshot/calendario/registro; categorie esterne marcate EXTERNAL. Task Celery beat giornaliero (esegue davvero solo con `PRIVACY_RETENTION_AUTORUN=1`). | `tests/test_privacy_retention.py` (12) |
| **H05** | Registro `PrivacyRequest` senza FK verso l'interessato (sopravvive all'anonimizzazione) con pseudonimo HMAC, scadenza a 1 mese e proroga unica di 2 mesi (art. 12.3), verifica identità obbligatoria. Accesso (JSON/CSV), portabilità (solo JSON), rettifica auditata, cancellazione governata = anonimizzazione (studente, account, famiglia quando vuota; revoca deleghe e inviti) con motivazione registrata, chiusura manuale (limitazione/opposizione), rifiuto. **Ledger esterno** JSONL con catena di hash (`PRIVACY_LEDGER_PATH`) + `privacy_reconcile` (riapplica revoche/anonimizzazioni dopo un restore, segnala richieste mancanti; bloccato se la catena è alterata) + `privacy_ledger_verify`. | `tests/test_privacy_rights.py` (9) |
| **H06** | Template CSV versionato `apps/privacy/import_templates/famiglie-v1.csv` (+ `GET /privacy/imports/template/v1`), intestazione esatta, validazione completa prima di scrivere, dry-run in transazione annullata, **nessun invito in dry-run** qualunque sia l'opzione (T17), idempotenza per chiavi naturali (`family_reference`, `student_key`, email, coppia), conflitti se una chiave cambia famiglia, inviti solo con `--create-invites` in esecuzione e solo per deleghe verificate. Comando `privacy_import` e API JSON/multipart. | `tests/test_privacy_import.py` (9) |
| **H07** | `ProtectedExport`: audience nominativa, file 0600 fuori da static/media con nome casuale, SHA-256 del contenuto e del token, scadenza (`PRIVACY_EXPORT_TTL_HOURS`=24), **token monouso nel corpo POST** (mai nell'URL), cancellazione del file dopo il download, revoca, verifica d'integrità, audit di creazione/download/negazione/purge; `Cache-Control: no-store`. T42: segreti artificiali redatti. | `tests/test_privacy_exports.py` (7) |
| **H11 (parte tecnica)** | `privacy_majority_review` + task beat: alla maggiore età segna le deleghe `PENDING` con scadenza (`PRIVACY_MAJORITY_GRACE_DAYS`=30), **senza revoca silenziosa**; alla scadenza `REPORT` (default) o `SUSPEND` auditato (D07). Riconferma/rifiuto da parte dello studente maggiorenne o del centro (API `reconfirm`/`decline`). 29 febbraio → 1° marzo. | `tests/test_privacy_majority.py` (7) |
| **E08** | `infra/postgres/`: `01_roles.sql` (owner/migrator/runtime/readonly, timeout, niente CREATE su public), `02_privileges.sql` (REVOKE UPDATE/DELETE/TRUNCATE su `lesson_calendar_calendaraudit`, `governance_pathauditevent`, `scheduling_planningaudit`, `scheduling_planningsnapshot`, + `governance_auditevent`, `privacy_retentionrun`), `03_append_only_triggers.sql` (generato da `apps/governance/pg_append_only.py`, installato anche dalla migrazione `governance.0004`), `04_verify.sql`, README con sequenza di deploy. | `tests/test_privacy_postgres.py` (3 statici + 4 PG-only skipped) |

## GAP parziali / cosa manca
- **H04**: backup PITR, dump logici e log diagnostici sono marcati EXTERNAL (infrastruttura s5); delivery notifiche spetta a s3 (nessun modello in v0.7). Minimizzazione del payload degli snapshot solo conteggio: il trigger del calendario legge il payload degli snapshot pubblicati.
- **H05**: la notifica ai responsabili (art. 19) e la consegna del token all'interessato sono fuori perimetro (nessun invio reale; il token è restituito una volta all'operatore del centro). Il ledger è su file locale: in produzione va montato su storage separato con object lock (D09/GAP-L03).
- **H07**: nessuna cifratura applicativa del file (nessuna nuova dipendenza): richiede volume cifrato a riposo (J04).
- **B06**: il vincolo "una delega attiva per coppia" è applicato nel servizio, non con indice parziale DB (richiede migrazione in `education`).
- **E08**: test trigger/ruoli da eseguire in CI PostgreSQL; separazione `DATABASES` runtime/migratore nelle impostazioni (proprietà s1/s5).

## Campi nuovi che servirebbero nei modelli identity/education (documentati, non modificati)
Vedi `backend/apps/privacy/README.md`: contatto famiglia, data di nascita, chiave di import, relazione dichiarata, `can_receive_notifications`, `can_request_changes`, verificatore/metodo, attore e motivo della revoca, stato di riconferma — oggi in `FamilyProfile`, `StudentProfile`, `StudentImportKey`, `GuardianLinkDetail` (1:1).

## File toccati fuori dalla proprietà
- `backend/config/settings.py`: blocco `# --- s4-privacy ---` in coda (INSTALLED_APPS += privacy, PRIVACY_*, 2 voci beat).
- `backend/config/urls.py`: 4 righe in coda (`urlpatterns += ...`).
- `.gitignore`: `backend/var/` (directory dati privacy locale).
- `backend/api/_privacy_common.py`: modulo nuovo di utilità condiviso da families.py/privacy.py.
- `backend/apps/governance/apps.py` nuovo (AppConfig con signal admin; label invariata `governance`).
- Integrazione (su incarico): `backend/apps/identity/policies.py` (`active_guardian_links`, `notification_guardian_links`, `can_request_student_changes`, eccezione `CONSENT_REQUIRED` per delega riconfermata); `backend/apps/communications/calendar_hooks.py` (`lesson_recipients` usa `notification_guardian_links`).

## Settings / URL / requirements / dipendenze
- Settings: `PRIVACY_DATA_DIR`, `PRIVACY_EXPORT_DIR`, `PRIVACY_EXPORT_TTL_HOURS`(24), `PRIVACY_LEDGER_PATH`, `PRIVACY_INVITE_TTL_HOURS`(72), `PRIVACY_MAJORITY_GRACE_DAYS`(30), `PRIVACY_MAJORITY_OVERDUE_ACTION`(REPORT), `PRIVACY_RETENTION_AUTORUN`(0).
- URL: `/api/v1/registry/{families,students,guardian-links,invitations}`, `/api/v1/registry/invitations/<id>/{verify-relation,resend,revoke}` (accettazione: endpoint s1 `/api/v1/invitations/accept`), `/api/v1/privacy/{retention-policies,retention-runs,requests,exports,imports,audit-events,majority-review}`.
- Migrazioni: `governance 0003_auditevent`, `0004_postgres_append_only` (PG-only), `0005_identity_audit_append_only` (PG-only); `privacy 0001_initial`, `0002_seed_retention_matrix`, `0003_identity_invitations`, `0004_seed_identity_retention`. Reversibilità verificata su SQLite (migrate → zero → migrate).
- Nessuna nuova dipendenza; `requirements.in` invariato.

## Risultati
- Dopo il merge con main (s1+s3) e l'integrazione: suite completa (SQLite) **496 passed, 15 skipped** in 217 s; test s4: 74 (70 passed, 4 PG-only skipped).
- `ruff check --select E9,F63,F7,F82` ok; `ruff format --check` ok; `manage.py check` ok; `makemigrations --check` nessuna modifica.

## Rischi / punti aperti
- Trigger PG: eccezione TRUNCATE per i DB `test_*` necessaria al flush di Django; la minimizzazione dell'audit richiede di eseguire il job come `app_owner`.
- Il pseudonimo usa `SECRET_KEY`: la rotazione della chiave cambia i pseudonimi futuri (non quelli già registrati).
- Le decisioni D07 (età e account studenti, azione alla scadenza della riconferma) e D09 (durate) vanno approvate e caricate via API; finché restano PROPOSED il job non cancella nulla.
- Consegna del token degli export ancora all'operatore (nessun canale s3 dedicato).
- Test staff con `force_login` ricevono 403 `MFA_REQUIRED` (s1): i test s4 usano `force_authenticate`.

## Integrazione con s1/s3 (merge main)
- **Inviti unificati**: rimosso `privacy.Invitation` e il mio endpoint di accettazione; registro, import e revoche usano `identity.Invitation`/`identity.services` (verifica relazione prima del token, consegna via `identity.delivery` in `on_commit`, errore uniforme `INVALID_TOKEN`, 409 `LOGIN_REQUIRED` per account esistente). Le condizioni della delega stanno in `privacy.InvitationTerms` e diventano `GuardianLinkDetail` all'accettazione. Il registro non crea più account inattivi: email nuova → 202 con invito.
- **Audit identity in retention/diritti**: `IdentityAuditEvent` protetto dalla guardia append-only comune (sostituisce il trigger s1); nuova categoria D09 `identity_audit_ip` (90 gg, MINIMIZE, PROPOSED); export account include sessioni e audit di sicurezza (mai segreti MFA); anonimizzazione revoca sessioni, cancella TOTP/recovery/reset, pseudonimizza email degli inviti chiusi, azzera gli IP; retention `invitations` su inviti identity chiusi/scaduti.
- **Policy**: riconferma (DECLINED esclusa, PENDING scaduta esclusa con `SUSPEND`, CONFIRMED abilita `CONSENT_REQUIRED`), `can_receive_notifications` nelle notifiche s3, `can_request_changes` (default negato). Test: `test_privacy_policies.py` (6), `test_privacy_identity.py` (3).
