"""Account sintetici per provare i portali tutor/famiglia/studente in sviluppo.

Nessuna credenziale predefinita: le password restano inutilizzabili. Per una prova
locale il centro imposta una password temporanea fuori dal repository (es.
``manage.py changepassword``) e la elimina al termine.
"""

from datetime import timedelta
from uuid import uuid5, UUID
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from apps.identity.models import Account, RoleGrant
from apps.identity.policies import is_center
from apps.education.models import GuardianLink, LearningPath, Tutor

NS = UUID("0c8c6a43-6f0a-4f43-a1f4-1d1c9d6a7e21")
FAMILY, STUDENT = "portale-famiglia-demo", "portale-studente-demo"
TUTOR = "tutor-planning-demo-1"


def account(username):
    row, created = Account.objects.get_or_create(
        username=username,
        defaults={"id": uuid5(NS, username), "email": f"{username}@example.invalid"},
    )
    if created:
        row.set_unusable_password()
        row.save()
    return row


def grant(user, role, since):
    if not RoleGrant.objects.filter(
        account=user, role=role, revoked_at__isnull=True
    ).exists():
        RoleGrant.objects.create(account=user, role=role, valid_from=since)


class Command(BaseCommand):
    help = "Account sintetici tutor/tutore legale/studente per i portali (password inutilizzabili)"

    def add_arguments(self, parser):
        parser.add_argument("--actor", required=True)

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.DEBUG or not settings.EXPERIMENTAL_DB_PLANNING:
            raise CommandError("Demo riservato allo sviluppo sperimentale")
        actor = Account.objects.filter(username=options["actor"]).first()
        if not actor or not is_center(actor):
            raise CommandError("Operatore del centro necessario")
        if not Tutor.objects.filter(account__username=TUTOR).exists():
            call_command("seed_planning_demo", actor=actor.username, verbosity=0)
        since = timezone.now() - timedelta(days=1)
        tutor = Account.objects.get(username=TUTOR)
        grant(tutor, "TUTOR", since)
        path = LearningPath.objects.get(
            title="DEMO SINTETICO — non programma scolastico reale"
        )
        students = [
            e.student for e in path.enrollments.select_related("student").order_by("id")
        ]
        if len(students) < 3:
            raise CommandError("Servono almeno tre studenti sintetici")
        family = account(FAMILY)
        grant(family, "GUARDIAN", since)
        for student in students[:2]:
            GuardianLink.objects.get_or_create(
                account=family,
                student=student,
                revoked_at=None,
                defaults={
                    "can_view": True,
                    "can_manage_availability": True,
                    "verified": True,
                    "valid_from": since,
                },
            )
        learner = account(STUDENT)
        grant(learner, "STUDENT", since)
        own = students[2]
        if own.account_id not in (None, learner.id):
            raise CommandError("Studente sintetico già collegato a un altro account")
        if own.account_id is None:
            own.account = learner
            own.save()
        self.stdout.write(
            f"Portali pronti: tutor {TUTOR}, famiglia {FAMILY} ({students[0].display_name}, "
            f"{students[1].display_name}), studente {STUDENT} ({own.display_name}). "
            "Password inutilizzabili: nessuna credenziale predefinita."
        )
