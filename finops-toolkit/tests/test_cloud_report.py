import csv
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from finops.cli import main
from finops.cloud_costs import render_cloud_report


class CloudReportTests(unittest.TestCase):
    def rows(self):
        rows = []
        for provider, cost in (("AWS", "1.25"), ("Google Cloud", "2"), ("Microsoft Azure", "3")):
            for offset in range(14):
                start = date(2026, 1, 5) + timedelta(days=offset)
                rows.append({
                    "ProviderName": provider,
                    "BillingCurrency": "USD",
                    "BilledCost": cost,
                    "ChargePeriodStart": f"{start}T00:00:00Z",
                    "ChargePeriodEnd": f"{start + timedelta(days=1)}T00:00:00Z",
                    "ServiceName": "Compute",
                    "Tags": json.dumps({"env": "dev", "team": "shop"}),
                })
        return rows

    def run_report(self, rows, fields=None):
        output, errors = io.StringIO(), io.StringIO()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "costs.csv"
            with path.open("w", encoding="utf-8", newline="") as source:
                writer = csv.DictWriter(source, fieldnames=fields or list(self.rows()[0]))
                writer.writeheader()
                writer.writerows(rows)
            with (
                redirect_stdout(output),
                redirect_stderr(errors),
                patch("finops.cli.notify") as notify,
                patch("urllib.request.urlopen", side_effect=AssertionError("offline")),
            ):
                try:
                    result = main(["cloud-report", "--input", str(path), "--as-of", "2026-01-19"])
                except SystemExit as exc:
                    result = exc.code
            notify.assert_not_called()
        return result, output.getvalue(), errors.getvalue()

    def test_combines_three_providers_without_network_or_notifications(self):
        result, output, errors = self.run_report(self.rows())
        self.assertEqual((result, errors), (0, ""))
        self.assertIn("43.75 USD", output)
        for provider, amount in (
            ("AWS", "8.75"),
            ("Google Cloud", "14.00"),
            ("Microsoft Azure", "21.00"),
        ):
            self.assertIn(f"| {provider} | {amount} USD | {amount} USD | +0.0% |", output)
        self.assertIn("dev", output)
        self.assertIn("shop", output)

    def test_keeps_currencies_separate(self):
        rows = self.rows()
        for row in rows:
            if row["ProviderName"] == "Google Cloud":
                row["BillingCurrency"] = "EUR"
        result, output, _ = self.run_report(rows)
        self.assertEqual(result, 0)
        self.assertIn("29.75 USD", output)
        self.assertIn("14.00 EUR", output)
        self.assertNotIn("43.75", output)

    def test_missing_provider_or_currency_day_aborts_without_partial_output(self):
        result, output, errors = self.run_report(self.rows()[1:])
        self.assertEqual((result, output), (1, ""))
        self.assertIn("AWS", errors)
        self.assertIn("daily", errors)

        mixed = self.rows()
        mixed[0]["BillingCurrency"] = "EUR"
        result2, output2, errors2 = self.run_report(mixed)
        self.assertEqual((result2, output2), (1, ""))
        self.assertIn("AWS (EUR)", errors2)

    def test_rejects_nonfinite_costs_and_bad_tags(self):
        for key, value in (
            ("BilledCost", "NaN"),
            ("BilledCost", "Infinity"),
            ("BilledCost", "invalid"),
            ("Tags", "[]"),
            ("Tags", "broken"),
            ("Tags", '{"env": []}'),
            ("BillingCurrency", "US"),
            ("ProviderName", ""),
        ):
            with self.subTest(key=key, value=value):
                rows = self.rows()
                rows[0][key] = value
                result, output, errors = self.run_report(rows)
                self.assertEqual((result, output), (1, ""))
                self.assertIn("row 2", errors)

    def test_rejects_ambiguous_charge_intervals_including_overlapping_monthly(self):
        for start, end in (
            ("2026-01-05", "2026-01-06"),
            ("2026-01-05T00:00:00", "2026-01-06T00:00:00"),
            ("2026-01-05T00:00:00Z", "2026-02-05T00:00:00Z"),
            ("2026-01-01T00:00:00Z", "2026-02-01T00:00:00Z"),
            ("2026-01-05T23:00:00Z", "2026-01-06T01:00:00Z"),
        ):
            with self.subTest(start=start, end=end):
                rows = self.rows()
                rows[0].update(ChargePeriodStart=start, ChargePeriodEnd=end)
                self.assertEqual(self.run_report(rows)[0], 1)

    def test_accepts_hourly_rows_credits_zero_and_missing_tags(self):
        rows = self.rows()
        rows[0].update(BilledCost="0", Tags="")
        rows[1].update(BilledCost="-1.25", Tags="null")
        rows[2].update(ChargePeriodEnd="2026-01-07T01:00:00Z")
        result, output, _ = self.run_report(rows)
        self.assertEqual(result, 0)
        self.assertIn("unallocated", output)

    def test_rejects_missing_columns_and_empty_export(self):
        for rows, fields in (([], ["ProviderName"]), ([], None)):
            with self.subTest(fields=fields):
                result, output, errors = self.run_report(rows, fields)
                self.assertEqual((result, output), (1, ""))
                self.assertIn("FOCUS", errors)

    def test_escapes_markdown_labels(self):
        rows = self.rows()
        rows[0]["Tags"] = '{"team": "shop|other\\nline"}'
        result, output, _ = self.run_report(rows)
        self.assertEqual(result, 0)
        self.assertIn("shop\\|other line", output)

    def test_rejects_duplicate_headers(self):
        fields = list(self.rows()[0]) + ["BilledCost"]
        result, output, errors = self.run_report(self.rows(), fields)
        self.assertEqual((result, output), (1, ""))
        self.assertIn("duplicate", errors)

    def test_ignores_single_and_multiday_rows_outside_the_comparison_windows(self):
        rows = self.rows()
        extras = [
            dict(
                rows[0],
                ChargePeriodStart="2026-01-19T00:00:00Z",
                ChargePeriodEnd="2026-01-20T00:00:00Z",
                BilledCost="1000",
            ),
            dict(
                rows[0],
                ChargePeriodStart="2025-12-01T00:00:00Z",
                ChargePeriodEnd="2026-01-01T00:00:00Z",
                BilledCost="5000",
            ),
            dict(
                rows[0],
                ChargePeriodStart="2026-01-19T00:00:00Z",
                ChargePeriodEnd="2026-02-19T00:00:00Z",
                BilledCost="5000",
            ),
        ]
        result, output, _ = self.run_report(rows + extras)
        self.assertEqual(result, 0)
        self.assertIn("43.75 USD", output)
        self.assertNotIn("1,000", output)
        self.assertNotIn("5,000", output)

    def render_with_rates(self, rows, rates):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "costs.csv"
            with path.open("w", encoding="utf-8", newline="") as source:
                writer = csv.DictWriter(source, fieldnames=list(self.rows()[0]))
                writer.writeheader()
                writer.writerows(rows)
            rates_path = Path(directory) / "usd_rates.json"
            rates_path.write_text(rates, encoding="utf-8")
            return render_cloud_report(path, date(2026, 1, 19), usd_rates=rates_path)

    def test_normalizes_mixed_currencies_and_credits_across_both_periods(self):
        rows = self.rows()
        for row in rows:
            if row["ProviderName"] == "Google Cloud":
                row.update(BillingCurrency="EUR", Tags='{"env":"prod","team":"data"}')
                if row["ChargePeriodStart"] >= "2026-01-12":
                    row["BilledCost"] = "3"
                if row["ChargePeriodStart"] == "2026-01-12T00:00:00Z":
                    row["BilledCost"] = "-1"
            elif row["ProviderName"] == "Microsoft Azure":
                row.update(BillingCurrency="GBP", Tags='{"env":"prod","team":"platform"}')
        output = self.render_with_rates(rows, '{"EUR": 1.1, "GBP": 1.25}')
        billed, normalized = output.split("## Normalized costs (USD)")
        self.assertIn("Total: 17.00 EUR vs 14.00 EUR (+21.4%)", billed)
        self.assertIn("Total: 21.00 GBP vs 21.00 GBP (+0.0%)", billed)
        self.assertIn("Total: 8.75 USD vs 8.75 USD (+0.0%)", billed)
        self.assertIn("Total: 53.70 USD vs 50.40 USD (+6.5%)", normalized)
        for label, now, before, change in (
            ("AWS", "8.75", "8.75", "+0.0%"),
            ("Google Cloud", "18.70", "15.40", "+21.4%"),
            ("Microsoft Azure", "26.25", "26.25", "+0.0%"),
            ("dev", "8.75", "8.75", "+0.0%"),
            ("prod", "44.95", "41.65", "+7.9%"),
            ("data", "18.70", "15.40", "+21.4%"),
            ("platform", "26.25", "26.25", "+0.0%"),
            ("shop", "8.75", "8.75", "+0.0%"),
        ):
            self.assertIn(f"| {label} | {now} USD | {before} USD | {change} |", normalized)
        self.assertIn("user-supplied", normalized)
        self.assertIn("both periods", normalized)
        self.assertIn("not authoritative invoice amounts", normalized)

    def test_usd_identity_needs_no_explicit_rate(self):
        for rates in ("{}", '{"USD": 1}'):
            with self.subTest(rates=rates):
                output = self.render_with_rates(self.rows(), rates)
                normalized = output.split("## Normalized costs (USD)")[1]
                self.assertIn("Total: 43.75 USD vs 43.75 USD (+0.0%)", normalized)

    def test_rejects_invalid_rates_without_partial_output(self):
        invalid = ["broken", "[]", "null", '{"EUR":1,"EUR":2}', '{"USD":2}']
        invalid += [
            f'{{"EUR":{value}}}'
            for value in (
                "0",
                "-1",
                "NaN",
                "Infinity",
                "-Infinity",
                "true",
                "null",
                '"1.1"',
                "{}",
                "[]",
            )
        ]
        invalid += [json.dumps({key: 1}) for key in ("eur", "EU", "E1R", " EUR")]
        for rates in invalid:
            with self.subTest(rates=rates):
                output = io.StringIO()
                with redirect_stdout(output), self.assertRaises((ValueError, TypeError)):
                    self.render_with_rates(self.rows(), rates)
                self.assertEqual(output.getvalue(), "")

    def test_rejects_missing_rate_for_currency_in_previous_period(self):
        rows = self.rows()
        for row in rows:
            if row["ProviderName"] == "Google Cloud":
                row["BillingCurrency"] = "EUR"
                if row["ChargePeriodStart"] >= "2026-01-12":
                    row["BilledCost"] = "0"
        output = io.StringIO()
        with redirect_stdout(output), self.assertRaisesRegex(ValueError, "EUR"):
            self.render_with_rates(rows, "{}")
        self.assertEqual(output.getvalue(), "")
