from django.db.models.signals import m2m_changed
from django.dispatch import receiver
from apps.education.models import LearningPath, TeachingRequest
from .revision import lock_revision, bump_revision


@receiver(m2m_changed, sender=LearningPath.required_subjects.through)
def subjects_changed(sender, action, **kwargs):
    if action in ("pre_add", "pre_remove", "pre_clear"):
        lock_revision()
        bump_revision()


@receiver(m2m_changed, sender=TeachingRequest.preferred_tutors.through)
def preferred_tutors_changed(sender, action, **kwargs):
    # v0.9.4: il tutor preferito/obbligatorio è un input del motore.
    if action in ("pre_add", "pre_remove", "pre_clear"):
        lock_revision()
        bump_revision()
