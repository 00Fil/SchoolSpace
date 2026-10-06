from django.conf import settings
from django.core.checks import Error, Warning, register


@register()
def communications_config(app_configs, **kwargs):
    issues = []
    env = settings.COMMUNICATIONS_ENV
    backend = settings.COMMUNICATIONS_EMAIL["BACKEND"]
    if env not in ("development", "test", "staging", "production"):
        issues.append(Error("COMMUNICATIONS_ENV non valido", id="communications.E001"))
    if backend != "sink" and env != "production":
        issues.append(
            Error(
                "Backend email reale configurato fuori dalla produzione",
                hint="Usare COMMUNICATIONS_EMAIL_BACKEND=sink in sviluppo/test/staging",
                id="communications.E002",
            )
        )
    if env == "production" and backend == "sink":
        issues.append(
            Warning(
                "Produzione con backend email sink: nessuna email sarà inviata",
                id="communications.W001",
            )
        )
    if env == "production" and not settings.COMMUNICATIONS_SEAL_KEYS:
        issues.append(
            Warning(
                "COMMUNICATIONS_SEAL_KEYS assente: chiave dei segreti derivata da SECRET_KEY",
                hint="Usare una chiave Fernet dedicata dal secret manager",
                id="communications.W002",
            )
        )
    for key in settings.COMMUNICATIONS_SEAL_KEYS:
        try:
            from cryptography.fernet import Fernet

            Fernet(key.encode())
        except Exception:
            issues.append(
                Error(
                    "COMMUNICATIONS_SEAL_KEYS: chiave Fernet non valida",
                    id="communications.E004",
                )
            )
            break
    if settings.COMMUNICATIONS_AMBIGUOUS_POLICY not in ("verify", "retry"):
        issues.append(
            Error(
                "COMMUNICATIONS_AMBIGUOUS_POLICY: verify|retry",
                id="communications.E003",
            )
        )
    return issues
