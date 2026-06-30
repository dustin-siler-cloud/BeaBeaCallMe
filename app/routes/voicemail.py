import logging
import os
import re
from datetime import datetime
from urllib.parse import quote, urlparse
from zoneinfo import ZoneInfo

import requests as http_requests
from flask import Blueprint, abort, request
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse

from app.gdrive import upload_recording
from app.utils.caller_role import get_caller_role
from app.utils.db import init_db, log_recording
from app.utils.slack import notify_new_recording
from app.utils.twilio_validator import validate_twilio_request
from app.utils.twiml import error_response, twiml_response
from config import Config

logger = logging.getLogger(__name__)
voicemail_bp = Blueprint("voicemail", __name__)

init_db()


@voicemail_bp.post("/voicemail")
@validate_twilio_request
def voicemail():
    """Prompt the caller to leave a message and start recording."""
    try:
        vr = VoiceResponse()
        caller = request.form.get("From", "unknown")
        vr.say("Please leave your message after the beep.")
        vr.record(
            action=f"{Config.BASE_URL}/voicemail/done",
            recording_status_callback=f"{Config.BASE_URL}/voicemail/callback?from={quote(caller, safe='')}",
            recording_status_callback_method="POST",
            finish_on_key="",
            max_length=300,
            play_beep=True,
        )
        return twiml_response(vr)
    except Exception:
        logger.exception("Error in /voicemail")
        return error_response()


@voicemail_bp.post("/voicemail/done")
@validate_twilio_request
def voicemail_done():
    """Thank the caller and end the call after recording."""
    try:
        vr = VoiceResponse()
        vr.say("Thank you. Your message has been saved. Goodbye.")
        vr.hangup()
        return twiml_response(vr)
    except Exception:
        logger.exception("Error in /voicemail/done")
        return error_response()


@voicemail_bp.post("/voicemail/callback")
@validate_twilio_request
def voicemail_callback():
    """
    Called by Twilio when a recording is complete.
    Downloads the audio, saves it locally, logs metadata, then deletes from Twilio.
    """
    try:
        recording_sid = request.form.get("RecordingSid", "")
        recording_url = request.form.get("RecordingUrl", "")
        duration = request.form.get("RecordingDuration", 0)
        caller_id = request.args.get("from", request.form.get("From", "unknown"))
        safe_caller_id = re.sub(r"[^A-Za-z0-9+\-]", "_", caller_id)

        logger.info(
            "Recording complete: sid=%s duration=%s from=%s",
            recording_sid,
            duration,
            safe_caller_id,
        )

        now = datetime.now(ZoneInfo("America/New_York"))
        date_path = now.strftime("%Y/%m/%d")
        caller_name = Config.CALLER_NAMES.get(caller_id, caller_id)
        caller_name = re.sub(r"[^A-Za-z0-9_\-]", "_", caller_name)
        timestamp = now.strftime("%d%b%Y-%-I-%M%p").upper()
        filename = f"{caller_name}-{timestamp}.wav"

        save_dir = os.path.join(Config.RECORDINGS_DIR, date_path)
        os.makedirs(save_dir, exist_ok=True)
        filepath = os.path.join(save_dir, filename)

        # Download the recording from Twilio (mp3 -> wav via URL param)
        audio_url = f"{recording_url}.wav"
        parsed = urlparse(audio_url)
        if not parsed.hostname or not parsed.hostname.endswith(".twilio.com"):
            logger.warning("Rejected non-Twilio recording URL: %s", parsed.hostname)
            abort(400)
        response = http_requests.get(
            audio_url,
            auth=(Config.TWILIO_ACCOUNT_SID, Config.TWILIO_AUTH_TOKEN),
            timeout=30,
        )
        response.raise_for_status()

        with open(filepath, "wb") as f:
            f.write(response.content)

        file_size = os.path.getsize(filepath)
        logger.info("Saved recording to %s (%d bytes)", filepath, file_size)

        role = get_caller_role(caller_id)
        folder_id = (
            Config.GDRIVE_FOLDER_ID_FROM_BEA
            if role == "bea"
            else Config.GDRIVE_FOLDER_ID_TO_BEA
        )

        drive_file_id = None
        try:
            drive_file_id = upload_recording(filepath, filename, folder_id)
        except Exception:
            logger.exception("GDrive upload failed for %s — keeping local copy", filename)

        log_recording(
            created_at=now.isoformat(),
            caller_id=caller_id,
            duration=int(duration),
            filename=os.path.join(date_path, filename),
            file_size=file_size,
            twilio_sid=recording_sid,
            gdrive_file_id=drive_file_id,
        )

        notify_new_recording(caller_name, timestamp, int(duration), drive_file_id)

        # Delete from Twilio to avoid storage costs
        _delete_from_twilio(recording_sid)

        return ("", 204)
    except Exception:
        logger.exception(
            "Error in /voicemail/callback for sid=%s", request.form.get("RecordingSid")
        )
        return ("", 500)


def _delete_from_twilio(recording_sid):
    """Delete a recording from Twilio's servers."""
    try:
        client = Client(Config.TWILIO_ACCOUNT_SID, Config.TWILIO_AUTH_TOKEN)
        client.recordings(recording_sid).delete()
        logger.info("Deleted recording %s from Twilio", recording_sid)
    except Exception:
        logger.warning(
            "Could not delete recording %s from Twilio", recording_sid, exc_info=True
        )
