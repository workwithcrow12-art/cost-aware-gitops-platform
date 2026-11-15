import io
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock, patch

from finops.athena_client import _costs, read_athena
from finops.cli import main
from finops.config import AthenaConfig
from finops.report import Cost


class AthenaCoverageTests(unittest.TestCase):
    def test_cur_rejects_nonfinite_costs_but_retains_credits(self):
        for amount in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(amount=amount), self.assertRaisesRegex(ValueError, "finite"):
                _costs([["current", "prod", "platform", "AmazonEC2", amount, "7"]])
        current, _ = _costs([
            ["current", "prod", "platform", "AmazonEC2", "-10", "7"],
            ["previous", "prod", "platform", "AmazonEC2", "0", "7"],
        ])
        self.assertEqual(current[0].amount, Decimal(-10))

    def test_missing_period_is_not_a_zero_cost_period(self):
        for period in ("current", "previous"):
            with self.subTest(period=period), self.assertRaisesRegex(ValueError, "CUR.*missing"):
                _costs([[period, "prod", "platform", "AmazonEC2", "100", "7"]])

    def test_partial_week_is_rejected(self):
        for period in ("current", "previous"):
            rows = [
                ["current", "prod", "platform", "AmazonEC2", "100", "7"],
                ["previous", "prod", "platform", "AmazonEC2", "120", "7"],
            ]
            rows[0 if period == "current" else 1][-1] = "6"
            with self.subTest(period=period), self.assertRaisesRegex(ValueError, "CUR.*7.*days"):
                _costs(rows)

    def test_explicit_zero_with_full_coverage_is_valid(self):
        self.assertEqual(_costs([
            ["current", "prod", "platform", "AmazonEC2", "0", "7"],
            ["previous", "prod", "platform", "AmazonEC2", "120", "7"],
        ]), (
            [Cost("prod", "platform", Decimal(0), "AmazonEC2")],
            [Cost("prod", "platform", Decimal(120), "AmazonEC2")],
        ))

    def test_empty_query_results_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "CUR.*missing"):
            _costs([])


class AthenaClientTests(unittest.TestCase):
    def setUp(self):
        self.client = Mock()
        self.client.start_query_execution.return_value = {"QueryExecutionId": "query-test"}
        self.client.get_query_execution.return_value = {
            "QueryExecution": {"Status": {"State": "SUCCEEDED"}}
        }
        # Only the AWS transport is replaced; query construction and result parsing are real.
        modules = {
            "boto3": SimpleNamespace(client=lambda *args, **kwargs: self.client),
            "botocore.exceptions": SimpleNamespace(BotoCoreError=OSError, ClientError=RuntimeError),
        }
        self.modules = patch.dict("sys.modules", modules)
        self.modules.start()
        self.addCleanup(self.modules.stop)

    def read(self):
        return read_athena(
            AthenaConfig("ap-southeast-1", "billing", "cur", "finops", "s3://results/"),
            (date(2026, 11, 3), date(2026, 11, 10)),
            (date(2026, 10, 27), date(2026, 11, 3)),
        )

    def test_pagination_keeps_both_periods_and_explicit_zero(self):
        def row(*values):
            return {"Data": [{"VarCharValue": value} for value in values]}

        self.client.get_paginator.return_value.paginate.return_value = [
            {"ResultSet": {"Rows": [
                row("period", "environment", "team", "service", "cost", "usage_days"),
                row("current", "prod", "platform", "AmazonEC2", "0", "7"),
            ]}},
            {"ResultSet": {"Rows": [row("previous", "prod", "platform", "AmazonEC2", "120", "7")]}},
        ]
        self.assertEqual(self.read(), (
            [Cost("prod", "platform", Decimal(0), "AmazonEC2")],
            [Cost("prod", "platform", Decimal(120), "AmazonEC2")],
        ))

    def test_athena_failure_reports_the_reason(self):
        self.client.get_query_execution.return_value = {
            "QueryExecution": {"Status": {"State": "FAILED", "StateChangeReason": "Access denied"}}
        }
        with self.assertRaisesRegex(ValueError, "query-test FAILED: Access denied"):
            self.read()

    def test_cli_does_not_print_or_notify_when_cur_is_missing(self):
        self.client.get_paginator.return_value.paginate.return_value = [
            {"ResultSet": {"Rows": []}}
        ]
        environment = {
            "OPENCOST_URL": "http://opencost.invalid", "AWS_REGION": "ap-southeast-1",
            "ATHENA_DATABASE": "billing", "ATHENA_TABLE": "cur", "ATHENA_WORKGROUP": "finops",
            "ATHENA_OUTPUT_S3": "s3://results/",
        }
        output, errors = io.StringIO(), io.StringIO()
        with patch.dict("os.environ", environment), patch(
            "finops.cli.read_opencost", return_value=[Cost("prod", "platform", Decimal(100))]
        ), patch("finops.cli.notify") as notify, redirect_stdout(output), redirect_stderr(errors):
            self.assertEqual(main(["report"]), 1)
        self.assertEqual(output.getvalue(), "")
        self.assertIn("CUR data missing", errors.getvalue())
        notify.assert_not_called()
