"""GAP-B08 (s1-sicurezza): matrice IDOR/BOLA su relazioni di identità e deleghe.

Ogni attore usa una sessione reale (middleware incluso). Un oggetto altrui deve dare
403/404 e non comparire nelle liste; i comandi su FK annidate verso oggetti altrui falliscono.
"""

from datetime import timedelta

import pytest
from django.core.cache import cache
from django.utils import timezone

from apps.availability.models import AvailabilityRule
from apps.education.models import Family, GuardianLink, Student, Tutor
from apps.identity.models import Invitation, StudentAccessPolicy, UserSession
from tests.identity_helpers import Api, login, make_account
from tests.test_api import payload

pytestmark = pytest.mark.django_db
DENIED = {403, 404}


@pytest.fixture(autouse=True)
def clean_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def world():
    now = timezone.now() - timedelta(days=1)
    fam_a = Family.objects.create(reference="BOLA-A")
    fam_b = Family.objects.create(reference="BOLA-B")
    a = Student.objects.create(display_name="Studente A", family=fam_a)
    b = Student.objects.create(display_name="Studente B", family=fam_b)
    sibling = Student.objects.create(display_name="Fratello di A", family=fam_a)
    actors = {}

    def guardian(name, student, **link):
        user = make_account(f"{name}@example.invalid", roles=["GUARDIAN"])
        GuardianLink.objects.create(
            account=user,
            student=student,
            valid_from=now,
            verified=link.pop("verified", True),
            can_view=link.pop("can_view", True),
            can_manage_availability=link.pop("manage", True),
            revoked_at=link.pop("revoked_at", None),
        )
        actors[name] = user

    guardian("guardian_a", a)
    guardian("guardian_b", b)
    guardian("unverified", a, verified=False)
    guardian("no_view", a, can_view=False)
    guardian("revoked", a, revoked_at=timezone.now() - timedelta(hours=1))
    pupil = make_account("pupil_a@example.invalid", roles=["STUDENT"])
    a.account = pupil
    a.save()
    actors["pupil_a"] = pupil
    tutor = make_account("tutor@example.invalid", roles=["TUTOR"])
    Tutor.objects.create(account=tutor, display_name="Tutor BOLA")
    actors["tutor"] = tutor
    actors["roleless"] = make_account("nessuno@example.invalid")
    center = make_account("centro@example.invalid", roles=["CENTER"])
    invitation = Invitation.objects.create(
        email="x@example.invalid", role="GUARDIAN", student=b, created_by=center
    )
    return {
        "a": a,
        "b": b,
        "sibling": sibling,
        "actors": actors,
        "invitation": invitation,
    }


def session(user):
    api = Api()
    assert login(api, user.email).status_code == 200
    return api


def ids(response):
    return {row["id"] for row in response.json()["results"]}


NON_OWNERS = ["guardian_b", "unverified", "no_view", "revoked", "tutor", "roleless"]


@pytest.mark.parametrize("actor", NON_OWNERS)
def test_foreign_student_is_invisible(world, actor):
    api = session(world["actors"][actor])
    a = world["a"]
    assert api.get(f"/api/v1/students/{a.id}/").status_code in DENIED
    listed = api.get("/api/v1/students/")
    assert listed.status_code in DENIED or str(a.id) not in ids(listed)
    # Stessa famiglia non significa accesso (lo scope è la delega, non la famiglia).
    assert api.get(f"/api/v1/students/{world['sibling'].id}/").status_code in DENIED


@pytest.mark.parametrize("actor", ["guardian_a", "pupil_a"])
def test_owner_sees_only_own_student(world, actor):
    api = session(world["actors"][actor])
    assert ids(api.get("/api/v1/students/")) == {str(world["a"].id)}
    assert api.get(f"/api/v1/students/{world['b'].id}/").status_code == 404
    assert api.get(f"/api/v1/students/{world['sibling'].id}/").status_code == 404


@pytest.mark.parametrize("actor", NON_OWNERS + ["pupil_a"])
def test_nested_fk_availability_for_foreign_student_rejected(world, actor):
    api = session(world["actors"][actor])
    response = api.post("/api/v1/availability-rules/", payload(world["a"]))
    assert response.status_code in {400, 403}
    assert not AvailabilityRule.objects.filter(student=world["a"]).exists()


def test_owner_availability_list_excludes_foreign(world):
    AvailabilityRule.objects.create(
        student=world["b"],
        weekday=1,
        start_time="16:00",
        end_time="17:00",
        period_start="2026-10-01",
        period_end="2026-12-31",
        mode="IN_PERSON",
        location="ON_SITE",
        author=world["actors"]["guardian_b"],
    )
    api = session(world["actors"]["guardian_a"])
    assert api.get("/api/v1/availability-rules/").json()["results"] == []
    foreign = AvailabilityRule.objects.get()
    assert api.get(f"/api/v1/availability-rules/{foreign.id}/").status_code == 404


@pytest.mark.parametrize("actor", NON_OWNERS + ["guardian_a", "pupil_a"])
def test_identity_admin_endpoints_denied_to_non_center(world, actor):
    api = session(world["actors"][actor])
    victim = world["actors"]["guardian_b"]
    inv = world["invitation"]
    assert api.get(f"/api/v1/invitations/{inv.id}").status_code == 403
    assert (
        api.post(
            f"/api/v1/invitations/{inv.id}/verify-relation", {"evidence": "x"}
        ).status_code
        == 403
    )
    assert api.post(f"/api/v1/invitations/{inv.id}/revoke").status_code == 403
    assert (
        api.post(
            f"/api/v1/identity/accounts/{victim.id}/sessions/revoke-all"
        ).status_code
        == 403
    )
    assert (
        api.post(
            f"/api/v1/identity/accounts/{victim.id}/mfa/reset", {"reason": "x"}
        ).status_code
        == 403
    )
    assert (
        api.put(
            f"/api/v1/identity/students/{world['a'].id}/access-policy",
            {"adult_confirmed": True, "guardian_access": "KEEP"},
        ).status_code
        == 403
    )
    assert api.get("/api/v1/identity/audit").status_code == 403
    inv.refresh_from_db()
    assert inv.status == "PENDING_VERIFICATION"
    assert not StudentAccessPolicy.objects.exists()


def test_session_ids_of_other_users_are_not_addressable(world):
    victim_api = session(world["actors"]["guardian_b"])
    attacker = session(world["actors"]["guardian_a"])
    victim_session = UserSession.objects.get(account=world["actors"]["guardian_b"])
    assert (
        attacker.post(f"/api/v1/auth/sessions/{victim_session.id}/revoke").status_code
        == 404
    )
    listed = attacker.get("/api/v1/auth/sessions").json()["results"]
    assert str(victim_session.id) not in {r["id"] for r in listed}
    assert victim_api.get("/api/v1/me").status_code == 200


def test_client_cannot_self_grant_context_or_role(world):
    api = session(world["actors"]["guardian_a"])
    for context in ("CENTER", "TUTOR", "STUDENT", "guardian", ""):
        assert api.post("/api/v1/auth/context", {"context": context}).status_code == 403
    assert api.get("/api/v1/resources/").status_code == 403
    assert api.get("/api/v1/me").json()["roles"] == ["GUARDIAN"]


def test_guardian_cannot_accept_invitation_for_foreign_student(world):
    # Il token esiste solo dopo la verifica; un ID di invito non è un token.
    api = session(world["actors"]["guardian_a"])
    response = api.post(
        "/api/v1/invitations/accept", {"token": str(world["invitation"].id)}
    )
    assert response.status_code == 400
    assert not GuardianLink.objects.filter(
        account=world["actors"]["guardian_a"], student=world["b"]
    ).exists()


def test_adult_student_policy_blocks_guardian_on_all_lists(world):
    center = world["actors"]["guardian_a"]  # attore qualsiasi per il FK obbligatorio
    StudentAccessPolicy.objects.create(
        student=world["a"],
        adult_confirmed=True,
        guardian_access="NONE",
        confirmed_by=center,
    )
    api = session(world["actors"]["guardian_a"])
    assert api.get("/api/v1/students/").json()["results"] == []
    assert api.get(f"/api/v1/students/{world['a'].id}/").status_code == 404
    assert api.post("/api/v1/availability-rules/", payload(world["a"])).status_code in {
        400,
        403,
    }
    # Lo studente maggiorenne mantiene il proprio accesso.
    assert ids(session(world["actors"]["pupil_a"]).get("/api/v1/students/")) == {
        str(world["a"].id)
    }
