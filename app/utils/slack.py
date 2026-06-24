import logging
import os

import requests

logger = logging.getLogger(__name__)

_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "")


def notify_new_recording(caller_name: str, timestamp: str, duration: int, drive_file_id: str | None) -> None:
    if not _WEBHOOK_URL:
        return

    drive_link = (
        f"https://drive.google.com/file/d/{drive_file_id}/view"
        if drive_file_id
        else None
    )

    text = f"*New voicemail from {caller_name}* — {timestamp} ({duration}s)"
    if drive_link:
        text += f"\n<{drive_link}|Listen on Google Drive>"

    try:
        resp = requests.post(
            _WEBHOOK_URL,
            json={"text": text},
            timeout=10,
        )
        if resp.status_code != 200:
            logger.warning("Slack notification failed: %s %s", resp.status_code, resp.text)
    except Exception:
        logger.warning("Slack notification error", exc_info=True)
