import csv
import re
from collections.abc import Iterable
from decimal import Decimal
from importlib.resources import files
from pathlib import Path
from string import Template
from time import monotonic, sleep

from finops.config import AthenaConfig
from finops.report import Comparison, Cost, Window


def _costs(rows: Iterable[Iterable[str]]) -> Comparison:
    periods: dict[str, list[Cost]] = {"current": [], "previous": []}
    for period, environment, team, service, amount, usage_days in rows:
        if int(usage_days) != 7:
            raise ValueError(f"CUR {period} period must contain 7 usage days; found {usage_days}")
        periods[period].append(Cost(environment, team, Decimal(amount), service))
    for period, costs in periods.items():
        if not costs:
            raise ValueError(f"CUR data missing for {period} period; wait for billing data to arrive")
    return periods["current"], periods["previous"]


def read_cur_fixture(path: Path) -> Comparison:
    with path.open(encoding="utf-8", newline="") as source:
        rows = csv.reader(source)
        next(rows)
        return _costs(rows)


def read_athena(config: AthenaConfig, current: Window, previous: Window) -> Comparison:
    if not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]*", config.table):
        raise ValueError("ATHENA_TABLE must be a simple Athena table name")
    try:
        import boto3
        from botocore.exceptions import BotoCoreError, ClientError
    except ImportError as exc:
        raise ValueError("Install the finops-toolkit[aws] extra to query Athena") from exc

    template = Template(files("finops").joinpath("sql/cost_breakdown.sql").read_text("utf-8"))
    query = template.substitute(
        table=config.table, start=previous[0], midpoint=current[0], end=current[1]
    )
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
            status = client.get_query_execution(QueryExecutionId=execution)["QueryExecution"]["Status"]
            if status["State"] == "SUCCEEDED":
                break
            if status["State"] in {"FAILED", "CANCELLED"}:
                raise ValueError(f"Athena query {execution} {status['State']}: "
                                 f"{status.get('StateChangeReason', 'No reason given')}")
            sleep(2)
        else:
            client.stop_query_execution(QueryExecutionId=execution)
            raise ValueError(f"Athena query {execution} exceeded 120 seconds")

        pages = client.get_paginator("get_query_results").paginate(QueryExecutionId=execution)
        rows = (row for page in pages for row in page["ResultSet"]["Rows"])
        next(rows, None)
        return _costs([field.get("VarCharValue", "") for field in row["Data"]] for row in rows)
    except (BotoCoreError, ClientError) as exc:
        raise ValueError(f"Athena request failed: {exc}") from exc
