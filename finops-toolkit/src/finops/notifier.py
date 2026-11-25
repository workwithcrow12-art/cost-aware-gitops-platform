import json
import re
import sys
from http.client import HTTPException
from os import environ
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from finops.config import required

_TELEGRAM_TOKEN = re.compile(r"\d+:[A-Za-z0-9_-]+")


def _chunks(message: str, limit: int = 4096) -> list[str]:
    if len(message) <= limit:
        return [message]
    parts, current = [], ""
    for line in message.split("\n"):
        while len(line) > limit:
            if current:
                parts.append(current)
                current = ""
            parts.append(line[:limit])
            line = line[limit:]
        candidate = f"{current}\n{line}" if current else line
        if len(candidate) > limit:
            parts.append(current)
            current = line
        else:
            current = candidate
    return [*parts, current] if current or not parts else parts


def notify(message: str) -> None:
    destination = environ.get("NOTIFIER", "").strip().lower()
    if not destination:
        print("finops: NOTIFIER is not set; skipping notification delivery", file=sys.stderr)
        return
    if destination == "telegram":
        token = required("TELEGRAM_BOT_TOKEN")
        if not _TELEGRAM_TOKEN.fullmatch(token):
            raise ValueError("TELEGRAM_BOT_TOKEN has an invalid format")
        chat_id = required("TELEGRAM_CHAT_ID")
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payloads = [{"chat_id": chat_id, "text": part} for part in _chunks(message)]
    elif destination == "slack":
        url = required("SLACK_WEBHOOK_URL")
        parsed = urlsplit(url)
        if parsed.scheme != "https" or not parsed.netloc or any(ch.isspace() for ch in url):
            raise ValueError("SLACK_WEBHOOK_URL must be a valid https:// URL")
        payloads = [{"text": message, "mrkdwn": False}]
    else:
        raise ValueError("NOTIFIER must be slack or telegram")

    for payload in payloads:
        req = Request(  # noqa: S310
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urlopen(req, timeout=15):  # noqa: S310
                pass
        except (URLError, OSError, HTTPException):
            raise ValueError(
                f"{destination} rejected the notification or was unreachable"
            ) from None
