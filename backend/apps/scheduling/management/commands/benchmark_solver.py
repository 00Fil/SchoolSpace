"""T34 benchmark: N independent runs of the synthetic 720-unit fixture.

Each run executes in a fresh child process so that CPU time and peak RSS are
measured per run (``os.wait4``).  Results (times, memory, solver outcome,
proven levels, validation) are written as JSON and Markdown evidence.  No
database access, no bookings, synthetic data only.
"""

from datetime import datetime, timezone
import json
import os
import platform
import statistics
import subprocess
import sys
from pathlib import Path
from django.core.management.base import BaseCommand


def percentile(values, q):
    ordered = sorted(values)
    if not ordered:
        return None
    index = min(len(ordered) - 1, max(0, round(q * (len(ordered) - 1))))
    return ordered[index]


class Command(BaseCommand):
    help = "Esegue il benchmark T34 del solver sul fixture sintetico da 720 unità"

    def add_arguments(self, parser):
        parser.add_argument("--runs", type=int, default=20)
        parser.add_argument("--budget", type=float, default=30.0)
        parser.add_argument("--workers", type=int, default=1)
        parser.add_argument("--weeks", type=int, default=6)
        parser.add_argument("--output", default="")
        parser.add_argument("--single", action="store_true", help="uso interno")

    def handle(self, *args, **options):
        if options["single"]:
            return self.single(options)
        records = []
        for index in range(options["runs"]):
            command = [
                sys.executable,
                str(Path(__file__).resolve().parents[4] / "manage.py"),
                "benchmark_solver",
                "--single",
                f"--budget={options['budget']}",
                f"--workers={options['workers']}",
                f"--weeks={options['weeks']}",
            ]
            started = datetime.now(timezone.utc)
            process = subprocess.Popen(
                command, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            out = process.stdout.read()
            err = process.stderr.read()
            _, status, usage = os.wait4(process.pid, 0)
            process.returncode = os.waitstatus_to_exitcode(status)
            try:
                record = json.loads(out.decode().strip().splitlines()[-1])
            except (ValueError, IndexError):
                record = {"solver_status": "CRASHED", "error": err.decode()[-400:]}
            record.update(
                run=index + 1,
                started_at=started.isoformat(),
                exit_code=process.returncode,
                cpu_user_seconds=round(usage.ru_utime, 3),
                cpu_system_seconds=round(usage.ru_stime, 3),
                peak_rss_mb=round(usage.ru_maxrss / 1024, 1),
            )
            records.append(record)
            self.stdout.write(
                f"run {index + 1}: {record.get('solver_status')} "
                f"wall={record.get('wall_time_seconds')}s rss={record['peak_rss_mb']}MB"
            )
        report = summarize(records, options)
        if options["output"]:
            base = Path(options["output"])
            base.parent.mkdir(parents=True, exist_ok=True)
            base.with_name(base.name + ".json").write_text(
                json.dumps(report, indent=2) + "\n"
            )
            base.with_name(base.name + ".md").write_text(markdown(report))
        self.stdout.write(json.dumps(report["summary"], indent=2))

    def single(self, options):
        from time import monotonic
        from apps.scheduling.benchmark import benchmark_input
        from apps.scheduling.solver import simulate
        from apps.scheduling.contracts import input_hash, parse_input

        data = benchmark_input(weeks=options["weeks"], budget=options["budget"])
        data["search_workers"] = options["workers"]
        began = monotonic()
        result = simulate(data)
        end_to_end = monotonic() - began
        stats = result.get("statistics", {})
        summary = {
            "solver_status": result["solver_status"],
            "termination_reason": result.get("termination_reason"),
            "validation": result["validation"]["status"],
            "proven_levels": result["optimality_proven_levels"],
            "objective_values": result.get("objective_values", {}),
            "assigned": len(result["assignments"]),
            "unassigned": len(result["unassigned"]),
            "unassigned_mandatory": sum(
                1 for u in result["unassigned"] if u["mandatory"]
            ),
            "candidate_count": stats.get("candidate_count"),
            "variables": stats.get("variables"),
            "constraints": stats.get("constraints"),
            "model_build_seconds": stats.get("model_build_seconds"),
            "search_seconds": stats.get("search_seconds"),
            "diagnostic_seconds": stats.get("diagnostic_seconds", 0),
            "wall_time_seconds": round(end_to_end, 3),
            "phases": stats.get("phases", []),
            "input_hash": input_hash(parse_input(data)),
        }
        sys.stdout.write(json.dumps(summary) + "\n")


def summarize(records, options):
    ok = [r for r in records if r.get("solver_status") in ("OPTIMAL", "FEASIBLE")]
    walls = [r["wall_time_seconds"] for r in records if "wall_time_seconds" in r]
    rss = [r["peak_rss_mb"] for r in records]
    cpu = [r["cpu_user_seconds"] + r["cpu_system_seconds"] for r in records]
    outcomes = {}
    for r in records:
        outcomes[r.get("solver_status")] = outcomes.get(r.get("solver_status"), 0) + 1
    return {
        "test": "T34",
        "fixture": "benchmark_input(): 10 tutor, 80 studenti/50 famiglie, 3 spazi, 120 sessioni/settimana x 6 settimane = 720 unità (sintetico)",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "machine": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "cpu_count": os.cpu_count(),
            "note": "macchina di sviluppo condivisa con altri processi: tempi indicativi",
        },
        "parameters": {k: options[k] for k in ("runs", "budget", "workers", "weeks")},
        "targets": {
            "NFR04_search_budget_seconds": 30,
            "NFR04_valid_proposal_end_to_end_seconds": 60,
            "NFR04_job_hard_limit_seconds": 90,
        },
        "summary": {
            "runs": len(records),
            "outcomes": outcomes,
            "valid_proposals": sum(1 for r in ok if r.get("validation") == "PASSED"),
            "validation_failed": sum(
                1 for r in records if r.get("validation") == "FAILED"
            ),
            "wall_seconds": {
                "min": min(walls, default=None),
                "median": statistics.median(walls) if walls else None,
                "p95": percentile(walls, 0.95),
                "max": max(walls, default=None),
            },
            "cpu_seconds": {
                "median": statistics.median(cpu) if cpu else None,
                "max": max(cpu, default=None),
            },
            "peak_rss_mb": {
                "median": statistics.median(rss) if rss else None,
                "max": max(rss, default=None),
            },
            "within_60s": sum(1 for w in walls if w <= 60),
            "within_90s": sum(1 for w in walls if w <= 90),
            "unassigned_mandatory_max": max(
                (r.get("unassigned_mandatory", 0) for r in records), default=None
            ),
        },
        "runs": records,
    }


def markdown(report):
    s = report["summary"]
    lines = [
        "# Benchmark solver T34 (GAP-D08)",
        "",
        f"Generato: {report['generated_at']}  ",
        f"Fixture: {report['fixture']}  ",
        f"Parametri: {report['parameters']}  ",
        f"Macchina: {report['machine']}",
        "",
        "## Sintesi",
        "",
        f"- Run: {s['runs']}; esiti: {s['outcomes']}",
        f"- Proposte valide (validatore indipendente PASSED): {s['valid_proposals']}; VALIDATION_FAILED: {s['validation_failed']}",
        f"- Wall end-to-end s: {s['wall_seconds']}",
        f"- CPU s (user+sys): {s['cpu_seconds']}",
        f"- Picco RSS MB: {s['peak_rss_mb']}",
        f"- Entro 60 s: {s['within_60s']}/{s['runs']}; entro 90 s: {s['within_90s']}/{s['runs']}",
        f"- Unità obbligatorie non assegnate (max): {s['unassigned_mandatory_max']}",
        "",
        "## Run",
        "",
        "| # | esito | livelli provati | assegnate | non assegnate | build s | ricerca s | diagnostica s | wall s | CPU s | RSS MB |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in report["runs"]:
        lines.append(
            f"| {r['run']} | {r.get('solver_status')} | {','.join(r.get('proven_levels', []))} | "
            f"{r.get('assigned')} | {r.get('unassigned')} | {r.get('model_build_seconds')} | "
            f"{r.get('search_seconds')} | {r.get('diagnostic_seconds')} | {r.get('wall_time_seconds')} | "
            f"{round(r['cpu_user_seconds'] + r['cpu_system_seconds'], 1)} | {r['peak_rss_mb']} |"
        )
    lines += [
        "",
        "Nota: OPTIMAL/FEASIBLE si riferiscono al vettore lessicografico dichiarato; un livello FEASIBLE ferma la sequenza senza ottimalità dei livelli inferiori. Nessuna garanzia di ottimalità entro il budget (NFR04).",
        "",
    ]
    return "\n".join(lines)
