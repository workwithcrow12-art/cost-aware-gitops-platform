import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from finops.cli import main
from finops.waste import RATES, read_findings


class WasteTests(unittest.TestCase):
    def test_rate_overrides_change_monthly_estimate(self):
        fixtures = Path(__file__).parent / "fixtures" / "custodian"
        with patch.dict(
            "os.environ",
            {
                "EBS_GB_MONTH_RATE": "0.10",
                "EIP_HOURLY_RATE": "0",
                "SNAPSHOT_GB_MONTH_RATE": "0.025",
                "ALB_HOURLY_RATE": "0.03",
            },
        ):
            findings = read_findings(fixtures)
        self.assertEqual(sum(item.monthly for item in findings), Decimal("31.20"))

    def test_float_sizes_and_incremental_snapshot_bytes_are_supported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = {
                "unattached-ebs": [{"Size": 12.5}],
                "unused-eip": [{"PublicIp": "203.0.113.10"}],
                "old-snapshots": [{"VolumeSize": 100, "FullSnapshotSizeInBytes": 2 * (1024**3)}],
                "idle-load-balancer": [],
            }
            for policy, items in data.items():
                target = root / policy
                target.mkdir(parents=True)
                (target / "resources.json").write_text(json.dumps(items), encoding="utf-8")
            findings = {item.policy: item for item in read_findings(root)}
        self.assertEqual(findings["unattached-ebs"].monthly, Decimal("1.000"))
        self.assertEqual(findings["old-snapshots"].monthly, Decimal("0.10"))

    def test_rejects_boolean_negative_missing_or_malformed_resources(self):
        bad_payloads = (
            ("unattached-ebs", '{"not": "a list"}', TypeError),
            ("unused-eip", "[null]", TypeError),
            ("unattached-ebs", '[{"Size": true}]', ValueError),
            ("unattached-ebs", '[{"Size": -5}]', ValueError),
            ("unattached-ebs", "[{}]", ValueError),
        )
        for policy_name, raw_json, exc_type in bad_payloads:
            with (
                self.subTest(policy=policy_name, raw=raw_json),
                tempfile.TemporaryDirectory() as tmp,
            ):
                root = Path(tmp)
                for name in RATES:
                    folder = root / name
                    folder.mkdir()
                    (folder / "resources.json").write_text("[]", encoding="utf-8")
                (root / policy_name / "resources.json").write_text(raw_json, encoding="utf-8")
                with self.assertRaises(exc_type):
                    read_findings(root)

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
        self.assertIn("VolumeSize", output.getvalue())

    def test_missing_results_fail_instead_of_reporting_zero(self):
        with tempfile.TemporaryDirectory() as output_dir, redirect_stderr(io.StringIO()):
            self.assertEqual(main(["waste", "--input", output_dir, "--dry-run"]), 1)
