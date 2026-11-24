import io
import json
import unittest
from contextlib import redirect_stderr
from http.client import InvalidURL
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

from finops.config import AthenaConfig, required
from finops.notifier import notify


def _ok() -> MagicMock:
    ctx = MagicMock()
    ctx.__enter__.return_value = ctx
    ctx.__exit__.return_value = False
    return ctx


class ConfigAndNotifierTests(unittest.TestCase):
    def test_config_validation_and_overrides(self) -> None:
        with patch.dict("os.environ", {"OPENCOST_URL": "   "}, clear=True):
            with self.assertRaisesRegex(ValueError, "OPENCOST_URL"):
                required("OPENCOST_URL")
        with patch.dict("os.environ", {}, clear=True):
            self.assertIsNone(AthenaConfig.from_environment())

        base = {
            "AWS_REGION": "ap-southeast-1",
            "ATHENA_DATABASE": "finops",
            "ATHENA_TABLE": "cur",
            "ATHENA_WORKGROUP": "finops",
            "ATHENA_OUTPUT_S3": "s3://results/",
        }
        with patch.dict(
            "os.environ",
            {**base, "ATHENA_PARTITIONED": "false", "ATHENA_ENV_TAG_COLUMN": "none"},
            clear=True,
        ):
            cfg = AthenaConfig.from_environment()
        assert cfg is not None
        self.assertFalse(cfg.partitioned)
        self.assertIsNone(cfg.env_tag_column)

        for key, bad in (("ATHENA_PARTITIONED", "maybe"), ("ATHENA_ENV_TAG_COLUMN", "bad;col")):
            with patch.dict("os.environ", {**base, key: bad}, clear=True):
                with self.assertRaisesRegex(ValueError, key):
                    AthenaConfig.from_environment()

    def test_unset_and_unknown_notifiers(self) -> None:
        stderr = io.StringIO()
        with (
            patch.dict("os.environ", {"NOTIFIER": ""}, clear=True),
            patch("finops.notifier.urlopen") as mock_open,
            redirect_stderr(stderr),
        ):
            notify("hello")
        mock_open.assert_not_called()
        self.assertIn("NOTIFIER is not set", stderr.getvalue())

        with patch.dict("os.environ", {"NOTIFIER": "email"}, clear=True):
            with self.assertRaisesRegex(ValueError, "slack or telegram"):
                notify("hello")

    def test_slack_url_validation_and_delivery(self) -> None:
        for bad_url in (
            "http://hooks.slack.com/services/secret-path",
            "file:///etc/passwd",
            "hooks.slack.com/services/secret-path",
            "https://hooks.slack.com/services/secret path",
        ):
            env = {"NOTIFIER": "slack", "SLACK_WEBHOOK_URL": bad_url}
            with self.subTest(url=bad_url), patch.dict("os.environ", env, clear=True):
                with self.assertRaises(ValueError) as ctx:
                    notify("report")
                self.assertNotIn("secret-path", str(ctx.exception))

        env = {"NOTIFIER": "slack", "SLACK_WEBHOOK_URL": "https://hooks.slack.com/services/T/B/X"}
        with patch.dict("os.environ", env, clear=True), patch(
            "finops.notifier.urlopen", return_value=_ok()
        ) as mock_open:
            notify("weekly summary")
        body = json.loads(mock_open.call_args.args[0].data.decode("utf-8"))
        self.assertEqual(body, {"text": "weekly summary", "mrkdwn": False})

    def test_telegram_token_validation_chunking_and_secret_suppression(self) -> None:
        for bad_tok in ("not-a-token", "12345:abc@evil.example/path", "12345:abc?x=1"):
            env = {"NOTIFIER": "telegram", "TELEGRAM_BOT_TOKEN": bad_tok, "TELEGRAM_CHAT_ID": "99"}
            with self.subTest(token=bad_tok), patch.dict("os.environ", env, clear=True):
                with self.assertRaises(ValueError) as ctx:
                    notify("report")
                self.assertNotIn(bad_tok, str(ctx.exception))

        secret = "123456:SuperSecretBotToken_XYZ"
        url = f"https://api.telegram.org/bot{secret}/sendMessage"
        http_err = HTTPError(url, 401, "No", None, None)  # type: ignore[arg-type]
        self.addCleanup(http_err.close)
        env = {"NOTIFIER": "telegram", "TELEGRAM_BOT_TOKEN": secret, "TELEGRAM_CHAT_ID": "-100"}
        for exc in (http_err, URLError("boom"), TimeoutError("timeout"), InvalidURL("bad")):
            with patch.dict("os.environ", env, clear=True), patch(
                "finops.notifier.urlopen", side_effect=exc
            ):
                with self.assertRaises(ValueError) as ctx:
                    notify("report")
                self.assertIsNone(ctx.exception.__cause__)
                self.assertNotIn(secret, repr(ctx.exception))

        long_msg = "\n".join(f"line-{idx:04d}-" + ("x" * 90) for idx in range(60))
        with patch.dict("os.environ", env, clear=True), patch(
            "finops.notifier.urlopen", return_value=_ok()
        ) as mock_open:
            notify(long_msg)
        calls = mock_open.call_args_list
        chunks = [json.loads(c.args[0].data.decode("utf-8"))["text"] for c in calls]
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(part) <= 4096 for part in chunks))
        self.assertEqual("\n".join(chunks), long_msg)
