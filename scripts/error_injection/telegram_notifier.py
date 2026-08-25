"""
Sends Telegram notifications about the error-injection pipeline's progress.

Credentials are read from the TELEGRAM_BOT_TOKEN and CHAT_ID environment
variables. Notifications are optional: if either variable is unset, sending
is a no-op so the pipeline can still run without Telegram configured.
"""

import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("CHAT_ID", "")

_TELEGRAM_API_URL_TEMPLATE = "https://api.telegram.org/bot{token}/sendMessage"
_REQUEST_TIMEOUT_SECONDS = 10


class TelegramNotificationError(RuntimeError):
    """Raised when a Telegram notification fails to send."""


def send_telegram_message(
    message: str,
    bot_token: str | None = None,
    chat_id: str | None = None,
) -> None:
    """
    Send `message` to a Telegram chat via the Bot API.

    Does nothing if credentials are not configured (neither passed in nor
    present in the TELEGRAM_BOT_TOKEN / CHAT_ID environment variables).

    Raises:
        TelegramNotificationError: If credentials are set but sending fails.
    """
    resolved_token = bot_token if bot_token is not None else TELEGRAM_BOT_TOKEN
    resolved_chat_id = chat_id if chat_id is not None else TELEGRAM_CHAT_ID

    if not resolved_token or not resolved_chat_id:
        logger.debug("Telegram credentials not configured; skipping notification.")
        return

    url = _TELEGRAM_API_URL_TEMPLATE.format(token=resolved_token)
    data = urllib.parse.urlencode({"chat_id": resolved_chat_id, "text": message}).encode("utf-8")
    request = urllib.request.Request(url, data=data, method="POST")

    try:
        with urllib.request.urlopen(request, timeout=_REQUEST_TIMEOUT_SECONDS):
            pass
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise TelegramNotificationError(
            f"Telegram API returned HTTP {exc.code}: {detail}"
        ) from exc
    except urllib.error.URLError as exc:
        raise TelegramNotificationError(f"Failed to reach Telegram API: {exc.reason}") from exc


def _utc_timestamp() -> str:
    """Return the current UTC time formatted for notification messages."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def build_start_message(num_stories: int, errors_per_story: int) -> str:
    """Build the notification sent when the injection process starts."""
    return (
        "🟢 Injection Process started\n"
        f"📖 Number of stories detected: {num_stories}\n"
        f"🔴 Number of errors to inject per story: {errors_per_story}\n"
        f"🕒 Start time: {_utc_timestamp()}"
    )


def build_end_message(num_stories: int, errors_per_story: int, summary_lines: list[str]) -> str:
    """Build the notification sent when the injection process finishes."""
    summary = "\n".join(summary_lines)
    return (
        "✅ Injection Process finished\n"
        f"📖 Number of stories detected: {num_stories}\n"
        f"✒️ Summary:\n{summary}\n"
        f"🔴 Number of errors injected per story: {errors_per_story}\n"
        f"🕒 End time: {_utc_timestamp()}"
    )


def build_failure_message(error_message: str) -> str:
    """Build the notification sent when the injection process fails."""
    return (
        "❌ Injection Process failed\n"
        f"⚠️ Error: {error_message}\n"
        f"🕒 Time: {_utc_timestamp()}"
    )
