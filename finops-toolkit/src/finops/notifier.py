import json
from os import environ
from urllib.error import URLError
from urllib.request import Request, urlopen

from finops.config import required


def notify(message: str) -> None:
    destination = environ.get("NOTIFIER", "").strip().lower()
    if not destination:
        return
    if destination == "telegram":
        token = required("TELEGRAM_BOT_TOKEN")
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {"chat_id": required("TELEGRAM_CHAT_ID"), "text": message}
    elif destination == "slack":
        url = required("SLACK_WEBHOOK_URL")
        payload = {"text": message, "mrkdwn": False}
    else:
        raise ValueError("NOTIFIER must be slack or telegram")

    request = Request(
        url, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"}
    )
    try:
        with urlopen(request, timeout=15):
            pass
    except URLError as exc:
        raise ValueError(f"{destination} rejected the notification or was unreachable") from exc
