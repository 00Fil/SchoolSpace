import pytest
from datetime import timedelta
from django.utils import timezone
from django.core.management import call_command
from django.db import IntegrityError, transaction
from rest_framework.test import APIClient
from apps.identity.models import Account, RoleGrant
from apps.education.models import Family, Student, GuardianLink, Tutor, Resource
from apps.availability.models import AvailabilityRule

pytestmark = pytest.mark.django_db


@pytest.fixture
def fixture():
    guardian = Account.objects.create_user(
        username="guardian", email="guardian@example.invalid", password="test-password"
    )
    staff = Account.objects.create_superuser(
        username="center", email="center@example.invalid", password="test-password"
    )
    family = Family.objects.create(reference="SYNTHETIC")
    a = Student.objects.create(display_name="Studente A sintetico", family=family)
    b = Student.objects.create(display_name="Studente B sintetico", family=family)
    RoleGrant.objects.create(
        account=guardian, role="GUARDIAN", valid_from=timezone.now() - timedelta(days=1)
    )
    link = GuardianLink.objects.create(
        account=guardian,
        student=a,
        can_view=True,
        can_manage_availability=True,
        verified=True,
        valid_from=timezone.now() - timedelta(days=1),
    )
    return guardian, staff, a, b, link


def auth(user):
    c = APIClient()
    c.force_authenticate(user=user)
    return c


def payload(student):
    return {
        "student": str(student.id),
        "weekday": 2,
        "start_time": "16:00",
        "end_time": "18:00",
        "period_start": "2026-10-01",
        "period_end": "2026-12-31",
        "timezone": "Europe/Rome",
        "mode": "IN_PERSON",
        "location": "ON_SITE",
    }


def test_anonymous_denied():
    assert APIClient().get("/api/v1/students/").status_code == 403


def test_family_is_not_access_scope(fixture):
    g, _, a, b, _ = fixture
    c = auth(g)
    assert [x["id"] for x in c.get("/api/v1/students/").data["results"]] == [str(a.id)]
    assert c.get(f"/api/v1/students/{b.id}/").status_code == 404


def test_revocation_immediate(fixture):
    g, _, a, _, link = fixture
    c = auth(g)
    assert c.get(f"/api/v1/students/{a.id}/").status_code == 200
    link.revoked_at = timezone.now()
    link.save()
    assert c.get(f"/api/v1/students/{a.id}/").status_code == 404


def test_unauthorized_foreign_key(fixture):
    g, _, _, b, _ = fixture
    assert (
        auth(g)
        .post("/api/v1/availability-rules/", payload(b), format="json")
        .status_code
        == 400
    )
    assert AvailabilityRule.objects.count() == 0


def test_guardian_creates_only_draft(fixture):
    g, _, a, _, _ = fixture
    result = auth(g).post("/api/v1/availability-rules/", payload(a), format="json")
    assert result.status_code == 201
    assert result.data["status"] == "DRAFT"
    assert AvailabilityRule.objects.get().author == g


@pytest.mark.parametrize(
    "field,value",
    [
        ("status", "APPROVED"),
        ("role", "CENTER"),
        ("weekday", 7),
        ("end_time", "15:00"),
        ("mode", "HYBRID"),
        ("timezone", "not/a-zone"),
        ("location", "REMOTE"),
    ],
)
def test_invalid_payload_rejected(fixture, field, value):
    g, _, a, _, _ = fixture
    p = payload(a)
    p[field] = value
    assert (
        auth(g).post("/api/v1/availability-rules/", p, format="json").status_code == 400
    )
    assert AvailabilityRule.objects.count() == 0


def test_readonly_guardian_cannot_write(fixture):
    g, _, a, _, link = fixture
    link.can_manage_availability = False
    link.save()
    assert (
        auth(g)
        .post("/api/v1/availability-rules/", payload(a), format="json")
        .status_code
        == 400
    )


def test_role_revocation_removes_scope(fixture):
    g, _, a, _, _ = fixture
    grant = g.role_grants.get()
    grant.revoked_at = timezone.now()
    grant.save()
    assert auth(g).get(f"/api/v1/students/{a.id}/").status_code == 404


def test_tutor_only_own_availability(fixture):
    g, staff, a, _, _ = fixture
    other = Account.objects.create_user(username="tutor", email="tutor@example.invalid")
    t = Tutor.objects.create(account=other, display_name="Tutor sintetico")
    RoleGrant.objects.create(account=other, role="TUTOR", valid_from=timezone.now())
    p = payload(a)
    p.pop("student")
    p["tutor"] = str(t.id)
    assert (
        auth(g).post("/api/v1/availability-rules/", p, format="json").status_code == 400
    )
    assert (
        auth(other).post("/api/v1/availability-rules/", p, format="json").status_code
        == 201
    )
    assert auth(other).get("/api/v1/availability-rules/").data["count"] == 1


def test_readiness_not_fake(fixture):
    _, staff, _, _, _ = fixture
    call_command("bootstrap_center")
    result = auth(staff).get("/api/v1/planning/readiness").data
    assert result["ready"] is False
    assert len(result["blockers"]) == 7  # D01-D06 + G1
    # v0.9.4: i run dipendono solo da FEATURE_PLANNING (non da DEBUG); un comando
    # vuoto è rifiutato come payload non valido, mai eseguito.
    assert (
        auth(staff).post("/api/v1/schedule-runs", {}, format="json").status_code == 400
    )


def test_seed_idempotent():
    call_command("bootstrap_center")
    call_command("bootstrap_center")
    assert Resource.objects.count() == 3
    assert set(Resource.objects.values_list("student_capacity", flat=True)) == {2}


def test_database_xor_constraint(fixture):
    g, _, a, _, _ = fixture
    t = Tutor.objects.create(account=g, display_name="Sintetico")
    with pytest.raises(IntegrityError), transaction.atomic():
        AvailabilityRule.objects.create(
            student=a,
            tutor=t,
            weekday=2,
            start_time="16:00",
            end_time="18:00",
            period_start="2026-10-01",
            period_end="2026-12-31",
            mode="IN_PERSON",
            location="ON_SITE",
            author=g,
        )


def test_login_requires_csrf(fixture):
    from django.test import Client

    client = Client(enforce_csrf_checks=True)
    assert (
        client.post(
            "/api/v1/auth/login",
            data={"username": "guardian", "password": "test-password"},
            content_type="application/json",
        ).status_code
        == 403
    )


def test_session_login_and_logout(fixture, settings):
    settings.DEBUG = True
    from django.test import Client

    client = Client(enforce_csrf_checks=True)
    client.get("/api/v1/auth/csrf")
    token = client.cookies["csrftoken"].value
    response = client.post(
        "/api/v1/auth/login",
        data={"username": "guardian", "password": "test-password"},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=token,
    )
    assert response.status_code == 200
    assert client.get("/api/v1/me").status_code == 200
    token = client.cookies["csrftoken"].value
    assert client.post("/api/v1/auth/logout", HTTP_X_CSRFTOKEN=token).status_code == 200
    assert client.get("/api/v1/me").status_code == 403


def test_login_enabled_without_debug(fixture, settings):
    # GAP-B01 (s1-sicurezza): il login API funziona con DEBUG=0, tramite email normalizzata.
    from django.test import Client

    settings.DEBUG = False
    settings.SECURE_SSL_REDIRECT = False
    client = Client()
    assert (
        client.post(
            "/api/v1/auth/login", data={}, content_type="application/json"
        ).status_code
        == 400
    )
    response = client.post(
        "/api/v1/auth/login",
        data={"email": " Guardian@Example.INVALID ", "password": "test-password"},
        content_type="application/json",
    )
    assert response.status_code == 200
    assert client.get("/api/v1/me").status_code == 200


def test_expired_guardian_link(fixture):
    g, _, a, _, link = fixture
    link.valid_until = timezone.now() - timedelta(seconds=1)
    link.save()
    assert auth(g).get(f"/api/v1/students/{a.id}/").status_code == 404


def test_unverified_guardian_link(fixture):
    g, _, a, _, link = fixture
    link.verified = False
    link.save()
    assert auth(g).get(f"/api/v1/students/{a.id}/").status_code == 404


def test_student_only_self(fixture):
    g, _, a, b, _ = fixture
    account = Account.objects.create_user(
        username="student", email="student@example.invalid"
    )
    a.account = account
    a.save()
    RoleGrant.objects.create(account=account, role="STUDENT", valid_from=timezone.now())
    c = auth(account)
    assert c.get(f"/api/v1/students/{a.id}/").status_code == 200
    assert c.get(f"/api/v1/students/{b.id}/").status_code == 404
    assert (
        c.post("/api/v1/availability-rules/", payload(a), format="json").status_code
        == 400
    )


def test_governance_center_only(fixture):
    g, _, _, _, _ = fixture
    c = auth(g)
    assert c.get("/api/v1/decisions/").status_code == 403
    assert c.get("/api/v1/planning/readiness").status_code == 403
    assert c.get("/api/v1/resources/").status_code == 403
    assert c.post("/api/v1/schedule-runs", {}, format="json").status_code == 403


def test_inactive_user_scope_empty(fixture):
    g, _, a, _, _ = fixture
    g.is_active = False
    g.save()
    assert auth(g).get(f"/api/v1/students/{a.id}/").status_code == 404


def test_g1_flag_does_not_implement_solver(fixture, settings):
    _, staff, _, _, _ = fixture
    settings.G1_APPROVED = True
    assert auth(staff).get("/api/v1/planning/readiness").data["ready"] is False
    settings.FEATURE_PLANNING = False
    assert (
        auth(staff).post("/api/v1/schedule-runs", {}, format="json").status_code == 503
    )


def test_readiness_ready_when_all_approved(fixture, settings):
    """Con D01-D06 approvate (esito, responsabile, data) e G1 approvato il gate si apre."""
    from apps.governance.models import Decision

    _, staff, _, _, _ = fixture
    call_command("bootstrap_center")
    settings.G1_APPROVED = True
    Decision.objects.filter(code__in=[f"D{i:02d}" for i in range(1, 7)]).update(
        status="APPROVED",
        outcome="Approvata",
        owner="Responsabile del centro",
        approved_at=timezone.now(),
    )
    result = auth(staff).get("/api/v1/planning/readiness").data
    assert result["blockers"] == []
    assert result["ready"] is True


def test_approve_decisions_superuser_only(fixture):
    """Le approvazioni finali sono del gestore del centro (superuser)."""
    from django.core.management.base import CommandError

    guardian, staff, _, _, _ = fixture
    call_command("bootstrap_center")
    with pytest.raises(CommandError):
        call_command("approve_decisions", by=guardian.username)
    assert auth(staff).get("/api/v1/planning/readiness").data["ready"] is False
    call_command("approve_decisions", by=staff.username)
    result = auth(staff).get("/api/v1/planning/readiness").data
    assert result["blockers"] == [] and result["ready"] is True
