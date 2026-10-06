"""L'admin Django resta per emergenze: ogni sua modifica finisce nell'audit unificato."""

from django.contrib.admin.models import LogEntry
from django.db.models.signals import post_save
from django.dispatch import receiver

ACTIONS = {1: "ADMIN_ADD", 2: "ADMIN_CHANGE", 3: "ADMIN_DELETE"}


@receiver(post_save, sender=LogEntry, dispatch_uid="governance_admin_audit")
def audit_admin_action(sender, instance, created, **kwargs):
    if not created:
        return
    from .audit import record

    record(
        "ADMIN",
        ACTIONS.get(instance.action_flag, "ADMIN_ACTION"),
        actor=instance.user,
        object_type=(
            instance.content_type.model_class()._meta.label_lower
            if instance.content_type_id and instance.content_type.model_class()
            else ""
        ),
        object_id=instance.object_id or "",
        purpose="emergenza",
        command="django-admin",
        details={"change_message": instance.get_change_message()[:300]},
    )
