"""Optional synthetic example, never a real curriculum template or school certification."""

from datetime import date
from uuid import UUID, uuid5, uuid4
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from apps.identity.models import Account
from apps.identity.policies import is_center
from apps.education.models import (
    Family,
    Student,
    Subject,
    LearningPath,
    PathEnrollment,
    TeachingGroup,
    GroupMembership,
    CurriculumBlock,
)
from apps.education.path_services import derive_requests

NS = UUID("785e99cc-55cb-4f58-a4e6-daa4aa20f620")


def uid(name):
    return uuid5(NS, name)


class Command(BaseCommand):
    help = "Esempio sintetico: 4 studenti, 2 materie di prova, sottogruppi di 2; nessun account o appuntamento creato"

    def add_arguments(self, parser):
        parser.add_argument(
            "--actor",
            required=True,
            help="Nome utente di un operatore centro già esistente",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        try:
            actor = Account.objects.get(username=options["actor"])
        except Account.DoesNotExist:
            raise CommandError(
                "Operatore inesistente; creare un account locale prima del demo"
            )
        if not is_center(actor):
            raise CommandError("Solo un operatore del centro può creare il demo")
        first, last = date(2026, 10, 1), date(2027, 6, 30)
        subjects = []
        for name in ("Matematica (demo sintetica)", "Scienze (demo sintetiche)"):
            subject, _ = Subject.objects.get_or_create(
                id=uid(name), defaults={"name": name}
            )
            subjects.append(subject)
        path, created = LearningPath.objects.get_or_create(
            id=uid("path"),
            defaults={
                "title": "DEMO SINTETICO — non programma scolastico reale",
                "kind": "HOME_EDUCATION",
                "academic_year": "2026/2027",
                "level": "Livello sintetico non curricolare",
                "period_start": first,
                "period_end": last,
            },
        )
        if created:
            path.required_subjects.set(subjects)
        students = []
        for n in range(1, 5):
            family, _ = Family.objects.get_or_create(
                id=uid(f"family-{(n + 1) // 2}"),
                defaults={"reference": f"DEMO-PARENTALI-{(n + 1) // 2}"},
            )
            student, _ = Student.objects.get_or_create(
                id=uid(f"student-{n}"),
                defaults={
                    "family": family,
                    "display_name": f"Studente sintetico {n}",
                    "level": "Demo",
                },
            )
            PathEnrollment.objects.get_or_create(
                path=path,
                student=student,
                defaults={"period_start": first, "period_end": last},
            )
            students.append(student)
        for subject in subjects:
            for pair in range(2):
                label = f"{subject.id}-{pair}"
                group, _ = TeachingGroup.objects.get_or_create(
                    id=uid("group-" + label),
                    defaults={
                        "path": path,
                        "name": f"Sottogruppo demo {pair + 1}: {subject.name}",
                        "subject": subject,
                        "approved": True,
                    },
                )
                for student in students[pair * 2 : pair * 2 + 2]:
                    GroupMembership.objects.get_or_create(
                        group=group,
                        student=student,
                        defaults={"period_start": first, "period_end": last},
                    )
                sessions = 2 if subject == subjects[0] else 1
                CurriculumBlock.objects.get_or_create(
                    id=uid("block-" + label),
                    defaults={
                        "path": path,
                        "subject": subject,
                        "objective": "Obiettivo illustrativo; non standard scolastico",
                        "group": group,
                        "period_start": first,
                        "period_end": last,
                        "minutes_per_week": 60 * sessions,
                        "duration_minutes": 60,
                        "sessions_per_week": sessions,
                        "mode": "IN_PERSON",
                        "priority": "P1",
                        "mandatory": True,
                    },
                )
        result = derive_requests(path.id, actor, path.version, "demo-" + str(uuid4()))
        self.stdout.write(
            self.style.SUCCESS(
                f"Demo sintetico: 4 studenti, 2 materie, 4 sottogruppi, {len(result['request_ids'])} richieste canoniche ({result['created']} nuove). Nessuna lezione pubblicata."
            )
        )
