"""Parte s5-infra delle impostazioni di produzione: code Celery, heartbeat, Redis TLS con
CA privata, probe interni esenti dal redirect, ``check --deploy`` a 0 warning."""

import json

import pytest

from tests.test_security_settings import load_settings, run

NAMES = (
    "CELERY_TASK_ROUTES",
    "CELERY_TASK_DEFAULT_QUEUE",
    "CELERY_BEAT_SCHEDULE",
    "CELERY_BROKER_TRANSPORT_OPTIONS",
    "CELERY_TASK_TIME_LIMIT",
    "CELERY_WORKER_MAX_TASKS_PER_CHILD",
    "OPS_WORKER_QUEUES",
    "SECURE_REDIRECT_EXEMPT",
    "BUILD_VERSION",
    "DEPLOY_ENVIRONMENT",
    "LOGGING",
    "MIDDLEWARE",
)


def test_queues_routes_and_heartbeats():
    s = load_settings(*NAMES, BUILD_VERSION="1.0.0+abc")
    assert s["CELERY_TASK_ROUTES"]["apps.scheduling.tasks.*"]["queue"] == "solver"
    assert (
        s["CELERY_TASK_ROUTES"]["apps.communications.tasks.*"]["queue"]
        == "notifications"
    )
    assert s["CELERY_TASK_DEFAULT_QUEUE"] == "default"
    assert s["OPS_WORKER_QUEUES"] == ["solver", "notifications", "default"]
    beat = s["CELERY_BEAT_SCHEDULE"]
    for queue in ("solver", "notifications", "default"):
        assert beat[f"ops-heartbeat-{queue}"]["options"]["queue"] == queue
    # Schedule degli altri moduli preservate (s3, s4, scheduling).
    assert {"communications-reconcile", "privacy-retention", "reconcile-runs"} <= set(
        beat
    )
    assert (
        s["CELERY_BROKER_TRANSPORT_OPTIONS"]["visibility_timeout"]
        > s["CELERY_TASK_TIME_LIMIT"]
    )
    assert s["CELERY_WORKER_MAX_TASKS_PER_CHILD"] == 20
    assert s["BUILD_VERSION"] == "1.0.0+abc" and s["DEPLOY_ENVIRONMENT"] == "production"
    assert "^healthz$" in s["SECURE_REDIRECT_EXEMPT"]
    assert s["MIDDLEWARE"][0] == "apps.ops.middleware.RequestContextMiddleware"
    assert s["LOGGING"]["handlers"]["stdout"]["formatter"] == "json"


def test_redis_private_ca_applied_to_cache_and_broker():
    s = load_settings(
        "CACHES", "CELERY_BROKER_USE_SSL", REDIS_CA_PATH="/run/secrets/redis_ca"
    )
    assert s["CACHES"]["default"]["OPTIONS"]["ssl_ca_certs"] == "/run/secrets/redis_ca"
    assert s["CELERY_BROKER_USE_SSL"]["ssl_ca_certs"] == "/run/secrets/redis_ca"


def test_deploy_environment_validated():
    result = run(["-c", "import django; django.setup()"], DEPLOY_ENVIRONMENT="dev")
    assert result.returncode != 0 and "DEPLOY_ENVIRONMENT" in result.stderr


@pytest.mark.parametrize("env_name", ["staging", "production"])
def test_check_deploy_zero_warnings_with_ops(env_name):
    result = run(
        ["manage.py", "check", "--deploy", "--fail-level", "WARNING"],
        DEPLOY_ENVIRONMENT=env_name,
        OPS_METRICS_TOKEN="synthetic-metrics-token",
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_healthz_not_redirected_in_production():
    code = (
        "import django,json; django.setup();"
        "from django.test import Client;"
        "r=Client(SERVER_NAME='app.centro.example').get('/healthz');"
        "print(json.dumps([r.status_code, r.json()['status']]))"
    )
    result = run(["-c", code])
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout.strip().splitlines()[-1]) == [200, "ok"]
