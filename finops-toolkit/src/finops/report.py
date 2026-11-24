from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from importlib.resources import files
from string import Template

ZERO = Decimal(0)
Window = tuple[date, date]
Comparison = tuple[list["Cost"], list["Cost"]]


@dataclass(frozen=True)
class Cost:
    environment: str
    team: str
    amount: Decimal
    service: str = ""

    def __post_init__(self) -> None:
        if not self.amount.is_finite():
            raise ValueError("Cost amount must be finite")


def weekly_windows(end: date) -> tuple[Window, Window]:
    midpoint = end - timedelta(days=7)
    return (midpoint, end), (midpoint - timedelta(days=7), midpoint)


def percent_change(current: Decimal, previous: Decimal) -> str:
    return f"{(current - previous) / previous:+.1%}" if previous > ZERO else "n/a"


def money(amount: Decimal) -> str:
    formatted = f"{abs(amount):,.2f}"
    return f"-${formatted}" if amount < ZERO and formatted != "0.00" else f"${formatted}"


def _totals(rows: list[Cost], field: str) -> dict[str, Decimal]:
    totals: dict[str, Decimal] = defaultdict(Decimal)
    for row in rows:
        totals[getattr(row, field)] += row.amount
    return totals


def _table(comparison: Comparison, field: str, label: str, limit: int | None = None) -> str:
    current, previous = (_totals(rows, field) for rows in comparison)
    keys = sorted(current.keys() | previous.keys())
    if limit is not None:
        keys.sort(
            key=lambda key: (
                max(abs(current.get(key, ZERO)), abs(previous.get(key, ZERO))),
                abs(current.get(key, ZERO)),
            ),
            reverse=True,
        )
    lines = [f"| {label} | Current | Previous | Change |", "| --- | ---: | ---: | ---: |"]
    for key in keys[:limit]:
        this_week, last_week = current.get(key, ZERO), previous.get(key, ZERO)
        name = key.replace("|", "\\|").replace("\n", " ").replace("\r", " ")
        lines.append(
            f"| {name} | {money(this_week)} | {money(last_week)} | "
            f"{percent_change(this_week, last_week)} |"
        )
    return "\n".join(lines)


def _section(title: str, comparison: Comparison) -> str:
    current, previous = (sum((row.amount for row in rows), ZERO) for rows in comparison)
    return "\n\n".join([
        f"## {title}",
        f"Total: {money(current)} vs {money(previous)} ({percent_change(current, previous)})",
        _table(comparison, "environment", "Environment"),
        _table(comparison, "team", "Team"),
    ])


def render_report(end: date, cluster: Comparison, aws: Comparison | None, *, demo: bool) -> str:
    current, previous = weekly_windows(end)
    sections = [_section("OpenCost Kubernetes allocations", cluster)]
    if aws is not None:
        sections.append(_section("AWS CUR unblended costs", aws))
        sections.append(_table(aws, "service", "AWS service (top 10)", limit=10))
        sections.append(
            "AWS CUR and OpenCost can cover the same resources. Compare them separately."
        )
    template = Template(files("finops").joinpath("templates/weekly_report.md").read_text("utf-8"))
    return template.substitute(
        title="Weekly cost report (synthetic demo)" if demo else "Weekly cost report",
        current=f"{current[0]} to {current[1]}",
        previous=f"{previous[0]} to {previous[1]}",
        sections="\n\n".join(sections),
    ).rstrip()
