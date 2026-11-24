import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "portfolio_demo.py"


class PortfolioDemoTests(unittest.TestCase):
    def test_offline_demo_runs_from_another_directory_and_saves_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "evidence"
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--output-dir", str(output)],
                cwd=directory, capture_output=True, text=True, timeout=60,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("synthetic demo", (output / "weekly-report.md").read_text())
            self.assertIn("43.75 USD", (output / "cloud-report.md").read_text())
            self.assertIn("4 candidates", (output / "waste-report.md").read_text())
            self.assertIn("OK", (output / "finops-tests.log").read_text())
            self.assertIn("OK", (output / "digest-tests.log").read_text())
            self.assertIn("PASS", (output / "summary.md").read_text())
            original = (output / "summary.md").read_bytes()
            repeated = subprocess.run(
                [sys.executable, str(SCRIPT), "--output-dir", str(output)],
                cwd=directory, capture_output=True, text=True, timeout=10,
            )
            self.assertNotEqual(repeated.returncode, 0)
            self.assertEqual((output / "summary.md").read_bytes(), original)

    def test_failed_command_stops_the_demo_and_records_its_exit_code(self):
        self.assertTrue(SCRIPT.is_file(), "portfolio demo runner has not been implemented")
        spec = importlib.util.spec_from_file_location("portfolio_demo", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "failed"
            code = module.run_demo(output, [
                ("failure.log", [sys.executable, "-c", "print('failure evidence'); raise SystemExit(7)"]),
                ("not-run.log", [sys.executable, "-c", "print('must not run')"]),
            ])
            self.assertEqual(code, 7)
            self.assertIn("failure evidence", (output / "failure.log").read_text())
            self.assertIn("FAIL (exit 7)", (output / "summary.md").read_text())
            self.assertFalse((output / "not-run.log").exists())

    def test_timeout_retains_partial_command_output(self):
        spec = importlib.util.spec_from_file_location("portfolio_demo", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        timeout = subprocess.TimeoutExpired(["demo"], 60, output=b"partial diagnostic\n")
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "timeout"
            with patch.object(module.subprocess, "run", side_effect=timeout):
                code = module.run_demo(output, [("timeout.log", [sys.executable, "-c", "pass"])])
            self.assertNotEqual(code, 0)
            log = (output / "timeout.log").read_text()
            self.assertIn("partial diagnostic", log)
            self.assertIn("timed out", log)
            self.assertIn("FAIL", (output / "summary.md").read_text())


if __name__ == "__main__":
    unittest.main()
