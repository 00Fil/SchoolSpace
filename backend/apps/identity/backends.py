from django.contrib.auth.backends import ModelBackend

from . import conf
from .models import Account, normalize_email


class EmailBackend(ModelBackend):
    """Autenticazione con email normalizzata (GAP-B01).

    Il nome utente è accettato solo se ``IDENTITY_ALLOW_USERNAME_LOGIN`` (sviluppo). Per
    account inesistenti si calcola comunque un hash, così i tempi non rivelano l'esistenza.
    """

    def authenticate(self, request, username=None, password=None, email=None, **kwargs):
        identifier = email if email is not None else username
        if identifier is None or password is None:
            return None
        identifier = normalize_email(identifier)
        user = None
        if "@" in identifier:
            user = Account.objects.filter(email__iexact=identifier).first()
        elif conf.get("ALLOW_USERNAME_LOGIN"):
            user = Account.objects.filter(username=identifier).first()
            if user is None:
                user = Account.objects.filter(username__iexact=identifier).first()
        if user is None:
            Account().set_password(password)
            return None
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
