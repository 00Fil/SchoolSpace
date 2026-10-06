#!/usr/bin/env python3
"""Stampa i segreti per Dokploy (Environment). Solo libreria standard.

Uso: python3 scripts/dokploy-secrets.py   -> copia l'output nella scheda Environment.
Generare UNA volta: cambiare le password PG dopo il primo deploy richiede di rieseguire
il deploy (db-init aggiorna i ruoli), mentre PG_ADMIN_PASSWORD resta quella del primo avvio.
"""
import base64
import os
import secrets

values = {
    "DJANGO_SECRET_KEY": secrets.token_urlsafe(64),
    "PG_ADMIN_PASSWORD": secrets.token_hex(24),
    "PG_MIGRATOR_PASSWORD": secrets.token_hex(24),
    "PG_RUNTIME_PASSWORD": secrets.token_hex(24),
    "PG_READONLY_PASSWORD": secrets.token_hex(24),
    "REDIS_PASSWORD": secrets.token_hex(32),
    "OPS_METRICS_TOKEN": secrets.token_hex(32),
    "COMMUNICATIONS_SEAL_KEYS": base64.urlsafe_b64encode(os.urandom(32)).decode(),
}
for key, value in values.items():
    print(f"{key}={value}")
