import json

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.ops import restore


class Command(BaseCommand):
    help = (
        "Riconciliazione dopo un restore (revoche, cancellazioni, outbox, run, invarianti). "
        "Dry-run di default; --apply per scrivere. Exit code ≠ 0 se la riapertura è bloccata."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--restore-point",
            required=True,
            help="Istante effettivo del restore (ISO 8601)",
        )
        parser.add_argument(
            "--external-log",
            help="Registro JSONL esterno aggiuntivo (oltre al ledger privacy PRIVACY_LEDGER_PATH)",
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Applica le modifiche (default: dry-run)",
        )
        parser.add_argument(
            "--allow-missing",
            action="store_true",
            help="Non bloccare per hook non ancora implementati",
        )
        parser.add_argument(
            "--report", help="Scrive il report JSON in questo file (evidenza)"
        )

    def handle(self, *args, **opts):
        point = restore.parse_ts(opts["restore_point"])
        if point is None:
            raise CommandError("--restore-point non valido (ISO 8601)")
        try:
            events = restore.load_external_log(opts.get("external_log"))
        except (OSError, ValueError) as exc:
            raise CommandError(f"registro esterno illeggibile: {exc}") from exc
        ctx = restore.RestoreContext(
            restore_point=point, apply=opts["apply"], external_events=events
        )
        hooks = getattr(settings, "OPS_POST_RESTORE_HOOKS", restore.DEFAULT_HOOKS)
        report = restore.run(ctx, hooks=hooks, allow_missing=opts["allow_missing"])
        text = json.dumps(report, ensure_ascii=False, indent=2)
        if opts.get("report"):
            with open(opts["report"], "w", encoding="utf-8") as fh:
                fh.write(text + "\n")
        self.stdout.write(text)
        if not report["ok"]:
            raise CommandError(
                "Riconciliazione incompleta: riapertura bloccata (vedi report)"
            )
