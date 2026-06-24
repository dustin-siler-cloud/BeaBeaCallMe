import logging
import re
from flask import Blueprint, request
from twilio.twiml.voice_response import VoiceResponse

from app.utils.twilio_validator import validate_twilio_request
from app.utils.twiml import error_response, main_menu_twiml, twiml_response
from config import Config

logger = logging.getLogger(__name__)
ivr_bp = Blueprint("ivr", __name__)


@ivr_bp.post("/call")
@validate_twilio_request
def call():
    """Entry point for all incoming calls — presents the main menu."""
    try:
        caller = request.form.get("From", "unknown")
        safe_caller = re.sub(r"[^A-Za-z0-9+\-]", "_", caller)
        logger.info("Incoming call from %s", safe_caller)

        if Config.ALLOWED_CALLERS and caller not in Config.ALLOWED_CALLERS:
            logger.warning("Rejected call from unlisted number: %s", safe_caller)
            vr = VoiceResponse()
            vr.reject()
            return twiml_response(vr)

        return main_menu_twiml()
    except Exception:
        logger.exception("Error in /call")
        return error_response()


@ivr_bp.post("/call/route")
@validate_twilio_request
def route():
    """Routes keypad input from the main menu."""
    try:
        digit = request.form.get("Digits", "")
        logger.info("Main menu digit pressed: %s", digit)

        vr = VoiceResponse()

        if digit == "1":
            vr.redirect(f"{Config.BASE_URL}/voicemail")
        else:
            vr.say("I didn't catch that. Press 1 to leave a voicemail.")
            vr.redirect(f"{Config.BASE_URL}/call")

        return twiml_response(vr)
    except Exception:
        logger.exception("Error in /call/route")
        return error_response()


