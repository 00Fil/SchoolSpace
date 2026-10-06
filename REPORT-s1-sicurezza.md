# REPORT s1-sicurezza

Branch `s1-sicurezza`. Tutto il codice è coperto da test; i dati sono sintetici; non ci sono invii reali.

## GAP chiusi (codice e test)

| GAP | Implementazione | Test |
| --- | --- | --- |
| B01 | `normalize_email` (NFC, trim, minuscolo) in `Account.save` e manager. Vincolo DB `UniqueConstraint(Lower("email"))`. Migrazione dati che normalizza e si ferma se trova duplicati. `EmailBackend` usa l'email: lo username è ammesso solo in sviluppo, e per gli account inesistenti calcola comunque l'hash (tempi uguali). Il nuovo `api/auth.py` funziona con `DEBUG=0`. | `test_identity_auth.py` (B01), `test_api.py::test_login_enabled_without_debug` |
| B02 | Modello `Invitation`: token di 256 bit, nel DB solo l'hash SHA-256, monouso, 72 h, reinvio che invalida il token precedente, revoca. Un invito aperto per email, ruolo e studente. Il tutore riceve il token solo dopo `verify-relation` con evidenza; un vincolo DB lo impone. Le risposte non rivelano se l'account esiste (`INVALID_TOKEN` unico). Se l'account esiste già serve il login: il token non sostituisce la password. Per lo studente l'account viene collegato a `Student`. | `test_identity_invitations.py` |
| B03 | Reset: 30 min, monouso, una nuova richiesta invalida le precedenti, risposta 202 sempre identica, revoca di tutte le sessioni, validatori (min 12). Argon2id è l'hasher primario (`ConfigurableArgon2PasswordHasher`, parametri da env); PBKDF2/scrypt restano come fallback con rehash al login. Comando `manage.py benchmark_hashers`. | `test_identity_*` |
| B04 | TOTP (pyotp) obbligatorio per superuser, staff, ruoli `MFA_REQUIRED_ROLES` (default `CENTER`) e account con `mfa_required`. Login in due fasi: nessuna sessione prima della MFA. Anti-replay del passo, 10 codici di recupero salvati come hash SHA-256 (80 bit), step-up se il ruolo staff arriva dopo il login. Reset della MFA solo da un secondo amministratore, con audit. Registro `UserSession` (solo id, mai la chiave di sessione) con revoca singola, totale e dall'admin. Timeout di inattività e assoluti per profilo, rotazione dell'ID a login e cambio contesto, logout lato server. | `test_identity_auth.py` |
| B05 | `apps/identity/throttle.py`: limite per IP e per identità normalizzata (digest, niente PII nelle chiavi) su login, MFA, reset, conferma reset e accettazione invito. Blocco progressivo (60 s raddoppiati fino a 1 h) con `Retry-After`. Lo stato sta nella cache Django: Redis (`CACHE_URL`) in produzione, quindi condiviso tra worker. IP del client solo tramite `TRUSTED_PROXY_HOPS`, così XFF non è falsificabile. | `test_identity_auth.py` (B05) |
| B07 | Contesto multi-ruolo verificato lato server (`auth/context`). Senza scelta: `409 CONTEXT_REQUIRED`. `active_roles` e `is_center` rispettano il contesto: un superuser in contesto GUARDIAN perde i poteri del centro. `StudentAccessPolicy`: la maggiore età è confermata esplicitamente dal centro, non calcolata dall'età. Accesso dei tutori `KEEP`/`CONSENT_REQUIRED`/`NONE` con consenso dello studente; vale in `visible_students` e `can_manage_student_availability`. | `test_identity_auth.py`, `test_identity_bola.py` |
| B08 (identità e deleghe) | Matrice con sessioni reali: delega non verificata, revocata o `can_view=False`, altra famiglia, fratello, tutor, account senza ruoli, studente. Coperti: dettaglio e lista studenti, FK annidata delle disponibilità, endpoint admin di identità, sessioni altrui, contesto autoconcesso, invito altrui, policy maggiorenne. | `test_identity_bola.py` (28 casi) |
| I02 | `SecurityHeadersMiddleware`: CSP (report-only in DEBUG), Permissions-Policy, CORP, `Cache-Control: no-store` sulle API. Referrer-Policy e COOP `same-origin`; HSTS configurabile (3600 di default, poi 1 anno). CORS assente, verificato da test. | `test_security_settings.py` |
| I03 | `config/env.py`: segreti da `NOME` o `NOME_FILE`, `SECRET_KEY_FALLBACKS`. La produzione si ferma all'avvio con chiave debole o placeholder e con env obbligatorie mancanti; nessun segreto compare nei messaggi. Test che scansiona i file versionati in cerca di segreti. | idem |
| I06 | Admin spento in produzione (`DJANGO_ADMIN_ENABLED=0`, URL non registrato e 404 dal middleware). Se acceso servono un'allowlist di reti (no `/0`) e una sessione con MFA (`admin.site.has_permission`). | idem |
| I08 | `djangorestframework>=3.17.2,<4`, `pytest>=9.0.3,<10`, rimosso `<3.17`. Lock `requirements*.txt` con hash SHA-256 da PyPI, verificati con `pip install --dry-run --require-hashes` (dipendenze complete). In produzione solo `JSONRenderer` e `JSONParser`. | idem |
| Settings | `config/settings_production.py`: `ALLOWED_HOSTS` e `CSRF_TRUSTED_ORIGINS` obbligatori senza wildcard; `SECURE_PROXY_SSL_HEADER`; Redis `rediss://` per `CACHES` e broker; DB `sslmode=verify-full` con `sslrootcert`, `CONN_MAX_AGE=60`, `CONN_HEALTH_CHECKS`; `DATA_UPLOAD_MAX_MEMORY_SIZE=1 MB`; cookie 8 h; DEBUG, SQLite e flag sperimentali vietati. `check --deploy --fail-level WARNING` dà **0 avvisi**: W021 (preload HSTS) è silenziato in modo documentato finché `DJANGO_HSTS_PRELOAD=0`. | `test_check_deploy_has_zero_warnings` più 17 casi di fail-fast |

Audit: `IdentityAuditEvent` è append-only (guardie ORM e trigger PostgreSQL su UPDATE/DELETE). Rifiuta le chiavi che potrebbero contenere segreti. Copre login, MFA, sessioni, inviti, reset, contesto e policy.

## GAP parziali

- **B06**: sono auditate solo le API di identità (inviti, sessioni, MFA, policy maggiorenne). Mancano le API CRUD auditate per famiglie, studenti e deleghe (`/families`, `/guardian-links`); l'admin resta solo per le emergenze.
- **B08**: coperte identità e deleghe. Restano da coprire calendario, export e link (s2, s4) con lo stesso schema di `tests/identity_helpers.py`.
- **B04, MFA**: il segreto TOTP è in chiaro nel DB (`cryptography` non è installato). Si consiglia la cifratura di campo con una chiave del secret manager.
- **B03**: Argon2id è attivo con i default di Django. I parametri definitivi vanno fissati con `benchmark_hashers` sull'hardware di produzione.

## File toccati fuori dalla mia proprietà

- `backend/config/urls.py`: `include("api.auth")` e admin condizionale; rimosse le due route `views.login_view` e `views.logout_view`, che restano in `api/views.py` come codice morto da far rimuovere al proprietario.
- `backend/tests/test_api.py`: `test_provisional_login_disabled_in_production` diventa `test_login_enabled_without_debug`; il comportamento cambia per GAP-B01.
- Nuovi file: `backend/tests/{identity_helpers,test_identity_auth,test_identity_invitations,test_identity_bola,test_security_settings}.py`, `backend/config/env.py`, `docs/security/identita-e-configurazione.md` (contratto API e variabili d'ambiente).

## Settings, urls, requirements

- `settings.py`: import di `config.env`, `SECRET_KEY` da file, fallback, 3 middleware, `min_length=12`, blocco `# --- s1-sicurezza ---` dopo `SECURE_CONTENT_TYPE_NOSNIFF`. Il blocco contiene backend, hasher, sessioni, `IDENTITY_*`, `CACHES` da `CACHE_URL`, Referrer e COOP, upload massimo 1 MB. In `REST_FRAMEWORK` si aggiungono il renderer Browsable solo con DEBUG e `NUM_PROXIES`.
- Nuove dipendenze runtime (già nel venv, nessuna installazione): `argon2-cffi` 25.1.0 (più `argon2-cffi-bindings`, `cffi`, `pycparser`), `pyotp` 2.10.0, `qrcode` 8.2. Dev: `hypothesis`, `pytest` 9.1.1.

## Test

- Suite completa: **353 passed, 9 skipped, 1 failed**. L'unico fallimento è `test_solver.py::test_real_cp_sat_demo_valid_complete`, FEASIBLE invece di OPTIMAL: fallisce anche sulla baseline `a2fe972` estratta a parte, quindi non dipende da s1.
- Nuovi test s1: 110 (1 PG-only skipped).
- `ruff check --select E9,F63,F7,F82` ok, `ruff format --check` ok, `manage.py check` ok, `makemigrations --check` ok.
- Migrazione `identity.0003` reversibile, verificata con `migrate identity 0002` e poi di nuovo in avanti.

## Rischi e punti aperti

1. **Frontend (s6)**: il login va ora per email, con flusso MFA (`mfa_required`, setup, confirm, verify), selezione del contesto (`409 CONTEXT_REQUIRED`) e nuove pagine `/invito#token=` e `/reimposta-password#token=`. Contratto in `docs/security/`. Il campo "Nome utente" funziona già se si inserisce l'email.
2. **Infra (s5)**: Dockerfile e compose devono usare `DJANGO_SETTINGS_MODULE=config.settings_production` e `pip install --require-hashes`. Restano a s5: le nuove variabili in `.env.example`, i limiti e gli header su nginx, `pip-audit` e gitleaks in CI, `wsgi.py` e `celery.py` (oggi default `config.settings`).
3. **Comunicazioni (s3)**: collegare `IDENTITY_MESSAGE_SENDER` all'outbox. Oggi l'invio sincrono via `send_mail` crea una piccola differenza di tempi tra account esistenti e inesistenti nel reset; l'outbox asincrono la elimina.
4. **Privacy (s4)**: l'audit conserva l'IP e ha FK `PROTECT` verso `Account`, quindi retention e cancellazione richiedono pseudonimizzazione. Il trigger non blocca TRUNCATE, che serve al flush dei test: il ruolo DB di runtime non deve avere quel privilegio.
5. **Decisioni da approvare (D07)**: timeout (staff 30 min di inattività, 8 h assolute, famiglie 8 h), `ADULT_GUARDIAN_ACCESS=CONSENT_REQUIRED`, `MFA_REQUIRED_ROLES=CENTER`, HSTS preload.
6. **Test di altri stream**: i test con `force_login` di staff ricevono ora `403 MFA_REQUIRED` sulle API; `APIClient.force_authenticate` non è toccato. `MANIFEST.sha256` è da rigenerare al merge.
