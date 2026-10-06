from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(
    post_save, sender="identity.Invitation", dispatch_uid="privacy_invitation_terms"
)
def invitation_accepted(sender, instance, **kwargs):
    if instance.status == "ACCEPTED" and instance.role == "GUARDIAN":
        from .registry import apply_invitation_terms

        apply_invitation_terms(instance)
