from decimal import Decimal
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import cloud_lab_preflight as preflight  # noqa: E402
import cloud_lab_runner as runner  # noqa: E402


VALID_NONPROD_ENV = {
    "STATE_BUCKET": "cost-aware-tfstate-example",
    "TF_VAR_operator_role_arn": "arn:aws:iam::123456789012:role/ClusterOperator",
    "TF_VAR_operator_access_cidrs": '["10.20.1.0/24"]',
}


def all_tools_present(name: str) -> str:
    return f"/usr/local/bin/{name}"


class CloudLabPreflightTests(unittest.TestCase):
    def test_decimal_cost_math_for_nonprod_and_prod(self):
        nonprod = preflight.evaluate_preflight(
            env="nonprod",
            hours="2.5",
            environ=VALID_NONPROD_ENV,
            which=all_tools_present,
        )
        self.assertTrue(nonprod.ready, nonprod.blockers)
        self.assertIsInstance(nonprod.total_hourly_usd, Decimal)
        self.assertEqual(nonprod.total_hourly_usd, Decimal("0.2403"))
        self.assertEqual(nonprod.total_session_usd, Decimal("0.60"))
        self.assertEqual(nonprod.total_monthly_30d_usd, Decimal("173.02"))

        prod_env = {
            **VALID_NONPROD_ENV,
            "TF_VAR_budget": '{"monthly_limit_usd": 500, "email": "finops@example.com"}',
            "TF_VAR_break_glass_role_arn": "arn:aws:iam::123456789012:role/ClusterBreakGlassAdmin",
        }
        prod = preflight.evaluate_preflight(
            env="prod",
            hours=2,
            environ=prod_env,
            which=all_tools_present,
        )
        self.assertTrue(prod.ready, prod.blockers)
        self.assertEqual(prod.total_hourly_usd, Decimal("0.6477"))
        self.assertEqual(prod.total_session_usd, Decimal("1.30"))
        self.assertEqual(prod.total_monthly_30d_usd, Decimal("466.34"))

    def test_missing_cli_tools_are_detected(self):
        def missing_kubeseal_and_aws(name: str) -> str | None:
            return None if name in ("kubeseal", "aws") else f"/usr/bin/{name}"

        report = preflight.evaluate_preflight(
            env="nonprod",
            hours=2,
            environ=VALID_NONPROD_ENV,
            which=missing_kubeseal_and_aws,
        )
        self.assertFalse(report.ready)
        missing_names = [t.name for t in report.tools if not t.found]
        self.assertEqual(missing_names, ["kubeseal", "aws"])
        self.assertTrue(any("kubeseal" in b for b in report.blockers))
        self.assertTrue(any("aws" in b for b in report.blockers))

    def test_prod_requires_budget_env_var_and_distinct_break_glass_role(self):
        without_budget = preflight.evaluate_preflight(
            env="prod",
            hours=2,
            environ=VALID_NONPROD_ENV,
            which=all_tools_present,
        )
        self.assertFalse(without_budget.ready)
        self.assertTrue(any("TF_VAR_budget" in b for b in without_budget.blockers))

        duplicate_break_glass = preflight.evaluate_preflight(
            env="prod",
            hours=2,
            environ={
                **VALID_NONPROD_ENV,
                "TF_VAR_budget": '{"monthly_limit_usd": 500, "email": "finops@example.com"}',
                "TF_VAR_break_glass_role_arn": VALID_NONPROD_ENV["TF_VAR_operator_role_arn"],
            },
            which=all_tools_present,
        )
        self.assertFalse(duplicate_break_glass.ready)
        self.assertTrue(any("TF_VAR_break_glass_role_arn" in b for b in duplicate_break_glass.blockers))

    def test_public_zero_cidr_and_non_positive_hours_are_rejected(self):
        bad_cidr = preflight.evaluate_preflight(
            env="nonprod",
            hours=2,
            environ={
                **VALID_NONPROD_ENV,
                "TF_VAR_operator_access_cidrs": '["0.0.0.0/0"]',
            },
            which=all_tools_present,
        )
        self.assertFalse(bad_cidr.ready)
        self.assertTrue(any("/0" in b for b in bad_cidr.blockers))

        with self.assertRaises(ValueError):
            preflight.parse_hours(0)
        with self.assertRaises(ValueError):
            preflight.parse_hours("-1.5")

    def test_cli_json_and_markdown_formats_include_private_api_and_free_tier_warnings(self):
        report = preflight.evaluate_preflight(
            env="gke",
            hours=3,
            environ={},
            which=all_tools_present,
        )
        md = preflight.render_markdown(report)
        self.assertIn("Private Control-Plane Reachability Warning", md)
        self.assertIn("Free Tier", md)

        parsed = json.loads(preflight.render_json(report))
        self.assertEqual(parsed["env"], "gke")
        self.assertEqual(parsed["region"], "asia-southeast1")
        self.assertFalse(parsed["ready"])
        self.assertEqual(parsed["cost_estimate"]["currency"], "USD")

    def test_verify_identity_redacts_account_id_on_error(self):
        fake_proc = subprocess.CompletedProcess(
            args=["aws", "sts", "get-caller-identity"],
            returncode=254,
            stdout="",
            stderr="AccessDenied for arn:aws:iam::987654321098:role/SecretRole in account 987654321098",
        )
        report = preflight.evaluate_preflight(
            env="nonprod",
            hours=2,
            verify_identity=True,
            environ=VALID_NONPROD_ENV,
            which=all_tools_present,
            runner=lambda *a, **kw: fake_proc,
        )
        self.assertFalse(report.ready)
        rendered = preflight.render_markdown(report)
        self.assertNotIn("987654321098", rendered)
        self.assertNotIn("SecretRole", rendered)
        self.assertIn("<REDACTED_ARN>", rendered)


class CloudLabRunnerTests(unittest.TestCase):
    def test_log_redaction_strips_account_ids_arns_tokens_and_secrets_preserving_digests(self):
        digest = "sha256:092501a03f2bc3a4265a0ba336da285a7d9f255d8d44ce5c80ba3b042eb82a8e"
        sample = "\n".join([
            "Account: 123456789012",
            "Role: arn:aws:iam::123456789012:role/ClusterBreakGlassAdmin",
            "Key: AKIAIOSFODNN7EXAMPLE",
            "GitHub: ghp_1234567890abcdefghijklmnopqrstuv",
            "Header: Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.sig",
            'Secret: aws_secret_access_key = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"',
            f"Image: ghcr.io/workwithcrow12-art/frontend@{digest}",
        ])
        cleaned = runner.redact_sensitive_text(sample)
        self.assertNotIn("123456789012", cleaned)
        self.assertNotIn("ClusterBreakGlassAdmin", cleaned)
        self.assertNotIn("AKIAIOSFODNN7EXAMPLE", cleaned)
        self.assertNotIn("ghp_1234567890abcdefghijklmnopqrstuv", cleaned)
        self.assertNotIn("wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY", cleaned)
        self.assertNotIn("eyJhbGciOiJIUzI1NiJ9", cleaned)
        self.assertIn("<REDACTED_ACCOUNT_ID>", cleaned)
        self.assertIn("<REDACTED_ARN>", cleaned)
        self.assertIn("<REDACTED_AWS_KEY_ID>", cleaned)
        self.assertIn("<REDACTED_TOKEN>", cleaned)
        self.assertIn("<REDACTED_SECRET>", cleaned)
        self.assertIn(digest, cleaned)

    def test_dry_run_generates_plan_and_not_run_evidence_and_refuses_existing_output_dir(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "dry-run-lab"
            proc = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS_DIR / "cloud_lab_runner.py"),
                    "--env",
                    "prod",
                    "--dry-run",
                    "--output-dir",
                    str(output),
                ],
                cwd=directory,
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            plan_text = (output / "readiness-plan.md").read_text(encoding="utf-8")
            evidence_text = (output / "evidence-template.md").read_text(encoding="utf-8")

            self.assertIn("AWS Cloud Lab Readiness & Execution Plan (`prod`)", plan_text)
            self.assertIn("TF_VAR_budget", plan_text)
            self.assertIn("NOT RUN (DRY RUN)", evidence_text)
            self.assertNotIn("| PASS", evidence_text)

            original_bytes = (output / "evidence-template.md").read_bytes()
            repeated = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS_DIR / "cloud_lab_runner.py"),
                    "--dry-run",
                    "--output-dir",
                    str(output),
                ],
                cwd=directory,
                capture_output=True,
                text=True,
                timeout=15,
            )
            self.assertNotEqual(repeated.returncode, 0)
            self.assertIn("already exists", repeated.stderr)
            self.assertEqual((output / "evidence-template.md").read_bytes(), original_bytes)

    def test_execute_stage_records_timestamps_redacts_logs_and_stops_on_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "live-stage"
            steps = [
                runner.StageExecutionStep(
                    stage_id="preflight",
                    log_name="preflight.log",
                    command=[
                        sys.executable,
                        "-c",
                        "print('Caller arn:aws:iam::111122223333:role/Admin token=my-secret-value')",
                    ],
                ),
                runner.StageExecutionStep(
                    stage_id="smoke",
                    log_name="smoke-fail.log",
                    command=[
                        sys.executable,
                        "-c",
                        "print('Account 111122223333 checkout failed'); raise SystemExit(5)",
                    ],
                ),
                runner.StageExecutionStep(
                    stage_id="smoke",
                    log_name="must-not-run.log",
                    command=[sys.executable, "-c", "print('unreachable')"],
                ),
            ]
            code = runner.run_lab(
                output,
                env="nonprod",
                dry_run=False,
                execute_stage="all",
                steps=steps,
                revision="deadbeefcafe",
            )
            self.assertEqual(code, 5)
            preflight_log = (output / "preflight.log").read_text(encoding="utf-8")
            smoke_log = (output / "smoke-fail.log").read_text(encoding="utf-8")
            evidence = (output / "evidence-template.md").read_text(encoding="utf-8")

            self.assertNotIn("111122223333", preflight_log)
            self.assertNotIn("my-secret-value", preflight_log)
            self.assertIn("<REDACTED_ARN>", preflight_log)
            self.assertIn("<REDACTED_SECRET>", preflight_log)
            self.assertNotIn("111122223333", smoke_log)
            self.assertIn("PASS (`preflight.log`)", evidence)
            self.assertIn("FAIL (exit 5; see `smoke-fail.log`)", evidence)
            self.assertFalse((output / "must-not-run.log").exists())

    def test_timeout_in_execute_stage_retains_redacted_partial_output(self):
        timeout = subprocess.TimeoutExpired(
            ["kubectl"],
            120,
            output=b"Connecting to arn:aws:eks:ap-southeast-1:123456789012:cluster/nonprod\n",
        )
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "timeout-stage"
            with patch.object(runner.subprocess, "run", side_effect=timeout):
                code = runner.run_lab(
                    output,
                    env="nonprod",
                    dry_run=False,
                    execute_stage="smoke",
                    steps=[
                        runner.StageExecutionStep(
                            stage_id="smoke",
                            log_name="timeout.log",
                            command=[sys.executable, "-c", "pass"],
                        )
                    ],
                    revision="abcdef123456",
                )
            self.assertNotEqual(code, 0)
            log_text = (output / "timeout.log").read_text(encoding="utf-8")
            self.assertNotIn("123456789012", log_text)
            self.assertIn("<REDACTED_ARN>", log_text)
            self.assertIn("timed out", log_text)


if __name__ == "__main__":
    unittest.main()
