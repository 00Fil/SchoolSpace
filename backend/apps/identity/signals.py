from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.dispatch import receiver

from . import sessions


@receiver(user_logged_in)
def register_session(sender, request, user, **kwargs):
    if request is not None and hasattr(request, "session"):
        sessions.register(request, user)


@receiver(user_logged_out)
def revoke_session(sender, request, user, **kwargs):
    if request is not None and hasattr(request, "session"):
        record = sessions.current(request)
        if record is not None:
            sessions.revoke(record, "logout")
