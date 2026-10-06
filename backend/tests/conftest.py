"""Configurazione comune dei test.

Il registro privacy (ledger) e un file append-only esterno al database: il flush del DB
fra un test e l'altro non lo svuota. Senza isolamento, le voci scritte da un test (o da
un'esecuzione precedente della suite) restano e la riconciliazione post-ripristino le
vede come "richieste privacy assenti dal DB", bloccando la riapertura.
Ogni test riceve quindi una cartella privacy temporanea e pulita.
"""

import pytest


@pytest.fixture(autouse=True)
def isolated_privacy_storage(settings, tmp_path):
    base = tmp_path / "privacy"
    settings.PRIVACY_DATA_DIR = base
    settings.PRIVACY_EXPORT_DIR = base / "exports"
    settings.PRIVACY_LEDGER_PATH = base / "ledger.jsonl"
    (base / "exports").mkdir(parents=True, exist_ok=True)
    yield
