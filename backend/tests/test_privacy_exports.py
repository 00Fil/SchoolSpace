"""GAP-H07 / T42: export protetti, download a scadenza e token monouso, audit delle esportazioni."""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.governance.models import AuditEvent
from apps.privacy import exports
from apps.privacy.errors import Gone, NotAllowed
from apps.privacy.models import ProtectedExport
from apps.privacy.testing import (  # noqa: F401
    api,
    center,
    family,
    make_account,
    outsider,
    privacy_storage,
    student,
)

pytestmark = pytest.mark.django_db
SENSITIVE = b'{"note": "dato sensibile artificiale", "video": "https://v.invalid/r"}'


def make(center, audience, content=SENSITIVE):
    return exports.create_export(
        actor=center,
        audience=audience,
        content=content,
        fmt="json",
        filename="x.json",
        purpose="test",
    )


def test_file_is_private_and_only_hashes_stored(center, privacy_storage):
    export, token = make(center, center)
    path = privacy_storage / "exports" / export.storage_name
    assert path.read_bytes() == SENSITIVE
    assert oct(path.stat().st_mode & 0o777) == "0o600"
    assert export.token_hash != token and token not in str(
        ProtectedExport.objects.filter(pk=export.pk).values().first()
    )
    created = AuditEvent.objects.get(operation="EXPORT_CREATED")
    assert created.details["sha256"] == export.sha256
    assert "dato sensibile" not in str(created.details)


def test_single_use_download_then_file_removed(center, privacy_storage):
    export, token = make(center, center)
    _, content = exports.consume(export.pk, user=center, token=token)
    assert content == SENSITIVE
    assert not (privacy_storage / "exports" / export.storage_name).exists()
    with pytest.raises(Gone):
        exports.consume(export.pk, user=center, token=token)
    ops = list(
        AuditEvent.objects.filter(category="EXPORT").values_list("operation", flat=True)
    )
    assert ops == [
        "EXPORT_CREATED",
        "EXPORT_DOWNLOADED",
        "EXPORT_PURGED",
        "EXPORT_DOWNLOAD_DENIED",
    ]


def test_wrong_audience_bad_token_and_expiry_are_denied_and_audited(center, outsider):
    export, token = make(center, center)
    with pytest.raises(NotAllowed):
        exports.consume(export.pk, user=outsider, token=token)
    with pytest.raises(Gone):
        exports.consume(export.pk, user=center, token="sbagliato")
    ProtectedExport.objects.filter(pk=export.pk).update(
        expires_at=timezone.now() - timedelta(seconds=1)
    )
    with pytest.raises(Gone):
        exports.consume(export.pk, user=center, token=token)
    codes = [
        e.details["code"]
        for e in AuditEvent.objects.filter(operation="EXPORT_DOWNLOAD_DENIED")
    ]
    assert codes == ["WRONG_AUDIENCE", "BAD_TOKEN", "EXPIRED"]
    assert all(token not in str(e.details) for e in AuditEvent.objects.all())


def test_integrity_check(center, privacy_storage):
    export, token = make(center, center)
    (privacy_storage / "exports" / export.storage_name).write_bytes(b"alterato")
    with pytest.raises(Gone):
        exports.consume(export.pk, user=center, token=token)
    assert AuditEvent.objects.filter(details__code="INTEGRITY").exists()


def test_api_download_revoke_and_listing(center, outsider, student):
    other_center = make_account("s4-center-2", "CENTER")
    client = api(center)
    response = client.post(
        "/api/v1/privacy/exports/operational",
        {
            "subject_type": "STUDENT",
            "subject_id": str(student.pk),
            "audience": str(other_center.pk),
        },
        format="json",
    )
    assert response.status_code == 201
    token = response.data["token"]
    assert "token" not in client.get("/api/v1/privacy/exports").data["results"][0]
    assert api(outsider).get("/api/v1/privacy/exports").data["count"] == 0
    in_url = api(other_center).post(
        f"/api/v1/privacy/exports/{response.data['id']}/download?token={token}",
        {},
        format="json",
    )
    assert in_url.status_code == 400  # il token non si passa nell'URL
    revoked = client.post(
        f"/api/v1/privacy/exports/{response.data['id']}/revoke",
        {"reason": "inviato per errore"},
        format="json",
    )
    assert revoked.status_code == 200 and revoked.data["available"] is False
    denied = api(other_center).post(
        f"/api/v1/privacy/exports/{response.data['id']}/download",
        {"token": token},
        format="json",
    )
    assert denied.status_code == 410
    assert (
        api(outsider)
        .post(
            "/api/v1/privacy/exports/operational",
            {"subject_type": "STUDENT", "subject_id": str(student.pk)},
            format="json",
        )
        .status_code
        == 403
    )


def test_retention_purges_expired_files(center, privacy_storage):
    from apps.privacy import retention
    from apps.privacy.models import RetentionPolicy

    export, _ = make(center, center)
    ProtectedExport.objects.filter(pk=export.pk).update(
        expires_at=timezone.now() - timedelta(hours=1)
    )
    policy = RetentionPolicy.objects.get(category="protected_exports")
    retention.approve_policy(
        center, policy, expected_version=policy.version, reference="D09", reason="ok"
    )
    run = retention.run_retention(dry_run=False, categories=["protected_exports"])
    assert run.results[0]["affected"] == 1
    export.refresh_from_db()
    assert export.purged_at and export.storage_name == ""
    assert list((privacy_storage / "exports").iterdir()) == []


def test_orphan_files_are_swept(privacy_storage):
    import os
    import time

    from apps.privacy.exports import export_dir
    from apps.privacy.retention import sweep_orphan_files

    orphan = export_dir() / "orfano"
    orphan.write_bytes(b"x")
    assert sweep_orphan_files() == 0  # troppo recente
    old = time.time() - 7200
    os.utime(orphan, (old, old))
    assert sweep_orphan_files() == 1 and not orphan.exists()
