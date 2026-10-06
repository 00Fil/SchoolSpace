"""Helper condivisi dai test identità (s1-sicurezza). Dati sintetici."""

import json
from datetime import timedelta

import pyotp
from django.test import Client
from django.utils import timezone

from apps.identity import mfa
from apps.identity.models import Account, RoleGrant

PW = "Sintetica-Lunga-2026!"


def make_account(email, roles=(), superuser=False, password=PW, **extra):
    username = extra.pop("username", email.split("@")[0])
    factory = (
        Account.objects.create_superuser if superuser else Account.objects.create_user
    )
    user = factory(username=username, email=email, password=password, **extra)
    for role in roles:
        RoleGrant.objects.create(
            account=user, role=role, valid_from=timezone.now() - timedelta(days=1)
        )
    return user


class Api:
    """Client browser-like: cookie di sessione e CSRF obbligatorio."""

    def __init__(self, **extra):
        self.client = Client(enforce_csrf_checks=True, **extra)
        self.client.get("/api/v1/auth/csrf")

    def token(self):
        cookie = self.client.cookies.get("csrftoken")
        return cookie.value if cookie else ""

    def post(self, url, data=None, method="post", **extra):
        call = getattr(self.client, method)
        return call(
            url,
            data=json.dumps({} if data is None else data),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=self.token(),
            **extra,
        )

    def put(self, url, data=None, **extra):
        return self.post(url, data, method="put", **extra)

    def get(self, url, **extra):
        return self.client.get(url, **extra)


class Clock:
    """Orologio TOTP controllato: ogni chiamata a ``tick`` avanza di un passo."""

    def __init__(self, monkeypatch, start=1_800_000_000):
        self.now = start
        monkeypatch.setattr(mfa, "_now", lambda: self.now)

    def tick(self, steps=1):
        self.now += 30 * steps
        return self.now

    def code(self, secret):
        return pyotp.TOTP(secret).at(self.now)


def login(api, email, password=PW):
    return api.post("/api/v1/auth/login", {"email": email, "password": password})


def enroll_staff(api, clock, email, password=PW):
    """Login + configurazione TOTP: restituisce (secret, recovery_codes)."""
    response = login(api, email, password)
    assert response.status_code == 200, response.content
    assert response.json()["mfa_required"] is True
    setup = api.post("/api/v1/auth/mfa/setup")
    assert setup.status_code == 200, setup.content
    secret = setup.json()["secret"]
    clock.tick()
    confirm = api.post("/api/v1/auth/mfa/confirm", {"code": clock.code(secret)})
    assert confirm.status_code == 200, confirm.content
    return secret, confirm.json()["recovery_codes"]


def login_staff(api, clock, email, secret, password=PW):
    response = login(api, email, password)
    assert response.status_code == 200 and response.json()["mfa_required"]
    clock.tick()
    verify = api.post("/api/v1/auth/mfa/verify", {"code": clock.code(secret)})
    assert verify.status_code == 200, verify.content
    return verify
