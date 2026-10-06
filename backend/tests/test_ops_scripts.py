"""Script operativi (GAP-L01, L03): backup cifrato e restore drill.

- test con comandi finti (pg_dump/pg_restore/psql/age) sempre eseguiti: percorsi di
  errore, retention, rifiuto dei bersagli di produzione;
- round trip reale backup -> restore drill su PostgreSQL 17 se ``S5_PG_DRILL=1`` e le
  variabili libpq (PGHOST, PGPORT, PGUSER amministratore) puntano a un server di prova con
  un database migrato ``S5_PG_SOURCE_DB`` (in CI: job postgres di .github/workflows/ci.yml).
"""

import json
import os
import shutil
import subprocess
import textwrap
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"


def _stub(bindir: Path, name: str, body: str):
    path = bindir / name
    path.write_text("#!/usr/bin/env bash\nset -eu\n" + textwrap.dedent(body))
    path.chmod(0o755)


@pytest.fixture
def stubs(tmp_path):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    _stub(bindir, "psql", 'echo "17.10"\n')
    _stub(
        bindir,
        "pg_dump",
        """
        out=""
        for a in "$@"; do case $a in --file=*) out=${a#--file=};; --version) echo "pg_dump (PostgreSQL) 17.10"; exit 0;; esac; done
        head -c "${FAKE_DUMP_BYTES:-8192}" /dev/urandom > "$out"
        """,
    )
    _stub(
        bindir,
        "pg_restore",
        """
        printf ';\\n; Archive\\n1; 1259 1 TABLE public t app_owner\\n2; 0 1 TABLE DATA public t app_owner\\n'
        """,
    )
    # age finto: "cifra" copiando (il test reale usa age vero).
    _stub(
        bindir,
        "age",
        """
        out=""; in=""
        while [ $# -gt 0 ]; do case $1 in --output) out=$2; shift 2;; --recipients-file|--identity) shift 2;; --encrypt|--decrypt) shift;; *) in=$1; shift;; esac; done
        cp "$in" "$out"
        """,
    )
    recipients = tmp_path / "recipients.txt"
    recipients.write_text(
        "age1qqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqq\n"
    )
    env = {
        "PATH": f"{bindir}:{os.environ['PATH']}",
        "HOME": str(tmp_path),
        "PGDATABASE": "ripetizioni",
        "BACKUP_DIR": str(tmp_path / "out"),
        "BACKUP_AGE_RECIPIENTS_FILE": str(recipients),
        "BACKUP_TEXTFILE_DIR": str(tmp_path / "textfile"),
    }
    return tmp_path, env


def run(script, env, *args):
    return subprocess.run(
        ["bash", str(SCRIPTS / script), *args],
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_backup_success_manifest_status_and_retention(stubs):
    tmp, env = stubs
    out = tmp / "out"
    out.mkdir()
    old = out / "ripetizioni-ripetizioni-20200101T000000Z.dump.age"
    old.write_text("old")
    keep = out / "unrelated.txt"
    keep.write_text("x")
    past = time.time() - 40 * 86400
    os.utime(old, (past, past))
    os.utime(keep, (past, past))
    uploads = tmp / "uploads"
    uploads.mkdir()
    env["BACKUP_UPLOAD_CMD"] = str(tmp / "upload.sh")
    (tmp / "upload.sh").write_text(f'#!/bin/sh\ncp "$1" "{uploads}/$2"\n')
    (tmp / "upload.sh").chmod(0o755)
    res = run("backup.sh", env)
    assert res.returncode == 0, res.stderr
    enc = Path(res.stdout.strip())
    manifest = json.loads(
        enc.with_name(enc.name.replace(".dump.age", ".manifest.json")).read_text()
    )
    assert manifest["table_data_entries"] == 1 and manifest["retention_days"] == 35
    assert manifest["dump_bytes"] == 8192
    status = json.loads((out / "backup-status.json").read_text())
    assert (
        status["size_bytes"] == enc.stat().st_size and status["last_success_epoch"] > 0
    )
    assert sorted(p.name for p in uploads.iterdir()) == sorted(
        [enc.name, enc.name.replace(".dump.age", ".manifest.json")]
    )
    assert not old.exists() and keep.exists()  # retention solo sui file di backup
    assert not list(out.glob(".work-*")) and not list(out.glob("*.dump"))
    prom = (tmp / "textfile" / "ripetizioni_backup.prom").read_text()
    assert "ripetizioni_backup_last_run_success 1" in prom
    # i log sono JSON e non contengono la stringa di connessione
    for line in res.stderr.splitlines():
        json.loads(line)


def test_backup_too_small_fails_without_leaving_files(stubs):
    tmp, env = stubs
    env["FAKE_DUMP_BYTES"] = "10"
    res = run("backup.sh", env)
    assert res.returncode != 0
    out = tmp / "out"
    assert not list(out.glob("*.age")) and not list(out.glob("*.manifest.json"))
    assert not (out / "backup-status.json").exists()
    failed = json.loads((out / "backup-status.failed.json").read_text())
    assert failed["last_failure_exit"] != 0
    assert (
        "ripetizioni_backup_last_run_success 0"
        in (tmp / "textfile" / "ripetizioni_backup.prom").read_text()
    )


def test_backup_requires_recipients(stubs):
    _, env = stubs
    env.pop("BACKUP_AGE_RECIPIENTS_FILE")
    res = run("backup.sh", env)
    assert res.returncode != 0 and "BACKUP_AGE_RECIPIENTS_FILE" in res.stderr


def _backup(stubs):
    tmp, env = stubs
    res = run("backup.sh", env)
    assert res.returncode == 0, res.stderr
    return Path(res.stdout.strip())


@pytest.mark.parametrize(
    "extra, message",
    [
        ({"RESTORE_CONFIRM_HOST": "altro"}, "non confermato"),
        ({"PROD_DB_HOSTS": "x,pg-test"}, "host di produzione"),
        ({"RESTORE_DB_NAME": "ripetizioni"}, "drill"),
    ],
)
def test_restore_drill_refuses_unsafe_targets(stubs, extra, message):
    tmp, env = stubs
    enc = _backup(stubs)
    for name in ("createdb", "dropdb"):
        _stub(tmp / "bin", name, "echo NON-DEVE-ESSERE-CHIAMATO >&2; exit 99\n")
    env.update({"PGHOST": "pg-test", "RESTORE_CONFIRM_HOST": "pg-test", **extra})
    res = run("restore-drill.sh", env, str(enc))
    assert res.returncode != 0 and message in res.stderr
    assert "NON-DEVE-ESSERE-CHIAMATO" not in res.stderr


def test_restore_drill_rejects_tampered_backup(stubs):
    tmp, env = stubs
    enc = _backup(stubs)
    with enc.open("ab") as fh:
        fh.write(b"x")
    for name in ("createdb", "dropdb"):
        _stub(tmp / "bin", name, "exit 99\n")
    env.update(
        PGHOST="pg-test",
        RESTORE_CONFIRM_HOST="pg-test",
        RESTORE_AGE_IDENTITY_FILE=str(tmp / "id"),
    )
    res = run("restore-drill.sh", env, str(enc))
    assert res.returncode != 0 and "hash" in res.stderr


@pytest.mark.skipif(
    os.environ.get("S5_PG_DRILL") != "1" or not shutil.which("age"),
    reason="round trip reale: S5_PG_DRILL=1, PostgreSQL di prova e age richiesti",
)
def test_real_backup_and_restore_drill_roundtrip(tmp_path):
    keys = tmp_path / "id.txt"
    gen = subprocess.run(
        ["age-keygen", "-o", str(keys)], capture_output=True, text=True, check=True
    )
    recipients = tmp_path / "recipients.txt"
    recipients.write_text(gen.stderr.split("Public key: ")[1].strip() + "\n")
    env = {
        **os.environ,
        "PGDATABASE": os.environ.get("S5_PG_SOURCE_DB", "ripetizioni_src"),
        "BACKUP_DIR": str(tmp_path / "out"),
        "BACKUP_AGE_RECIPIENTS_FILE": str(recipients),
    }
    res = run("backup.sh", env)
    assert res.returncode == 0, res.stderr
    env.update(
        RESTORE_CONFIRM_HOST=env["PGHOST"],
        RESTORE_AGE_IDENTITY_FILE=str(keys),
        RESTORE_SKIP_ROLES="1",
        RESTORE_EVIDENCE_DIR=str(tmp_path / "evidence"),
    )
    drill = run("restore-drill.sh", env, res.stdout.strip())
    assert drill.returncode == 0, drill.stderr
    evidence = json.loads(Path(drill.stdout.strip().splitlines()[-1]).read_text())
    assert (
        evidence["ok"] and evidence["problems"] == [] and evidence["public_tables"] > 50
    )


@pytest.mark.skipif(not shutil.which("shellcheck"), reason="shellcheck non installato")
def test_scripts_pass_shellcheck():
    files = sorted(str(p) for p in SCRIPTS.rglob("*.sh"))
    res = subprocess.run(
        ["shellcheck", "-x", *files], cwd=ROOT, capture_output=True, text=True
    )
    assert res.returncode == 0, res.stdout


# ------------------------------------------------------------------ deploy.sh


@pytest.fixture
def deploy_env(tmp_path):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    calls = tmp_path / "calls.log"
    # docker finto: registra "IMAGE_TAG=<tag> <argomenti>"; "up" fallisce se FAIL_UP_TAG.
    _stub(
        bindir,
        "docker",
        f"""
        echo "IMAGE_TAG=${{IMAGE_TAG:-}} $*" >> {calls}
        case " $* " in *" up "*) [ "${{IMAGE_TAG:-}}" != "${{FAIL_UP_TAG:-none}}" ] || exit 1;; esac
        exit 0
        """,
    )
    _stub(
        bindir,
        "psql",
        f'echo "psql $*" >> {calls}\ncat >/dev/null\nexit 0\n',
    )
    smoke = tmp_path / "smoke.sh"
    smoke.write_text(
        f'#!/bin/sh\necho "smoke $1" >> {calls}\n[ "$(cat {tmp_path}/smoke-fails 2>/dev/null)" != yes ]\n'
    )
    smoke.chmod(0o755)
    state = tmp_path / "state"
    state.mkdir()
    status = tmp_path / "backup-status.json"
    status.write_text(json.dumps({"last_success_epoch": int(time.time()) - 3600}))
    env = {
        "PATH": f"{bindir}:{os.environ['PATH']}",
        "HOME": str(tmp_path),
        "BASE_URL": "https://app.example.invalid",
        "BACKUP_STATUS_FILE": str(status),
        "DEPLOY_STATE_DIR": str(state),
        "SMOKE_CMD": str(smoke),
    }
    return tmp_path, env, calls, state


def test_deploy_success_records_tag(deploy_env):
    tmp, env, calls, state = deploy_env
    (state / "current-tag").write_text("v1\n")
    res = run("deploy.sh", env, "v2")
    assert res.returncode == 0, res.stderr
    log = calls.read_text()
    assert (
        "IMAGE_TAG=v2 compose -f compose.prod.yaml --profile jobs run --rm -T migrate"
        in log
    )
    assert "02_privileges" not in log  # SQL passato su stdin
    assert log.index("migrate") < log.index(" up -d")  # migrazioni prima del rollout
    assert "smoke https://app.example.invalid" in log
    assert (state / "current-tag").read_text() == "v2\n"
    assert (state / "previous-tag").read_text() == "v1\n"


def test_deploy_blocked_without_recent_backup(deploy_env):
    tmp, env, calls, state = deploy_env
    Path(env["BACKUP_STATUS_FILE"]).write_text(
        json.dumps({"last_success_epoch": int(time.time()) - 30 * 3600})
    )
    res = run("deploy.sh", env, "v2")
    assert res.returncode != 0 and "rilascio bloccato" in res.stderr
    assert "run --rm -T migrate" not in calls.read_text()


def test_deploy_rolls_back_when_smoke_fails(deploy_env):
    tmp, env, calls, state = deploy_env
    (state / "current-tag").write_text("v1\n")
    (tmp / "smoke-fails").write_text("yes")
    res = run("deploy.sh", env, "v2")
    assert res.returncode != 0
    log = calls.read_text()
    assert "IMAGE_TAG=v1 compose -f compose.prod.yaml up -d --wait" in log
    assert (state / "current-tag").read_text() == "v1\n"


def test_deploy_rolls_back_when_healthchecks_fail(deploy_env):
    tmp, env, calls, state = deploy_env
    (state / "current-tag").write_text("v1\n")
    env["FAIL_UP_TAG"] = "v2"
    res = run("deploy.sh", env, "v2")
    assert res.returncode != 0 and "ripristinata v1" in res.stderr
    assert "IMAGE_TAG=v1 compose -f compose.prod.yaml up -d --wait" in calls.read_text()


def test_deploy_rejects_bad_tag(deploy_env):
    _, env, calls, _ = deploy_env
    res = run("deploy.sh", env, "v2;rm -rf /")
    assert res.returncode != 0 and not calls.exists()
