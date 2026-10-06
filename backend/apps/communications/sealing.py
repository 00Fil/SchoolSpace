"""Cifratura dei segreti effimeri delle consegne (Fernet: AES-128-CBC + HMAC-SHA256).

Chiavi: ``COMMUNICATIONS_SEAL_KEYS`` (prima = attiva, le altre solo per decifrare durante
la rotazione). Se assenti, chiave derivata con HKDF da ``SECRET_KEY`` e dai suoi fallback:
accettabile in sviluppo, in produzione è raccomandata una chiave dedicata (check W002).
"""

import base64
import json

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from django.conf import settings


class SealError(Exception):
    pass


def _derive(secret):
    key = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"gestionale-ripetizioni",
        info=b"communications-sealed-secret-v1",
    ).derive(secret.encode())
    return base64.urlsafe_b64encode(key)


def _fernet():
    keys = [k.encode() for k in settings.COMMUNICATIONS_SEAL_KEYS if k]
    if not keys:
        keys = [_derive(settings.SECRET_KEY)] + [
            _derive(k) for k in getattr(settings, "SECRET_KEY_FALLBACKS", []) if k
        ]
    return MultiFernet([Fernet(k) for k in keys])


def seal(values):
    if not isinstance(values, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in values.items()
    ):
        raise SealError("Segreti: dizionario di stringhe")
    return _fernet().encrypt(json.dumps(values).encode()).decode()


def unseal(ciphertext):
    try:
        return json.loads(_fernet().decrypt(ciphertext.encode()))
    except (InvalidToken, ValueError) as exc:
        raise SealError("Segreto non decifrabile") from exc
