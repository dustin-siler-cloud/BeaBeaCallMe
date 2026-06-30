import logging

from twilio.rest import Client

from config import Config

logger = logging.getLogger(__name__)


def notify_new_recording(
    caller_name: str, timestamp: str, duration: int, drive_file_id: str | None, role: str | None
) -> None:
    if not Config.SMS_NOTIFY_NUMBERS:
        return

    direction = "from Bea" if role == "bea" else f"for Bea (from {caller_name})"
    body = f"New voicemail {direction} — {timestamp} ({duration}s)"
    if drive_file_id:
        body += f"\nhttps://drive.google.com/file/d/{drive_file_id}/view"

    client = Client(Config.TWILIO_ACCOUNT_SID, Config.TWILIO_AUTH_TOKEN)
    for number in Config.SMS_NOTIFY_NUMBERS:
        try:
            client.messages.create(to=number, from_=Config.TWILIO_PHONE_NUMBER, body=body)
        except Exception:
            logger.warning("SMS notification failed for a recipient", exc_info=True)
