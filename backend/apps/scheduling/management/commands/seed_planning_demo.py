"""Optional local DB fixture. Accounts are synthetic and have unusable passwords."""

from datetime import date, time
from uuid import uuid5, UUID
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from apps.identity.models import Account
from apps.identity.policies import is_center
from apps.education.models import LearningPath, Tutor, Resource
from apps.availability.models import AvailabilityRule, AvailabilityDeclaration
from apps.scheduling.models import (
    TutorSkill,
    TutorOperatingPolicy,
    ResourceTiming,
    ServiceWindow,
    PlanningPolicy,
)

NS = UUID("e277d4e3-bb1b-49f2-8c58-d6a4b5a599a5")
# Default dimostrativo: lunedì, mercoledì e giovedì 10–16 (il martedì resta libero).
# I test passano --days 0 per mantenere il solver rapido e deterministico.
DEFAULT_DAYS = "0,2,3"


def uid(key):
    return uuid5(NS, key)


class Command(BaseCommand):
    help = "Seed DB sintetico con competenze, disponibilità approvate e policy esplorativa, senza credenziali utilizzabili"

    def add_arguments(self, parser):
        parser.add_argument("--actor", required=True)
        parser.add_argument(
            "--days",
            default=DEFAULT_DAYS,
            help="Giorni ISO-1 (0=lunedì) con disponibilità e finestre di servizio, es. 0,2,3",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.DEBUG or not settings.EXPERIMENTAL_DB_PLANNING:
            raise CommandError("Demo riservato allo sviluppo sperimentale")
        try:
            WEEKDAYS = sorted({int(d) for d in str(options["days"]).split(",")})
        except ValueError as error:
            raise CommandError("--days: elenco di interi 0–6") from error
        if not WEEKDAYS or not all(0 <= d <= 6 for d in WEEKDAYS):
            raise CommandError("--days: elenco di interi 0–6")
        actor = Account.objects.filter(username=options["actor"]).first()
        if not actor or not is_center(actor):
            raise CommandError("Operatore del centro necessario")
        call_command("bootstrap_center", verbosity=0)
        call_command("seed_parentali_demo", actor=actor.username, verbosity=0)
        path = LearningPath.objects.get(
            title="DEMO SINTETICO — non programma scolastico reale"
        )
        first, last = path.period_start, path.period_end
        for n in (1, 2):
            account, created = Account.objects.get_or_create(
                id=uid("account-" + str(n)),
                defaults={
                    "username": f"tutor-planning-demo-{n}",
                    "email": f"tutor-planning-demo-{n}@example.invalid",
                },
            )
            if created:
                account.set_unusable_password()
                account.save()
            tutor, _ = Tutor.objects.get_or_create(
                id=uid("tutor-" + str(n)),
                defaults={
                    "account": account,
                    "display_name": f"Tutor pianificazione sintetico {n}",
                },
            )
            TutorOperatingPolicy.objects.get_or_create(
                tutor=tutor,
                defaults={
                    "daily_limit_minutes": 300,
                    "weekly_limit_minutes": 600,
                    "pause_minutes": 0,
                    "site_to_remote_minutes": 30,
                    "remote_to_site_minutes": 30,
                },
            )
            AvailabilityDeclaration.objects.get_or_create(
                tutor=tutor, defaults={"state": "APPROVED"}
            )
            for weekday in WEEKDAYS:
                AvailabilityRule.objects.get_or_create(
                    tutor=tutor,
                    weekday=weekday,
                    period_start=first,
                    period_end=last,
                    mode="IN_PERSON",
                    location="ON_SITE",
                    defaults={
                        "start_time": time(10),
                        "end_time": time(16),
                        "status": "APPROVED",
                        "author": actor,
                        "approved_by": actor,
                    },
                )
            for subject in path.required_subjects.all():
                TutorSkill.objects.get_or_create(
                    tutor=tutor,
                    subject=subject,
                    level=path.level,
                    mode="IN_PERSON",
                    valid_from=first,
                    valid_until=last,
                    defaults={"approved": True},
                )
        for enrollment in path.enrollments.all():
            student = enrollment.student
            AvailabilityDeclaration.objects.get_or_create(
                student=student, defaults={"state": "APPROVED"}
            )
            for weekday in WEEKDAYS:
                AvailabilityRule.objects.get_or_create(
                    student=student,
                    weekday=weekday,
                    period_start=first,
                    period_end=last,
                    mode="IN_PERSON",
                    location="ON_SITE",
                    defaults={
                        "start_time": time(10),
                        "end_time": time(16),
                        "status": "APPROVED",
                        "author": actor,
                        "approved_by": actor,
                    },
                )
        for weekday in WEEKDAYS:
            ServiceWindow.objects.get_or_create(
                # Id storico per il lunedì: i database già popolati restano idempotenti.
                id=uid("service" if weekday == 0 else f"service-{weekday}"),
                defaults={
                    "mode": "IN_PERSON",
                    "location": "ON_SITE",
                    "weekday": weekday,
                    "start_time": time(10),
                    "end_time": time(16),
                    "period_start": first,
                    "period_end": last,
                },
            )
        for resource in Resource.objects.filter(active=True):
            ResourceTiming.objects.get_or_create(
                resource=resource,
                defaults={"buffer_minutes": 0, "inherit_service_windows": True},
            )
        policy, _ = PlanningPolicy.objects.get_or_create(
            id=uid("policy"),
            defaults={
                "name": "DEMO DB — non approvazione G1",
                "budget_seconds": 3,
                "online_onsite_requires_space": True,
                "video_channels_required": False,
                "partial_week_rule": "BLOCK",
                "unsupported_constraints": [],
                "approved_for_exploration": True,
            },
        )
        self.stdout.write(
            f"Demo DB pronto. Policy {policy.id}; settimana consigliata 2026-10-05; giorni {','.join(map(str, WEEKDAYS))}. I due account tutor non possono autenticarsi."
        )
