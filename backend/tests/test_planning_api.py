import pytest
from rest_framework.test import APIClient
from apps.identity.models import Account
from apps.education.models import TeachingRequest
from apps.scheduling.fixtures import demo_input

pytestmark = pytest.mark.django_db


@pytest.fixture
def center(settings):
    settings.DEBUG = True
    user = Account.objects.create_superuser(
        username="simulation-center",
        email="simulation-center@example.invalid",
        password="synthetic-test-password",
    )
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def test_simulation_api_real_solver_no_database_writes(center):
    before = TeachingRequest.objects.count()
    result = center.post("/api/v1/planning/simulate", demo_input(), format="json")
    assert result.status_code == 200, result.data
    assert (
        result.data["validation"]["status"] == "PASSED"
        and len(result.data["assignments"]) == 6
    )
    assert (
        result.data["publishable"] is False
        and TeachingRequest.objects.count() == before
    )


def test_example_is_synthetic_and_schema_closed(center):
    result = center.get("/api/v1/planning/example")
    assert (
        result.status_code == 200
        and result.data["policy_version"] == "SYNTHETIC-NOT-APPROVED"
    )
    data = result.data
    data["email"] = "not-a-valid-dto"
    assert (
        center.post("/api/v1/planning/simulate", data, format="json").status_code == 400
    )


def test_simulation_center_only(settings):
    settings.DEBUG = True
    user = Account.objects.create_user(
        username="family-simulation", email="family-simulation@example.invalid"
    )
    client = APIClient()
    client.force_authenticate(user=user)
    assert client.get("/api/v1/planning/example").status_code == 403
    assert (
        client.post(
            "/api/v1/planning/simulate", demo_input(), format="json"
        ).status_code
        == 403
    )


def test_simulation_disabled_outside_development(center, settings):
    settings.FEATURE_PLANNING_LAB = False
    assert center.get("/api/v1/planning/example").status_code == 503
    assert (
        center.post(
            "/api/v1/planning/simulate", demo_input(), format="json"
        ).status_code
        == 503
    )


def test_busy_simulation_returns_retry_after(center):
    from api.planning import RUN_SLOT

    RUN_SLOT.acquire()
    try:
        result = center.post("/api/v1/planning/simulate", demo_input(), format="json")
        assert result.status_code == 429 and result["Retry-After"] == "3"
    finally:
        RUN_SLOT.release()


def test_operation_jobs_still_not_implemented(center):
    assert center.post("/api/v1/schedule-runs", {}, format="json").status_code == 400
    assert center.get("/api/v1/planning/readiness").data["ready"] is False
