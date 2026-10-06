"""Lettura tipizzata della configurazione da variabili d'ambiente (s1-sicurezza, GAP-I03).

I segreti si leggono da ``NOME`` oppure da ``NOME_FILE`` (file montato dal secret manager o
da Docker/Kubernetes secrets). Non esistono default per i segreti: il chiamante decide se
l'assenza è un errore. Nessuna funzione registra o stampa i valori letti.
"""

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off", ""}


def env(name, default=None):
    value = os.environ.get(name)
    return default if value is None else value


def env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in _TRUE:
        return True
    if normalized in _FALSE:
        return False
    raise ImproperlyConfigured(f"{name} must be a boolean (0/1)")


def env_int(name, default=None, minimum=None, maximum=None):
    value = os.environ.get(name)
    if value is None or value.strip() == "":
        return default
    try:
        number = int(value)
    except ValueError as exc:
        raise ImproperlyConfigured(f"{name} must be an integer") from exc
    if minimum is not None and number < minimum:
        raise ImproperlyConfigured(f"{name} must be >= {minimum}")
    if maximum is not None and number > maximum:
        raise ImproperlyConfigured(f"{name} must be <= {maximum}")
    return number


def env_list(name, default=None, separator=","):
    value = os.environ.get(name)
    if value is None:
        return list(default or [])
    return [item.strip() for item in value.split(separator) if item.strip()]


def secret(name, default=""):
    """Legge un segreto da ``name`` o dal file indicato in ``name_FILE`` (mutuamente esclusivi)."""
    direct = os.environ.get(name)
    file_path = os.environ.get(name + "_FILE")
    if direct and file_path:
        raise ImproperlyConfigured(f"Set only one of {name} and {name}_FILE")
    if file_path:
        try:
            value = Path(file_path).read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise ImproperlyConfigured(f"{name}_FILE is not readable") from exc
        if not value:
            raise ImproperlyConfigured(f"{name}_FILE is empty")
        return value
    return direct if direct else default


def required(name):
    value = os.environ.get(name, "").strip()
    if not value:
        raise ImproperlyConfigured(f"{name} is required in production")
    return value


def required_secret(name):
    value = secret(name)
    if not value:
        raise ImproperlyConfigured(f"{name} (or {name}_FILE) is required in production")
    return value
