"""Log JSON strutturati con redazione dei dati sensibili (GAP-K01, GAP-I07).

Campi obbligatori: ts, level, logger, message, correlation_id, build, env.
Campi facoltativi ammessi: action, outcome, duration_ms, actor_id (pseudonimo),
method, route, status, queue, task, run_id e simili identificativi tecnici.
Vietati: email, nomi, token, cookie, URL video, corpo delle richieste, note.
La redazione avviene due volte (filtro + formatter) come difesa in profondità.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import re
import traceback

from .context import actor_id_var, correlation_id_var

REDACTED = "[REDACTED]"

# Chiavi che non devono mai comparire con il loro valore (confronto case-insensitive,
# anche come sottostringa: "video_url", "notes_private", "X-Api-Token"...).
SENSITIVE_KEY_PARTS = (
    "password",
    "passwd",
    "secret",
    "token",
    "authorization",
    "cookie",
    "session",
    "csrf",
    "api_key",
    "apikey",
    "otp",
    "totp",
    "email",
    "phone",
    "telefono",
    "note",
    "video",
    "meeting",
    "link",
    "body",
    "first_name",
    "last_name",
    "full_name",
    "codice_fiscale",
    "fiscal",
    "iban",
    "address",
    "indirizzo",
)
# Chiavi tecniche esplicitamente consentite anche se contengono parti "sensibili".
SAFE_KEYS = frozenset({"session_id_present", "correlation_id"})

_PATTERNS: list[tuple[re.Pattern, str]] = [
    # Header/parametri di autenticazione: "Bearer xxx", "Token xxx", "Basic xxx".
    (
        re.compile(r"(?i)\b(bearer|token|basic)\s+[A-Za-z0-9._~+/=-]{8,}"),
        r"\1 " + REDACTED,
    ),
    # coppie chiave=valore o chiave: valore con chiavi sensibili (query string, form, testo libero).
    (
        re.compile(
            r"(?i)\b([\w-]*(?:password|passwd|secret|token|api[_-]?key|sessionid|csrftoken|"
            r"signature|sig|otp|auth_?code|invite[_-]?code|key))(\s*[=:]\s*)(\"[^\"]*\"|'[^']*'|[^\s&,;\"']+)"
        ),
        r"\1\2" + REDACTED,
    ),
    # URL assoluti: si conservano schema e host, si rimuovono percorso e query
    # (gli URL di videolezione e i link firmati hanno il segreto nel path).
    (
        re.compile(r"(?i)\b((?:https?|wss?)://[^/\s\"'<>?#]+)[^\s\"'<>]*"),
        r"\1/" + REDACTED,
    ),
    # Token del feed ICS personale (s3: prefisso "ics_") anche fuori da "token=".
    (re.compile(r"\bics_[A-Za-z0-9_-]{8,}"), REDACTED),
    # Email.
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), REDACTED),
    # Codice fiscale italiano.
    (re.compile(r"\b[A-Z]{6}\d{2}[A-EHLMPR-T]\d{2}[A-Z]\d{3}[A-Z]\b", re.I), REDACTED),
    # IBAN.
    (re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b"), REDACTED),
    # Telefoni con prefisso internazionale o cellulari italiani.
    (
        re.compile(
            r"(?<![\w.])(?:\+|00)\d{1,3}[\s.-]?\d{2,4}[\s.-]?\d{3,4}[\s.-]?\d{0,4}\b"
        ),
        REDACTED,
    ),
    (re.compile(r"(?<![\w.])3\d{2}[\s.-]?\d{3}[\s.-]?\d{3,4}\b"), REDACTED),
    # JWT / token firmati Django (tre segmenti) e stringhe opache lunghe (>= 32 caratteri base64/hex
    # che non siano UUID con trattini).
    (
        re.compile(r"\beyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\b"),
        REDACTED,
    ),
    (
        re.compile(r"\b[A-Za-z0-9_-]{6,}:[A-Za-z0-9_-]{6,}:[A-Za-z0-9_-]{20,}\b"),
        REDACTED,
    ),
    (
        re.compile(
            r"\b(?=[A-Za-z0-9+/_-]*\d)(?=[A-Za-z0-9+/_-]*[A-Za-z])[A-Za-z0-9+/_-]{32,}={0,2}"
        ),
        REDACTED,
    ),
]

# Attributi standard di LogRecord: tutto il resto è "extra".
_STANDARD_ATTRS = frozenset(
    vars(logging.LogRecord("x", logging.INFO, "x", 0, "x", None, None))
) | {"message", "asctime", "correlation_id", "build", "env", "actor_id", "_redacted"}


_UUID = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)
_HOLD = re.compile(r"\x00(\d+)\x00")


def redact_text(value: str) -> str:
    """Redige pattern sensibili lasciando intatti gli UUID (ID tecnici, non segreti)."""
    if not value:
        return value
    held: list[str] = []

    def hold(match):
        held.append(match.group(0))
        return f"\x00{len(held) - 1}\x00"

    value = _UUID.sub(hold, value.replace("\x00", ""))
    for pattern, repl in _PATTERNS:
        value = pattern.sub(repl, value)
    return _HOLD.sub(lambda m: held[int(m.group(1))], value)


def is_sensitive_key(key: str) -> bool:
    k = str(key).lower()
    if k in SAFE_KEYS:
        return False
    return any(part in k for part in SENSITIVE_KEY_PARTS)


def redact_value(value, depth: int = 0):
    """Redige ricorsivamente stringhe, dict, liste. Le chiavi sensibili sono azzerate."""
    if depth > 6:
        return REDACTED
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        return {
            str(k): (REDACTED if is_sensitive_key(k) else redact_value(v, depth + 1))
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple, set, frozenset)):
        return [redact_value(v, depth + 1) for v in value]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return redact_text(str(value))


def _extras(record: logging.LogRecord) -> dict:
    return {
        k: v
        for k, v in vars(record).items()
        if k not in _STANDARD_ATTRS and not k.startswith("_")
    }


class RedactFilter(logging.Filter):
    """Sostituisce messaggio, argomenti ed extra del record con versioni redatte."""

    def filter(self, record: logging.LogRecord) -> bool:
        if getattr(record, "_redacted", False):
            return True
        try:
            message = record.getMessage()
        except Exception:  # argomenti incoerenti: non far cadere il logging
            message = str(record.msg)
        record.msg = redact_text(message)
        record.args = None
        for key, value in _extras(record).items():
            setattr(
                record, key, REDACTED if is_sensitive_key(key) else redact_value(value)
            )
        record._redacted = True
        return True


class CorrelationFilter(logging.Filter):
    """Aggiunge correlation_id, actor_id pseudonimo, build e ambiente a ogni record."""

    def filter(self, record: logging.LogRecord) -> bool:
        from django.conf import settings

        # django.request registra 4xx/5xx dopo la catena dei middleware (contesto già
        # azzerato): in quel caso l'id è sulla richiesta allegata al record.
        record.correlation_id = (
            getattr(record, "correlation_id", None)
            or correlation_id_var.get()
            or getattr(getattr(record, "request", None), "correlation_id", None)
        )
        record.actor_id = getattr(record, "actor_id", None) or actor_id_var.get()
        record.build = getattr(settings, "BUILD_VERSION", "unknown")
        record.env = getattr(settings, "DEPLOY_ENVIRONMENT", "unknown")
        return True


class JsonFormatter(logging.Formatter):
    """Una riga JSON per evento; redige sempre (anche senza RedactFilter)."""

    def format(self, record: logging.LogRecord) -> str:
        if not getattr(record, "_redacted", False):
            RedactFilter().filter(record)
        payload = {
            "ts": dt.datetime.fromtimestamp(record.created, tz=dt.timezone.utc)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.msg
            if isinstance(record.msg, str)
            else redact_text(str(record.msg)),
            "correlation_id": getattr(record, "correlation_id", None),
            "build": getattr(record, "build", None),
            "env": getattr(record, "env", None),
        }
        actor = getattr(record, "actor_id", None)
        if actor:
            payload["actor_id"] = actor
        for key, value in _extras(record).items():
            payload.setdefault(key, value)
        if record.exc_info:
            exc_type = record.exc_info[0]
            payload["exc_type"] = exc_type.__name__ if exc_type else None
            payload["exc"] = redact_text(
                "".join(traceback.format_exception(*record.exc_info))[-4000:]
            )
        if record.stack_info:
            payload["stack"] = redact_text(record.stack_info[-2000:])
        return json.dumps(
            payload, ensure_ascii=False, default=lambda o: redact_text(str(o))
        )


def build_logging_config(level: str = "INFO", json_logs: bool = True) -> dict:
    """Configurazione LOGGING per settings (stdout, JSON, redazione)."""
    formatter = "json" if json_logs else "plain"
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "filters": {
            "context": {"()": "apps.ops.logs.CorrelationFilter"},
            "redact": {"()": "apps.ops.logs.RedactFilter"},
        },
        "formatters": {
            "json": {"()": "apps.ops.logs.JsonFormatter"},
            "plain": {
                "format": "%(asctime)s %(levelname)s %(name)s [%(correlation_id)s] %(message)s"
            },
        },
        "handlers": {
            "stdout": {
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",
                "formatter": formatter,
                "filters": ["context", "redact"],
            }
        },
        "root": {"handlers": ["stdout"], "level": level},
        "loggers": {
            "django": {"level": level, "propagate": True},
            # django.server/request duplicano il nostro access log e includono il path grezzo.
            "django.server": {"level": "WARNING", "propagate": True},
            "django.request": {"level": "ERROR", "propagate": True},
            "django.security": {"level": "WARNING", "propagate": True},
            "django.db.backends": {"level": "WARNING", "propagate": True},
            "celery": {"level": level, "propagate": True},
            "gunicorn.error": {"level": level, "propagate": True},
            # gunicorn.access stampa l'URL completo con query string: disattivato,
            # l'access log strutturato è emesso da apps.ops.middleware.
            "gunicorn.access": {"level": "CRITICAL", "propagate": False},
            "ops.access": {"level": level, "propagate": True},
        },
    }
