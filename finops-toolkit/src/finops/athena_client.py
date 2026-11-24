import contextlib
import csv
import re
from collections.abc import Iterable
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from importlib.resources import files
from pathlib import Path
from string import Template
from time import monotonic, sleep

from finops.config import AthenaConfig
from finops.report import Comparison, Cost, Window

_IDENTIFIER = re.compile(r"[a-zA-Z_][a-zA-Z0-9_]*")


def _costs(rows: Iterable[Iterable[str]]) -> Comparison:
    periods: dict[str, list[Cost]] = {"current": [], "previous": []}
    for raw_row in rows:
        row = list(raw_row)
        if len(row) != 6:
            raise ValueError(f"CUR row must contain 6 columns; found {len(row)}")
        period, env, team, service, amount, usage_days = row
        if period not in periods:
            raise ValueError(f"Unexpected CUR period: {period!r}")
        try:
            days = int(usage_days)
        except ValueError as exc:
            raise ValueError(f"CUR usage_days must be an integer; found {usage_days!r}") from exc
        if days != 7:
            raise ValueError(f"CUR {period} period must contain 7 usage days; found {usage_days}")
        try:
            parsed = Decimal(amount)
        except InvalidOperation as exc:
            raise ValueError("CUR cost amount must be finite") from exc
        periods[period].append(
            Cost(
                env.strip() or "unallocated",
                team.strip() or "unallocated",
                parsed,
                service.strip() or "unallocated",
            )
        )
    for period, costs in periods.items():
        if not costs:
            raise ValueError(
                f"CUR data missing for {period} period; wait for billing data to arrive"
            )
    return periods["current"], periods["previous"]


def read_cur_fixture(path: Path) -> Comparison:
    with path.open(encoding="utf-8", newline="") as source:
        rows = csv.reader(source)
        next(rows, None)
        return _costs(rows)


def _tag_expr(column: str | None) -> str:
    if column is None:
        return "'unallocated'"
    if not _IDENTIFIER.fullmatch(column):
        raise ValueError(f"Invalid Athena tag column identifier: {column!r}")
    return f"COALESCE(NULLIF(TRIM(\"{column}\"), ''), 'unallocated')"


def _partition_predicate(start: date, end: date) -> str:
    days = [start + timedelta(days=i) for i in range((end - start).days)]
    months = list(dict.fromkeys((d.year, d.month) for d in days))
    clauses = [
        f"(year = '{y}' AND month IN ('{m}', '{m:02d}'))"
        if m < 10
        else f"(year = '{y}' AND month IN ('{m}'))"
        for y, m in months
    ]
    return f"({' OR '.join(clauses)}) AND"


def read_athena(config: AthenaConfig, current: Window, previous: Window) -> Comparison:
    if not _IDENTIFIER.fullmatch(config.table):
        raise ValueError("ATHENA_TABLE must be a simple Athena table name")
    if not _IDENTIFIER.fullmatch(config.database):
        raise ValueError("ATHENA_DATABASE must be a simple Athena database name")
    template = Template(files("finops").joinpath("sql/cost_breakdown.sql").read_text("utf-8"))
    partition_sql = _partition_predicate(previous[0], current[1]) if config.partitioned else ""
    query = template.substitute(
        table=config.table,
        start=previous[0],
        midpoint=current[0],
        end=current[1],
        env_expr=_tag_expr(config.env_tag_column),
        team_expr=_tag_expr(config.team_tag_column),
        partition_filter=partition_sql,
    )
    try:
        import boto3
        from botocore.exceptions import BotoCoreError, ClientError
    except ImportError as exc:
        raise ValueError("Install the finops-toolkit[aws] extra to query Athena") from exc

    try:
        client = boto3.client("athena", region_name=config.region)
        execution = client.start_query_execution(
            QueryString=query,
            QueryExecutionContext={"Database": config.database},
            WorkGroup=config.workgroup,
            ResultConfiguration={"OutputLocation": config.output_s3},
        )["QueryExecutionId"]
        deadline = monotonic() + 120
        while monotonic() < deadline:
            exec_resp = client.get_query_execution(QueryExecutionId=execution)
            status = exec_resp["QueryExecution"]["Status"]
            if status["State"] == "SUCCEEDED":
                break
            if status["State"] in {"FAILED", "CANCELLED"}:
                reason = status.get("StateChangeReason", "No reason given")
                hint = (
                    " (activate user cost allocation tags in AWS Billing or set "
                    "ATHENA_ENV_TAG_COLUMN=none / ATHENA_TEAM_TAG_COLUMN=none)"
                    if "COLUMN_NOT_FOUND" in reason and "resource_tags_user_" in reason
                    else ""
                )
                raise ValueError(f"Athena query {execution} {status['State']}: {reason}{hint}")
            sleep(2)
        else:
            with contextlib.suppress(BotoCoreError, ClientError):
                client.stop_query_execution(QueryExecutionId=execution)
            raise ValueError(f"Athena query {execution} exceeded 120 seconds")

        pages = client.get_paginator("get_query_results").paginate(QueryExecutionId=execution)
        rows = (row for page in pages for row in page["ResultSet"]["Rows"])
        next(rows, None)
        return _costs([field.get("VarCharValue", "") for field in row["Data"]] for row in rows)
    except (BotoCoreError, ClientError) as exc:
        raise ValueError(f"Athena request failed: {exc}") from exc
