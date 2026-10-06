import json

from django.contrib.auth import get_user_model
from django.core.management.base import CommandError

from apps.identity.policies import is_center


def resolve_actor(username, required=False):
    if not username:
        if required:
            raise CommandError("--actor obbligatorio (account del centro)")
        return None
    actor = get_user_model().objects.filter(username=username).first()
    if actor is None or not is_center(actor):
        raise CommandError("L'attore deve essere un account attivo del centro")
    return actor


def dump(data):
    return json.dumps(data, ensure_ascii=False, indent=2, default=str)
