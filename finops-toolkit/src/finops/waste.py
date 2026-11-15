import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from os import environ
from pathlib import Path

from finops.report import money

# Illustrative US East rates and a 730-hour month. This is a triage estimate.
RATES = {
    "unattached-ebs": ("Size", "EBS_GB_MONTH_RATE", "0.08", 1),
    "unused-eip": (None, "EIP_HOURLY_RATE", "0.005", 730),
    "old-snapshots": ("VolumeSize", "SNAPSHOT_GB_MONTH_RATE", "0.05", 1),
    "idle-load-balancer": (None, "ALB_HOURLY_RATE", "0.0225", 730),
}


@dataclass(frozen=True)
class Finding:
    policy: str
    count: int
    monthly: Decimal


def read_findings(directory: Path) -> list[Finding]:
    findings = []
    for policy, (size_key, variable, default, hours) in RATES.items():
        try:
            rate = Decimal(environ.get(variable, "").strip() or default)
        except InvalidOperation as exc:
            raise ValueError(f"{variable} must be a finite nonnegative USD rate") from exc
        if not rate.is_finite() or rate < 0:
            raise ValueError(f"{variable} must be a finite nonnegative USD rate")
        path = directory / policy / "resources.json"
        if not path.is_file():
            raise ValueError(f"Missing Custodian result: {path}")
        resources = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(resources, list):
            raise TypeError(f"Expected a list of Custodian resources in {path}")
        units = len(resources) if size_key is None else sum(item[size_key] for item in resources)
        findings.append(Finding(policy, len(resources), rate * hours * units))
    return findings


def render_findings(findings: list[Finding]) -> str:
    monthly = sum((item.monthly for item in findings), Decimal(0))
    count = sum(item.count for item in findings)
    lines = ["# Cloud waste candidates", "", f"{count} candidates, {money(monthly)}/month estimate", ""]
    lines.extend(f"- {item.policy}: {item.count} ({money(item.monthly)}/month)" for item in findings)
    lines.extend(["", ("Configured rates or illustrative US East defaults; 730-hour month. "
                       "Verify usage, ownership, and pricing before taking action.")])
    return "\n".join(lines)
