import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from finops.cli import main


class FailureNotificationTests(unittest.TestCase):
    def test_live_failure_sends_generic_notification_and_strips_env_whitespace(self):
        with (
            patch.dict("os.environ", {"NOTIFY_FAILURES": " true \r\n"}),
            patch("finops.cli._report", side_effect=ValueError("sensitive upstream response")),
            patch("finops.cli.notify") as notify,
            redirect_stderr(io.StringIO()),
            redirect_stdout(io.StringIO()) as output,
        ):
            self.assertEqual(main(["report"]), 1)
        self.assertEqual(output.getvalue(), "")
        notify.assert_called_once_with(
            "FinOps report failed. Check the job logs; no report was generated."
        )

    def test_live_waste_sends_notification_without_dry_run(self):
        fixtures = Path(__file__).parent / "fixtures" / "custodian"
        output = io.StringIO()
        with patch("finops.cli.notify") as notify, redirect_stdout(output):
            self.assertEqual(main(["waste", "--input", str(fixtures)]), 0)
        notify.assert_called_once()
        self.assertIn("4 candidates", notify.call_args.args[0])

    def test_offline_and_dry_run_failures_never_notify(self):
        with tempfile.TemporaryDirectory() as directory:
            commands = (
                ["report", "--fixtures", directory],
                ["report", "--dry-run"],
                ["waste", "--input", directory, "--dry-run"],
            )
            for args in commands:
                with (
                    self.subTest(args=args),
                    patch.dict("os.environ", {"NOTIFY_FAILURES": "true"}),
                    patch("finops.cli._report", side_effect=ValueError("missing data")),
                    patch("finops.cli.notify") as notify,
                    redirect_stderr(io.StringIO()),
                ):
                    self.assertEqual(main(args), 1)
                notify.assert_not_called()

    def test_notification_failure_does_not_mask_report_failure(self):
        with (
            patch.dict("os.environ", {"NOTIFY_FAILURES": "true"}),
            patch("finops.cli._report", side_effect=ValueError("missing data")),
            patch("finops.cli.notify", side_effect=ValueError("unreachable")),
            redirect_stderr(io.StringIO()) as errors,
        ):
            self.assertEqual(main(["report"]), 1)
        self.assertIn("missing data", errors.getvalue())
        self.assertIn("failure notification could not be delivered", errors.getvalue())

    def test_success_notification_failure_is_not_retried(self):
        with (
            patch.dict("os.environ", {"NOTIFY_FAILURES": "true"}),
            patch("finops.cli._report", return_value="complete report"),
            patch("finops.cli.notify", side_effect=ValueError("unreachable")) as notify,
            redirect_stderr(io.StringIO()),
            redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(main(["report"]), 1)
        notify.assert_called_once_with("complete report")

    def test_usd_rates_option_reaches_the_report(self):
        fixtures = Path(__file__).parent / "fixtures"
        with tempfile.TemporaryDirectory() as directory:
            rates = Path(directory) / "rates.json"
            rates.write_text('{"USD": 2}', encoding="utf-8")
            with redirect_stderr(io.StringIO()) as errors, redirect_stdout(io.StringIO()) as output:
                try:
                    code = main([
                        "cloud-report",
                        "--input",
                        str(fixtures / "focus_sample.csv"),
                        "--as-of",
                        "2026-01-19",
                        "--usd-rates",
                        str(rates),
                    ])
                except SystemExit as exc:
                    code = exc.code
            self.assertEqual(code, 1)
            self.assertEqual(output.getvalue(), "")
            self.assertIn("USD", errors.getvalue())
