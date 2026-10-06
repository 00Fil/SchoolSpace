"""Consegna dei messaggi di identità (inviti, reset).

Il default usa il backend email di Django (console in sviluppo, locmem nei test, provider in
produzione). Lo stream comunicazioni può sostituirlo con l'outbox impostando
``IDENTITY_MESSAGE_SENDER``. Il link porta il token nel frammento (#), che i browser non
inviano ai server né nel Referer: non finisce nei log di accesso.
"""

from django.core.mail import send_mail
from django.db import transaction
from django.utils.module_loading import import_string

from . import conf

SUBJECTS = {
    "invitation": "Invito al gestionale del centro",
    "password_reset": "Reimpostazione della password",
}
BODIES = {
    "invitation": (
        "Ciao,\n\nsei stato invitato ad accedere al gestionale del centro. "
        "Apri il link entro {hours} ore per attivare l'accesso:\n\n{link}\n\n"
        "Se non ti aspettavi questo messaggio, ignoralo."
    ),
    "password_reset": (
        "Ciao,\n\nè stata chiesta la reimpostazione della password. Il link vale "
        "{minutes} minuti e si può usare una sola volta:\n\n{link}\n\n"
        "Se non sei stato tu, ignora il messaggio: la password non cambia."
    ),
}
PATHS = {"invitation": "/invito", "password_reset": "/reimposta-password"}


def build_link(kind, token):
    return conf.get("PORTAL_BASE_URL").rstrip("/") + PATHS[kind] + "#token=" + token


def send_email(kind, to, token):
    link = build_link(kind, token)
    body = BODIES[kind].format(
        link=link,
        hours=conf.get("INVITATION_TTL_SECONDS") // 3600,
        minutes=conf.get("PASSWORD_RESET_TTL_SECONDS") // 60,
    )
    send_mail(SUBJECTS[kind], body, None, [to], fail_silently=False)


def deliver(kind, to, token, ref=None):
    """Chiamato dentro la transazione che emette il token.

    Un sender con ``transactional = True`` (es. l'outbox di s3) registra il messaggio
    nello stesso commit e riceve ``ref`` (invito o record di reset) per ricontrollarne
    la validità all'invio; gli altri sender sono eseguiti solo dopo il commit.
    """
    sender = import_string(conf.get("MESSAGE_SENDER"))
    if getattr(sender, "transactional", False):
        sender(kind, to, token, ref=ref)
    else:
        transaction.on_commit(lambda: sender(kind, to, token))
