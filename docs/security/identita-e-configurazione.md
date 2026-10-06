# Identità, sessioni e configurazione di produzione (s1-sicurezza)

Stato: implementato in v1.0-dev. I valori marcati **da approvare** dipendono da D07.

## API (prefisso `/api/v1`, JSON, CSRF obbligatorio su ogni POST/PUT)

| Endpoint | Chi | Note |
| --- | --- | --- |
| `POST auth/login` `{email, password}` | anonimo | `{"username"}` accettato solo se `ALLOW_USERNAME_LOGIN` (sviluppo). Staff: risposta `mfa_required: true`, nessuna sessione finché la MFA non è verificata. Errore unico `INVALID_CREDENTIALS`; `429 RATE_LIMITED` + `Retry-After`. |
| `POST auth/mfa/setup` → `{secret, otpauth_uri, qr_svg}` | login a metà o sessione senza MFA | Solo se non già attivata. |
| `POST auth/mfa/confirm` `{code}` → `recovery_codes` (10, mostrati una sola volta) | idem | Completa il login. |
| `POST auth/mfa/verify` `{code}` o `{recovery_code}` | idem | Anti-replay del passo TOTP; 5 errori → blocco progressivo. |
| `GET auth/mfa`, `POST auth/mfa/recovery-codes` `{code}` | utente | Stato e rigenerazione dei codici. |
| `POST auth/logout` | utente | Revoca server-side. |
| `GET auth/sessions`, `POST auth/sessions/<id>/revoke`, `POST auth/sessions/revoke-all` `{include_current?}` | utente | Solo le proprie sessioni. |
| `POST auth/password-reset` `{email}` → 202 sempre uguale | anonimo | Token 256 bit, hash SHA-256, 30 min, monouso. |
| `POST auth/password-reset/confirm` `{token, password}` | anonimo | Revoca tutte le sessioni. |
| `POST auth/password-change` `{current_password, new_password}` | utente | Revoca le altre sessioni. |
| `GET/POST auth/context` `{context}` | utente | Multi-ruolo: finché non si sceglie, le API rispondono `409 CONTEXT_REQUIRED` (eccetto `auth/*`, `me`). |
| `POST auth/student-consent` `{granted}` | studente maggiorenne confermato | Consenso alla visibilità dei tutori (D07). |
| `GET/POST invitations`, `GET invitations/<id>`, `POST …/verify-relation` `{evidence}`, `…/resend`, `…/revoke` | centro + MFA | Invito tutore: token emesso solo dopo `verify-relation`. 72 h, monouso, hash. |
| `POST invitations/accept` `{token, password?}` | anonimo / account esistente loggato | Errore unico `INVALID_TOKEN`; account esistente → `409 LOGIN_REQUIRED`. |
| `POST identity/accounts/<id>/sessions/revoke-all`, `POST identity/accounts/<id>/mfa/reset` `{reason}` | centro + MFA | Reset MFA solo da un secondo amministratore. |
| `GET/PUT identity/students/<id>/access-policy` | centro + MFA | Maggiorenne confermato esplicitamente, non calcolato dall'età. |
| `GET identity/audit?subject=<id>` | centro + MFA | Audit append-only (trigger PostgreSQL). |

Il link negli inviti/reset porta il token nel frammento (`/invito#token=…`, `/reimposta-password#token=…`):
il frontend lo legge da `location.hash` e lo invia in POST.

## Variabili d'ambiente

Segreti: `NOME` oppure `NOME_FILE` (mai entrambi). Produzione: `DJANGO_SETTINGS_MODULE=config.settings_production`.

| Variabile | Produzione | Default |
| --- | --- | --- |
| `DJANGO_SECRET_KEY[_FILE]`, `DJANGO_SECRET_KEY_FALLBACKS[_FILE]` | obbligatoria, ≥50 caratteri casuali | — |
| `DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS` (https) | obbligatorie, senza wildcard | — |
| `POSTGRES_DB/USER/PASSWORD[_FILE]`, `DB_HOST`, `DB_SSLMODE`, `DB_SSLROOTCERT` | obbligatorie | `verify-full` |
| `CACHE_URL[_FILE]` (`rediss://`), `CELERY_BROKER_URL[_FILE]` (`rediss://`) | obbligatorie | — |
| `DJANGO_HSTS_SECONDS`, `DJANGO_HSTS_INCLUDE_SUBDOMAINS`, `DJANGO_HSTS_PRELOAD` | | 3600, 1, 0 |
| `TRUSTED_PROXY_HOPS` | numero di proxy davanti a gunicorn | 1 (prod), 0 (base) |
| `DJANGO_ADMIN_ENABLED`, `DJANGO_ADMIN_ALLOWED_NETWORKS` | admin spento; se acceso serve l'allowlist | 0 |
| `SESSION_COOKIE_AGE`, `SESSION_IDLE_TIMEOUT_STAFF`, `SESSION_ABSOLUTE_TIMEOUT_STAFF`, `SESSION_IDLE_TIMEOUT_DEFAULT`, `SESSION_ABSOLUTE_TIMEOUT_DEFAULT` | **da approvare (D07)** | 8 h, 30 min, 8 h, 8 h, 8 h |
| `ADULT_GUARDIAN_ACCESS` (`KEEP`/`CONSENT_REQUIRED`/`NONE`) | **da approvare (D07)** | `CONSENT_REQUIRED` |
| `MFA_REQUIRED_ROLES` | | `CENTER` (+ superuser/staff/`mfa_required`) |
| `ARGON2_TIME_COST`, `ARGON2_MEMORY_COST_KIB`, `ARGON2_PARALLELISM` | dopo `manage.py benchmark_hashers` | 2, 102400, 8 |
| `CSP_REPORT_ONLY`, `PORTAL_BASE_URL` | | 0 (prod), origine CSRF |

Verifica: `python manage.py check --deploy --fail-level WARNING` → 0 avvisi (W021 silenziato finché
`DJANGO_HSTS_PRELOAD=0`, decisione esplicita dopo la verifica dei domini).
