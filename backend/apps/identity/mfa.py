"""TOTP (RFC 6238) e codici di recupero (GAP-B04)."""

import base64
import hashlib
import hmac
import io
import secrets
import time

import pyotp
from django.db import transaction
from django.utils import timezone

from . import conf
from .models import RecoveryCode, TOTPDevice

STEP = 30
_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # senza 0/O/1/I


def _now():
    return time.time()


class MFAError(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def confirmed_device(user):
    return TOTPDevice.objects.filter(account=user, confirmed_at__isnull=False).first()


def is_enrolled(user):
    return confirmed_device(user) is not None


def provisioning_uri(user, secret):
    return pyotp.TOTP(secret).provisioning_uri(
        name=user.email or user.username, issuer_name=conf.get("MFA_ISSUER")
    )


def qr_svg(uri):
    try:
        import qrcode
        import qrcode.image.svg
    except ImportError:  # pragma: no cover - dipendenza dichiarata
        return None
    image = qrcode.make(uri, image_factory=qrcode.image.svg.SvgPathImage)
    buffer = io.BytesIO()
    image.save(buffer)
    return "data:image/svg+xml;base64," + base64.b64encode(buffer.getvalue()).decode()


@transaction.atomic
def begin_setup(user):
    if is_enrolled(user):
        raise MFAError("MFA_ALREADY_ENROLLED")
    secret = pyotp.random_base32(32)
    TOTPDevice.objects.update_or_create(
        account=user,
        defaults={"secret": secret, "confirmed_at": None, "last_used_step": 0},
    )
    uri = provisioning_uri(user, secret)
    return {"secret": secret, "otpauth_uri": uri, "qr_svg": qr_svg(uri)}


def _match_step(device, code, at=None):
    code = (code or "").strip().replace(" ", "")
    if len(code) != 6 or not code.isdigit():
        return None
    totp = pyotp.TOTP(device.secret)
    now_step = int((at if at is not None else _now()) // STEP)
    for step in (now_step - 1, now_step, now_step + 1):
        if hmac.compare_digest(totp.at(step * STEP), code):
            return step
    return None


def _consume(device, code):
    """Verifica il codice e impedisce il riuso dello stesso passo (anti-replay)."""
    device = TOTPDevice.objects.select_for_update().get(pk=device.pk)
    step = _match_step(device, code)
    if step is None or step <= device.last_used_step:
        return False
    device.last_used_step = step
    device.save(update_fields=["last_used_step"])
    return True


def _normalize_recovery(code):
    return "".join(ch for ch in (code or "").upper() if ch.isalnum())


def hash_recovery(code):
    return hashlib.sha256(_normalize_recovery(code).encode()).hexdigest()


def _new_recovery_code():
    raw = "".join(secrets.choice(_ALPHABET) for _ in range(16))  # 80 bit
    return "-".join(raw[i : i + 4] for i in range(0, 16, 4))


@transaction.atomic
def regenerate_recovery_codes(user):
    RecoveryCode.objects.filter(account=user).delete()
    codes = [_new_recovery_code() for _ in range(int(conf.get("MFA_RECOVERY_CODES")))]
    RecoveryCode.objects.bulk_create(
        RecoveryCode(account=user, code_hash=hash_recovery(c)) for c in codes
    )
    return codes


@transaction.atomic
def confirm_setup(user, code):
    device = (
        TOTPDevice.objects.select_for_update()
        .filter(account=user, confirmed_at__isnull=True)
        .first()
    )
    if device is None:
        raise MFAError("MFA_SETUP_NOT_STARTED")
    if not _consume(device, code):
        raise MFAError("INVALID_CODE")
    TOTPDevice.objects.filter(pk=device.pk).update(confirmed_at=timezone.now())
    return regenerate_recovery_codes(user)


@transaction.atomic
def verify(user, code=None, recovery_code=None):
    """True se il codice TOTP o un codice di recupero non usato è valido. Restituisce il metodo."""
    device = confirmed_device(user)
    if device is None:
        return None
    if code and _consume(device, code):
        return "totp"
    if recovery_code:
        updated = RecoveryCode.objects.filter(
            account=user, code_hash=hash_recovery(recovery_code), used_at__isnull=True
        ).update(used_at=timezone.now())
        if updated:
            return "recovery_code"
    return None


def remaining_recovery_codes(user):
    return RecoveryCode.objects.filter(account=user, used_at__isnull=True).count()


@transaction.atomic
def reset(user):
    TOTPDevice.objects.filter(account=user).delete()
    RecoveryCode.objects.filter(account=user).delete()
