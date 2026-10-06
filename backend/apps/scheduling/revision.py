"""Conservative revision fence for application ORM writes. Raw SQL is not covered."""

from django.db import models, transaction
from django.db.models import F

TRACKED = {
    "identity.account",
    "identity.rolegrant",
    "education.guardianlink",
    "education.student",
    "education.tutor",
    "education.subject",
    "education.resource",
    "education.teachingrequest",
    "education.learningpath",
    "education.pathenrollment",
    "education.teachinggroup",
    "education.groupmembership",
    "education.curriculumblock",
    "education.requestparticipant",
    "availability.availabilityrule",
    "availability.availabilitydeclaration",
    "availability.availabilityexception",
    "availability.availabilityconflict",
    "scheduling.tutorskill",
    "scheduling.tutoroperatingpolicy",
    "scheduling.resourcetiming",
    "scheduling.servicewindow",
    "scheduling.closure",
    "scheduling.planningpolicy",
    "scheduling.lessonseries",  # s8: recurring-slot stability (GAP-D03)
}


def lock_revision():
    from .models import PlanningRevision

    row, _ = PlanningRevision.objects.get_or_create(pk=1, defaults={"revision": 0})
    return PlanningRevision.objects.select_for_update().get(pk=row.pk)


def bump_revision():
    from .models import PlanningRevision

    PlanningRevision.objects.filter(pk=1).update(revision=F("revision") + 1)


class TrackedQuerySet(models.QuerySet):
    def _mutate(self, method, *args, **kwargs):
        if self.model._meta.label_lower not in TRACKED:
            return method(*args, **kwargs)
        with transaction.atomic():
            lock_revision()
            result = method(*args, **kwargs)
            bump_revision()
            return result

    def update(self, **kwargs):
        return self._mutate(super().update, **kwargs)

    def delete(self):
        return self._mutate(super().delete)

    def bulk_create(self, *args, **kwargs):
        return self._mutate(super().bulk_create, *args, **kwargs)

    def bulk_update(self, *args, **kwargs):
        return self._mutate(super().bulk_update, *args, **kwargs)


def tracked_save(instance, callback, args, kwargs):
    if instance._meta.label_lower not in TRACKED:
        return callback(*args, **kwargs)
    with transaction.atomic():
        lock_revision()
        if not instance._state.adding:
            current = type(instance).objects.only("version").get(pk=instance.pk)
            instance.version = current.version + 1
            if kwargs.get("update_fields") is not None:
                kwargs["update_fields"] = set(kwargs["update_fields"]) | {
                    "version",
                    "updated_at",
                }
        result = callback(*args, **kwargs)
        bump_revision()
        return result
