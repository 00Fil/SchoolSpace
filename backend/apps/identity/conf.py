"""Impostazioni del modulo identity con default prudenziali.

Ogni valore si sovrascrive in settings con il prefisso ``IDENTITY_``. I valori marcati
"da approvare" dipendono da decisioni aperte (D07 timeout/maggiorenni) e vanno confermati.
"""

from django.conf import settings

DEFAULTS = {
    # Inviti e reset (tec2: 72 h / 30 min).
    "INVITATION_TTL_SECONDS": 72 * 3600,
    "INVITATION_MAX_SENDS": 5,
    "INVITATION_QR_TTL_SECONDS": 15 * 60,
    "PASSWORD_RESET_TTL_SECONDS": 30 * 60,
    "PORTAL_BASE_URL": "http://localhost:5173",
    "MESSAGE_SENDER": "apps.identity.delivery.send_email",
    # MFA (GAP-B04).
    "MFA_ENFORCED": True,
    "MFA_REQUIRED_ROLES": ["CENTER"],
    "MFA_ISSUER": "Gestionale ripetizioni",
    "MFA_RECOVERY_CODES": 10,
    "MFA_PENDING_TTL_SECONDS": 300,
    # Timeout di sessione (D07, da approvare): staff 30 min di inattività, famiglie 8 h.
    "SESSION_IDLE_TIMEOUT_STAFF": 30 * 60,
    "SESSION_ABSOLUTE_TIMEOUT_STAFF": 8 * 3600,
    "SESSION_IDLE_TIMEOUT_DEFAULT": 8 * 3600,
    "SESSION_ABSOLUTE_TIMEOUT_DEFAULT": 8 * 3600,
    "SESSION_TOUCH_INTERVAL_SECONDS": 60,
    # Rate limit (GAP-B05): (tentativi, finestra in secondi) per IP e per identità.
    "THROTTLE_CACHE": "default",
    "THROTTLE_RULES": {
        "login": {"ip": (30, 900), "identity": (5, 900)},
        "mfa": {"ip": (30, 900), "identity": (5, 900)},
        "password_reset": {"ip": (10, 900), "identity": (3, 900)},
        "password_reset_confirm": {"ip": (20, 900)},
        "invitation_accept": {"ip": (20, 900)},
    },
    "THROTTLE_LOCKOUT_BASE_SECONDS": 60,
    "THROTTLE_LOCKOUT_MAX_SECONDS": 3600,
    "THROTTLE_LEVEL_TTL_SECONDS": 24 * 3600,
    # Rete: numero di proxy fidati davanti all'applicazione (X-Forwarded-For).
    "TRUSTED_PROXY_HOPS": 0,
    # Login: l'identificativo è l'email; il nome utente resta solo per lo sviluppo.
    "ALLOW_USERNAME_LOGIN": True,
    # Contesto multi-ruolo (GAP-B07).
    "REQUIRE_CONTEXT_SELECTION": True,
    # Studente maggiorenne confermato dal centro (D07, da approvare):
    # KEEP | CONSENT_REQUIRED | NONE.
    "ADULT_GUARDIAN_ACCESS": "CONSENT_REQUIRED",
    # Admin Django (GAP-I06).
    "ADMIN_ENABLED": True,
    "ADMIN_ALLOWED_NETWORKS": [],
    "ADMIN_REQUIRE_MFA": True,
    # Percorsi esenti dai controlli MFA/contesto (devono restare raggiungibili).
    "GATE_EXEMPT_PREFIXES": [
        "/api/v1/auth/",
        "/api/v1/health",
        "/api/v1/invitations/accept",
    ],
    "CONTEXT_EXEMPT_PREFIXES": ["/api/v1/me"],
}


def get(name):
    if name not in DEFAULTS:
        raise KeyError(name)
    return getattr(settings, "IDENTITY_" + name, DEFAULTS[name])
