"""Rate limit persistente con blocco progressivo (GAP-B05).

Lo stato vive nella cache Django configurata (``IDENTITY_THROTTLE_CACHE``): Redis in
produzione, così il limite è condiviso tra worker e processi. Le chiavi contengono solo
digest, mai email o IP in chiaro.

Per ogni scope e dimensione (``ip``/``identity``) si contano i fallimenti in una finestra;
superato il limite scatta un blocco di durata ``base * 2**livello`` (fino al massimo), e il
livello cresce a ogni blocco successivo entro ``THROTTLE_LEVEL_TTL_SECONDS``.
"""

import math
import time
from dataclasses import dataclass

from django.core.cache import caches

from . import conf
from .tokens import identity_digest


@dataclass(frozen=True)
class Decision:
    allowed: bool
    retry_after: int = 0


def _cache():
    return caches[conf.get("THROTTLE_CACHE")]


def _rules(scope):
    return conf.get("THROTTLE_RULES").get(scope, {})


def _key(scope, kind, value, suffix):
    return f"idthr:{scope}:{kind}:{identity_digest(scope, kind, value)}:{suffix}"


def _dimensions(scope, ip, identity):
    rules = _rules(scope)
    for kind, value in (("ip", ip), ("identity", identity)):
        if value and kind in rules:
            limit, window = rules[kind]
            yield kind, value, int(limit), int(window)


def check(scope, ip=None, identity=None):
    cache = _cache()
    now = time.time()
    wait = 0
    for kind, value, _, _ in _dimensions(scope, ip, identity):
        until = cache.get(_key(scope, kind, value, "lock"))
        if until and until > now:
            wait = max(wait, math.ceil(until - now))
    return Decision(allowed=wait == 0, retry_after=wait)


def _incr(cache, key, timeout):
    cache.add(key, 0, timeout)
    try:
        return cache.incr(key)
    except ValueError:  # chiave scaduta tra add e incr
        cache.set(key, 1, timeout)
        return 1


def fail(scope, ip=None, identity=None):
    """Registra un tentativo fallito (o una richiesta, per gli scope a consumo)."""
    cache = _cache()
    base = int(conf.get("THROTTLE_LOCKOUT_BASE_SECONDS"))
    maximum = int(conf.get("THROTTLE_LOCKOUT_MAX_SECONDS"))
    level_ttl = int(conf.get("THROTTLE_LEVEL_TTL_SECONDS"))
    for kind, value, limit, window in _dimensions(scope, ip, identity):
        count = _incr(cache, _key(scope, kind, value, "n"), window)
        if count >= limit:
            level_key = _key(scope, kind, value, "lvl")
            level = _incr(cache, level_key, level_ttl) - 1
            duration = min(maximum, base * (2 ** min(level, 20)))
            cache.set(
                _key(scope, kind, value, "lock"), time.time() + duration, duration
            )
            cache.delete(_key(scope, kind, value, "n"))


def consume(scope, ip=None, identity=None):
    """Controlla e conta una richiesta (per scope senza esito, es. richiesta di reset)."""
    decision = check(scope, ip=ip, identity=identity)
    if decision.allowed:
        fail(scope, ip=ip, identity=identity)
    return decision


def succeed(scope, identity=None):
    """Esito positivo: azzera contatore e livello dell'identità (non dell'IP)."""
    if not identity:
        return
    cache = _cache()
    for suffix in ("n", "lvl"):
        cache.delete(_key(scope, "identity", identity, suffix))
