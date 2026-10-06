"""Contesto di richiesta/task condiviso da log, middleware e Celery.

Usa ``contextvars`` così il valore è corretto sia con gunicorn sync sia con
worker Celery prefork e non trapela tra richieste diverse.
"""

from __future__ import annotations

import re
import uuid
from contextvars import ContextVar

correlation_id_var: ContextVar[str | None] = ContextVar("correlation_id", default=None)
actor_id_var: ContextVar[str | None] = ContextVar("actor_id", default=None)

# Header in ingresso accettato solo se "innocuo": niente spazi, niente PII, lunghezza limitata.
_SAFE_ID = re.compile(r"^[A-Za-z0-9._-]{8,64}$")


def new_correlation_id() -> str:
    return uuid.uuid4().hex


def sanitize_correlation_id(value: str | None) -> str:
    """Restituisce l'ID ricevuto se sicuro, altrimenti ne genera uno nuovo."""
    if value and _SAFE_ID.match(value):
        return value
    return new_correlation_id()


def get_correlation_id() -> str | None:
    return correlation_id_var.get()


def pseudonymous_actor(pk) -> str:
    """ID attore pseudonimo e stabile (HMAC con SECRET_KEY): mai username o email nei log."""
    from django.utils.crypto import salted_hmac

    return salted_hmac("apps.ops.actor", str(pk)).hexdigest()[:16]
