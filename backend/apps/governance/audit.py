"""Audit applicativo append-only unificato (FR23, paper §10.5).

Ogni evento registra attore, scopo, oggetto, comando, versione, motivo e correlazione.
I dettagli passano sempre da :func:`redact`: password, token, segreti, URL video e
note libere non entrano mai nell'audit (T42).
"""

import re
import uuid

from django.db import transaction

REDACTED = "[REDATTO]"
SECRET_PARTS = {
    "password",
    "passwd",
    "pwd",
    "token",
    "secret",
    "otp",
    "totp",
    "mfa",
    "cookie",
    "csrf",
    "authorization",
    "apikey",
    "url",
    "note",
    "notes",
    "nota",
    "diagnosi",
    "diagnosis",
    "bes",
    "dsa",
}
_SPLIT = re.compile(r"[^a-z0-9]+")
_SECRET_VALUE = re.compile(
    r"(https?://\S+|pbkdf2_\S+|argon2\S*|md5\$\S+|bcrypt\S*|"
    r"\b(?![0-9a-fA-F]{8}-[0-9a-fA-F]{4}-)(?![0-9a-f]{64}\b)[A-Za-z0-9_\-]{32,})"
)


def _is_secret_key(key):
    lowered = key.lower()
    compact = _SPLIT.sub("", lowered)
    if any(
        word in compact
        for word in ("password", "token", "secret", "apikey", "privatekey", "sessionid")
    ):
        return True
    return bool(SECRET_PARTS & set(_SPLIT.split(lowered)))


MAX_TEXT = 500


def redact(value, _depth=0):
    """Restituisce una copia JSON-compatibile priva di segreti e contenuti sensibili."""
    if _depth > 8:
        return REDACTED
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            key = str(key)
            out[key] = REDACTED if _is_secret_key(key) else redact(item, _depth + 1)
        return out
    if isinstance(value, (list, tuple, set)):
        return [redact(item, _depth + 1) for item in value]
    if isinstance(value, str):
        text = _SECRET_VALUE.sub(REDACTED, value)
        return text[:MAX_TEXT]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return redact(str(value), _depth + 1)


def record(
    category,
    operation,
    *,
    actor=None,
    obj=None,
    object_type="",
    object_id="",
    object_version=None,
    purpose="",
    reason="",
    command="",
    correlation_id=None,
    details=None,
):
    """Scrive un evento di audit nella transazione corrente (rollback = nessun evento)."""
    from .models import AuditEvent

    if obj is not None:
        object_type = object_type or obj._meta.label_lower
        object_id = object_id or str(obj.pk)
        if object_version is None:
            object_version = getattr(obj, "version", None)
    if actor is not None and not getattr(actor, "is_authenticated", False):
        actor = None
    with transaction.atomic():
        return AuditEvent.objects.create(
            category=category,
            operation=operation,
            actor=actor,
            object_type=object_type,
            object_id=str(object_id or ""),
            object_version=object_version,
            purpose=purpose[:120],
            reason=redact(reason or "")[:200],
            command=command[:120],
            correlation_id=correlation_id or uuid.uuid4(),
            details=redact(details or {}),
        )
