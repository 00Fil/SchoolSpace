"""Coerenza statica della configurazione di esercizio (GAP-J03, J04, J06, K02, L04).

Non sostituisce `docker compose config`/`promtool`/CI reale: verifica le proprietà che
nessuno strumento controlla da solo (hardening dei servizi, code coerenti con le route
Celery, Actions fissate per SHA, runbook referenziati esistenti).
"""

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def load(path):
    return yaml.safe_load((ROOT / path).read_text())


def test_prod_services_are_hardened():
    services = load("compose.prod.yaml")["services"]
    for name in (
        "web",
        "worker-solver",
        "worker-notifications",
        "beat",
        "proxy",
        "redis",
    ):
        svc = services[name]
        assert svc.get("read_only") is True, name
        assert "ALL" in svc.get("cap_drop", []), name
        assert "no-new-privileges:true" in svc.get("security_opt", []), name
        assert svc.get("deploy", {}).get("resources", {}).get("limits"), name
    backend = (ROOT / "compose.prod.yaml").read_text()
    assert "x-backend: &backend" in backend and 'user: "10001:10001"' in backend
    # nessun servizio applicativo esegue migrate all'avvio
    for name, svc in services.items():
        if name != "migrate":
            assert "migrate" not in " ".join(map(str, svc.get("command", []) or [])), (
                name
            )
    assert services["migrate"]["profiles"] == ["jobs"]


def test_worker_queues_cover_celery_routes():
    services = load("compose.prod.yaml")["services"]
    consumed = set()
    for name in ("worker-solver", "worker-notifications"):
        args = " ".join(services[name]["command"])
        consumed |= set(re.search(r"--queues=(\S+)", args)[1].split(","))
    src = (ROOT / "backend/config/settings_production.py").read_text()
    routed = set(re.findall(r'\{"queue": "([a-z_]+)"\}', src)) | {"default"}
    assert routed <= consumed, routed - consumed
    beat = (ROOT / "backend/config/settings.py").read_text()
    for queue in re.findall(r'"options": \{"queue": "([a-z_]+)"\}', beat):
        assert queue in consumed, queue


def test_github_actions_pinned_by_sha_and_ci_gate():
    for wf in (ROOT / ".github/workflows").glob("*.yml"):
        text = wf.read_text()
        for ref in re.findall(r"uses:\s*(\S+)", text):
            assert re.search(r"@[0-9a-f]{40}$", ref), (
                f"{wf.name}: {ref} non fissata per SHA"
            )
    ci = load(".github/workflows/ci.yml")
    jobs = set(ci["jobs"]) - {"ci-ok"}
    assert set(ci["jobs"]["ci-ok"]["needs"]) == jobs
    assert ci["permissions"] == {"contents": "read"}


def test_alert_runbooks_exist():
    rules = load("infra/monitoring/alerts.yml")
    for group in rules["groups"]:
        for rule in group["rules"]:
            url = rule.get("annotations", {}).get("runbook_url")
            if "alert" in rule:
                assert url, rule["alert"]
                path = ROOT / url.split("#")[0]
                assert path.exists(), f"{rule['alert']}: {url}"


def test_env_examples_have_no_real_secrets_and_match_settings():
    text = (ROOT / "infra/env/production.env.example").read_text()
    for line in text.splitlines():
        if "=" in line and not line.startswith("#"):
            key, value = line.split("=", 1)
            if any(k in key for k in ("SECRET", "PASSWORD", "TOKEN")):
                assert value.startswith("<"), key
    assert "EXPERIMENTAL_" not in "".join(
        line for line in text.splitlines() if not line.startswith("#")
    )
    assert "DB_SSLMODE=verify-full" in text
