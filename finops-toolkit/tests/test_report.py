import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from finops.cli import main
from finops.opencost_client import parse_allocations, read_opencost
from finops.report import Cost, percent_change, weekly_windows


class ReportTests(unittest.TestCase):
    def test_allocations_reject_nonfinite_costs(self):
        for amount in ("NaN", "Infinity", "-Infinity"):
            payload = {"code": 200, "data": [{"shop/dev/store": {"totalCost": amount}}]}
            with self.subTest(amount=amount), self.assertRaisesRegex(ValueError, "finite"):
                parse_allocations(payload)

    def test_malformed_allocation_sets_fail_with_a_validation_error(self):
        for payload in (None, [], {"code": 200, "data": [None]},
                        {"code": 200, "data": [{"shop/dev/store": None}]}):
            with self.subTest(payload=payload), self.assertRaises((ValueError, TypeError)):
                parse_allocations(payload)

    def test_windows_use_the_last_fourteen_completed_utc_days(self):
        self.assertEqual(
            weekly_windows(date(2026, 1, 5)),
            (
                (date(2025, 12, 29), date(2026, 1, 5)),
                (date(2025, 12, 22), date(2025, 12, 29)),
            ),
        )

    def test_missing_baseline_and_fractional_change(self):
        self.assertEqual(percent_change(Decimal(10), Decimal(0)), "n/a")
        self.assertEqual(percent_change(Decimal(10), Decimal(12)), "-16.7%")

    def test_allocation_preserves_unallocated_and_idle_costs(self):
        payload = {"code": 200, "data": [{
            "shop/dev/store": {"totalCost": 1.125},
            "shop/__unallocated__/store": {"totalCost": 2},
            "__idle__": {"totalCost": 3},
        }]}
        self.assertEqual(parse_allocations(payload), [
            Cost("dev", "store", Decimal("1.125")),
            Cost("unallocated", "store", Decimal(2)),
            Cost("idle", "idle", Decimal(3)),
        ])

    def test_live_allocation_rejects_empty_window(self):
        window = (date(2025, 12, 22), date(2025, 12, 29))
        for body in (b'{"code": 200, "data": []}', b'{"code": 200, "data": [{}]}'):
            with self.subTest(body=body), patch(
                "finops.opencost_client.urlopen", return_value=io.BytesIO(body)
            ), self.assertRaisesRegex(ValueError, "2025-12-22 to 2025-12-29"):
                read_opencost("http://opencost:9003", window)

    def test_live_allocation_accepts_zero_cost(self):
        window = (date(2025, 12, 22), date(2025, 12, 29))
        body = json.dumps({"code": 200, "data": [
            {"shop/dev/store": {"totalCost": 0}} for _ in range(7)
        ]}).encode()
        with patch("finops.opencost_client.urlopen", return_value=io.BytesIO(body)):
            self.assertEqual(
                read_opencost("http://opencost:9003", window),
                [Cost("dev", "store", Decimal(0))] * 7,
            )

    def test_live_allocation_rejects_missing_daily_data(self):
        window = (date(2025, 12, 22), date(2025, 12, 29))
        day = {"shop/dev/store": {"totalCost": 1}}
        for days in ([day] * 6, [day] * 3 + [{}] + [day] * 3):
            body = json.dumps({"code": 200, "data": days}).encode()
            with self.subTest(days=days), patch(
                "finops.opencost_client.urlopen", return_value=io.BytesIO(body)
            ), self.assertRaisesRegex(ValueError, "OpenCost.*daily.*2025-12-22"):
                read_opencost("http://opencost:9003", window)

    def test_live_allocation_requests_daily_sets_and_sums_them_without_idle_sharing(self):
        window = (date(2025, 12, 22), date(2025, 12, 29))
        body = json.dumps({"code": 200, "data": [
            {"shop/dev/store": {"totalCost": 1.25}, "__idle__": {"totalCost": 0.5}}
            for _ in range(7)
        ]}).encode()
        with patch("finops.opencost_client.urlopen", return_value=io.BytesIO(body)) as request:
            costs = read_opencost("http://opencost:9003/", window)
        self.assertEqual(sum(cost.amount for cost in costs), Decimal("12.25"))
        url = urlparse(request.call_args.args[0])
        self.assertEqual(url.path, "/allocation")
        self.assertEqual(parse_qs(url.query), {
            "window": ["2025-12-22T00:00:00Z,2025-12-29T00:00:00Z"],
            "aggregate": ["namespace,label:env,label:team"],
            "step": ["1d"], "accumulate": ["false"],
            "includeIdle": ["true"], "shareIdle": ["false"],
        })

    def test_cli_does_not_print_or_notify_a_partial_opencost_report(self):
        body = b'{"code": 200, "data": [{"shop/dev/store": {"totalCost": 1}}]}'
        output, errors = io.StringIO(), io.StringIO()
        with patch.dict("os.environ", {"OPENCOST_URL": "http://opencost.invalid",
                                      "ATHENA_TABLE": ""}), patch(
            "finops.opencost_client.urlopen", side_effect=lambda *a, **kw: io.BytesIO(body)
        ), patch("finops.cli.notify") as notify, redirect_stdout(output), redirect_stderr(errors):
            self.assertEqual(main(["report"]), 1)
        self.assertEqual(output.getvalue(), "")
        self.assertIn("OpenCost", errors.getvalue())
        notify.assert_not_called()

    def test_cli_demo_is_offline_and_keeps_cloud_and_cluster_totals_separate(self):
        output = io.StringIO()
        fixtures = Path(__file__).parent / "fixtures"
        with redirect_stdout(output), patch("finops.cli.read_opencost") as opencost, patch(
            "finops.cli.read_athena"
        ) as athena, patch("finops.cli.notify") as notify:
            self.assertEqual(main(["report", "--fixtures", str(fixtures)]), 0)
        self.assertIn("OpenCost Kubernetes allocations", output.getvalue())
        self.assertIn("$89.47", output.getvalue())
        self.assertIn("AWS CUR unblended costs", output.getvalue())
        self.assertIn("$140.00", output.getvalue())
        self.assertNotIn("$229.47", output.getvalue())
        opencost.assert_not_called()
        athena.assert_not_called()
        notify.assert_not_called()
