"""Impostazioni di produzione (s1-sicurezza; tec1 "Esempio di impostazioni di produzione").

Uso: ``DJANGO_SETTINGS_MODULE=config.settings_production``. Ogni valore obbligatorio manca
=> ``ImproperlyConfigured`` all'avvio (fail fast). Segreti da variabile o da ``*_FILE``.
Verifica: ``python manage.py check --deploy --fail-level WARNING`` deve dare 0 avvisi.
"""

import ipaddress
import os

from django.core.exceptions import ImproperlyConfigured

# Il modulo base legge DJANGO_DEBUG: in produzione è vietato attivarlo.
if os.environ.get("DJANGO_DEBUG", "0") not in ("", "0"):
    raise ImproperlyConfigured("DJANGO_DEBUG must be 0 in production")
if os.environ.get("USE_SQLITE_FOR_TESTS") == "1":
    raise ImproperlyConfigured("USE_SQLITE_FOR_TESTS is forbidden in production")

from .env import env, env_bool, env_int, env_list, required, required_secret, secret  # noqa: E402
from .settings import *  # noqa: E402,F401,F403
from .settings import DATABASES, REST_FRAMEWORK, SECRET_KEY  # noqa: E402

DEBUG = False

# --- Segreti (GAP-I03) -----------------------------------------------------------------
_WEAK_MARKERS = (
    "replace-with",
    "changeme",
    "django-insecure",
    "test-only",
    "ci-only",
    "not-for-production",
)
if (
    len(SECRET_KEY) < 50
    or len(set(SECRET_KEY)) < 10
    or any(m in SECRET_KEY.lower() for m in _WEAK_MARKERS)
):
    raise ImproperlyConfigured(
        "DJANGO_SECRET_KEY is too weak: use >= 50 random characters from a secret manager"
    )

# --- Host e origini --------------------------------------------------------------------
ALLOWED_HOSTS = [h.strip() for h in required("DJANGO_ALLOWED_HOSTS").split(",") if h]
if any(h in ("*", ".") or h.startswith("*") for h in ALLOWED_HOSTS):
    raise ImproperlyConfigured("DJANGO_ALLOWED_HOSTS must not contain wildcards")
CSRF_TRUSTED_ORIGINS = [
    o.strip() for o in required("DJANGO_CSRF_TRUSTED_ORIGINS").split(",") if o
]
if any(not o.startswith("https://") or "*" in o for o in CSRF_TRUSTED_ORIGINS):
    raise ImproperlyConfigured(
        "DJANGO_CSRF_TRUSTED_ORIGINS must be explicit https origins"
    )
IDENTITY_PORTAL_BASE_URL = env("PORTAL_BASE_URL", CSRF_TRUSTED_ORIGINS[0])
if not IDENTITY_PORTAL_BASE_URL.startswith("https://"):
    raise ImproperlyConfigured("PORTAL_BASE_URL must be https in production")

# --- TLS, cookie e header (GAP-I02) ----------------------------------------------------
# Il reverse proxy termina TLS e imposta X-Forwarded-Proto; senza questa impostazione
# Django vedrebbe http e andrebbe in loop di redirect.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = False
SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", True)
# HSTS: si parte da 1 ora e si sale a 1 anno dopo la verifica dei domini (paper §10.3).
SECURE_HSTS_SECONDS = env_int("DJANGO_HSTS_SECONDS", 3600, minimum=1)
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool("DJANGO_HSTS_INCLUDE_SUBDOMAINS", True)
SECURE_HSTS_PRELOAD = env_bool("DJANGO_HSTS_PRELOAD", False)
SECURE_REFERRER_POLICY = "same-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_NAME = env("SESSION_COOKIE_NAME", "__Host-sessionid")
# Il frontend legge il cookie "csrftoken": cambiare nome solo insieme a frontend/src/api.ts.
CSRF_COOKIE_NAME = env("CSRF_COOKIE_NAME", "csrftoken")
SECURITY_CSP_REPORT_ONLY = env_bool("CSP_REPORT_ONLY", False)
DATA_UPLOAD_MAX_MEMORY_SIZE = env_int("DATA_UPLOAD_MAX_MEMORY_SIZE", 1_048_576)
SILENCED_SYSTEM_CHECKS = []
if not SECURE_HSTS_PRELOAD:
    # La preload list è irreversibile a breve termine: decisione esplicita dopo la verifica
    # di tutti i sottodomini (tec1). Fino ad allora W021 è atteso.
    SILENCED_SYSTEM_CHECKS.append("security.W021")

# --- Autenticazione (GAP-B01, B04, B05) ------------------------------------------------
IDENTITY_ALLOW_USERNAME_LOGIN = False
IDENTITY_MFA_ENFORCED = True  # non disattivabile in produzione
IDENTITY_TRUSTED_PROXY_HOPS = env_int("TRUSTED_PROXY_HOPS", 1, minimum=0)
REST_FRAMEWORK = {
    **REST_FRAMEWORK,
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "NUM_PROXIES": IDENTITY_TRUSTED_PROXY_HOPS or None,
}

# --- Admin Django (GAP-I06): spento salvo decisione esplicita, poi solo da allowlist ----
IDENTITY_ADMIN_ENABLED = env_bool("DJANGO_ADMIN_ENABLED", False)
IDENTITY_ADMIN_ALLOWED_NETWORKS = env_list("DJANGO_ADMIN_ALLOWED_NETWORKS")
IDENTITY_ADMIN_REQUIRE_MFA = True
if IDENTITY_ADMIN_ENABLED:
    if not IDENTITY_ADMIN_ALLOWED_NETWORKS:
        raise ImproperlyConfigured(
            "DJANGO_ADMIN_ALLOWED_NETWORKS is required when the admin is enabled"
        )
    for _network in IDENTITY_ADMIN_ALLOWED_NETWORKS:
        try:
            if ipaddress.ip_network(_network, strict=False).prefixlen == 0:
                raise ValueError
        except ValueError as exc:
            raise ImproperlyConfigured(f"Invalid admin network: {_network}") from exc

# --- Database: TLS verificato e connessioni persistenti --------------------------------
_sslmode = env("DB_SSLMODE", "verify-full")
if _sslmode not in ("require", "verify-ca", "verify-full"):
    raise ImproperlyConfigured("DB_SSLMODE must be require, verify-ca or verify-full")
_db_options = {"sslmode": _sslmode}
if _sslmode in ("verify-ca", "verify-full"):
    _db_options["sslrootcert"] = required("DB_SSLROOTCERT")
DATABASES = {
    "default": {
        **DATABASES["default"],
        "NAME": required("POSTGRES_DB"),
        "USER": required("POSTGRES_USER"),
        "PASSWORD": required_secret("POSTGRES_PASSWORD"),
        "HOST": required("DB_HOST"),
        "CONN_MAX_AGE": env_int("DB_CONN_MAX_AGE", 60, minimum=0),
        "CONN_HEALTH_CHECKS": True,
        "OPTIONS": _db_options,
    }
}

# --- Cache condivisa (throttle, rate limit) e broker -----------------------------------
_cache_url = required_secret("CACHE_URL")
if not _cache_url.startswith("rediss://") and not env_bool(
    "CACHE_ALLOW_PLAINTEXT", False
):
    raise ImproperlyConfigured("CACHE_URL must use rediss:// (TLS) in production")
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": _cache_url,
        "KEY_PREFIX": env("CACHE_KEY_PREFIX", "ripetizioni"),
        "TIMEOUT": 300,
    }
}
CELERY_BROKER_URL = required_secret("CELERY_BROKER_URL")
if CELERY_BROKER_URL.startswith("rediss://"):
    CELERY_BROKER_USE_SSL = {"ssl_cert_reqs": "required"}
elif not env_bool("CELERY_BROKER_ALLOW_PLAINTEXT", False):
    raise ImproperlyConfigured("CELERY_BROKER_URL must use rediss:// in production")
# v0.9.4: i run accurati vanno al servizio worker-solver-long (compose.prod.yaml).
PLANNING_THOROUGH_QUEUE = env("PLANNING_THOROUGH_QUEUE", "solver_long")
CELERY_BROKER_TRANSPORT_OPTIONS = {
    "visibility_timeout": env_int("CELERY_VISIBILITY_TIMEOUT", 3600, minimum=120),
    "socket_connect_timeout": 5,
    "socket_timeout": 5,
}

# --- Flag di funzione (guida v3.1, P0/T1; sostituisce GAP-E09) -------------------------
# I vecchi flag sperimentali restano vietati: in produzione si usano solo i FEATURE_*.
for _flag in ("EXPERIMENTAL_DB_PLANNING", "EXPERIMENTAL_CALENDAR"):
    if os.environ.get(_flag, "0") == "1":
        raise ImproperlyConfigured(f"{_flag} is forbidden in production: use FEATURE_*")
FEATURE_PLANNING = env_bool("FEATURE_PLANNING", True)
FEATURE_CALENDAR = env_bool("FEATURE_CALENDAR", True)
# Il laboratorio usa dati di esempio: solo su richiesta esplicita (es. staging).
FEATURE_PLANNING_LAB = env_bool("FEATURE_PLANNING_LAB", False)
EXPERIMENTAL_DB_PLANNING = FEATURE_PLANNING  # alias deprecato
EXPERIMENTAL_CALENDAR = FEATURE_CALENDAR  # alias deprecato
CALENDAR_ALLOW_SQLITE_TESTS = False

# --- s5-infra: esercizio (GAP-J03/J04, GAP-K01/K02) --------------------------------------
from apps.ops.schedule import heartbeat_schedule  # noqa: E402
from .settings import CELERY_BEAT_SCHEDULE  # noqa: E402

DEPLOY_ENVIRONMENT = env("DEPLOY_ENVIRONMENT", "production")
if DEPLOY_ENVIRONMENT not in ("staging", "production"):
    raise ImproperlyConfigured("DEPLOY_ENVIRONMENT must be staging or production")
BUILD_VERSION = env("BUILD_VERSION", "unknown")  # impostata dall'immagine (build arg)
# Senza token /metrics risponde 404 (DEBUG=False): default sicuro.
OPS_METRICS_TOKEN = secret("OPS_METRICS_TOKEN", "")
# Probe e scrape interni arrivano in HTTP direttamente su web:8000 (rete privata).
SECURE_REDIRECT_EXEMPT = [r"^healthz$", r"^readyz$", r"^metrics$"]
# CA privata di Redis (rediss://) per cache e broker, se non firmato da una CA pubblica.
_redis_ca = env("REDIS_CA_PATH", "")
if _redis_ca:
    if CACHES["default"]["LOCATION"].startswith("rediss://"):
        CACHES["default"]["OPTIONS"] = {
            "ssl_cert_reqs": "required",
            "ssl_ca_certs": _redis_ca,
        }
    if CELERY_BROKER_URL.startswith("rediss://"):
        CELERY_BROKER_USE_SSL = {"ssl_cert_reqs": "required", "ssl_ca_certs": _redis_ca}
# Code separate con worker dedicati (compose.prod.yaml): solver, notifications, default.
CELERY_TASK_DEFAULT_QUEUE = "default"
CELERY_TASK_ROUTES = {
    "apps.scheduling.tasks.*": {"queue": "solver"},
    "apps.communications.tasks.*": {"queue": "notifications"},
    "apps.privacy.tasks.*": {"queue": "default"},
}
CELERY_WORKER_MAX_TASKS_PER_CHILD = env_int("CELERY_MAX_TASKS_PER_CHILD", 20, minimum=1)
OPS_WORKER_QUEUES = tuple(
    env_list("OPS_WORKER_QUEUES", ["solver", "notifications", "default"])
)
CELERY_BEAT_SCHEDULE = {
    **{
        k: v
        for k, v in CELERY_BEAT_SCHEDULE.items()
        if not k.startswith("ops-heartbeat-")
    },
    **heartbeat_schedule(OPS_WORKER_QUEUES),
}
# --- fine s5-infra ---
