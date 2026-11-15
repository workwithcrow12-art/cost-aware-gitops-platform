import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from finops.cli import main
from finops.waste import read_findings


class WasteTests(unittest.TestCase):
    def test_rate_overrides_change_monthly_estimate(self):
        fixtures = Path(__file__).parent / "fixtures" / "custodian"
        with patch.dict("os.environ", {"EBS_GB_MONTH_RATE": "0.10", "EIP_HOURLY_RATE": "0",
                                       "SNAPSHOT_GB_MONTH_RATE": "0.025",
                                       "ALB_HOURLY_RATE": "0.03"}):
            findings = read_findings(fixtures)
        self.assertEqual(sum(item.monthly for item in findings), Decimal("31.20"))

    def test_invalid_rates_fail_without_a_partial_report(self):
        fixtures = Path(__file__).parent / "fixtures" / "custodian"
        for value in ("-1", "NaN", "Infinity", "bad"):
            with self.subTest(value=value), patch.dict("os.environ", {"ALB_HOURLY_RATE": value}):
                output, errors = io.StringIO(), io.StringIO()
                with redirect_stdout(output), redirect_stderr(errors):
                    self.assertEqual(main(["waste", "--input", str(fixtures), "--dry-run"]), 1)
                self.assertEqual(output.getvalue(), "")
                self.assertIn("ALB_HOURLY_RATE", errors.getvalue())

    def test_reads_custodian_output_and_labels_rates_as_estimates(self):
        fixtures = Path(__file__).parent / "fixtures" / "custodian"
        self.assertEqual(sum(item.count for item in read_findings(fixtures)), 4)
        self.assertEqual(sum(item.monthly for item in read_findings(fixtures)), Decimal("27.875"))

        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(main(["waste", "--input", str(fixtures), "--dry-run"]), 0)
        self.assertIn("4 candidates", output.getvalue())
        self.assertIn("$27.88", output.getvalue())
        self.assertIn("estimate", output.getvalue().lower())

    def test_missing_results_fail_instead_of_reporting_zero(self):
        with tempfile.TemporaryDirectory() as output_dir, redirect_stderr(io.StringIO()):
            self.assertEqual(main(["waste", "--input", output_dir, "--dry-run"]), 1)
