"""Utilità condivise dalle API s4-privacy (families.py, privacy.py)."""

import functools
from datetime import date, datetime

from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.utils.dateparse import parse_datetime
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from apps.identity.policies import is_center
from apps.privacy.errors import PrivacyError
from apps.reasons import DEFAULT_REASON, reason_or_default


class BadPayload(Exception):
    pass


def handle_errors(view):
    @functools.wraps(view)
    def wrapper(*args, **kwargs):
        try:
            return view(*args, **kwargs)
        except PrivacyError as exc:
            return Response(
                {"code": exc.code, "message": exc.message}, status=exc.status
            )
        except BadPayload as exc:
            return Response(
                {"code": "INVALID_PAYLOAD", "message": str(exc)}, status=400
            )
        except ObjectDoesNotExist:
            return Response({"code": "NOT_FOUND"}, status=404)
        except ValidationError as exc:
            return Response({"code": "INVALID", "message": exc.messages}, status=400)

    return wrapper


def center_only(request):
    if not is_center(request.user):
        raise PermissionDenied()


def payload(request, required=(), optional=(), reason_default=DEFAULT_REASON):
    """Corpo JSON chiuso. ``reason`` è sempre facoltativo: se manca o è vuoto vale il testo standard."""
    data = request.data
    if not isinstance(data, dict):
        raise BadPayload("Oggetto JSON richiesto")
    wants_reason = "reason" in required or "reason" in optional
    if wants_reason:
        required = tuple(k for k in required if k != "reason")
        optional = (*optional, "reason")
    keys = set(data)
    missing = set(required) - keys
    extra = keys - set(required) - set(optional)
    if missing or extra:
        raise BadPayload(
            "Campi mancanti: "
            + ", ".join(sorted(missing))
            + "; non ammessi: "
            + ", ".join(sorted(extra))
        )
    if wants_reason:
        data = {**data, "reason": reason_or_default(data.get("reason"), reason_default)}
    return data


def text(data, key, limit, required=True):
    value = data.get(key, "")
    if value is None:
        value = ""
    if (
        not isinstance(value, str)
        or len(value) > limit
        or (required and not value.strip())
    ):
        raise BadPayload(f"{key}: testo obbligatorio (max {limit})")
    return value.strip()


def integer(data, key, required=True):
    value = data.get(key)
    if value is None and not required:
        return None
    if type(value) is not int:
        raise BadPayload(f"{key}: intero richiesto")
    return value


def boolean(data, key, default=False):
    value = data.get(key, default)
    if not isinstance(value, bool):
        raise BadPayload(f"{key}: booleano richiesto")
    return value


def iso_date(data, key):
    value = data.get(key)
    if value in (None, ""):
        return None
    try:
        parsed = date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise BadPayload(f"{key}: data ISO richiesta") from exc
    return parsed


def iso_datetime(data, key):
    value = data.get(key)
    if value in (None, ""):
        return None
    parsed = parse_datetime(value) if isinstance(value, str) else None
    if parsed is None or parsed.tzinfo is None:
        raise BadPayload(f"{key}: data/ora ISO con fuso richiesta")
    return parsed


def iso(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def paginate(request, queryset, render, limit=100):
    try:
        page = max(1, int(request.query_params.get("page", "1")))
    except ValueError:
        page = 1
    total = queryset.count()
    rows = queryset[(page - 1) * limit : page * limit]
    return Response(
        {"count": total, "page": page, "results": [render(row) for row in rows]}
    )
