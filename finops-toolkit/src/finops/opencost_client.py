import json
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from http.client import HTTPException
from typing import Any
from urllib.error import URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import urlopen

from finops.report import Cost, Window


def _bucket(label: str) -> str:
    stripped = label.strip()
    return "unallocated" if stripped in {"", "__unallocated__"} else stripped


def _extract_labels(name: str, allocation: dict[str, Any]) -> tuple[str, str]:
    if name == "__idle__" or "__idle__" in name.split("/"):
        return "idle", "idle"
    props = allocation.get("properties")
    if isinstance(props, dict) and isinstance(props.get("labels"), dict):
        labels = props["labels"]
        env_v, team_v = labels.get("env", ""), labels.get("team", "")
        return (
            _bucket(env_v if isinstance(env_v, str) else ""),
            _bucket(team_v if isinstance(team_v, str) else ""),
        )
    parts = name.split("/", 2)
    if len(parts) == 3:
        return _bucket(parts[1]), _bucket(parts[2])
    return "unallocated", "unallocated"


def parse_allocations(payload: dict[str, Any]) -> list[Cost]:
    if (
        not isinstance(payload, dict)
        or payload.get("code") != 200
        or not isinstance(payload.get("data"), list)
    ):
        raise ValueError("OpenCost returned an invalid allocation response")
    rows = []
    for allocation_set in payload["data"]:
        if not isinstance(allocation_set, dict):
            raise TypeError("OpenCost returned an invalid allocation set")
        for name, allocation in allocation_set.items():
            if not isinstance(name, str) or not isinstance(allocation, dict):
                raise TypeError("OpenCost returned an invalid allocation")
            raw_cost = allocation.get("totalCost")
            if raw_cost is None or isinstance(raw_cost, bool) or not isinstance(
                raw_cost, (int, float, Decimal, str)
            ):
                raise ValueError("OpenCost allocation totalCost must be a finite number")
            try:
                amount = Decimal(str(raw_cost))
            except InvalidOperation as exc:
                raise ValueError("OpenCost allocation totalCost must be a finite number") from exc
            environment, team = _extract_labels(name, allocation)
            rows.append(Cost(environment, team, amount))
    return rows


def _validate_windows(data: list[dict[str, Any]], start: date, end: date) -> None:
    seen_days: set[date] = set()
    for allocation_set in data:
        set_day: date | None = None
        for allocation in allocation_set.values():
            if "window" not in allocation:
                continue
            win = allocation["window"]
            if not isinstance(win, dict) or not isinstance(win.get("start"), str) or not isinstance(
                win.get("end"), str
            ):
                raise ValueError(f"OpenCost daily window metadata is invalid for {start} to {end}")
            ws, we = datetime.fromisoformat(win["start"]), datetime.fromisoformat(win["end"])
            if (
                ws.utcoffset() != timedelta(0)
                or we.utcoffset() != timedelta(0)
                or we - ws != timedelta(days=1)
                or not (start <= ws.date() < end)
                or (set_day is not None and set_day != ws.date())
            ):
                raise ValueError(f"OpenCost daily window does not match {start} to {end} UTC")
            set_day = ws.date()
        if set_day is not None:
            if set_day in seen_days:
                raise ValueError(f"OpenCost daily buckets duplicate {set_day} in {start} to {end}")
            seen_days.add(set_day)


def read_opencost(url: str, window: Window) -> list[Cost]:
    start, end = window
    if end <= start:
        raise ValueError("OpenCost window end date must be after start date")
    cleaned = url.strip()
    parsed = urlsplit(cleaned)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.query
        or parsed.fragment
        or any(ch.isspace() for ch in cleaned)
    ):
        raise ValueError("OPENCOST_URL must be an http:// or https:// base URL")
    params = urlencode({
        "window": f"{start}T00:00:00Z,{end}T00:00:00Z",
        "aggregate": "namespace,label:env,label:team",
        "step": "1d",
        "accumulate": "false",
        "includeIdle": "true",
        "shareIdle": "false",
    })
    try:
        with urlopen(f"{cleaned.rstrip('/')}/allocation?{params}", timeout=90) as res:  # noqa: S310
            payload = json.load(res, parse_float=Decimal)
    except (URLError, OSError, HTTPException) as exc:
        raise ValueError("OpenCost allocation API request failed") from exc
    allocations = parse_allocations(payload)
    if not allocations:
        raise ValueError(f"OpenCost returned no allocations for {start} to {end} UTC")
    if len(payload["data"]) != (end - start).days or not all(payload["data"]):
        raise ValueError(f"OpenCost daily data is incomplete for {start} to {end} UTC")
    _validate_windows(payload["data"], start, end)
    return allocations
