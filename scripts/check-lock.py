#!/usr/bin/env python3
"""Freschezza dei lockfile (GAP-J06): ricompila requirements*.in in una directory temporanea
con pip-compile e confronta l'insieme dei pin (nome normalizzato, versione) con
backend/requirements.txt e requirements-dev.txt. Formattazione e ordine non contano.
Fallisce anche se un pin del lock non ha hash.

Uso: python3 scripts/check-lock.py [--pip-compile PATH]
"""

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
PIN = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==([^\s\\;]+)")


def norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def pins(path: Path, base: Path | None = None) -> dict[str, str]:
    result: dict[str, str] = {}
    lines = path.read_text().splitlines()
    for i, line in enumerate(lines):
        if line.startswith("-r "):
            result.update(pins((base or path.parent) / line[3:].strip(), base))
            continue
        m = PIN.match(line)
        if m:
            block = "\n".join(lines[i : i + 3])
            if "--hash=sha256:" not in block:
                raise SystemExit(f"{path.name}: {m.group(1)} senza hash")
            result[norm(m.group(1))] = m.group(2)
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--pip-compile", default=shutil.which("pip-compile") or "pip-compile"
    )
    args = ap.parse_args()
    failed = False
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        for name in ("requirements.in", "requirements-dev.in"):
            shutil.copy(BACKEND / name, tmp / name)
        # Il .in di sviluppo include il lock di produzione: si usa quello committato.
        shutil.copy(BACKEND / "requirements.txt", tmp / "requirements.txt")
        for src, lock in (
            ("requirements.in", "requirements.txt"),
            ("requirements-dev.in", "requirements-dev.txt"),
        ):
            out = tmp / f"compiled-{lock}"
            # Senza --upgrade pip-compile riusa le versioni già nel lock (seed).
            shutil.copy(BACKEND / lock, out)
            subprocess.run(
                [
                    args.pip_compile,
                    "--quiet",
                    "--no-header",
                    "--generate-hashes",
                    "--allow-unsafe",
                    "--strip-extras",
                    "--output-file",
                    str(out),
                    src,
                ],
                cwd=tmp,
                check=True,
            )
            want, have = pins(out, tmp), pins(BACKEND / lock, BACKEND)
            if want != have:
                failed = True
                for k in sorted(set(want) | set(have)):
                    if want.get(k) != have.get(k):
                        print(f"{lock}: {k} lock={have.get(k)} atteso={want.get(k)}")
    if failed:
        print("lockfile non coerenti: eseguire scripts/lock-deps.sh", file=sys.stderr)
        sys.exit(1)
    print("lockfile coerenti con requirements*.in")


if __name__ == "__main__":
    main()
