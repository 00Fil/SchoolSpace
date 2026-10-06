"""Export protetti: audience nominativa, download a scadenza e token monouso (GAP-H07, T42).

Il file sta in ``PRIVACY_EXPORT_DIR`` (fuori da static/media, permessi 0600) con nome casuale;
nel DB restano solo hash del contenuto e del token. In produzione la directory va su volume
cifrato a riposo (J04): la cifratura applicativa non è inclusa per non aggiungere dipendenze.
"""

import hashlib
import os
import secrets
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.governance.audit import record

from .errors import Gone, NotAllowed
from .models import ProtectedExport
from .registry import token_digest


def export_dir():
    path = Path(settings.PRIVACY_EXPORT_DIR)
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    return path


def export_ttl():
    return timedelta(hours=int(getattr(settings, "PRIVACY_EXPORT_TTL_HOURS", 24)))


@transaction.atomic
def create_export(
    *, actor, audience, content, fmt, filename, purpose, privacy_request=None
):
    """Salva il contenuto e restituisce (export, token in chiaro, mostrato una sola volta)."""
    token = secrets.token_urlsafe(32)
    storage_name = secrets.token_hex(16)
    target = export_dir() / storage_name
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(content)
    export = ProtectedExport.objects.create(
        created_by=actor,
        audience=audience,
        purpose=purpose,
        privacy_request=privacy_request,
        format=fmt,
        filename=filename,
        storage_name=storage_name,
        size_bytes=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
        token_hash=token_digest(token),
        expires_at=timezone.now() + export_ttl(),
    )

    record(
        "EXPORT",
        "EXPORT_CREATED",
        actor=actor,
        obj=export,
        purpose=purpose,
        details={
            "audience": str(audience.pk),
            "format": fmt,
            "size_bytes": len(content),
            "sha256": export.sha256,
            "expires_at": export.expires_at,
            "privacy_request": str(privacy_request.pk) if privacy_request else None,
        },
    )
    return export, token


def _deny(export, user, code):
    record(
        "EXPORT",
        "EXPORT_DOWNLOAD_DENIED",
        actor=user,
        obj=export,
        details={"code": code},
    )


def consume(export_id, *, user, token):
    """Verifica audience, token, scadenza e uso singolo; restituisce (export, bytes).

    I tentativi negati sono auditati in una transazione propria, così restano anche se
    la richiesta fallisce.
    """
    with transaction.atomic():
        export = (
            ProtectedExport.objects.select_for_update().filter(pk=export_id).first()
        )
        if export is None:
            raise Gone("EXPORT_UNAVAILABLE", "Export non disponibile")
        now = timezone.now()
        code = None
        if export.audience_id != user.pk:
            code = "WRONG_AUDIENCE"
        elif not isinstance(token, str) or not secrets.compare_digest(
            token_digest(token), export.token_hash
        ):
            code = "BAD_TOKEN"
        elif export.revoked_at or export.purged_at:
            code = "REVOKED"
        elif export.downloaded_at:
            code = "ALREADY_DOWNLOADED"
        elif export.expires_at <= now:
            code = "EXPIRED"
        if code:
            _deny(export, user, code)
        else:
            path = export_dir() / export.storage_name
            content = path.read_bytes()
            if hashlib.sha256(content).hexdigest() != export.sha256:
                code = "INTEGRITY"
                _deny(export, user, code)
            else:
                export.downloaded_at = now
                export.save(update_fields=["downloaded_at"])
                record("EXPORT", "EXPORT_DOWNLOADED", actor=user, obj=export)
    if code == "WRONG_AUDIENCE":
        raise NotAllowed(code, "Export destinato a un altro utente")
    if code:
        raise Gone(code, "Export non disponibile, scaduto o già scaricato")
    # Il file non serve più: un solo download (rigenerare se necessario).
    purge_file(export, reason="downloaded")
    return export, content


def purge_file(export, reason="retention"):
    path = export_dir() / export.storage_name if export.storage_name else None
    if path and path.exists():
        path.unlink()
    ProtectedExport.objects.filter(pk=export.pk).update(
        purged_at=timezone.now(), storage_name=""
    )
    record(
        "EXPORT",
        "EXPORT_PURGED",
        object_type="privacy.protectedexport",
        object_id=str(export.pk),
        details={"reason": reason},
    )


@transaction.atomic
def revoke_export(actor, export, *, reason):
    from .registry import require_center, require_reason

    require_center(actor)
    reason = require_reason(reason)
    ProtectedExport.objects.filter(pk=export.pk).update(revoked_at=timezone.now())
    record("EXPORT", "EXPORT_REVOKED", actor=actor, obj=export, reason=reason)
    transaction.on_commit(lambda: purge_file(export, reason="revoked"))
