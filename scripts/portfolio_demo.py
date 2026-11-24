"""Run the credential-free portfolio demo and retain its command output."""

import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import shlex
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
STEPS = [
    ("finops-tests.log", [sys.executable, "-m", "unittest", "discover", "-s", "finops-toolkit/tests", "-v"]),
    ("digest-tests.log", [sys.executable, "-m", "unittest", "discover", "-s", "boutique-app/.github/tests", "-p", "test_scanned_images.py", "-v"]),
    ("weekly-report.md", [sys.executable, "-m", "finops.cli", "report", "--fixtures", "finops-toolkit/tests/fixtures"]),
    ("cloud-report.md", [sys.executable, "-m", "finops.cli", "cloud-report", "--input", "finops-toolkit/tests/fixtures/focus_sample.csv", "--as-of", "2026-01-19"]),
    ("waste-report.md", [sys.executable, "-m", "finops.cli", "waste", "--input", "finops-toolkit/tests/fixtures/custodian", "--dry-run"]),
]


def run_demo(output: Path, steps: list) -> int:
    output.mkdir(parents=True, exist_ok=False)
    environment = dict(os.environ)
    environment.update(
        PYTHONPATH=str(ROOT / "finops-toolkit/src"),
        PYTHONDONTWRITEBYTECODE="1",
        PYTHONUTF8="1",
    )
    summary = [
        "# Offline portfolio demo", "",
        f"Started (UTC): {datetime.now(timezone.utc).isoformat()}",
        f"Python: {sys.version.split()[0]}",
        "Working directory: monorepo root", "",
        "Synthetic fixtures only. No cloud deployment or measured savings are established.",
        "Commands below use shell notation; Python uses the current interpreter.", "",
    ]
    for name, command in steps:
        try:
            result = subprocess.run(
                command, cwd=ROOT, env=environment, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, text=True, encoding="utf-8", timeout=60,
            )
            code, log = result.returncode, result.stdout
        except subprocess.TimeoutExpired as exc:
            partial = exc.output or b""
            if isinstance(partial, bytes):
                partial = partial.decode("utf-8", errors="replace")
            code, log = 1, partial + "\n" + str(exc) + "\n"
        except OSError as exc:
            code, log = 1, str(exc) + "\n"
        (output / name).write_text(log, encoding="utf-8")
        status = "PASS" if code == 0 else f"FAIL (exit {code})"
        display = ["python", *command[1:]] if command[0] == sys.executable else command
        summary.extend([f"- {name}: **{status}**", f"  - Command: `{shlex.join(display)}`"])
        (output / "summary.md").write_text("\n".join(summary) + "\n", encoding="utf-8")
        print(f"{status}: {name}")
        if code != 0:
            return code
    print(f"Evidence: {output}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir", type=Path,
        default=ROOT / ".scratch" / ("portfolio-demo-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")),
        help="New evidence directory; existing directories are never overwritten",
    )
    args = parser.parse_args()
    try:
        return run_demo(args.output_dir.resolve(), STEPS)
    except FileExistsError:
        parser.error("output directory already exists; choose a new path to preserve its evidence")


if __name__ == "__main__":
    raise SystemExit(main())
