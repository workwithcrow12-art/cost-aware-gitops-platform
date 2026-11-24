import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from os import environ
from pathlib import Path
from typing import Any

from finops.report import money

_BYTES_PER_GIB = Decimal(1024**3)
RATES: dict[str, tuple[str | None, str, str, int]] = {
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


def _numeric_field(item: dict[str, Any], key: str, path: Path) -> Decimal:
    raw = item.get(key)
    if isinstance(raw, bool) or not isinstance(raw, (int, Decimal)):
        raise ValueError(f"Expected numeric {key} in {path}")
    value = Decimal(raw)
    if not value.is_finite() or value < 0:
        raise ValueError(f"{key} must be a finite nonnegative number in {path}")
    return value


def _units(policy: str, item: Any, size_key: str | None, path: Path) -> Decimal:
    if not isinstance(item, dict):
        raise TypeError(f"Expected JSON resource objects in {path}")
    if size_key is None:
        return Decimal(1)
    if policy == "old-snapshots" and "FullSnapshotSizeInBytes" in item:
        return _numeric_field(item, "FullSnapshotSizeInBytes", path) / _BYTES_PER_GIB
    return _numeric_field(item, size_key, path)


def read_findings(
    directory: Path,
    policies: dict[str, tuple[str | None, str, str, int]] | None = None,
) -> list[Finding]:
    findings = []
    for policy, (size_key, variable, default, hours) in (policies or RATES).items():
        try:
            rate = Decimal(environ.get(variable, "").strip() or default)
        except InvalidOperation as exc:
            raise ValueError(f"{variable} must be a finite nonnegative USD rate") from exc
        if not rate.is_finite() or rate < 0:
            raise ValueError(f"{variable} must be a finite nonnegative USD rate")
        path = directory / policy / "resources.json"
        if not path.is_file():
            raise ValueError(f"Missing Custodian result: {path}")
        resources = json.loads(path.read_text(encoding="utf-8"), parse_float=Decimal)
        if not isinstance(resources, list):
            raise TypeError(f"Expected a list of Custodian resources in {path}")
        units = sum((_units(policy, item, size_key, path) for item in resources), Decimal(0))
        findings.append(Finding(policy, len(resources), rate * hours * units))
    return findings


def render_findings(findings: list[Finding]) -> str:
    monthly = sum((item.monthly for item in findings), Decimal(0))
    count = sum(item.count for item in findings)
    lines = [
        "# Cloud waste candidates",
        "",
        f"{count} candidates, {money(monthly)}/month estimate",
        "",
    ]
    lines.extend(
        f"- {item.policy}: {item.count} ({money(item.monthly)}/month)" for item in findings
    )
    lines.extend([
        "",
        "Configured rates or illustrative US East defaults; 730-hour month; "
        "snapshots without FullSnapshotSizeInBytes use full VolumeSize as an upper bound. "
        "Verify usage, ownership, and pricing before taking action.",
    ])
    return "\n".join(lines)
