import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from finops.athena_client import _costs, read_athena, read_cur_fixture
from finops.cli import main
from finops.config import AthenaConfig
from finops.report import Cost


class AthenaCoverageTests(unittest.TestCase):
    def test_cur_rejects_nonfinite_or_empty_costs_but_retains_credits(self) -> None:
        for amount in ("NaN", "Infinity", "-Infinity", "", "abc"):
            with self.subTest(amount=amount), self.assertRaisesRegex(ValueError, "finite"):
                _costs([["current", "prod", "platform", "AmazonEC2", amount, "7"]])
        current, _ = _costs([
            ["current", "  ", "platform", "AmazonEC2", "-10", "7"],
            ["previous", "prod", "  ", "  ", "0", "7"],
        ])
        self.assertEqual(current[0], Cost("unallocated", "platform", Decimal(-10), "AmazonEC2"))

    def test_cur_rejects_malformed_rows_and_periods(self) -> None:
        with self.assertRaisesRegex(ValueError, "6 columns"):
            _costs([["current", "prod", "platform"]])
        with self.assertRaisesRegex(ValueError, "Unexpected CUR period"):
            _costs([["other", "prod", "platform", "AmazonEC2", "10", "7"]])
        with self.assertRaisesRegex(ValueError, "integer"):
            _costs([["current", "prod", "platform", "AmazonEC2", "10", "seven"]])

    def test_empty_cur_fixture_raises_value_error_not_stop_iteration(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            empty = Path(tmp) / "empty.csv"
            empty.write_text("", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "CUR data missing"):
                read_cur_fixture(empty)

    def test_missing_period_is_not_a_zero_cost_period(self) -> None:
        for period in ("current", "previous"):
            with self.subTest(period=period), self.assertRaisesRegex(ValueError, "CUR.*missing"):
                _costs([[period, "prod", "platform", "AmazonEC2", "100", "7"]])

    def test_partial_week_is_rejected(self) -> None:
        for period in ("current", "previous"):
            rows = [
                ["current", "prod", "platform", "AmazonEC2", "100", "7"],
                ["previous", "prod", "platform", "AmazonEC2", "120", "7"],
            ]
            rows[0 if period == "current" else 1][-1] = "6"
            with self.subTest(period=period), self.assertRaisesRegex(ValueError, "CUR.*7.*days"):
                _costs(rows)

    def test_explicit_zero_with_full_coverage_is_valid(self) -> None:
        self.assertEqual(
            _costs([
                ["current", "prod", "platform", "AmazonEC2", "0", "7"],
                ["previous", "prod", "platform", "AmazonEC2", "120", "7"],
            ]),
            (
                [Cost("prod", "platform", Decimal(0), "AmazonEC2")],
                [Cost("prod", "platform", Decimal(120), "AmazonEC2")],
            ),
        )

    def test_empty_query_results_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "CUR.*missing"):
            _costs([])


class AthenaClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = Mock()
        self.client.start_query_execution.return_value = {"QueryExecutionId": "query-test"}
        self.client.get_query_execution.return_value = {
            "QueryExecution": {"Status": {"State": "SUCCEEDED"}}
        }
        modules = {
            "boto3": SimpleNamespace(client=lambda *args, **kwargs: self.client),
            "botocore.exceptions": SimpleNamespace(BotoCoreError=OSError, ClientError=RuntimeError),
        }
        self.modules = patch.dict("sys.modules", modules)
        self.modules.start()
        self.addCleanup(self.modules.stop)

    def read(self, config: AthenaConfig | None = None):
        cfg = config or AthenaConfig("ap-southeast-1", "billing", "cur", "finops", "s3://results/")
        return read_athena(
            cfg,
            (date(2026, 11, 3), date(2026, 11, 10)),
            (date(2026, 10, 27), date(2026, 11, 3)),
        )

    def test_pagination_prunes_partitions_and_filters_usage_types(self) -> None:
        def row(*values: str):
            return {"Data": [{"VarCharValue": value} for value in values]}

        self.client.get_paginator.return_value.paginate.return_value = [
            {
                "ResultSet": {
                    "Rows": [
                        row("period", "environment", "team", "service", "cost", "usage_days"),
                        row("current", "prod", "platform", "AmazonEC2", "0", "7"),
                    ]
                }
            },
            {"ResultSet": {"Rows": [row("previous", "prod", "platform", "AmazonEC2", "120", "7")]}},
        ]
        self.assertEqual(
            self.read(),
            (
                [Cost("prod", "platform", Decimal(0), "AmazonEC2")],
                [Cost("prod", "platform", Decimal(120), "AmazonEC2")],
            ),
        )
        sql = self.client.start_query_execution.call_args.kwargs["QueryString"]
        self.assertIn("(year = '2026' AND month IN ('10'))", sql)
        self.assertIn("(year = '2026' AND month IN ('11'))", sql)
        self.assertIn("SavingsPlanCoveredUsage", sql)

    def test_rejects_invalid_table_and_missing_boto3(self) -> None:
        bad = AthenaConfig("ap-southeast-1", "billing", "cur;DROP", "finops", "s3://results/")
        with self.assertRaisesRegex(ValueError, "ATHENA_TABLE"):
            self.read(bad)
        with patch.dict("sys.modules", {"boto3": None}):
            with self.assertRaisesRegex(ValueError, "finops-toolkit\\[aws\\]"):
                self.read()

    def test_athena_failure_cancelled_timeout_and_transport_errors(self) -> None:
        self.client.get_query_execution.return_value = {
            "QueryExecution": {
                "Status": {
                    "State": "FAILED",
                    "StateChangeReason": "COLUMN_NOT_FOUND: resource_tags_user_env",
                }
            }
        }
        with self.assertRaisesRegex(ValueError, "ATHENA_ENV_TAG_COLUMN=none"):
            self.read()

        self.client.get_query_execution.return_value = {
            "QueryExecution": {"Status": {"State": "CANCELLED"}}
        }
        with self.assertRaisesRegex(ValueError, "query-test CANCELLED: No reason given"):
            self.read()

        self.client.get_query_execution.return_value = {
            "QueryExecution": {"Status": {"State": "RUNNING"}}
        }
        self.client.stop_query_execution.side_effect = RuntimeError("already finished")
        with (
            patch("finops.athena_client.monotonic", side_effect=[0, 0, 121]),
            patch("finops.athena_client.sleep"),
        ):
            with self.assertRaisesRegex(ValueError, "exceeded 120 seconds"):
                self.read()
        self.client.stop_query_execution.assert_called_once_with(QueryExecutionId="query-test")

        self.client.start_query_execution.side_effect = RuntimeError("throttled")
        with self.assertRaisesRegex(ValueError, "Athena request failed: throttled"):
            self.read()

    def test_cli_does_not_print_or_notify_when_cur_is_missing(self) -> None:
        self.client.get_paginator.return_value.paginate.return_value = [{"ResultSet": {"Rows": []}}]
        environment = {
            "OPENCOST_URL": "http://opencost.invalid",
            "AWS_REGION": "ap-southeast-1",
            "ATHENA_DATABASE": "billing",
            "ATHENA_TABLE": "cur",
            "ATHENA_WORKGROUP": "finops",
            "ATHENA_OUTPUT_S3": "s3://results/",
        }
        output, errors = io.StringIO(), io.StringIO()
        with (
            patch.dict("os.environ", environment),
            patch(
                "finops.cli.read_opencost",
                return_value=[Cost("prod", "platform", Decimal(100))],
            ),
            patch("finops.cli.notify") as notify,
            redirect_stdout(output),
            redirect_stderr(errors),
        ):
            self.assertEqual(main(["report"]), 1)
        self.assertEqual(output.getvalue(), "")
        self.assertIn("CUR data missing", errors.getvalue())
        notify.assert_not_called()
