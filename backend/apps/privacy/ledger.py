"""Ledger esterno delle richieste privacy e delle cancellazioni (GAP-H05, GAP-L03).

File JSON Lines append-only, fuori dal database, con catena di hash: un restore del DB non
lo riporta indietro e ``privacy_reconcile`` lo usa per riapplicare revoche e cancellazioni.
In produzione il percorso va su storage separato con versioning/object lock (D09).
"""

import fcntl
import hashlib
import json
import os
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from apps.governance.audit import redact

GENESIS = "0" * 64


def ledger_path():
    return Path(settings.PRIVACY_LEDGER_PATH)


def _digest(previous, payload):
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256((previous + body).encode()).hexdigest()


def read_entries():
    path = ledger_path()
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def append(event, **fields):
    """Accoda una voce (dopo il commit della transazione chiamante, se presente)."""
    payload = {
        "event": event,
        "at": timezone.now().isoformat(),
        **redact(fields),
    }
    path = ledger_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(fd, "r+", encoding="utf-8") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            handle.seek(0)
            previous = GENESIS
            for line in handle:
                if line.strip():
                    previous = json.loads(line)["hash"]
            payload["prev"] = previous
            payload["hash"] = _digest(previous, payload)
            handle.seek(0, os.SEEK_END)
            handle.write(json.dumps(payload, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)
    return payload


def verify_chain():
    """Restituisce (ok, indice della prima voce non valida o None)."""
    previous = GENESIS
    for index, entry in enumerate(read_entries()):
        body = {k: v for k, v in entry.items() if k != "hash"}
        if entry.get("prev") != previous or _digest(previous, body) != entry.get(
            "hash"
        ):
            return False, index
        previous = entry["hash"]
    return True, None


def append_on_commit(event, **fields):
    from django.db import transaction

    transaction.on_commit(lambda: append(event, **fields))
