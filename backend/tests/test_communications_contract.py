"""Le risposte reali delle API comunicazioni rispettano contracts/openapi.yaml."""

from pathlib import Path

import pytest
from django.db import transaction
from django.urls import get_resolver
from jsonschema import Draft202012Validator
from rest_framework.test import APIClient

from apps.communications.dispatch import process_delivery
from apps.communications.models import Delivery
from apps.communications.services import emit
from apps.identity.models import Account

yaml = pytest.importorskip("yaml")
SPEC = yaml.safe_load(
    (Path(__file__).resolve().parents[2] / "contracts" / "openapi.yaml").read_text()
)
OURS = {
    "/notifications": ["get"],
    "/notifications/{pk}/read": ["post"],
    "/notifications/read-all": ["post"],
    "/notifications/preferences": ["get", "put"],
    "/calendar-feed-tokens": ["get", "post"],
    "/calendar-feed-tokens/{pk}/revoke": ["post"],
    "/calendar.ics": ["get"],
    "/occurrences/{pk}/meeting": ["get"],
    "/occurrences/{pk}/meeting/presence": ["get", "post"],
    "/communications/status": ["get"],
    "/communications/deliveries/{pk}/resolve": ["post"],
}


def check(name, data):
    schema = {"components": SPEC["components"], "$ref": f"#/components/schemas/{name}"}
    errors = list(Draft202012Validator(schema).iter_errors(data))
    assert not errors, [e.message for e in errors]


def test_contract_lists_every_communications_route():
    for path, methods in OURS.items():
        assert set(methods) <= set(SPEC["paths"][path]), path
    routes = {str(p.pattern) for p in get_resolver().url_patterns}
    for path in OURS:
        django = "api/v1" + path.replace("{pk}", "<uuid:pk>")
        assert django in routes, django


@pytest.mark.django_db
def test_live_responses_match_schemas():
    user = Account.objects.create_user(
        username="c", email="c@example.invalid", password=None, email_verified=True
    )
    center = Account.objects.create_superuser(
        username="cc", email="cc@example.invalid", password=None
    )
    with transaction.atomic():
        emit(
            "lesson.published",
            {"lesson_id": "x", "version": 1, "subject_name": "Chimica"},
            [user],
            idempotency_key="contract",
        )
    for delivery in Delivery.objects.filter(channel="IN_APP"):
        process_delivery(delivery.pk)
    api = APIClient()
    api.force_authenticate(user)
    page = api.get("/api/v1/notifications").json()
    check("NotificationPage", page)
    check(
        "Notification",
        api.post(f"/api/v1/notifications/{page['results'][0]['id']}/read").json(),
    )
    check(
        "NotificationPreferences", api.get("/api/v1/notifications/preferences").json()
    )
    token = api.post(
        "/api/v1/calendar-feed-tokens", {"label": "x"}, format="json"
    ).json()
    check(
        "CalendarFeedToken",
        {k: v for k, v in token.items() if k not in ("token", "feed_path")},
    )
    check(
        "CalendarFeedToken",
        api.post(f"/api/v1/calendar-feed-tokens/{token['id']}/revoke").json(),
    )
    admin = APIClient()
    admin.force_authenticate(center)
    check("CommunicationsStatus", admin.get("/api/v1/communications/status").json())
