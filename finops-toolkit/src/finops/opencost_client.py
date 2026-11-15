import json
from decimal import Decimal
from typing import Any
from urllib.parse import urlencode
from urllib.request import urlopen

from finops.report import Cost, Window


def parse_allocations(payload: dict[str, Any]) -> list[Cost]:
    if (not isinstance(payload, dict) or payload.get("code") != 200
            or not isinstance(payload.get("data"), list)):
        raise ValueError("OpenCost returned an invalid allocation response")
    rows = []
    for allocation_set in payload["data"]:
        if not isinstance(allocation_set, dict):
            raise ValueError("OpenCost returned an invalid allocation set")
        for name, allocation in allocation_set.items():
            if not isinstance(name, str) or not isinstance(allocation, dict):
                raise ValueError("OpenCost returned an invalid allocation")
            parts = name.split("/")
            if "__idle__" in parts:
                environment = team = "idle"
            elif len(parts) == 3:
                # OpenCost joins aggregation values in the requested order.
                environment, team = map(_bucket, parts[1:])
            else:
                environment = team = "unallocated"
            rows.append(Cost(environment, team, Decimal(str(allocation["totalCost"]))))
    return rows


def _bucket(label: str) -> str:
    return "unallocated" if label in {"", "__unallocated__"} else label


def read_opencost(url: str, window: Window) -> list[Cost]:
    start, end = window
    params = urlencode({
        "window": f"{start}T00:00:00Z,{end}T00:00:00Z",
        "aggregate": "namespace,label:env,label:team",
        "step": "1d",
        "accumulate": "false",
        "includeIdle": "true",
        "shareIdle": "false",
    })
    with urlopen(f"{url.rstrip('/')}/allocation?{params}", timeout=90) as response:
        payload = json.load(response, parse_float=Decimal)
    allocations = parse_allocations(payload)
    if not allocations:
        raise ValueError(f"OpenCost returned no allocations for {start} to {end} UTC")
    if len(payload["data"]) != (end - start).days or not all(payload["data"]):
        raise ValueError(f"OpenCost daily data is incomplete for {start} to {end} UTC")
    return allocations
