import hashlib
import secrets


def new_token():
    """Token opaco di 256 bit e relativo hash SHA-256 (solo l'hash va salvato)."""
    token = secrets.token_urlsafe(32)
    return token, hash_token(token)


def hash_token(token):
    return hashlib.sha256(str(token).encode("utf-8")).hexdigest()


def identity_digest(*parts):
    """Digest non reversibile per chiavi di cache e audit: niente email in chiaro."""
    raw = "\x1f".join(str(p) for p in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]
