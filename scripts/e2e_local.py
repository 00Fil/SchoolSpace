#!/usr/bin/env python3
"""Prova end-to-end SENZA Docker (GAP-J07): gli stessi componenti di compose.prod.yaml
come processi locali, con la configurazione di produzione reale.

- PostgreSQL 17 con TLS obbligatorio (hostssl + scram) e certificato di una CA locale,
  ruoli s4 (infra/postgres), migrazione come app_migrator, privilegi + verifica;
- Redis 6/7 solo TLS con ACL (infra/redis/redis-tls.conf, utente "app");
- gunicorn con ``config.settings_production`` (DB verify-full, rediss:// verificato);
- worker Celery "solver" e "notifications,default" + beat;
- nginx con la configurazione dell'immagine proxy, HTTPS, frontend compilato reale;
- smoke (scripts/smoke.sh) e scenari di resilienza; evidenza JSON in docs/evidence.

Uso:  python3 scripts/e2e_local.py [--workdir DIR] [--keep] [--loadtest]
Binari: initdb/pg_ctl/psql (PG 17), redis-server (o redis6-server), nginx, openssl, node.
Python: l'interprete del venv del backend (--python, default /data/venv/bin/python).
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import signal
import socket
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
PW = {"runtime": "e2e-runtime-pw", "migrator": "e2e-migrator-pw", "ro": "e2e-ro-pw"}
REDIS_PW = "e2e-redis-pw"
METRICS_TOKEN = "e2e-metrics-token-0123456789"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def which(*names):
    for n in names:
        p = shutil.which(n)
        if p:
            return p
    raise SystemExit(f"binario richiesto assente: {' / '.join(names)}")


def log(msg, **kw):
    print(
        json.dumps({"ts": datetime.now(timezone.utc).isoformat(), "msg": msg, **kw}),
        file=sys.stderr,
        flush=True,
    )


class Stack:
    def __init__(self, work: Path, python: str):
        self.work = work
        self.python = python
        self.procs: dict[str, subprocess.Popen] = {}
        self.ports = {k: free_port() for k in ("pg", "redis", "web", "http", "https")}
        self.certs = work / "certs"
        self.sock = work / "pgsock"
        self.results: list[dict] = []

    # ------------------------------------------------------------------ util
    def run(self, cmd, env=None, cwd=None, check=True, input=None):
        res = subprocess.run(
            cmd,
            env=env,
            cwd=cwd,
            capture_output=True,
            text=True,
            input=input,
            timeout=600,
        )
        if check and res.returncode != 0:
            raise RuntimeError(f"{cmd[0]} fallito: {res.stderr[-2000:]}")
        return res

    def spawn(self, name, cmd, env=None, cwd=None):
        out = open(self.work / "logs" / f"{name}.log", "ab")
        self.procs[name] = subprocess.Popen(
            cmd,
            env=env,
            cwd=cwd,
            stdout=out,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )

    def stop(self, name, sig=signal.SIGTERM):
        proc = self.procs.pop(name, None)
        if proc and proc.poll() is None:
            os.killpg(proc.pid, sig)
            try:
                proc.wait(30)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)

    def record(self, name, ok, **detail):
        self.results.append({"scenario": name, "ok": bool(ok), **detail})
        log(f"scenario {name}", ok=bool(ok), **detail)

    def https(self, path, headers=None):
        ctx = ssl.create_default_context(cafile=str(self.certs / "ca.crt"))
        req = urllib.request.Request(
            f"https://localhost:{self.ports['https']}{path}", headers=headers or {}
        )
        try:
            with urllib.request.urlopen(req, context=ctx, timeout=10) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()
        except OSError:
            return 0, b""

    def web(self, path, headers=None):
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.ports['web']}{path}", headers=headers or {}
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()
        except OSError:
            return 0, b""

    def wait(self, fn, timeout=60, every=1.0):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if fn():
                return True
            time.sleep(every)
        return False

    # ------------------------------------------------------------- componenti
    def make_certs(self):
        script = (
            ". scripts/lib/common.sh; . scripts/lib/e2e-certs.sh; "
            f'e2e_certs "{self.certs}" localhost localhost; '
            f'e2e_acl "{self.work}/users.acl" "{REDIS_PW}"'
        )
        self.run(["bash", "-c", script], cwd=ROOT)

    def start_postgres(self):
        data = self.work / "pgdata"
        self.sock.mkdir()
        self.run(
            [
                which("initdb"),
                "-D",
                str(data),
                "-U",
                "postgres",
                "-E",
                "UTF8",
                "--auth-local=trust",
                "--auth-host=scram-sha-256",
            ]
        )
        key = data / "server.key"
        shutil.copy(self.certs / "db/key.pem", key)
        key.chmod(0o600)
        shutil.copy(self.certs / "db/cert.pem", data / "server.crt")
        with open(data / "postgresql.conf", "a") as fh:
            fh.write(
                f"\nport = {self.ports['pg']}\nlisten_addresses = '127.0.0.1'\n"
                f"unix_socket_directories = '{self.sock}'\nssl = on\n"
                "ssl_min_protocol_version = 'TLSv1.2'\nlog_min_duration_statement = 500\n"
                "password_encryption = 'scram-sha-256'\n"
            )
        # TLS obbligatorio per le connessioni TCP: senza TLS la connessione è rifiutata.
        (data / "pg_hba.conf").write_text(
            "local all postgres trust\n"
            "hostssl all all 127.0.0.1/32 scram-sha-256\n"
            "hostnossl all all 127.0.0.1/32 reject\n"
        )
        self.run(
            [
                which("pg_ctl"),
                "-D",
                str(data),
                "-l",
                str(self.work / "logs/pg.log"),
                "-w",
                "start",
            ]
        )
        self.procs_pg = data
        psql = [
            which("psql"),
            "-X",
            "-q",
            "-v",
            "ON_ERROR_STOP=1",
            "-h",
            str(self.sock),
            "-p",
            str(self.ports["pg"]),
            "-U",
            "postgres",
        ]
        self.psql_admin = psql
        self.run(psql + ["-d", "postgres", "-c", "CREATE DATABASE ripetizioni"])
        self.run(psql + ["-d", "ripetizioni", "-c", "CREATE EXTENSION btree_gist"])
        self.run(
            psql
            + [
                "-d",
                "ripetizioni",
                "-v",
                "db=ripetizioni",
                "-v",
                f"pw_migrator={PW['migrator']}",
                "-v",
                f"pw_runtime={PW['runtime']}",
                "-v",
                f"pw_ro={PW['ro']}",
                "-f",
                str(ROOT / "infra/postgres/01_roles.sql"),
            ]
        )

    def start_redis(self):
        conf = (ROOT / "infra/redis/redis-tls.conf").read_text()
        conf = (
            conf.replace("/tls/redis.crt", str(self.certs / "redis/cert.pem"))
            .replace("/tls/redis.key", str(self.certs / "redis/key.pem"))
            .replace("/tls/ca.crt", str(self.certs / "ca.crt"))
            .replace("tls-port 6380", f"tls-port {self.ports['redis']}")
            .replace("bind 0.0.0.0", "bind 127.0.0.1")
            .replace("/usr/local/etc/redis/users.acl", str(self.work / "users.acl"))
        )
        conf += f"\ndir {self.work}\n"
        (self.work / "redis.conf").write_text(conf)
        self.spawn(
            "redis",
            [which("redis-server", "redis6-server"), str(self.work / "redis.conf")],
        )
        time.sleep(1)

    def app_env(self, **extra):
        base_url = f"https://localhost:{self.ports['https']}"
        redis = f"rediss://app:{REDIS_PW}@localhost:{self.ports['redis']}"
        env = {
            "PATH": os.environ["PATH"],
            "HOME": str(self.work),
            "DJANGO_SETTINGS_MODULE": "config.settings_production",
            "DEPLOY_ENVIRONMENT": "staging",
            "BUILD_VERSION": "e2e-local",
            "DJANGO_SECRET_KEY": "e2e-local-Qm7v2Lx9Rk4Tz8Wn3Pc6Hb1Yd5Fg0Js2Ua7Ie4Ko9Xr6Nt3",
            "DJANGO_ALLOWED_HOSTS": "localhost,127.0.0.1",
            "DJANGO_CSRF_TRUSTED_ORIGINS": base_url,
            "PORTAL_BASE_URL": base_url,
            "POSTGRES_DB": "ripetizioni",
            "POSTGRES_USER": "app_runtime",
            "POSTGRES_PASSWORD": PW["runtime"],
            "DB_HOST": "localhost",
            "DB_PORT": str(self.ports["pg"]),
            "DB_SSLMODE": "verify-full",
            "DB_SSLROOTCERT": str(self.certs / "ca.crt"),
            "CACHE_URL": f"{redis}/1",
            "CELERY_BROKER_URL": f"{redis}/0",
            "REDIS_CA_PATH": str(self.certs / "ca.crt"),
            "OPS_METRICS_TOKEN": METRICS_TOKEN,
            "OPS_HEARTBEAT_MAX_AGE": "45",
            "OPS_BACKUP_STATUS_FILE": str(self.work / "backup-status.json"),
            "PROMETHEUS_MULTIPROC_DIR": str(self.work / "prom"),
            "GUNICORN_BIND": f"127.0.0.1:{self.ports['web']}",
            "GUNICORN_WORKERS": os.environ.get("E2E_GUNICORN_WORKERS", "3"),
            "PYTHONUNBUFFERED": "1",
        }
        env.update(extra)
        return env

    def migrate(self):
        env = self.app_env(
            POSTGRES_USER="app_migrator",
            POSTGRES_PASSWORD=PW["migrator"],
            PGOPTIONS="-c role=app_owner",
        )
        self.run(
            [self.python, "manage.py", "migrate", "--noinput"], env=env, cwd=BACKEND
        )
        psql = " ".join(
            self.psql_admin[:1] + self.psql_admin[5:] + ["-d", "ripetizioni"]
        )
        self.run(
            [str(ROOT / "scripts/pg-privileges.sh")], env={**os.environ, "PSQL": psql}
        )
        # Il runtime non può fare DDL né connettersi senza TLS.
        bad = self.run(
            [self.python, "manage.py", "migrate", "--check"],
            env=self.app_env(),
            cwd=BACKEND,
            check=False,
        )
        return bad

    def collectstatic(self):
        static = self.work / "static"
        code = (
            "import django, os; os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings');"
            "django.setup(); from django.test.utils import override_settings;"
            "from django.core.management import call_command;"
            f"\nwith override_settings(STATIC_ROOT={str(static)!r}):"
            " call_command('collectstatic', interactive=False, verbosity=0)"
        )
        self.run(
            [self.python, "-c", code],
            cwd=BACKEND,
            env={**os.environ, "USE_SQLITE_FOR_TESTS": "1", "DJANGO_SECRET_KEY": "x"},
        )
        return static

    def start_web(self):
        (self.work / "prom").mkdir(exist_ok=True)
        gunicorn = [self.python, "-m", "gunicorn"]
        self.spawn(
            "web",
            [
                *gunicorn,
                "config.wsgi:application",
                "--config",
                str(ROOT / "infra/gunicorn.conf.py"),
            ],
            env=self.app_env(),
            cwd=BACKEND,
        )

    def start_workers(self, only=None):
        celery = [self.python, "-m", "celery"]
        specs = {
            "worker-solver": [
                *celery,
                "-A",
                "config",
                "worker",
                "-Q",
                "solver",
                "-c",
                "1",
                "--prefetch-multiplier=1",
                "--without-gossip",
                "--without-mingle",
                "-n",
                "solver@e2e",
                "--loglevel=INFO",
            ],
            "worker-notifications": [
                *celery,
                "-A",
                "config",
                "worker",
                "-Q",
                "notifications,default",
                "-c",
                "2",
                "--without-gossip",
                "--without-mingle",
                "-n",
                "notifications@e2e",
                "--loglevel=INFO",
            ],
            "beat": [
                *celery,
                "-A",
                "config",
                "beat",
                "--loglevel=INFO",
                f"--schedule={self.work}/celerybeat-schedule",
            ],
        }
        for name, cmd in specs.items():
            if only is None or name in only:
                self.spawn(name, cmd, env=self.app_env(), cwd=BACKEND)

    def start_proxy(self, static):
        spec = importlib.util.spec_from_file_location(
            "local_layout", ROOT / "infra/nginx/local_layout.py"
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        tmp = self.work / "proxy"
        dist = ROOT / "frontend/dist"
        etc = mod.build_layout(
            tmp,
            self.ports["web"],
            self.ports["http"],
            self.ports["https"],
            frontend_dist=dist if dist.exists() else None,
            static_root=static,
        )
        env = {
            **os.environ,
            "SERVER_NAME": "localhost",
            "CSP_MODE": "enforce",
            "TLS_CERT": str(self.certs / "proxy/fullchain.pem"),
            "TLS_KEY": str(self.certs / "proxy/privkey.pem"),
            "HSTS_SECONDS": "3600",
            "TLS_RELOAD_INTERVAL": "0",
        }
        self.run(["sh", str(tmp / "entry.sh")], env=env)
        nginx = which("nginx", "/usr/sbin/nginx")
        conf = str(etc / "nginx.conf")
        self.run([nginx, "-t", "-p", str(tmp), "-c", conf])
        self.spawn("proxy", [nginx, "-p", str(tmp), "-c", conf, "-g", "daemon off;"])
        self.maintenance_flag = tmp / "srv/maintenance/on"

    def ops_check(self, checks):
        res = self.run(
            [self.python, "manage.py", "ops_check", "--checks", checks],
            env=self.app_env(),
            cwd=BACKEND,
            check=False,
        )
        return res.returncode == 0

    def teardown(self):
        for name in list(self.procs):
            self.stop(name)
        if getattr(self, "procs_pg", None):
            subprocess.run(
                [which("pg_ctl"), "-D", str(self.procs_pg), "-m", "fast", "stop"],
                capture_output=True,
            )


def scenarios(st: Stack, loadtest: bool):
    # 1. Broker giù all'avvio: il web parte, healthz 200, readiness 503 (broker/cache).
    st.start_web()
    up = st.wait(lambda: st.web("/healthz")[0] == 200, 60)
    ready = st.web("/readyz")[0]
    st.record("broker_down_at_start", up and ready == 503, healthz=up, readyz=ready)
    st.start_redis()
    st.record(
        "broker_recovers",
        st.wait(lambda: st.web("/readyz")[0] == 200, 60),
        readyz=st.web("/readyz")[0],
    )
    st.start_workers()
    st.record("workers_heartbeat", st.wait(lambda: st.ops_check("workers"), 90, 3))

    # 2. Smoke completo via proxy HTTPS (CSP reale del frontend compilato).
    smoke = st.run(
        [str(ROOT / "scripts/smoke.sh"), f"https://localhost:{st.ports['https']}"],
        env={**os.environ, "SMOKE_CACERT": str(st.certs / "ca.crt")},
        check=False,
    )
    (st.work / "logs/smoke.log").write_text(smoke.stderr)
    st.record(
        "smoke",
        smoke.returncode == 0,
        failed=[l for l in smoke.stderr.splitlines() if "FALLITO" in l],
    )

    # 3. Metriche con token; senza token 404.
    code, body = st.web("/metrics", {"Authorization": f"Bearer {METRICS_TOKEN}"})
    text = body.decode(errors="replace")
    st.record(
        "metrics",
        code == 200
        and st.web("/metrics")[0] in (401, 404)
        and 'ripetizioni_worker_heartbeat_age_seconds{queue="solver"}' in text
        and "ripetizioni_http_requests_total" in text
        and "ripetizioni_outbox_pending" in text,
        status=code,
    )

    # 4. Redis riavviato: readiness torna verde senza riavviare web/worker.
    st.stop("redis")
    down = st.wait(lambda: st.web("/readyz")[0] == 503, 30)
    st.start_redis()
    back = st.wait(lambda: st.web("/readyz")[0] == 200, 60)
    hb = st.wait(lambda: st.ops_check("workers"), 120, 5)
    st.record(
        "redis_restart",
        down and back and hb,
        detected=down,
        recovered=back,
        workers_after=hb,
    )

    # 5. Worker notifiche ucciso (SIGKILL): heartbeat scaduto rilevato, poi recupero.
    st.stop("worker-notifications", signal.SIGKILL)
    t0 = time.monotonic()
    detected = st.wait(lambda: not st.ops_check("workers"), 150, 5)
    detect_s = round(time.monotonic() - t0)
    st.start_workers(only={"worker-notifications"})
    recovered = st.wait(lambda: st.ops_check("workers"), 120, 3)
    st.record("worker_kill", detected and recovered, detection_seconds=detect_s)

    # 6. Manutenzione: 503 con pagina dedicata, poi ritorno al servizio.
    st.maintenance_flag.write_text("on")
    m_on = st.https("/")[0] == 503
    st.maintenance_flag.unlink()
    m_off = st.https("/")[0] == 200
    st.record("maintenance", m_on and m_off, on=m_on, off=m_off)

    # 7. Log: JSON, correlation id, nessun segreto (token ICS dello smoke, password, chiavi).
    web_log = (st.work / "logs/web.log").read_text(errors="replace")
    access = [
        json.loads(l)
        for l in web_log.splitlines()
        if l.startswith("{") and '"http.request"' in l
    ]
    leaks = [
        s
        for s in ("ics_smoke_invalid", PW["runtime"], REDIS_PW, METRICS_TOKEN)
        if s in web_log
    ]
    st.record(
        "logs_redacted",
        bool(access)
        and not leaks
        and all(a.get("request_id") or a.get("correlation_id") for a in access),
        access_lines=len(access),
        leaks=leaks,
    )

    # 8. Il runtime non può fare DDL (ruolo s4) né connettersi senza TLS.
    nossl = st.run(
        [
            which("psql"),
            "-X",
            "-h",
            "127.0.0.1",
            "-p",
            str(st.ports["pg"]),
            "-U",
            "app_runtime",
            "-d",
            "ripetizioni",
            "-c",
            "select 1",
        ],
        env={**os.environ, "PGPASSWORD": PW["runtime"], "PGSSLMODE": "disable"},
        check=False,
    )
    ddl = st.run(
        [
            which("psql"),
            "-X",
            "-h",
            "localhost",
            "-p",
            str(st.ports["pg"]),
            "-U",
            "app_runtime",
            "-d",
            "ripetizioni",
            "-c",
            "create table e2e_x(id int)",
        ],
        env={
            **os.environ,
            "PGPASSWORD": PW["runtime"],
            "PGSSLMODE": "verify-full",
            "PGSSLROOTCERT": str(st.certs / "ca.crt"),
        },
        check=False,
    )
    st.record(
        "db_least_privilege",
        nossl.returncode != 0
        and ddl.returncode != 0
        and "permission denied" in ddl.stderr,
    )

    if loadtest:
        out = st.work / "loadtest"
        users = st.work / "loadtest-users.txt"
        seed = (
            "import secrets\nfrom apps.identity.models import Account\nrows=[]\n"
            "for i in range(25):\n"
            " pw='Load-'+secrets.token_urlsafe(18)\n"
            " a,_=Account.objects.get_or_create(username=f'load{i}@example.invalid',"
            " defaults={'email':f'load{i}@example.invalid'})\n"
            " a.set_password(pw); a.is_active=True; a.save()\n"
            " rows.append(f'load{i}@example.invalid {pw}')\n"
            f"open({str(users)!r},'w').write('\\n'.join(rows)+'\\n')\n"
        )
        st.run(
            [st.python, "manage.py", "shell", "-c", seed], env=st.app_env(), cwd=BACKEND
        )
        locust = os.environ.get("E2E_LOCUST") or which("locust")
        res = st.run(
            [
                locust,
                "-f",
                str(ROOT / "scripts/loadtest/locustfile.py"),
                "--headless",
                "-u",
                "25",
                "-r",
                "0.16",
                "-t",
                os.environ.get("E2E_LOAD_DURATION", "5m"),
                "--host",
                f"https://localhost:{st.ports['https']}",
                "--csv",
                str(out),
                "--only-summary",
            ],
            env={
                **os.environ,
                "LOADTEST_CA": str(st.certs / "ca.crt"),
                "LOADTEST_USERS_FILE": str(users),
            },
            check=False,
        )
        (st.work / "logs/loadtest.log").write_text(res.stdout + res.stderr)
        summary = [
            line
            for line in (res.stdout + res.stderr).splitlines()
            if "LOADTEST" in line
        ]
        stats = (
            Path(f"{out}_stats.csv").read_text()
            if Path(f"{out}_stats.csv").exists()
            else ""
        )
        st.record(
            "loadtest_25_users_p95",
            res.returncode == 0,
            summary=summary,
            stats_csv=stats.splitlines(),
        )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workdir")
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--loadtest", action="store_true")
    ap.add_argument(
        "--python", default=os.environ.get("E2E_PYTHON", "/data/venv/bin/python")
    )
    ap.add_argument("--evidence", default=str(ROOT / "docs/evidence"))
    args = ap.parse_args()
    work = Path(args.workdir or tempfile.mkdtemp(prefix="e2e-local-"))
    (work / "logs").mkdir(parents=True, exist_ok=True)
    st = Stack(work, args.python)

    def _terminate(signum, _frame):
        raise SystemExit(128 + signum)

    signal.signal(signal.SIGTERM, _terminate)
    started = datetime.now(timezone.utc)
    try:
        st.make_certs()
        st.start_postgres()
        check = st.migrate()
        st.record(
            "migrate_as_migrator_and_privileges",
            True,
            runtime_migrate_check=check.returncode,
        )
        static = st.collectstatic()
        st.start_proxy(static)
        scenarios(st, args.loadtest)
    except (Exception, SystemExit) as exc:  # evidenza anche in caso di errore
        st.record("harness", False, error=str(exc)[-1500:])
    finally:
        st.teardown()
    ok = all(r["ok"] for r in st.results)
    evidence = {
        "format": "ripetizioni-e2e-local/1",
        "started_at": started.isoformat(timespec="seconds"),
        "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "settings": "config.settings_production",
        "components": {
            "postgres": st.run([which("psql"), "--version"]).stdout.strip(),
            "redis": st.run(
                [which("redis-server", "redis6-server"), "--version"]
            ).stdout.split(" sha")[0],
            "nginx": st.run([which("nginx", "/usr/sbin/nginx"), "-v"]).stderr.strip(),
        },
        "results": st.results,
        "ok": ok,
        "not_covered": [
            "interruzione di un run del solver: la pianificazione è disattivata in produzione "
            "(EXPERIMENTAL_DB_PLANNING vietato); coperta dai test di lease/reconcile",
            "immagini Docker e rete compose: scripts/e2e-compose.sh (richiede Docker)",
        ],
    }
    Path(args.evidence).mkdir(parents=True, exist_ok=True)
    out = Path(args.evidence) / f"e2e-local-{started.strftime('%Y%m%dT%H%M%SZ')}.json"
    out.write_text(json.dumps(evidence, indent=2, ensure_ascii=False) + "\n")
    print(out)
    if not args.keep:
        shutil.rmtree(work, ignore_errors=True)
    else:
        log("workdir conservata", path=str(work))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
