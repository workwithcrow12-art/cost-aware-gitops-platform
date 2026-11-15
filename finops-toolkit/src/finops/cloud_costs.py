import csv
import json
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, DecimalException
from pathlib import Path

from finops.report import percent_change, weekly_windows


@dataclass(frozen=True)
class CloudCost:
    provider: str
    currency: str
    environment: str
    team: str
    amount: Decimal


def read_focus(path: Path, end: date) -> tuple[list[CloudCost], list[CloudCost]]:
    current, previous = weekly_windows(end)
    periods: tuple[list[CloudCost], list[CloudCost]] = ([], [])
    coverage: dict[str, set[date]] = defaultdict(set)
    required = {"ProviderName", "BillingCurrency", "BilledCost", "ChargePeriodStart",
                "ChargePeriodEnd", "Tags"}
    with path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        if len(reader.fieldnames or []) != len(set(reader.fieldnames or [])):
            raise ValueError("FOCUS CSV contains duplicate column headers")
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"FOCUS CSV missing columns: {', '.join(sorted(missing))}")
        for number, row in enumerate(reader, 2):
            try:
                if None in row or any(value is None for value in row.values()):
                    raise ValueError("column count does not match header")
                start, stop = (datetime.fromisoformat(row[key]) for key in
                               ("ChargePeriodStart", "ChargePeriodEnd"))
                if start.utcoffset() != timedelta(0) or stop.utcoffset() != timedelta(0):
                    raise ValueError("charge timestamps must include the UTC timezone")
                # Do not silently assign monthly purchases or cross-day charges to one usage day.
                if stop <= start or stop > datetime.combine(
                    start.date() + timedelta(days=1), datetime.min.time(), UTC
                ):
                    raise ValueError("normalize charges to hourly/daily UTC intervals first")
                if not previous[0] <= start.date() < end:
                    continue
                provider, currency = row["ProviderName"].strip(), row["BillingCurrency"].strip()
                amount = Decimal(row["BilledCost"])
                if not provider or not re.fullmatch("[A-Z]{3}", currency):
                    raise ValueError("provider and three-letter billing currency are required")
                if not amount.is_finite():
                    raise ValueError("BilledCost must be finite")
                tags = json.loads(row["Tags"] or "null")
                if tags is None:
                    tags = {}
                if not isinstance(tags, dict) or any(
                    not isinstance(value, str) for value in tags.values()
                ):
                    raise ValueError("Tags must be a JSON object of string values or null")
                cost = CloudCost(provider, currency, tags.get("env", "").strip() or "unallocated",
                                 tags.get("team", "").strip() or "unallocated", amount)
                periods[0 if start.date() >= current[0] else 1].append(cost)
                coverage[provider].add(start.date())
            except (ValueError, TypeError, DecimalException) as exc:
                raise ValueError(f"FOCUS CSV row {number}: {exc}") from exc
    if not coverage:
        raise ValueError("FOCUS CSV contains no charges in the comparison windows")
    for provider, days in coverage.items():
        if len(days) != 14:
            raise ValueError(f"FOCUS daily coverage for {provider}: expected 14 days, found {len(days)}")
    return periods


def _table(periods: tuple[list[CloudCost], list[CloudCost]], field: str, currency: str) -> str:
    totals = []
    for rows in periods:
        groups: dict[str, Decimal] = defaultdict(Decimal)
        for row in rows:
            groups[getattr(row, field)] += row.amount
        totals.append(groups)
    current, previous = totals
    lines = [f"| {field.title()} | Current | Previous | Change |",
             "| --- | ---: | ---: | ---: |"]
    for key in sorted(current.keys() | previous.keys()):
        now, before = current[key], previous[key]
        label = key.replace("|", "\\|").replace("\n", " ").replace("\r", " ")
        lines.append(f"| {label} | {now:,.2f} {currency} | {before:,.2f} {currency} | "
                     f"{percent_change(now, before)} |")
    return "\n".join(lines)


def _read_usd_rates(path: Path) -> dict[str, Decimal]:
    def unique_keys(pairs):
        rates = {}
        for currency, rate in pairs:
            if currency in rates:
                raise ValueError(f"USD rates contain duplicate currency: {currency}")
            rates[currency] = rate
        return rates

    rates = json.loads(path.read_text(encoding="utf-8-sig"), parse_float=Decimal,
                       parse_int=Decimal, parse_constant=Decimal, object_pairs_hook=unique_keys)
    if not isinstance(rates, dict):
        raise TypeError("USD rates must be a JSON object of currency codes and numeric rates")
    for currency, rate in rates.items():
        if not re.fullmatch("[A-Z]{3}", currency):
            raise ValueError(f"USD rates require three-letter uppercase currency codes: {currency}")
        if not isinstance(rate, Decimal) or not rate.is_finite() or rate <= 0:
            raise ValueError(f"USD rate for {currency} must be a positive finite number")
        if currency == "USD" and rate != 1:
            raise ValueError("USD rate must equal 1")
    return {"USD": Decimal(1), **rates}


def render_cloud_report(path: Path, end: date, usd_rates: Path | None = None) -> str:
    periods = read_focus(path, end)
    current, previous = weekly_windows(end)
    sections = ["# Multi-cloud billed cost report",
                f"Current: {current[0]} to {current[1]} UTC (end exclusive)",
                f"Previous: {previous[0]} to {previous[1]} UTC (end exclusive)"]
    currencies = sorted({row.currency for rows in periods for row in rows})
    for currency in currencies:
        rows = tuple([row for row in period if row.currency == currency] for period in periods)
        now, before = (sum((row.amount for row in period), Decimal(0)) for period in rows)
        sections.extend([f"## Billed costs ({currency})",
                         (f"Total: {now:,.2f} {currency} vs {before:,.2f} {currency} "
                          f"({percent_change(now, before)})")])
        for field in ("provider", "environment", "team"):
            sections.append(_table(rows, field, currency))
    if usd_rates is not None:
        rates = _read_usd_rates(usd_rates)
        missing = set(currencies) - rates.keys()
        if missing:
            raise ValueError(f"Missing USD rates for: {', '.join(sorted(missing))}")
        normalized = tuple([
            CloudCost(row.provider, "USD", row.environment, row.team,
                      row.amount * rates[row.currency]) for row in period
        ] for period in periods)
        now, before = (sum((row.amount for row in period), Decimal(0)) for period in normalized)
        sections.extend(["## Normalized costs (USD)",
                         ("Uses one user-supplied rate table for both periods, in USD per unit of "
                          "source currency. These are not authoritative invoice amounts."),
                         (f"Total: {now:,.2f} USD vs {before:,.2f} USD "
                          f"({percent_change(now, before)})")])
        for field in ("provider", "environment", "team"):
            sections.append(_table(normalized, field, "USD"))
    sections.append(("Currencies are kept separate; no exchange rates are assumed. "
                     if usd_rates is None else "Original billed costs remain separate by currency. ") +
                    "These billed costs may overlap OpenCost allocations; do not add them together. "
                    "Daily presence does not prove invoice completeness. "
                    "Only providers present in the export are checked.")
    return "\n\n".join(sections)
