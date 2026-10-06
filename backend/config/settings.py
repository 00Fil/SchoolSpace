import os
from pathlib import Path
from django.core.exceptions import ImproperlyConfigured
from config.env import env, env_bool, env_int, env_list, secret  # --- s1-sicurezza ---

BASE_DIR = Path(__file__).resolve().parent.parent
DEBUG = os.environ.get("DJANGO_DEBUG", "0") == "1"
# --- s1-sicurezza: segreti da env o da file (*_FILE), mai nel repository (GAP-I03) ---
SECRET_KEY = secret("DJANGO_SECRET_KEY")
if not SECRET_KEY:
    raise ImproperlyConfigured("DJANGO_SECRET_KEY is required")
# Rotazione senza invalidare in blocco sessioni e token: chiavi precedenti separate da virgola.
SECRET_KEY_FALLBACKS = [
    k for k in secret("DJANGO_SECRET_KEY_FALLBACKS").split(",") if k
]
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "apps.identity",
    "apps.education",
    "apps.availability",
    "apps.governance",
    "apps.scheduling",
    "apps.calendar.apps.CalendarConfig",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "apps.identity.middleware.SecurityHeadersMiddleware",  # --- s1-sicurezza ---
    "apps.identity.middleware.AdminGuardMiddleware",  # --- s1-sicurezza ---
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "apps.identity.middleware.SessionSecurityMiddleware",  # --- s1-sicurezza ---
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
ROOT_URLCONF = "config.urls"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    }
]
WSGI_APPLICATION = "config.wsgi.application"
if os.environ.get("USE_SQLITE_FOR_TESTS") == "1":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "dev.sqlite3",
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.environ.get("POSTGRES_DB", "ripetizioni"),
            "USER": os.environ.get("POSTGRES_USER", "ripetizioni"),
            "PASSWORD": os.environ.get("POSTGRES_PASSWORD", ""),
            "HOST": os.environ.get("DB_HOST", "db"),
            "PORT": os.environ.get("DB_PORT", "5432"),
        }
    }
AUTH_USER_MODEL = "identity.Account"
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 12},  # --- s1-sicurezza: ASVS V6 ---
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LANGUAGE_CODE = "it-it"
TIME_ZONE = "Europe/Rome"
USE_I18N = True
USE_TZ = True
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_SSL_REDIRECT = not DEBUG
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True

# --- s1-sicurezza: autenticazione, sessioni, cache, header (GAP-B01..B07, I02, I06) ---
# Dettagli e default in apps/identity/conf.py; produzione in config/settings_production.py.
AUTHENTICATION_BACKENDS = ["apps.identity.backends.EmailBackend"]
PASSWORD_HASHERS = [
    # Argon2id primario; PBKDF2 resta per verificare e aggiornare al login gli hash esistenti.
    "apps.identity.hashers.ConfigurableArgon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.ScryptPasswordHasher",
]
ARGON2_TIME_COST = env_int("ARGON2_TIME_COST", 2, minimum=1)
ARGON2_MEMORY_COST_KIB = env_int("ARGON2_MEMORY_COST_KIB", 102400, minimum=19456)
ARGON2_PARALLELISM = env_int("ARGON2_PARALLELISM", 8, minimum=1)
# Timeout approvati il 3/10/2026: cookie 8 h; inattività staff 30 min (vedi IDENTITY_*).
SESSION_COOKIE_AGE = env_int("SESSION_COOKIE_AGE", 8 * 3600, minimum=300)
SESSION_COOKIE_NAME = env("SESSION_COOKIE_NAME", "sessionid")
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")
IDENTITY_SESSION_IDLE_TIMEOUT_STAFF = env_int("SESSION_IDLE_TIMEOUT_STAFF", 30 * 60)
IDENTITY_SESSION_ABSOLUTE_TIMEOUT_STAFF = env_int(
    "SESSION_ABSOLUTE_TIMEOUT_STAFF", 8 * 3600
)
IDENTITY_SESSION_IDLE_TIMEOUT_DEFAULT = env_int(
    "SESSION_IDLE_TIMEOUT_DEFAULT", 8 * 3600
)
IDENTITY_SESSION_ABSOLUTE_TIMEOUT_DEFAULT = env_int(
    "SESSION_ABSOLUTE_TIMEOUT_DEFAULT", 8 * 3600
)
IDENTITY_MFA_ENFORCED = env_bool("MFA_ENFORCED", True)
IDENTITY_MFA_REQUIRED_ROLES = env_list("MFA_REQUIRED_ROLES", ["CENTER"])
IDENTITY_TRUSTED_PROXY_HOPS = env_int("TRUSTED_PROXY_HOPS", 0, minimum=0)
IDENTITY_ALLOW_USERNAME_LOGIN = env_bool("ALLOW_USERNAME_LOGIN", DEBUG)
IDENTITY_REQUIRE_CONTEXT_SELECTION = env_bool("REQUIRE_CONTEXT_SELECTION", True)
IDENTITY_ADULT_GUARDIAN_ACCESS = env("ADULT_GUARDIAN_ACCESS", "CONSENT_REQUIRED")
IDENTITY_PORTAL_BASE_URL = env("PORTAL_BASE_URL", "http://localhost:5173")
IDENTITY_ADMIN_ENABLED = env_bool("DJANGO_ADMIN_ENABLED", True)
IDENTITY_ADMIN_ALLOWED_NETWORKS = env_list("DJANGO_ADMIN_ALLOWED_NETWORKS")
# Cache condivisa: Redis (redis:// o rediss://) per throttle e rate limit tra worker (GAP-B05).
_cache_url = secret("CACHE_URL")
if _cache_url.startswith(("redis://", "rediss://")):
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": _cache_url,
            "KEY_PREFIX": env("CACHE_KEY_PREFIX", "ripetizioni"),
            "TIMEOUT": 300,
        }
    }
elif _cache_url:
    raise ImproperlyConfigured("CACHE_URL must be a redis:// or rediss:// URL")
else:
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
# Header: Referrer-Policy e COOP da SecurityMiddleware; CSP e Permissions-Policy dal
# middleware identity. CSP in sola segnalazione finché non è verificata in E2E.
SECURE_REFERRER_POLICY = "same-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"
SECURITY_CSP_REPORT_ONLY = env_bool("CSP_REPORT_ONLY", DEBUG)
DATA_UPLOAD_MAX_MEMORY_SIZE = env_int("DATA_UPLOAD_MAX_MEMORY_SIZE", 1_048_576)
# CORS assente: nessun middleware CORS installato; stessa origine dietro il reverse proxy.
G1_APPROVED = os.environ.get("G1_APPROVED", "0") == "1"
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication"
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 100,
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {"anon": "30/minute", "user": "120/minute"},
    # --- s1-sicurezza: Browsable API solo in sviluppo; proxy fidati per l'IP dei throttle ---
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"]
    + (["rest_framework.renderers.BrowsableAPIRenderer"] if DEBUG else []),
    "NUM_PROXIES": IDENTITY_TRUSTED_PROXY_HOPS or None,
}

# Runtime jobs are an experimental data bridge, not production scheduling.
# --- P0 (guida v3.1, T1): flag di funzione per ambiente, indipendenti da DEBUG ---
# I nomi EXPERIMENTAL_* restano letti come alias per gli ambienti di sviluppo esistenti.
FEATURE_PLANNING = env_bool("FEATURE_PLANNING", env_bool("EXPERIMENTAL_DB_PLANNING", False))
FEATURE_PLANNING_LAB = env_bool("FEATURE_PLANNING_LAB", DEBUG)
EXPERIMENTAL_DB_PLANNING = FEATURE_PLANNING  # alias deprecato
from urllib.parse import quote

CELERY_BROKER_URL = (
    os.environ.get("CELERY_BROKER_URL")
    or "redis://:"
    + quote(os.environ.get("REDIS_PASSWORD", ""), safe="")
    + "@"
    + os.environ.get("REDIS_HOST", "redis")
    + ":6379/0"
)
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_TASK_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_IGNORE_RESULT = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_TASK_TIME_LIMIT = 90
CELERY_TASK_SOFT_TIME_LIMIT = 60
# v0.9.4: calcolo accurato (profilo THOROUGH), pensato per girare di notte.
# I limiti Celery e il lease del singolo run sono scalati su questo budget.
PLANNING_THOROUGH_BUDGET_SECONDS = min(
    43200.0, float(os.environ.get("PLANNING_THOROUGH_BUDGET_SECONDS", 6 * 3600))
)
PLANNING_THOROUGH_WORKERS = max(
    1,
    min(8, int(os.environ.get("PLANNING_THOROUGH_WORKERS", os.cpu_count() or 1))),
)
# Coda dei run lunghi: "solver_long" (servizio worker-solver-long in compose.prod)
# o "solver" se si usa un solo worker.
PLANNING_THOROUGH_QUEUE = os.environ.get("PLANNING_THOROUGH_QUEUE", "solver")
CELERY_BROKER_CONNECTION_TIMEOUT = 1
CELERY_BROKER_TRANSPORT_OPTIONS = {"socket_connect_timeout": 1, "socket_timeout": 1}
if os.environ.get("CELERY_FILE_TRANSPORT_DIR"):
    path = os.environ["CELERY_FILE_TRANSPORT_DIR"]
    CELERY_BROKER_TRANSPORT_OPTIONS = {
        "data_folder_in": path,
        "data_folder_out": path,
        "store_processed": False,
    }
CELERY_BEAT_SCHEDULE = {
    "reconcile-runs": {
        "task": "apps.scheduling.tasks.reconcile",
        "schedule": 15.0,
        "options": {"queue": "solver"},
    }
}

FEATURE_CALENDAR = env_bool("FEATURE_CALENDAR", env_bool("EXPERIMENTAL_CALENDAR", False))
EXPERIMENTAL_CALENDAR = FEATURE_CALENDAR  # alias deprecato
CALENDAR_ALLOW_SQLITE_TESTS = (
    False  # Never enabled by an environment flag in normal settings.
)

# --- s2-calendario ---
# D06 (approvata il 3/10/2026): ciclo MENSILE. Il gestore genera con il motore il
# calendario del mese successivo, lo valida e lo pubblica; ogni tutor coinvolto approva
# la pianificazione mensile o chiede rettifiche (schedule-acks), che il gestore decide
# con l'aiuto del motore. I conflitti vengono segnalati, mai sospesi automaticamente.
# Pubblicazione solo dopo POST /schedule-plans/{id}/validate/ se attivo.
CALENDAR_REQUIRE_EXPLICIT_VALIDATION = (
    os.environ.get("CALENDAR_REQUIRE_EXPLICIT_VALIDATION", "0") == "1"
)
# MONTH = settimane del mese solare successivo (D06); WEEKS = CALENDAR_HORIZON_WEEKS.
CALENDAR_HORIZON_MODE = os.environ.get("CALENDAR_HORIZON_MODE", "MONTH")
if CALENDAR_HORIZON_MODE not in ("MONTH", "WEEKS"):
    raise ImproperlyConfigured("CALENDAR_HORIZON_MODE: MONTH|WEEKS")
CALENDAR_HORIZON_WEEKS = int(os.environ.get("CALENDAR_HORIZON_WEEKS", "6"))
# Il recupero nasce da comando esplicito del gestore (regole in recovery_policy.py).
CALENDAR_RECOVERY_POLICY = "EXPLICIT_ONLY"
# Rilevazione automatica di ConflictCase dopo modifiche a disponibilità/chiusure.
CALENDAR_AUTO_CONFLICT_DETECTION = (
    os.environ.get("CALENDAR_AUTO_CONFLICT_DETECTION", "1") == "1"
)
# Il tutor della lezione può registrare le presenze (non correggerle).
CALENDAR_TUTOR_RECORDS_ATTENDANCE = (
    os.environ.get("CALENDAR_TUTOR_RECORDS_ATTENDANCE", "1") == "1"
)
# Operatore (username) usato dal job periodico; vuoto = job disabilitato.
CALENDAR_HORIZON_ACTOR = os.environ.get("CALENDAR_HORIZON_ACTOR", "")
CELERY_BEAT_SCHEDULE["calendar-horizon"] = {
    "task": "apps.calendar.tasks.propose_horizon",
    "schedule": 86400.0,
}
CELERY_BEAT_SCHEDULE["calendar-conflicts"] = {
    "task": "apps.calendar.tasks.detect_conflicts",
    "schedule": 3600.0,
}
# --- s4-privacy ---
# Privacy, retention, import/export protetti e audit unificato. Durate e azioni sono
# D09 approvata il 3/10/2026: durate e azioni confermate dal gestore del centro.
INSTALLED_APPS += ["apps.privacy"]
PRIVACY_DATA_DIR = Path(
    os.environ.get("PRIVACY_DATA_DIR", BASE_DIR / "var" / "privacy")
)
# Export protetti: fuori da static/media, file 0600, download unico con scadenza.
PRIVACY_EXPORT_DIR = Path(
    os.environ.get("PRIVACY_EXPORT_DIR", PRIVACY_DATA_DIR / "exports")
)
PRIVACY_EXPORT_TTL_HOURS = int(os.environ.get("PRIVACY_EXPORT_TTL_HOURS", "24"))
# Ledger esterno delle richieste privacy: in produzione su storage separato dal DB.
PRIVACY_LEDGER_PATH = Path(
    os.environ.get("PRIVACY_LEDGER_PATH", PRIVACY_DATA_DIR / "ledger.jsonl")
)
PRIVACY_INVITE_TTL_HOURS = int(os.environ.get("PRIVACY_INVITE_TTL_HOURS", "72"))
PRIVACY_MAJORITY_GRACE_DAYS = int(os.environ.get("PRIVACY_MAJORITY_GRACE_DAYS", "30"))
# REPORT (confermato: si segnala, non si sospende) | SUSPEND.
PRIVACY_MAJORITY_OVERDUE_ACTION = os.environ.get(
    "PRIVACY_MAJORITY_OVERDUE_ACTION", "REPORT"
)
# Il job periodico esegue davvero solo se abilitato; altrimenti produce ricevute dry-run.
PRIVACY_RETENTION_AUTORUN = os.environ.get("PRIVACY_RETENTION_AUTORUN", "0") == "1"
CELERY_BEAT_SCHEDULE.update(
    {
        "privacy-majority-review": {
            "task": "apps.privacy.tasks.majority_review",
            "schedule": 24 * 3600.0,
        },
        "privacy-retention": {
            "task": "apps.privacy.tasks.retention",
            "schedule": 24 * 3600.0,
        },
    }
)
# --- fine s4-privacy ---
# --- s3-comunicazioni ---
# Outbox, consegne, notifiche interne, ICS e link video (GAP-F01..F05).
# D08 approvata il 3/10/2026: fornitore email Resend (backend "resend").
INSTALLED_APPS += ["apps.communications.apps.CommunicationsConfig"]
# development | test | staging | production. Fuori da production solo backend "sink".
COMMUNICATIONS_ENV = os.environ.get("COMMUNICATIONS_ENV", "development")
# Decisione del committente (3/10/2026): famiglie e tutor sono avvisati nel portale.
# Si imposta nel .env: COMMUNICATIONS_CHANNELS=IN_APP (solo portale, scelta del centro) oppure IN_APP,EMAIL.
COMMUNICATIONS_CHANNELS = tuple(
    c.strip() for c in os.environ.get("COMMUNICATIONS_CHANNELS", "IN_APP,EMAIL").split(",") if c.strip()
)
# D06 (decisione del 3/10/2026): recupero solo con assenza avvisata almeno 24 ore prima;
# il centro può concederlo esplicitamente anche con preavviso più breve.
RECOVERY_NOTICE_HOURS = int(os.environ.get("RECOVERY_NOTICE_HOURS", "24"))
# P6 · C04: cambiare la versione quando cambia il testo dell'informativa (tutti la riconfermano).
PRIVACY_NOTICE_VERSION = os.environ.get("PRIVACY_NOTICE_VERSION", "2026-10")
# Le richieste delle famiglie accolte dal centro vanno confermate anche dal tutor.
CHANGE_REQUEST_TUTOR_CONFIRMATION = os.environ.get("CHANGE_REQUEST_TUTOR_CONFIRMATION", "1") == "1"
COMMUNICATIONS_EMAIL = {
    "BACKEND": os.environ.get("COMMUNICATIONS_EMAIL_BACKEND", "sink"),  # sink|smtp|api|resend
    "RESEND_URL": os.environ.get("COMMUNICATIONS_RESEND_URL", "https://api.resend.com/emails"),
    "RESEND_API_KEY": secret("COMMUNICATIONS_RESEND_API_KEY"),
    "FROM": os.environ.get(
        "COMMUNICATIONS_EMAIL_FROM", "Centro ripetizioni <no-reply@example.invalid>"
    ),
    "MESSAGE_ID_DOMAIN": os.environ.get(
        "COMMUNICATIONS_MESSAGE_ID_DOMAIN", "example.invalid"
    ),
    "TIMEOUT_SECONDS": float(os.environ.get("COMMUNICATIONS_EMAIL_TIMEOUT", "10")),
    "SMTP_HOST": os.environ.get("COMMUNICATIONS_SMTP_HOST", ""),
    "SMTP_PORT": int(os.environ.get("COMMUNICATIONS_SMTP_PORT", "587")),
    "SMTP_USER": os.environ.get("COMMUNICATIONS_SMTP_USER", ""),
    "SMTP_PASSWORD": secret("COMMUNICATIONS_SMTP_PASSWORD"),
    "SMTP_SECURITY": os.environ.get("COMMUNICATIONS_SMTP_SECURITY", "starttls"),
    "API_URL": os.environ.get("COMMUNICATIONS_EMAIL_API_URL", ""),
    "API_STATUS_URL": os.environ.get("COMMUNICATIONS_EMAIL_API_STATUS_URL", ""),
    "API_TOKEN": secret("COMMUNICATIONS_EMAIL_API_TOKEN"),
    "API_IDEMPOTENT": os.environ.get("COMMUNICATIONS_EMAIL_API_IDEMPOTENT", "0") == "1",
}
COMMUNICATIONS_DELIVERY = {
    "MAX_ATTEMPTS": int(os.environ.get("COMMUNICATIONS_MAX_ATTEMPTS", "6")),
    "BACKOFF_BASE_SECONDS": 30,
    "BACKOFF_MAX_SECONDS": 3600,
    "LEASE_SECONDS": 120,
    "ENQUEUE_STALE_SECONDS": 300,
}
# "verify" (default): esito email ambiguo e ignoto -> dead-letter da verificare.
# "retry": reinvio at-least-once (possibile duplicato). Da approvare (D08).
COMMUNICATIONS_AMBIGUOUS_POLICY = os.environ.get(
    "COMMUNICATIONS_AMBIGUOUS_POLICY", "verify"
)
COMMUNICATIONS_DEFAULT_PREFERENCES = {
    "SERVICE": {"IN_APP": True, "EMAIL": True},
    "MARKETING": {"IN_APP": False, "EMAIL": False},
}
COMMUNICATIONS_MARKETING_ENABLED = False  # fuori baseline (paper §7.4)
COMMUNICATIONS_REQUIRE_VERIFIED_EMAIL = True
COMMUNICATIONS_EMAIL_STUDENTS = False  # D07 approvata: nessuna email agli studenti
COMMUNICATIONS_PORTAL_URL = os.environ.get("COMMUNICATIONS_PORTAL_URL", "")
COMMUNICATIONS_CENTER_NAME = os.environ.get(
    "COMMUNICATIONS_CENTER_NAME", "Centro ripetizioni"
)
COMMUNICATIONS_ICS_MAX_TOKENS = 3
COMMUNICATIONS_ICS_TOKEN_DAYS = int(
    os.environ.get("COMMUNICATIONS_ICS_TOKEN_DAYS", "365")
)
COMMUNICATIONS_ICS_PAST_DAYS = 30
COMMUNICATIONS_ICS_FUTURE_DAYS = 120
COMMUNICATIONS_MEETING_OPEN_MINUTES_BEFORE = 15
# --- v0.10: videolezioni automatiche (Jitsi Meet self-hosted, open source) ---
# VIDEO_PROVIDER=jitsi attiva la stanza automatica per ogni lezione ONLINE: nessun link
# da inserire a mano. Vuoto = solo i MeetingLink manuali (comportamento precedente).
VIDEO_PROVIDER = env("VIDEO_PROVIDER", "").strip().lower()
VIDEO_JITSI_URL = env("VIDEO_JITSI_URL", "").strip().rstrip("/")  # es. https://meet.esempio.it
VIDEO_JITSI_APP_ID = env("VIDEO_JITSI_APP_ID", "ripetizioni")
VIDEO_JITSI_APP_SECRET = secret("VIDEO_JITSI_APP_SECRET")
VIDEO_JITSI_AUDIENCE = env("VIDEO_JITSI_AUDIENCE", "jitsi")
# "sub" del token: dominio XMPP di Jitsi (docker-jitsi-meet: meet.jitsi) o "*".
VIDEO_JITSI_SUBJECT = env("VIDEO_JITSI_SUBJECT", "meet.jitsi")
VIDEO_ROOM_PREFIX = env("VIDEO_ROOM_PREFIX", "lezione")
# Minuti concessi oltre la fine per rientrare in stanza (cadute di rete, lezione che sfora).
VIDEO_GRACE_MINUTES = env_int("VIDEO_GRACE_MINUTES", 10, minimum=0, maximum=60)
# Videolezione integrata nella pagina (iframe) o in una nuova scheda.
VIDEO_EMBED = env_bool("VIDEO_EMBED", True)
# v0.10.1: una configurazione video incompleta NON blocca piu' l'avvio (migrate/web):
# le videolezioni automatiche restano disattivate, il motivo e' riportato dal system
# check communications.W010 (visibile nei log di migrate) e da apps.communications.video.
# Chiavi Fernet per i segreti effimeri (token di invito/reset) delle consegne:
# prima = attiva, successive solo in lettura (rotazione). Vuoto = derivata da SECRET_KEY.
COMMUNICATIONS_SEAL_KEYS = [
    k.strip() for k in secret("COMMUNICATIONS_SEAL_KEYS").split(",") if k.strip()
]
# Inviti e reset password di s1 consegnati tramite outbox (token mai in chiaro a riposo).
IDENTITY_MESSAGE_SENDER = "apps.communications.identity_hooks.send"
CELERY_BEAT_SCHEDULE["communications-reconcile"] = {
    "task": "apps.communications.tasks.reconcile",
    "schedule": 30.0,
    "options": {"queue": "notifications"},
}
# --- fine s3-comunicazioni ---
# --- s5-infra: osservabilità, health, metriche (GAP-K01/K02/K03, GAP-I07) ---
from apps.ops.logs import build_logging_config  # noqa: E402

INSTALLED_APPS += ["apps.ops"]
MIDDLEWARE.insert(0, "apps.ops.middleware.RequestContextMiddleware")
BUILD_VERSION = os.environ.get("BUILD_VERSION", "dev")
DEPLOY_ENVIRONMENT = os.environ.get("DEPLOY_ENVIRONMENT", "development")
LOGGING = build_logging_config(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    json_logs=os.environ.get("LOG_FORMAT", "json") == "json",
)
OPS_METRICS_TOKEN = os.environ.get("OPS_METRICS_TOKEN", "")
OPS_WORKER_QUEUES = tuple(
    q for q in os.environ.get("OPS_WORKER_QUEUES", "solver").split(",") if q
)
OPS_HEARTBEAT_MAX_AGE = int(os.environ.get("OPS_HEARTBEAT_MAX_AGE", "120"))
# Il worker assente è un alert (SEV2), non rende "non pronto" il web per default.
OPS_READY_REQUIRED_CHECKS = tuple(
    os.environ.get(
        "OPS_READY_REQUIRED_CHECKS", "database,migrations,cache,broker"
    ).split(",")
)
OPS_BACKUP_STATUS_FILE = os.environ.get("OPS_BACKUP_STATUS_FILE", "")
OPS_SLOW_REQUEST_MS = int(os.environ.get("OPS_SLOW_REQUEST_MS", "500"))
OPS_DB_STORAGE_LIMIT_BYTES = int(os.environ.get("OPS_DB_STORAGE_LIMIT_BYTES", "0"))
OPS_DB_WAL_LIMIT_BYTES = int(os.environ.get("OPS_DB_WAL_LIMIT_BYTES", "0"))
OPS_METRIC_PROVIDERS = tuple(
    p for p in os.environ.get("OPS_METRIC_PROVIDERS", "").split(",") if p
)
from apps.ops.schedule import heartbeat_schedule  # noqa: E402

CELERY_BEAT_SCHEDULE.update(heartbeat_schedule(OPS_WORKER_QUEUES))


# P5 · decisioni del committente (3 ottobre 2026)
# D07: lo studente ha un proprio account da 14 anni (consenso digitale, art. 2-quinquies
# Codice privacy); il centro lo attesta all'invito. Il minorenne vede solo lezioni e link
# video: non chiede cambi né dichiara disponibilità (restano ai genitori).
STUDENT_ACCOUNT_MIN_AGE = 14
PORTAL_STUDENT_CAN_REQUEST_CHANGES = env_bool("PORTAL_STUDENT_CAN_REQUEST_CHANGES", False)
PORTAL_STUDENT_CAN_EDIT_AVAILABILITY = False
# DC-CONFERMA-GENITORI: le modifiche chieste dal tutor e accolte dal centro richiedono
# sempre la conferma dei genitori prima di essere applicate.
TUTOR_CHANGES_REQUIRE_GUARDIANS = env_bool("TUTOR_CHANGES_REQUIRE_GUARDIANS", True)
