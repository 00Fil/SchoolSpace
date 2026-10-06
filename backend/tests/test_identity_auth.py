"""GAP-B01, B03, B04, B05, B07 (s1-sicurezza): login, hasher, MFA, sessioni, throttle, contesto."""

from datetime import timedelta

import pytest
from django.contrib.auth.hashers import check_password, make_password
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.test import override_settings
from django.utils import timezone

from apps.education.models import Family, GuardianLink, Student
from apps.identity import throttle
from apps.identity.models import (
    Account,
    IdentityAuditEvent,
    RecoveryCode,
    StudentAccessPolicy,
    UserSession,
)
from apps.identity.policies import visible_students
from tests.identity_helpers import (
    PW,
    Api,
    Clock,
    enroll_staff,
    login,
    login_staff,
    make_account,
)

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def clean_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def clock(monkeypatch):
    return Clock(monkeypatch)


# --- GAP-B01: email normalizzata e login con DEBUG=0 ---------------------------------


def test_email_is_normalized_and_unique_case_insensitive():
    user = make_account("  Mario.Rossi@Example.INVALID ")
    assert user.email == "mario.rossi@example.invalid"
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Account.objects.create_user(
                username="altro", email="MARIO.rossi@example.invalid"
            )


def test_case_insensitive_constraint_holds_for_raw_updates():
    make_account("a@example.invalid")
    other = make_account("b@example.invalid")
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Account.objects.filter(pk=other.pk).update(email="A@example.invalid")


def test_unicode_email_nfc_normalization():
    decomposed = "jose\u0301@example.invalid"
    user = make_account(decomposed, username="jose")
    assert user.email == "jos\u00e9@example.invalid"
    response = login(Api(), "JOS\u00c9@example.invalid")
    assert response.status_code == 200


@override_settings(DEBUG=False, SECURE_SSL_REDIRECT=False)
def test_login_with_debug_off_and_mixed_case_email():
    make_account("famiglia@example.invalid", roles=["GUARDIAN"])
    api = Api()
    response = login(api, "  FAMIGLIA@Example.invalid")
    assert response.status_code == 200
    body = response.json()
    assert body["mfa_required"] is False and body["contexts"] == ["GUARDIAN"]
    assert api.get("/api/v1/me").status_code == 200


def test_login_errors_are_not_enumerating():
    make_account("esiste@example.invalid", roles=["GUARDIAN"])
    inactive = make_account("inattivo@example.invalid")
    inactive.is_active = False
    inactive.save()
    api = Api()
    bodies = [
        login(api, "esiste@example.invalid", "password-sbagliata-1").json(),
        login(api, "nessuno@example.invalid", "password-sbagliata-1").json(),
        login(api, "inattivo@example.invalid", PW).json(),
    ]
    assert bodies[0] == bodies[1] == bodies[2]
    assert bodies[0]["code"] == "INVALID_CREDENTIALS"


def test_login_requires_csrf_and_strict_payload():
    from django.test import Client

    make_account("x@example.invalid")
    assert (
        Client(enforce_csrf_checks=True)
        .post(
            "/api/v1/auth/login",
            {"email": "x@example.invalid", "password": PW},
            content_type="application/json",
        )
        .status_code
        == 403
    )
    api = Api()
    assert (
        api.post("/api/v1/auth/login", {"email": "x@example.invalid"}).status_code
        == 400
    )
    assert (
        api.post(
            "/api/v1/auth/login",
            {"email": "x@example.invalid", "username": "x", "password": PW},
        ).status_code
        == 400
    )
    assert api.post("/api/v1/auth/login", ["x"]).status_code == 400


@override_settings(IDENTITY_ALLOW_USERNAME_LOGIN=False)
def test_username_login_disabled_in_production_mode():
    make_account("u@example.invalid", username="utente")
    api = Api()
    assert (
        api.post(
            "/api/v1/auth/login", {"username": "utente", "password": PW}
        ).status_code
        == 401
    )
    assert login(api, "u@example.invalid").status_code == 200


# --- GAP-B03: Argon2id primario con fallback PBKDF2 -----------------------------------


@override_settings(
    PASSWORD_HASHERS=[
        "apps.identity.hashers.ConfigurableArgon2PasswordHasher",
        "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    ],
    ARGON2_MEMORY_COST_KIB=19456,
    ARGON2_PARALLELISM=1,
)
def test_argon2id_primary_and_pbkdf2_rehashed_on_login():
    encoded = make_password("x" * 16)
    assert encoded.startswith("argon2$argon2id$")
    assert "m=19456" in encoded
    user = make_account("legacy@example.invalid")
    legacy = make_password(PW, hasher="pbkdf2_sha256")
    Account.objects.filter(pk=user.pk).update(password=legacy)
    assert login(Api(), "legacy@example.invalid").status_code == 200
    user.refresh_from_db()
    assert user.password.startswith("argon2$argon2id$")
    assert check_password(PW, user.password)


def test_base_settings_use_argon2_first():
    from config import settings as base

    assert base.PASSWORD_HASHERS[0].endswith("ConfigurableArgon2PasswordHasher")
    assert any("PBKDF2PasswordHasher" in h for h in base.PASSWORD_HASHERS)
    min_length = [
        v
        for v in base.AUTH_PASSWORD_VALIDATORS
        if v["NAME"].endswith("MinimumLengthValidator")
    ][0]
    assert min_length["OPTIONS"]["min_length"] >= 12


def test_benchmark_command_runs():
    from io import StringIO

    from django.core.management import call_command

    out = StringIO()
    with override_settings(
        PASSWORD_HASHERS=["apps.identity.hashers.ConfigurableArgon2PasswordHasher"],
        ARGON2_MEMORY_COST_KIB=19456,
        ARGON2_PARALLELISM=1,
    ):
        call_command("benchmark_hashers", rounds=1, stdout=out)
    assert "argon2" in out.getvalue() and "mediana" in out.getvalue()


# --- GAP-B04: MFA staff ---------------------------------------------------------------


def test_staff_requires_mfa_enrollment_before_session(clock):
    make_account("centro@example.invalid", roles=["CENTER"])
    api = Api()
    response = login(api, "centro@example.invalid")
    assert response.json() == {
        "detail": "Verifica in due passaggi richiesta",
        "mfa_required": True,
        "mfa_enrolled": False,
    }
    # Nessuna sessione autenticata finché la MFA non è completata.
    assert api.get("/api/v1/me").status_code == 403
    assert api.get("/api/v1/students/").status_code == 403
    setup = api.post("/api/v1/auth/mfa/setup").json()
    assert setup["otpauth_uri"].startswith("otpauth://totp/")
    assert setup["qr_svg"].startswith("data:image/svg+xml;base64,")
    assert api.post("/api/v1/auth/mfa/confirm", {"code": "000000"}).status_code == 400
    clock.tick()
    confirm = api.post(
        "/api/v1/auth/mfa/confirm", {"code": clock.code(setup["secret"])}
    )
    assert confirm.status_code == 200
    codes = confirm.json()["recovery_codes"]
    assert len(codes) == 10 and len(set(codes)) == 10
    # I codici sono salvati solo come hash.
    stored = set(RecoveryCode.objects.values_list("code_hash", flat=True))
    assert not any(c in stored or c.replace("-", "") in stored for c in codes)
    assert api.get("/api/v1/me").status_code == 200
    assert api.get("/api/v1/students/").status_code == 200
    # Il segreto non è più ottenibile una volta confermato.
    assert api.post("/api/v1/auth/mfa/setup").json()["code"] == "MFA_ALREADY_ENROLLED"


def test_totp_replay_rejected_and_recovery_code_single_use(clock):
    make_account("staff@example.invalid", superuser=True)
    secret, codes = enroll_staff(Api(), clock, "staff@example.invalid")
    api = Api()
    login(api, "staff@example.invalid")
    used = clock.code(secret)  # stesso passo già consumato alla conferma
    assert api.post("/api/v1/auth/mfa/verify", {"code": used}).status_code == 400
    assert (
        api.post(
            "/api/v1/auth/mfa/verify", {"recovery_code": codes[0].lower()}
        ).status_code
        == 200
    )
    other = Api()
    login(other, "staff@example.invalid")
    assert (
        other.post("/api/v1/auth/mfa/verify", {"recovery_code": codes[0]}).status_code
        == 400
    )
    assert (
        other.post("/api/v1/auth/mfa/verify", {"recovery_code": codes[1]}).status_code
        == 200
    )
    assert other.get("/api/v1/auth/mfa").json()["recovery_codes_remaining"] == 8


def test_mfa_pending_state_expires(clock, settings):
    make_account("staff@example.invalid", superuser=True)
    secret, _ = enroll_staff(Api(), clock, "staff@example.invalid")
    settings.IDENTITY_MFA_PENDING_TTL_SECONDS = -1
    api = Api()
    login(api, "staff@example.invalid")
    clock.tick()
    response = api.post("/api/v1/auth/mfa/verify", {"code": clock.code(secret)})
    assert response.status_code == 401
    assert response.json()["code"] == "MFA_SESSION_EXPIRED"


def test_mfa_bruteforce_is_throttled(clock):
    make_account("staff@example.invalid", superuser=True)
    enroll_staff(Api(), clock, "staff@example.invalid")
    api = Api()
    login(api, "staff@example.invalid")
    statuses = [
        api.post("/api/v1/auth/mfa/verify", {"code": "123456"}).status_code
        for _ in range(6)
    ]
    assert statuses[:5] == [400] * 5 and statuses[5] == 429


def test_session_created_without_mfa_is_gated(client):
    staff = make_account("staff@example.invalid", superuser=True)
    client.force_login(staff)  # es. login dal form admin, senza MFA
    response = client.get("/api/v1/students/")
    assert response.status_code == 403
    assert response.json()["code"] == "MFA_REQUIRED"
    # Gli endpoint di autenticazione restano raggiungibili per lo step-up.
    assert client.get("/api/v1/auth/mfa").status_code == 200


def test_step_up_after_role_grant(clock):
    user = make_account("promosso@example.invalid", roles=["TUTOR"])
    api = Api()
    assert login(api, "promosso@example.invalid").json()["mfa_required"] is False
    assert api.get("/api/v1/me").status_code == 200
    from apps.identity.models import RoleGrant

    RoleGrant.objects.create(account=user, role="CENTER", valid_from=timezone.now())
    api.post("/api/v1/auth/context", {"context": "TUTOR"})
    assert api.get("/api/v1/tutors/").json()["code"] == "MFA_REQUIRED"
    setup = api.post("/api/v1/auth/mfa/setup").json()
    clock.tick()
    assert (
        api.post(
            "/api/v1/auth/mfa/confirm", {"code": clock.code(setup["secret"])}
        ).status_code
        == 200
    )
    assert api.get("/api/v1/tutors/").status_code == 200


def test_mfa_reset_requires_second_admin(clock):
    make_account("a1@example.invalid", superuser=True)
    target = make_account("a2@example.invalid", superuser=True)
    s1, _ = enroll_staff(Api(), clock, "a1@example.invalid")
    victim = Api()
    enroll_staff(victim, clock, "a2@example.invalid")
    admin = Api()
    login_staff(admin, clock, "a1@example.invalid", s1)
    me = Account.objects.get(email="a1@example.invalid")
    assert (
        admin.post(
            f"/api/v1/identity/accounts/{me.pk}/mfa/reset", {"reason": "x"}
        ).status_code
        == 403
    )
    response = admin.post(
        f"/api/v1/identity/accounts/{target.pk}/mfa/reset", {"reason": "telefono perso"}
    )
    assert response.status_code == 200
    assert victim.get("/api/v1/me").status_code == 403  # sessioni revocate
    event = IdentityAuditEvent.objects.get(operation="mfa.reset")
    assert event.actor == me and event.subject == target
    assert "telefono" in event.details["reason"]


# --- GAP-B04: sessioni server-side, revoca e timeout ----------------------------------


def test_logout_revokes_server_side():
    make_account("f@example.invalid", roles=["GUARDIAN"])
    api = Api()
    login(api, "f@example.invalid")
    session_cookie = api.client.cookies["sessionid"].value
    assert api.post("/api/v1/auth/logout").status_code == 200
    record = UserSession.objects.get()
    assert record.revoked_at is not None and record.revoked_reason == "logout"
    # Riutilizzare il cookie rubato dopo il logout non funziona.
    stolen = Api()
    stolen.client.cookies["sessionid"] = session_cookie
    assert stolen.get("/api/v1/me").status_code == 403


def test_list_and_revoke_sessions():
    make_account("f@example.invalid", roles=["GUARDIAN"])
    phone, laptop = Api(HTTP_USER_AGENT="phone"), Api(HTTP_USER_AGENT="laptop")
    login(phone, "f@example.invalid")
    login(laptop, "f@example.invalid")
    rows = laptop.get("/api/v1/auth/sessions").json()["results"]
    assert len(rows) == 2 and sum(r["current"] for r in rows) == 1
    other = next(r for r in rows if not r["current"])
    assert laptop.post(f"/api/v1/auth/sessions/{other['id']}/revoke").status_code == 200
    assert phone.get("/api/v1/me").status_code == 403
    assert laptop.get("/api/v1/me").status_code == 200
    login(phone, "f@example.invalid")
    assert laptop.post("/api/v1/auth/sessions/revoke-all").json()["revoked"] == 1
    assert phone.get("/api/v1/me").status_code == 403
    assert (
        laptop.post(
            "/api/v1/auth/sessions/revoke-all", {"include_current": True}
        ).status_code
        == 200
    )
    assert laptop.get("/api/v1/me").status_code == 403


def test_cannot_revoke_other_users_session():
    make_account("a@example.invalid", roles=["GUARDIAN"])
    make_account("b@example.invalid", roles=["GUARDIAN"])
    a, b = Api(), Api()
    login(a, "a@example.invalid")
    login(b, "b@example.invalid")
    b_session = UserSession.objects.get(account__email="b@example.invalid")
    assert a.post(f"/api/v1/auth/sessions/{b_session.pk}/revoke").status_code == 404
    assert b.get("/api/v1/me").status_code == 200


def test_idle_and_absolute_timeouts(settings):
    make_account("f@example.invalid", roles=["GUARDIAN"])
    api = Api()
    login(api, "f@example.invalid")
    record = UserSession.objects.get()
    UserSession.objects.filter(pk=record.pk).update(
        last_seen_at=timezone.now()
        - timedelta(seconds=settings.IDENTITY_SESSION_IDLE_TIMEOUT_DEFAULT + 5)
    )
    assert api.get("/api/v1/me").status_code == 403
    assert UserSession.objects.get().revoked_reason == "timeout"
    login(api, "f@example.invalid")
    record = UserSession.objects.get(revoked_at__isnull=True)
    UserSession.objects.filter(pk=record.pk).update(
        created_at=timezone.now() - timedelta(hours=9)
    )
    assert api.get("/api/v1/me").status_code == 403


def test_staff_idle_timeout_is_shorter(clock):
    make_account("staff@example.invalid", superuser=True)
    api = Api()
    enroll_staff(api, clock, "staff@example.invalid")
    UserSession.objects.update(last_seen_at=timezone.now() - timedelta(minutes=31))
    assert api.get("/api/v1/me").status_code == 403


def test_password_change_revokes_other_sessions():
    make_account("f@example.invalid", roles=["GUARDIAN"])
    a, b = Api(), Api()
    login(a, "f@example.invalid")
    login(b, "f@example.invalid")
    response = a.post(
        "/api/v1/auth/password-change",
        {"current_password": PW, "new_password": "Nuova-Password-Sicura-77"},
    )
    assert response.status_code == 200
    assert a.get("/api/v1/me").status_code == 200
    assert b.get("/api/v1/me").status_code == 403
    assert (
        a.post(
            "/api/v1/auth/password-change",
            {
                "current_password": "sbagliata",
                "new_password": "Altra-Password-Sicura-78",
            },
        ).status_code
        == 400
    )
    weak = a.post(
        "/api/v1/auth/password-change",
        {"current_password": "Nuova-Password-Sicura-77", "new_password": "corta"},
    )
    assert weak.status_code == 400 and weak.json()["code"] == "WEAK_PASSWORD"


def test_session_id_rotates_on_login_and_context_change():
    make_account("multi@example.invalid", roles=["GUARDIAN", "TUTOR"])
    api = Api()
    api.client.cookies["sessionid"] = "attacker-fixed-session"
    login(api, "multi@example.invalid")
    first = api.client.cookies["sessionid"].value
    assert first != "attacker-fixed-session"
    api.post("/api/v1/auth/context", {"context": "TUTOR"})
    assert api.client.cookies["sessionid"].value != first


# --- GAP-B05: throttle persistente per IP e identità ----------------------------------


def test_login_throttle_per_identity_with_progressive_lockout(settings):
    make_account("vittima@example.invalid", roles=["GUARDIAN"])
    api = Api()
    statuses = [
        login(api, "Vittima@example.invalid", "sbagliata-123456").status_code
        for _ in range(6)
    ]
    assert statuses == [401] * 5 + [429]
    blocked = login(api, "vittima@example.invalid")  # anche con la password giusta
    assert blocked.status_code == 429
    first_wait = int(blocked["Retry-After"])
    assert 0 < first_wait <= 60
    # Allo scadere del blocco, altri 5 errori producono un blocco doppio.
    for key in list(cache._cache.keys()):
        if key.endswith(":lock"):
            cache._cache.pop(key)
            cache._expire_info.pop(key, None)
    for _ in range(5):
        login(api, "vittima@example.invalid", "sbagliata-123456")
    second = login(api, "vittima@example.invalid")
    assert second.status_code == 429 and 60 < int(second["Retry-After"]) <= 120
    # Un'altra identità dallo stesso IP non è bloccata dal limite per identità.
    make_account("altro@example.invalid", roles=["GUARDIAN"])
    assert login(api, "altro@example.invalid").status_code == 200


def test_login_throttle_per_ip(settings):
    settings.IDENTITY_THROTTLE_RULES = {
        "login": {"ip": (3, 900), "identity": (50, 900)}
    }
    api = Api()
    for i in range(3):
        assert login(api, f"n{i}@example.invalid", "x" * 12).status_code == 401
    assert login(api, "n9@example.invalid", "x" * 12).status_code == 429
    other_ip = Api(REMOTE_ADDR="10.9.9.9")
    assert login(other_ip, "n9@example.invalid", "x" * 12).status_code == 401


def test_throttle_uses_forwarded_ip_only_with_trusted_proxy(settings):
    settings.IDENTITY_THROTTLE_RULES = {"login": {"ip": (2, 900)}}
    spoof = Api(HTTP_X_FORWARDED_FOR="1.2.3.4")
    for _ in range(2):
        login(spoof, "z@example.invalid", "x" * 12)
    rotated = Api(HTTP_X_FORWARDED_FOR="5.6.7.8")
    assert login(rotated, "z@example.invalid", "x" * 12).status_code == 429
    settings.IDENTITY_TRUSTED_PROXY_HOPS = 1
    cache.clear()
    for _ in range(2):
        login(spoof, "z@example.invalid", "x" * 12)
    assert login(rotated, "z@example.invalid", "x" * 12).status_code == 401


def test_throttle_state_lives_in_configured_shared_cache(settings):
    settings.CACHES = {
        "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
        "shared": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "identity-shared",
        },
    }
    settings.IDENTITY_THROTTLE_CACHE = "shared"
    from django.core.cache import caches

    throttle.fail("login", identity="x@example.invalid")
    keys = list(caches["shared"]._cache.keys())
    assert keys and all("x@example.invalid" not in k for k in keys)
    caches["shared"].clear()


def test_redis_cache_configured_from_env():
    import os
    import subprocess
    import sys

    code = (
        "import django;from django.conf import settings;django.setup();"
        "print(settings.CACHES['default']['BACKEND'])"
    )
    env = {
        **os.environ,
        "DJANGO_SETTINGS_MODULE": "config.settings",
        "CACHE_URL": "rediss://:pw@redis:6380/1",
    }
    out = subprocess.run(
        [sys.executable, "-c", code],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    assert out.stdout.strip() == "django.core.cache.backends.redis.RedisCache"


# --- GAP-B07: contesto multi-ruolo e studente maggiorenne -----------------------------


@pytest.fixture
def family():
    fam = Family.objects.create(reference="SINTETICA-CTX")
    own = Student.objects.create(display_name="Figlio sintetico", family=fam)
    return fam, own


def test_multi_role_user_must_select_context(family):
    _, own = family
    user = make_account("multi@example.invalid", roles=["GUARDIAN", "TUTOR"])
    from apps.education.models import Tutor

    Tutor.objects.create(account=user, display_name="Tutor sintetico")
    GuardianLink.objects.create(
        account=user,
        student=own,
        verified=True,
        valid_from=timezone.now() - timedelta(days=1),
    )
    api = Api()
    body = login(api, "multi@example.invalid").json()
    assert body["context_required"] is True and body["contexts"] == [
        "GUARDIAN",
        "TUTOR",
    ]
    blocked = api.get("/api/v1/students/")
    assert blocked.status_code == 409 and blocked.json()["code"] == "CONTEXT_REQUIRED"
    assert api.get("/api/v1/me").status_code == 200
    assert api.post("/api/v1/auth/context", {"context": "CENTER"}).status_code == 403
    assert api.post("/api/v1/auth/context", {"context": "TUTOR"}).status_code == 200
    assert api.get("/api/v1/students/").json()["results"] == []
    assert len(api.get("/api/v1/tutors/").json()["results"]) == 1
    api.post("/api/v1/auth/context", {"context": "GUARDIAN"})
    assert [s["id"] for s in api.get("/api/v1/students/").json()["results"]] == [
        str(own.id)
    ]
    assert api.get("/api/v1/tutors/").json()["results"] == []


def test_revoked_grant_drops_selected_context(family):
    user = make_account("multi@example.invalid", roles=["GUARDIAN", "TUTOR"])
    api = Api()
    login(api, "multi@example.invalid")
    api.post("/api/v1/auth/context", {"context": "TUTOR"})
    user.role_grants.filter(role="TUTOR").update(revoked_at=timezone.now())
    assert api.get("/api/v1/auth/context").json()["context"] == "GUARDIAN"


def test_superuser_in_guardian_context_loses_center_powers(clock, family):
    make_account("boss@example.invalid", superuser=True, roles=["GUARDIAN"])
    api = Api()
    enroll_staff(api, clock, "boss@example.invalid")
    assert api.get("/api/v1/students/").status_code == 409
    api.post("/api/v1/auth/context", {"context": "GUARDIAN"})
    assert api.get("/api/v1/students/").json()["results"] == []
    assert api.get("/api/v1/resources/").status_code == 403
    api.post("/api/v1/auth/context", {"context": "CENTER"})
    assert len(api.get("/api/v1/students/").json()["results"]) == 1


def _adult_setup(family):
    _, student = family
    guardian = make_account("genitore@example.invalid", roles=["GUARDIAN"])
    GuardianLink.objects.create(
        account=guardian,
        student=student,
        verified=True,
        can_manage_availability=True,
        valid_from=timezone.now() - timedelta(days=1),
    )
    pupil = make_account("studente@example.invalid", roles=["STUDENT"])
    student.account = pupil
    student.save()
    return guardian, pupil, student


def test_adult_policy_is_explicit_not_age_based(clock, family, settings):
    guardian, pupil, student = _adult_setup(family)
    assert list(visible_students(guardian)) == [student]
    make_account("centro@example.invalid", roles=["CENTER"])
    center = Api()
    enroll_staff(center, clock, "centro@example.invalid")
    url = f"/api/v1/identity/students/{student.pk}/access-policy"
    assert center.get(url).json()["adult_confirmed"] is False
    response = center.put(url, {"adult_confirmed": True, "guardian_access": "DEFAULT"})
    assert response.status_code == 200 and response.json()["version"] == 1
    # Default (da approvare): serve il consenso dello studente.
    assert list(visible_students(guardian)) == []
    from apps.identity.policies import can_manage_student_availability

    assert not can_manage_student_availability(guardian, student)
    pupil_api = Api()
    login(pupil_api, "studente@example.invalid")
    assert (
        pupil_api.post("/api/v1/auth/student-consent", {"granted": True}).status_code
        == 200
    )
    assert list(visible_students(guardian)) == [student]
    pupil_api.post("/api/v1/auth/student-consent", {"granted": False})
    assert list(visible_students(guardian)) == []
    settings.IDENTITY_ADULT_GUARDIAN_ACCESS = "KEEP"
    assert list(visible_students(guardian)) == [student]
    stale = center.put(
        url, {"adult_confirmed": True, "guardian_access": "NONE", "expected_version": 1}
    )
    assert stale.status_code == 409  # versione cambiata dal consenso
    current = StudentAccessPolicy.objects.get().version
    center.put(
        url,
        {
            "adult_confirmed": True,
            "guardian_access": "NONE",
            "expected_version": current,
        },
    )
    assert list(visible_students(guardian)) == []
    assert (
        IdentityAuditEvent.objects.filter(operation="student_policy.updated").count()
        == 2
    )


def test_only_center_sets_adult_policy_and_only_student_consents(family):
    guardian, pupil, student = _adult_setup(family)
    api = Api()
    login(api, "genitore@example.invalid")
    url = f"/api/v1/identity/students/{student.pk}/access-policy"
    assert (
        api.put(url, {"adult_confirmed": True, "guardian_access": "KEEP"}).status_code
        == 403
    )
    assert (
        api.post("/api/v1/auth/student-consent", {"granted": True}).status_code == 400
    )
    pupil_api = Api()
    login(pupil_api, "studente@example.invalid")
    # Senza conferma della maggiore età il consenso non è applicabile.
    assert (
        pupil_api.post("/api/v1/auth/student-consent", {"granted": True}).status_code
        == 409
    )


# --- Audit append-only ---------------------------------------------------------------


def test_identity_audit_is_append_only_and_secret_free():
    from apps.identity import audit

    make_account("f@example.invalid", roles=["GUARDIAN"])
    api = Api()
    login(api, "f@example.invalid", "password-sbagliata-1")
    login(api, "f@example.invalid")
    events = list(IdentityAuditEvent.objects.all())
    assert [e.operation for e in events] == ["login.failed", "login.succeeded"]
    assert all(PW not in str(e.details) for e in events)
    assert events[0].ip == "127.0.0.1"
    event = events[0]
    event.operation = "manomesso"
    with pytest.raises(TypeError):
        event.save()
    with pytest.raises(TypeError):
        event.delete()
    with pytest.raises(TypeError):
        IdentityAuditEvent.objects.filter(pk=event.pk).update(operation="x")
    with pytest.raises(TypeError):
        IdentityAuditEvent.objects.all().delete()
    with pytest.raises(ValueError):
        audit.record("x", password="segreto")


@pytest.mark.skipif(
    __import__("django.db").db.connection.vendor != "postgresql",
    reason="Requires actual PostgreSQL trigger",
)
def test_postgres_trigger_blocks_raw_audit_changes():
    from django.db import DatabaseError, connection

    from apps.identity import audit

    event = audit.record("prova")
    for sql in (
        "UPDATE identity_identityauditevent SET operation='x' WHERE id=%s",
        "DELETE FROM identity_identityauditevent WHERE id=%s",
    ):
        # Il trigger di identity (s1) o la guardia unificata di governance (s4, che lo
        # sostituisce con SQLSTATE 42501) devono comunque rifiutare la modifica.
        with pytest.raises(DatabaseError):
            with transaction.atomic(), connection.cursor() as cursor:
                cursor.execute(sql, [str(event.pk)])
