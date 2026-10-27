import logging

import requests

from config import Config

logger = logging.getLogger(__name__)

_RESEND_API_URL = "https://api.resend.com/emails"

_CREAM = "#FAF5E7"
_YELLOW = "#FADF6F"
_GOLD = "#F4C400"
_TAN = "#E4C97D"
_INK = "#1f1f1f"
_FONT_STACK = "'Fredoka', 'Trebuchet MS', 'Arial Rounded MT Bold', sans-serif"


def _direction_copy(role: str | None, caller_name: str) -> tuple[str, str]:
    if role == "bea":
        return "New voicemail from Bea", "Bea left a voicemail for you"
    return "New voicemail for Bea", f"{caller_name} left Bea a voicemail"


def _build_text(subject: str, sentence: str, timestamp: str, duration: int, drive_link: str | None) -> str:
    body = f"{sentence} on {timestamp} ({duration} seconds long)."
    if drive_link:
        body += f"\n\nListen here: {drive_link}"
    return body


def _build_html(subject: str, sentence: str, timestamp: str, duration: int, drive_link: str | None) -> str:
    listen_button = ""
    if drive_link:
        listen_button = f"""
        <tr>
          <td align="center" style="padding: 28px 0 8px 0;">
            <a href="{drive_link}" style="background-color:{_GOLD}; color:{_INK}; text-decoration:none;
               font-family:{_FONT_STACK}; font-weight:bold; font-size:16px;
               padding:14px 32px; border-radius:999px; display:inline-block;">
              Listen to the message
            </a>
          </td>
        </tr>
        """

    header_image = ""
    if Config.EMAIL_HEADER_IMAGE_URL:
        header_image = f"""
          <tr>
            <td style="padding:0;">
              <img src="{Config.EMAIL_HEADER_IMAGE_URL}"
                   alt="Bea" width="480" style="display:block; width:100%; max-width:480px; height:auto;">
            </td>
          </tr>
        """

    return f"""\
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>{subject}</title>
  <link href="https://fonts.googleapis.com/css2?family=Fredoka:wght@500;700&display=swap" rel="stylesheet">
</head>
<body style="margin:0; padding:0; background-color:{_CREAM}; font-family:'Assistant',Helvetica,Arial,sans-serif;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:{_CREAM}; padding:32px 16px;">
    <tr>
      <td align="center">
        <table role="presentation" width="480" cellpadding="0" cellspacing="0"
               style="background-color:#ffffff; border-radius:20px; overflow:hidden; border:1px solid {_TAN};">
          {header_image}
          <tr>
            <td style="background-color:{_YELLOW}; padding:18px 24px; text-align:center;">
              <div style="font-family:{_FONT_STACK}; font-size:24px; font-weight:bold; color:{_INK};">
                BeaBeaCallMe
              </div>
            </td>
          </tr>
          <tr>
            <td style="padding:28px 32px 8px 32px; text-align:center;">
              <p style="font-size:17px; color:{_INK}; line-height:1.5; margin:0;">
                {sentence} on <strong>{timestamp}</strong> ({duration} seconds long).
              </p>
            </td>
          </tr>
          {listen_button}
          <tr>
            <td style="padding:20px 32px 28px 32px; text-align:center;">
              <p style="font-size:12px; color:#8a8a8a; margin:0;">
                Sent automatically by the family voicemail line — no reply needed.
              </p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
"""


def notify_new_recording(
    caller_name: str, timestamp: str, duration: int, drive_file_id: str | None, role: str | None
) -> None:
    if not Config.RESEND_API_KEY or not Config.EMAIL_NOTIFY_TO:
        return

    subject, sentence = _direction_copy(role, caller_name)
    drive_link = (
        f"https://drive.google.com/file/d/{drive_file_id}/view" if drive_file_id else None
    )

    text_body = _build_text(subject, sentence, timestamp, duration, drive_link)
    html_body = _build_html(subject, sentence, timestamp, duration, drive_link)

    try:
        resp = requests.post(
            _RESEND_API_URL,
            headers={"Authorization": f"Bearer {Config.RESEND_API_KEY}"},
            json={
                "from": Config.EMAIL_FROM,
                "to": Config.EMAIL_NOTIFY_TO,
                "subject": subject,
                "text": text_body,
                "html": html_body,
            },
            timeout=10,
        )
        if resp.status_code >= 300:
            logger.warning("Email notification failed: %s %s", resp.status_code, resp.text)
    except Exception:
        logger.warning("Email notification error", exc_info=True)
