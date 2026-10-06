"""Riconciliazione dopo un restore (FR24: "ripristino non riattiva utenti revocati").

Rilegge il ledger esterno e riapplica revoche di deleghe e anonimizzazioni avvenute dopo
l'istante di restore; segnala le richieste privacy assenti dal DB ripristinato.
"""

from django.contrib.auth import get_user_model

from apps.education.models import GuardianLink, Student

from . import ledger
from .models import PrivacyRequest


def plan():
    entries = ledger.read_entries()
    actions = []
    seen_requests = {}
    for entry in entries:
        event = entry.get("event")
        if event == "LINK_REVOKED":
            link = GuardianLink.objects.filter(pk=entry.get("link")).first()
            if link is not None and link.revoked_at is None:
                actions.append({"action": "REVOKE_LINK", "link": str(link.pk)})
        elif event == "REQUEST_COMPLETED" and entry.get("outcome") == "ANONYMIZED":
            from .subjects import is_anonymized

            stype, sid = entry["subject_type"], entry["subject_id"]
            model = Student if stype == "STUDENT" else get_user_model()
            if model.objects.filter(pk=sid).exists() and not is_anonymized(stype, sid):
                actions.append(
                    {"action": "ANONYMIZE", "subject_type": stype, "subject_id": sid}
                )
        if entry.get("request"):
            seen_requests[entry["request"]] = entry
    for request_id, last in seen_requests.items():
        if not PrivacyRequest.objects.filter(pk=request_id).exists():
            actions.append(
                {
                    "action": "MISSING_REQUEST",
                    "request": request_id,
                    "last_status": last.get("status"),
                    "kind": last.get("kind"),
                }
            )
    return actions


def apply(actions):
    from .registry import revoke_guardian_link
    from .subjects import anonymize_account, anonymize_student

    done = []
    for item in actions:
        if item["action"] == "REVOKE_LINK":
            link = GuardianLink.objects.get(pk=item["link"])
            if link.revoked_at is None:
                revoke_guardian_link(
                    None, link, reason="riconciliazione dopo restore", system=True
                )
                done.append(item)
        elif item["action"] == "ANONYMIZE":
            reason = "riconciliazione dopo restore"
            if item["subject_type"] == "STUDENT":
                anonymize_student(
                    Student.objects.get(pk=item["subject_id"]), reason=reason
                )
            else:
                anonymize_account(
                    get_user_model().objects.get(pk=item["subject_id"]), reason=reason
                )
            done.append(item)
    return done
