from django.db.models import Q
from django.utils import timezone

from . import conf

CONTEXT_ATTR = "_identity_context"


def granted_roles(user):
    """Ruoli concessi e validi ora, indipendenti dal contesto selezionato."""
    if not user.is_authenticated or not user.is_active:
        return set()
    now = timezone.now()
    return set(
        user.role_grants.filter(valid_from__lte=now, revoked_at__isnull=True)
        .filter(Q(valid_until__isnull=True) | Q(valid_until__gt=now))
        .values_list("role", flat=True)
    )


def available_contexts(user):
    """Contesti selezionabili: ruoli concessi più CENTER per il superuser (GAP-B07)."""
    roles = granted_roles(user)
    if user.is_authenticated and user.is_active and user.is_superuser:
        roles.add("CENTER")
    return roles


def selected_context(user):
    return getattr(user, CONTEXT_ATTR, None)


def active_roles(user):
    """Ruoli effettivi della richiesta: se l'utente ha scelto un contesto vale solo quello.

    Il contesto è impostato dal middleware solo dopo la verifica server-side della
    concessione; un parametro client non abilita mai ruoli non concessi.
    """
    roles = granted_roles(user)
    context = selected_context(user)
    if context:
        return roles & {context}
    return roles


def is_center(user):
    if not (user.is_authenticated and user.is_active):
        return False
    context = selected_context(user)
    if user.is_superuser and context in (None, "CENTER"):
        return True
    return "CENTER" in active_roles(user)


def guardian_blocked_students():
    """Studenti maggiorenni confermati per cui la policy esclude l'accesso dei tutori (D07)."""
    from .models import StudentAccessPolicy

    default = conf.get("ADULT_GUARDIAN_ACCESS")
    blocked = Q(guardian_access="NONE") | Q(
        guardian_access="CONSENT_REQUIRED", student_consent_at__isnull=True
    )
    if default == "NONE":
        blocked |= Q(guardian_access="DEFAULT")
    elif default == "CONSENT_REQUIRED":
        blocked |= Q(guardian_access="DEFAULT", student_consent_at__isnull=True)
    return StudentAccessPolicy.objects.filter(adult_confirmed=True).filter(blocked)


def guardian_excluded_students():
    """Maggiorenni confermati con accesso dei tutori ``NONE``: nessuna eccezione per delega."""
    from .models import StudentAccessPolicy

    default = conf.get("ADULT_GUARDIAN_ACCESS")
    excluded = Q(guardian_access="NONE")
    if default == "NONE":
        excluded |= Q(guardian_access="DEFAULT")
    return StudentAccessPolicy.objects.filter(adult_confirmed=True).filter(excluded)


def _privacy_installed():
    from django.apps import apps

    return apps.is_installed("apps.privacy")


def active_guardian_links(now=None, **flags):
    """Deleghe utilizzabili ora, per tutti gli account (portali e notifiche).

    Regole (s1 + s4, D07 da approvare):
    * verificata, non revocata, nel periodo di validità;
    * maggiorenne confermato con policy che esclude i tutori → esclusa, salvo
      ``CONSENT_REQUIRED`` e delega riconfermata dallo studente (consenso per singola delega);
    * riconferma alla maggiore età rifiutata → esclusa; in attesa e scaduta → esclusa solo
      se ``PRIVACY_MAJORITY_OVERDUE_ACTION=SUSPEND`` (con ``REPORT`` resta attiva e segnalata).
    """
    from django.conf import settings

    from apps.education.models import GuardianLink

    now = now or timezone.now()
    links = GuardianLink.objects.filter(
        revoked_at__isnull=True, verified=True, valid_from__lte=now, **flags
    ).filter(Q(valid_until__isnull=True) | Q(valid_until__gt=now))
    blocked = Q(student_id__in=guardian_blocked_students().values("student_id"))
    if not _privacy_installed():
        return links.exclude(blocked)
    hard = Q(student_id__in=guardian_excluded_students().values("student_id"))
    confirmed = Q(detail__reconfirmation="CONFIRMED")
    links = links.exclude(blocked & (hard | ~confirmed))
    links = links.exclude(detail__reconfirmation="DECLINED")
    if getattr(settings, "PRIVACY_MAJORITY_OVERDUE_ACTION", "REPORT") == "SUSPEND":
        links = links.exclude(
            detail__reconfirmation="PENDING", detail__reconfirmation_due_at__lte=now
        )
    return links


def _guardian_links(user, now, **flags):
    return active_guardian_links(now, **flags).filter(account=user)


def notification_guardian_links(student_ids, now=None):
    """Deleghe che ricevono notifiche: accesso valido e ``can_receive_notifications``."""
    links = active_guardian_links(now, can_view=True).filter(student_id__in=student_ids)
    if _privacy_installed():
        links = links.exclude(detail__can_receive_notifications=False)
    return links


def can_request_student_changes(user, student):
    """Richieste di modifica (paper §4.2 ``can_request_changes``): default negato."""
    if is_center(user):
        return True
    if "GUARDIAN" not in active_roles(user) or not _privacy_installed():
        return False
    return (
        _guardian_links(user, timezone.now(), can_view=True)
        .filter(student=student, detail__can_request_changes=True)
        .exists()
    )


def visible_students(user):
    from apps.education.models import Student

    if is_center(user):
        return Student.objects.all()
    now = timezone.now()
    roles = active_roles(user)
    scope = Q(pk__in=[])
    if "STUDENT" in roles:
        scope |= Q(account=user)
    if "GUARDIAN" in roles:
        ids = _guardian_links(user, now, can_view=True).values_list(
            "student_id", flat=True
        )
        scope |= Q(pk__in=ids)
    return Student.objects.filter(scope).distinct()


def can_manage_student_availability(user, student):
    if is_center(user):
        return True
    if "GUARDIAN" not in active_roles(user):
        return False
    return (
        _guardian_links(
            user, timezone.now(), can_view=True, can_manage_availability=True
        )
        .filter(student=student)
        .exists()
    )


def is_staff_account(user):
    """Account soggetto a MFA e ai timeout dello staff."""
    if not (user.is_authenticated and user.is_active):
        return False
    if user.is_superuser or user.is_staff or getattr(user, "mfa_required", False):
        return True
    return bool(granted_roles(user) & set(conf.get("MFA_REQUIRED_ROLES")))


def mfa_required(user):
    return bool(conf.get("MFA_ENFORCED")) and is_staff_account(user)
