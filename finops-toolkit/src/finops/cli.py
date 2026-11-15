import argparse
import json
import sys
from datetime import UTC, date, datetime
from decimal import Decimal, DecimalException
from os import environ
from pathlib import Path

from finops.athena_client import read_athena, read_cur_fixture
from finops.cloud_costs import render_cloud_report
from finops.config import AthenaConfig, required
from finops.notifier import notify
from finops.opencost_client import parse_allocations, read_opencost
from finops.report import render_report, weekly_windows
from finops.waste import read_findings, render_findings


def _report(fixtures: Path | None) -> str:
    if fixtures is not None:
        payload = json.loads(
            (fixtures / "opencost_sample.json").read_text(encoding="utf-8"), parse_float=Decimal
        )
        end = date.fromisoformat(payload["as_of"])
        cluster = (parse_allocations(payload["current"]), parse_allocations(payload["previous"]))
        return render_report(end, cluster, read_cur_fixture(fixtures / "cur_sample.csv"), demo=True)

    end = datetime.now(UTC).date()
    current, previous = weekly_windows(end)
    url = required("OPENCOST_URL")
    config = AthenaConfig.from_environment()
    cluster = (read_opencost(url, current), read_opencost(url, previous))
    aws = read_athena(config, current, previous) if config else None
    return render_report(end, cluster, aws, demo=False)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="finops", description="Cost reports and waste estimates")
    commands = parser.add_subparsers(dest="command", required=True)
    report = commands.add_parser("report", help="Compare the last two seven-day windows")
    report.add_argument("--fixtures", type=Path, help="Read local demo data without network calls")
    waste = commands.add_parser("waste", help="Summarize a Cloud Custodian output directory")
    waste.add_argument("--input", type=Path, default=Path("output"), help="Custodian output path")
    cloud = commands.add_parser("cloud-report", help="Compare FOCUS billing exports across providers")
    cloud.add_argument("--input", type=Path, required=True, help="Normalized FOCUS CSV export")
    cloud.add_argument("--as-of", type=date.fromisoformat, default=datetime.now(UTC).date(),
                       help="Exclusive end date, YYYY-MM-DD (default: today UTC)")
    cloud.add_argument("--usd-rates", type=Path,
                       help="JSON currency-to-USD rates; append a normalized comparison")
    for command in (report, waste):
        command.add_argument("--dry-run", action="store_true", help="Print without sending a notification")
    args = parser.parse_args(argv)

    send = args.command in ("report", "waste") and not args.dry_run
    if args.command == "report" and args.fixtures is not None:
        send = False
    report_ready = False
    try:
        if args.command == "report":
            message = _report(args.fixtures)
        elif args.command == "cloud-report":
            message = render_cloud_report(args.input, args.as_of, args.usd_rates)
        else:
            message = render_findings(read_findings(args.input))
        report_ready = True
        print(message)
        if send:
            notify(message)
    except (OSError, ValueError, TypeError, DecimalException, KeyError) as exc:
        print(f"finops: {exc}", file=sys.stderr)
        if send and not report_ready and environ.get("NOTIFY_FAILURES", "").lower() == "true":
            try:
                notify(f"FinOps {args.command} failed. Check the job logs; no report was generated.")
            except (OSError, ValueError):
                print("finops: failure notification could not be delivered", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
