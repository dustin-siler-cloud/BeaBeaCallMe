import logging

import requests

from config import Config

logger = logging.getLogger(__name__)

_RESEND_API_URL = "https://api.resend.com/emails"


def notify_new_recording(
    caller_name: str, timestamp: str, duration: int, drive_file_id: str | None, role: str | None
) -> None:
    if not Config.RESEND_API_KEY or not Config.EMAIL_NOTIFY_TO:
        return

    direction = "from Bea" if role == "bea" else f"for Bea (from {caller_name})"
    subject = f"New voicemail {direction}"
    body = f"New voicemail {direction} — {timestamp} ({duration}s)"
    if drive_file_id:
        body += f"\n\nhttps://drive.google.com/file/d/{drive_file_id}/view"

    try:
        resp = requests.post(
            _RESEND_API_URL,
            headers={"Authorization": f"Bearer {Config.RESEND_API_KEY}"},
            json={
                "from": Config.EMAIL_FROM,
                "to": Config.EMAIL_NOTIFY_TO,
                "subject": subject,
                "text": body,
            },
            timeout=10,
        )
        if resp.status_code >= 300:
            logger.warning("Email notification failed: %s %s", resp.status_code, resp.text)
    except Exception:
        logger.warning("Email notification error", exc_info=True)
