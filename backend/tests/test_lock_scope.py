"""Regressione v0.9.7 (500 su /occurrences/{id}/reschedule/ in produzione).

In produzione il runtime usa il ruolo ``app_runtime``, che NON ha UPDATE sulle tabelle
append-only (es. ``scheduling_planningsnapshot``). ``SELECT … FOR UPDATE`` con
``select_related`` blocca anche le righe delle tabelle collegate e richiede UPDATE su
tutte: "permission denied for table scheduling_planningsnapshot" → errore 500. Con join
su FK annullabili PostgreSQL rifiuta proprio la query. Ogni lock con select_related deve
quindi limitarsi alla tabella principale: ``select_for_update(of=("self",))``.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCK = re.compile(r"select_for_update\(\s*\)")


def test_locks_with_joins_are_limited_to_the_main_table():
    offenders = []
    for path in [*ROOT.glob("apps/**/*.py"), *ROOT.glob("api/**/*.py")]:
        if "migrations" in path.parts:
            continue
        lines = path.read_text(encoding="utf-8").splitlines()
        for i, line in enumerate(lines):
            if not LOCK.search(line):
                continue
            window = " ".join(lines[max(0, i - 2) : i + 4])
            if "select_related(" in window:
                offenders.append(f"{path.relative_to(ROOT)}:{i + 1}")
    assert not offenders, "select_for_update() con select_related senza of=('self',): " + ", ".join(offenders)
