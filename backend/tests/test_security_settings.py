"""GAP-I02, I03, I06, I08 (s1-sicurezza): impostazioni di produzione, header, admin, dipendenze."""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
from django.core.cache import cache

from tests.identity_helpers import Api, Clock, enroll_staff, make_account

BACKEND = Path(__file__).resolve().parent.parent
REPO = BACKEND.parent
STRONG_KEY = "k" + "Zq8".join(str(i) for i in range(40)) + "xY7#mN2$pL"


def prod_env(**overrides):
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("DJANGO_", "EXPERIMENTAL_", "FEATURE_", "USE_SQLITE", "CACHE_", "DB_"))
        and k not in ("POSTGRES_PASSWORD", "CELERY_BROKER_URL")
    }
    env.update(
        {
            "DJANGO_SETTINGS_MODULE": "config.settings_production",
            "DJANGO_SECRET_KEY": STRONG_KEY,
            "DJANGO_ALLOWED_HOSTS": "app.centro.example",
            "DJANGO_CSRF_TRUSTED_ORIGINS": "https://app.centro.example",
            "POSTGRES_DB": "ripetizioni",
            "POSTGRES_USER": "app_runtime",
            "POSTGRES_PASSWORD": "synthetic-db-password-for-tests",
            "DB_HOST": "db.internal",
            "DB_SSLROOTCERT": "/etc/ssl/certs/db-ca.pem",
            "CACHE_URL": "rediss://:synthetic@redis.internal:6380/1",
            "CELERY_BROKER_URL": "rediss://:synthetic@redis.internal:6380/0",
        }
    )
    for key, value in overrides.items():
        if value is None:
            env.pop(key, None)
        else:
            env[key] = value
    return env


def run(args, **overrides):
    return subprocess.run(
        [sys.executable, *args],
        cwd=BACKEND,
        env=prod_env(**overrides),
        capture_output=True,
        text=True,
        timeout=120,
    )


def load_settings(*names, **overrides):
    code = (
        "import json, django; from django.conf import settings; django.setup();"
        f"print(json.dumps({{n: getattr(settings, n) for n in {list(names)!r}}}, default=str))"
    )
    result = run(["-c", code], **overrides)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout.strip().splitlines()[-1])


def test_check_deploy_has_zero_warnings():
    result = run(["manage.py", "check", "--deploy", "--fail-level", "WARNING"])
    assert result.returncode == 0, result.stdout + result.stderr
    assert "System check identified no issues" in result.stdout


def test_production_values():
    values = load_settings(
        "DEBUG",
        "ALLOWED_HOSTS",
        "CSRF_TRUSTED_ORIGINS",
        "SECURE_PROXY_SSL_HEADER",
        "SECURE_HSTS_SECONDS",
        "SESSION_COOKIE_SECURE",
        "SESSION_COOKIE_AGE",
        "REST_FRAMEWORK",
        "DATABASES",
        "CACHES",
        "IDENTITY_ADMIN_ENABLED",
        "IDENTITY_ALLOW_USERNAME_LOGIN",
        "IDENTITY_MFA_ENFORCED",
        "DATA_UPLOAD_MAX_MEMORY_SIZE",
        "PASSWORD_HASHERS",
        "EXPERIMENTAL_DB_PLANNING",
        "FEATURE_PLANNING",
        "FEATURE_CALENDAR",
        "FEATURE_PLANNING_LAB",
    )
    assert values["DEBUG"] is False
    assert values["ALLOWED_HOSTS"] == ["app.centro.example"]
    assert values["CSRF_TRUSTED_ORIGINS"] == ["https://app.centro.example"]
    assert values["SECURE_PROXY_SSL_HEADER"] == ["HTTP_X_FORWARDED_PROTO", "https"]
    assert values["SECURE_HSTS_SECONDS"] == 3600
    assert values["SESSION_COOKIE_SECURE"] is True
    assert values["SESSION_COOKIE_AGE"] == 8 * 3600
    assert values["REST_FRAMEWORK"]["DEFAULT_RENDERER_CLASSES"] == [
        "rest_framework.renderers.JSONRenderer"
    ]
    db = values["DATABASES"]["default"]
    assert db["OPTIONS"]["sslmode"] == "verify-full" and db["CONN_MAX_AGE"] == 60
    assert db["CONN_HEALTH_CHECKS"] is True
    assert values["CACHES"]["default"]["BACKEND"].endswith("RedisCache")
    assert values["IDENTITY_ADMIN_ENABLED"] is False
    assert values["IDENTITY_ALLOW_USERNAME_LOGIN"] is False
    assert values["IDENTITY_MFA_ENFORCED"] is True
    assert values["DATA_UPLOAD_MAX_MEMORY_SIZE"] == 1_048_576
    assert "Argon2" in values["PASSWORD_HASHERS"][0]
    # P0 (guida v3.1): calendario e pianificazione attivi per default in produzione.
    assert values["FEATURE_PLANNING"] is True and values["FEATURE_CALENDAR"] is True
    assert values["FEATURE_PLANNING_LAB"] is False


@pytest.mark.parametrize(
    "overrides,message",
    [
        ({"DJANGO_ALLOWED_HOSTS": None}, "DJANGO_ALLOWED_HOSTS is required"),
        ({"DJANGO_ALLOWED_HOSTS": "*"}, "wildcards"),
        (
            {"DJANGO_CSRF_TRUSTED_ORIGINS": None},
            "DJANGO_CSRF_TRUSTED_ORIGINS is required",
        ),
        ({"DJANGO_CSRF_TRUSTED_ORIGINS": "http://app.centro.example"}, "https"),
        ({"DJANGO_SECRET_KEY": "replace-with-a-long-random-secret"}, "too weak"),
        ({"DJANGO_SECRET_KEY": None}, "DJANGO_SECRET_KEY is required"),
        ({"DJANGO_DEBUG": "1"}, "DJANGO_DEBUG must be 0"),
        ({"USE_SQLITE_FOR_TESTS": "1"}, "USE_SQLITE_FOR_TESTS"),
        ({"EXPERIMENTAL_CALENDAR": "1"}, "EXPERIMENTAL_CALENDAR is forbidden"),
        ({"POSTGRES_PASSWORD": None}, "POSTGRES_PASSWORD"),
        ({"DB_SSLMODE": "disable"}, "DB_SSLMODE"),
        ({"DB_SSLROOTCERT": None}, "DB_SSLROOTCERT"),
        ({"CACHE_URL": None}, "CACHE_URL"),
        ({"CACHE_URL": "redis://redis:6379/1"}, "rediss://"),
        ({"CELERY_BROKER_URL": "redis://redis:6379/0"}, "rediss://"),
        ({"DJANGO_ADMIN_ENABLED": "1"}, "DJANGO_ADMIN_ALLOWED_NETWORKS"),
        (
            {"DJANGO_ADMIN_ENABLED": "1", "DJANGO_ADMIN_ALLOWED_NETWORKS": "0.0.0.0/0"},
            "Invalid admin network",
        ),
    ],
)
def test_production_fails_fast_on_unsafe_configuration(overrides, message):
    result = run(["manage.py", "check"], **overrides)
    assert result.returncode != 0
    assert "ImproperlyConfigured" in result.stderr and message in result.stderr
    # Nessun valore segreto finisce nei messaggi d'errore.
    assert (
        STRONG_KEY not in result.stderr and "synthetic-db-password" not in result.stderr
    )


def test_secrets_can_be_read_from_files(tmp_path):
    key_file = tmp_path / "secret_key"
    key_file.write_text(STRONG_KEY + "\n")
    db_file = tmp_path / "db_password"
    db_file.write_text("from-file-password\n")
    values = load_settings(
        "SECRET_KEY",
        "DATABASES",
        DJANGO_SECRET_KEY=None,
        DJANGO_SECRET_KEY_FILE=str(key_file),
        POSTGRES_PASSWORD=None,
        POSTGRES_PASSWORD_FILE=str(db_file),
    )
    assert values["SECRET_KEY"] == STRONG_KEY
    assert values["DATABASES"]["default"]["PASSWORD"] == "from-file-password"
    both = run(["manage.py", "check"], DJANGO_SECRET_KEY_FILE=str(key_file))
    assert both.returncode != 0 and "Set only one of" in both.stderr


def test_admin_enabled_with_allowlist_passes_deploy_check():
    result = run(
        ["manage.py", "check", "--deploy", "--fail-level", "WARNING"],
        DJANGO_ADMIN_ENABLED="1",
        DJANGO_ADMIN_ALLOWED_NETWORKS="10.0.0.0/8",
    )
    assert result.returncode == 0, result.stderr


# --- Header di sicurezza e CORS (GAP-I02) --------------------------------------------


@pytest.mark.django_db
def test_security_headers_on_api_responses(settings):
    settings.SECURITY_CSP_REPORT_ONLY = False
    response = Api().get("/api/v1/health", HTTP_ORIGIN="https://evil.example")
    assert response["Content-Security-Policy"].startswith("default-src 'self'")
    assert "frame-ancestors 'none'" in response["Content-Security-Policy"]
    assert "camera=()" in response["Permissions-Policy"]
    assert response["Referrer-Policy"] == "same-origin"
    assert response["Cross-Origin-Opener-Policy"] == "same-origin"
    assert response["X-Frame-Options"] == "DENY"
    assert response["X-Content-Type-Options"] == "nosniff"
    assert response["Cache-Control"] == "no-store"
    assert not any(h.lower().startswith("access-control-") for h in response.headers)


@pytest.mark.django_db
def test_csp_report_only_mode(settings):
    settings.SECURITY_CSP_REPORT_ONLY = True
    response = Api().get("/api/v1/health")
    assert "Content-Security-Policy-Report-Only" in response
    assert "Content-Security-Policy" not in response


@pytest.mark.django_db
def test_cors_preflight_not_allowed():
    response = Api().client.options(
        "/api/v1/students/",
        HTTP_ORIGIN="https://evil.example",
        HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
    )
    assert "Access-Control-Allow-Origin" not in response


@pytest.mark.django_db
def test_hsts_header_when_secure(settings):
    settings.SECURE_HSTS_SECONDS = 3600
    settings.SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    response = Api().get("/api/v1/health", secure=True)
    assert response["Strict-Transport-Security"] == "max-age=3600; includeSubDomains"


def test_browsable_api_absent_in_production():
    code = (
        "import django; django.setup(); from api import views;"
        "print(sorted(c.__name__ for c in views.StudentsView.renderer_classes));"
        "print(sorted(c.__name__ for c in views.StudentsView.parser_classes))"
    )
    result = run(["-c", code])
    assert result.returncode == 0, result.stderr
    renderers, parsers = result.stdout.strip().splitlines()[-2:]
    assert renderers == "['JSONRenderer']" and parsers == "['JSONParser']"


# --- Admin Django (GAP-I06) -----------------------------------------------------------


@pytest.mark.django_db
def test_admin_disabled_returns_404(settings):
    settings.IDENTITY_ADMIN_ENABLED = False
    assert Api().get("/admin/login/").status_code == 404


@pytest.mark.django_db
def test_admin_network_allowlist(settings):
    settings.IDENTITY_ADMIN_ALLOWED_NETWORKS = ["10.0.0.0/8"]
    assert Api().get("/admin/login/").status_code == 404
    assert Api(REMOTE_ADDR="10.1.2.3").get("/admin/login/").status_code == 200


@pytest.mark.django_db
def test_admin_requires_mfa_verified_session(monkeypatch, client):
    cache.clear()
    staff = make_account("admin@example.invalid", superuser=True)
    client.force_login(staff)  # login senza MFA (es. form admin)
    assert client.get("/admin/").status_code == 302
    api = Api()
    enroll_staff(api, Clock(monkeypatch), "admin@example.invalid")
    assert api.get("/admin/").status_code == 200
    cache.clear()


# --- Dipendenze e segreti (GAP-I08, GAP-I03) -----------------------------------------


def _requirements(name):
    return (BACKEND / name).read_text()


def test_requirements_pin_fixed_versions_with_hashes():
    direct = _requirements("requirements.in")
    assert "<3.17" not in direct
    assert re.search(r"^djangorestframework>=3\.17\.2", direct, re.M)
    assert re.search(r"^pytest>=9\.0\.3", _requirements("requirements-dev.in"), re.M)
    locked = _requirements("requirements.txt")
    assert re.search(r"^djangorestframework==3\.17\.\d+", locked, re.M)
    dev_locked = _requirements("requirements-dev.txt")
    version = re.search(r"^pytest==(\d+)\.(\d+)\.(\d+)", dev_locked, re.M)
    assert version and tuple(map(int, version.groups())) >= (9, 0, 3)
    for text in (locked, dev_locked):
        pins = re.findall(r"^[A-Za-z0-9_.\-\[\]]+==\S+", text, re.M)
        assert pins
        blocks = re.split(r"\n(?=[A-Za-z0-9])", text)
        for block in blocks:
            if "==" in block.split("\n")[0]:
                assert "--hash=sha256:" in block, block.split("\n")[0]


def test_installed_versions_are_not_vulnerable():
    from importlib.metadata import version

    def parse(v):
        return tuple(int(x) for x in re.findall(r"\d+", v)[:3])

    assert parse(version("djangorestframework")) >= (3, 17, 2)
    assert parse(version("pytest")) >= (9, 0, 3)


SECRET_PATTERNS = [
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |)PRIVATE KEY-----"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"ghp_[A-Za-z0-9]{36}"),
    re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"sk_live_[A-Za-z0-9]{20,}"),
    re.compile(r"django-insecure-[A-Za-z0-9]"),
]


def test_no_secrets_committed():
    try:
        files = subprocess.run(
            ["git", "ls-files"], cwd=REPO, capture_output=True, text=True, check=True
        ).stdout.split()
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("git non disponibile")
    offenders = []
    for name in files:
        path = REPO / name
        if not path.is_file() or path.stat().st_size > 2_000_000:
            continue
        if name.startswith("frontend/node_modules"):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if any(p.search(text) for p in SECRET_PATTERNS):
            offenders.append(name)
        if Path(name).name == ".env":
            offenders.append(name)
    assert offenders == []
