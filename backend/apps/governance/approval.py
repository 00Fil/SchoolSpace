"""Gate G1: approvato dal gestore del centro (superuser) o da variabile d'ambiente."""

from django.conf import settings


def g1_approved():
    if settings.G1_APPROVED:
        return True
    from .models import Decision

    try:
        d = Decision.objects.filter(code="G1").first()
    except Exception:  # DB non disponibile: gate chiuso
        return False
    return bool(
        d
        and d.status == "APPROVED"
        and d.outcome.strip()
        and d.owner.strip()
        and d.approved_at
    )
