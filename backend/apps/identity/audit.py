from .models import IdentityAuditEvent
from .net import client_ip

FORBIDDEN_KEYS = {"password", "token", "code", "secret", "recovery_code"}


def record(
    operation, *, actor=None, subject=None, object_id=None, request=None, **details
):
    """Aggiunge un evento di audit. Rifiuta chiavi che potrebbero contenere segreti."""
    leaked = FORBIDDEN_KEYS & set(details)
    if leaked:
        raise ValueError(f"Audit details must not contain {sorted(leaked)}")
    if actor is not None and not getattr(actor, "is_authenticated", False):
        actor = None
    return IdentityAuditEvent.objects.create(
        operation=operation,
        actor=actor,
        subject=subject,
        object_id=object_id,
        ip=client_ip(request) if request is not None else None,
        details=details,
    )
