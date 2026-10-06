"""Controllo di configurazione prima dell'avvio: `python manage.py preflight`.

Stampa OK / ATTENZIONE / ERRORE per ogni voce; esce con codice 1 se c'è almeno un ERRORE.
Non modifica nulla.
"""

import os

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


class Command(BaseCommand):
    help = "Verifica la configurazione (variabili, database, migrazioni, privacy)."

    def handle(self, *args, **opts):
        rows = []
        add = lambda level, what, hint="": rows.append((level, what, hint))  # noqa: E731
        prod = not settings.DEBUG

        add("OK" if prod else "ATTENZIONE", f"DEBUG={'0' if prod else '1'}", "" if prod else "ammesso solo in sviluppo")
        key = settings.SECRET_KEY or ""
        bad_key = "replace" in key or len(key) < 50
        add("ERRORE" if bad_key else "OK", "DJANGO_SECRET_KEY", "valore di esempio o troppo corto (>= 50 caratteri casuali)" if bad_key else "")
        engine = settings.DATABASES["default"]["ENGINE"]
        add("OK" if "postgresql" in engine else "ERRORE", f"Database: {engine.rsplit('.', 1)[-1]}", "" if "postgresql" in engine else "serve PostgreSQL (SQLite solo per prove del core)")
        try:
            connection.ensure_connection()
            add("OK", "Connessione al database")
            ex = MigrationExecutor(connection)
            plan = ex.migration_plan(ex.loader.graph.leaf_nodes())
            add("ERRORE" if plan else "OK", f"Migrazioni da applicare: {len(plan)}", "python manage.py migrate" if plan else "")
            if not plan:
                self._data_checks(add)
        except Exception as exc:  # noqa: BLE001
            add("ERRORE", "Connessione al database", f"{type(exc).__name__}: {exc}"[:160])

        add("OK" if settings.ALLOWED_HOSTS else "ERRORE", "DJANGO_ALLOWED_HOSTS", "" if settings.ALLOWED_HOSTS else "vuoto")
        csrf = getattr(settings, "CSRF_TRUSTED_ORIGINS", [])
        add("OK" if csrf or not prod else "ERRORE", "DJANGO_CSRF_TRUSTED_ORIGINS", "" if csrf else "indicare l'indirizzo https del portale")
        add("OK", f"Informativa versione {getattr(settings, 'PRIVACY_NOTICE_VERSION', '?')}", "cambiarla quando cambia il testo")
        conf = getattr(settings, "COMMUNICATIONS_EMAIL", {}) or {}
        mail = str(conf.get("BACKEND", ""))
        email_on = "EMAIL" in getattr(settings, "COMMUNICATIONS_CHANNELS", ())
        missing = [k for k in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD") if mail == "smtp" and not conf.get(k)]
        bad = prod and email_on and (mail in ("", "sink") or bool(missing))
        level = "ERRORE" if missing else ("ATTENZIONE" if bad else "OK")
        hint = ("mancano " + ", ".join("COMMUNICATIONS_" + k for k in missing)) if missing else ("configurare SMTP o API (COMMUNICATIONS_*)" if bad else "")
        add(level, f"Invio email: {mail or 'non configurato'} (canali: {','.join(getattr(settings, 'COMMUNICATIONS_CHANNELS', ()))})", hint)
        for name in ("PRIVACY_EXPORT_DIR", "PRIVACY_DATA_DIR"):
            path = getattr(settings, name, None)
            if path:
                ok = os.path.isdir(path) and os.access(path, os.W_OK)
                add("OK" if ok else "ERRORE", f"{name}={path}", "" if ok else "cartella assente o non scrivibile")
        for flag in ("EXPERIMENTAL_DB_PLANNING", "FEATURE_PLANNING_LAB"):
            if prod and getattr(settings, flag, False):
                add("ATTENZIONE", f"{flag} attivo", "in produzione va spento")

        width = max(len(w) for _, w, _ in rows)
        for level, what, hint in rows:
            style = {"OK": self.style.SUCCESS, "ATTENZIONE": self.style.WARNING}.get(level, self.style.ERROR)
            self.stdout.write(style(f"{level:<10}") + f" {what:<{width}}  {hint}")
        errors = sum(1 for r in rows if r[0] == "ERRORE")
        self.stdout.write(f"\n{errors} errori, {sum(1 for r in rows if r[0] == 'ATTENZIONE')} avvisi.")
        if errors:
            raise SystemExit(1)

    def _data_checks(self, add):
        from apps.privacy.models import RetentionPolicy

        users = get_user_model().objects
        add("OK" if users.filter(is_superuser=True).exists() else "ERRORE", "Amministratore creato", "" if users.filter(is_superuser=True).exists() else "python manage.py createsuperuser")
        total = RetentionPolicy.objects.count()
        todo = RetentionPolicy.objects.exclude(status="APPROVED").count()
        add("ERRORE" if not total else ("ATTENZIONE" if todo else "OK"), f"Regole di conservazione: {total - todo}/{total} approvate", "approvarle in Privacy → Conservazione (D09)" if todo else "")
