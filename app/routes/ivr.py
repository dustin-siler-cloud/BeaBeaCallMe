import logging
import re
from flask import Blueprint, request
from twilio.twiml.voice_response import VoiceResponse

from app.utils.caller_role import get_caller_role
from app.utils.time_window import is_conference_window_open
from app.utils.twilio_validator import validate_twilio_request
from app.utils.twiml import error_response, main_menu_twiml, twiml_response
from config import Config

logger = logging.getLogger(__name__)
ivr_bp = Blueprint("ivr", __name__)


@ivr_bp.post("/call")
@validate_twilio_request
def call():
    """Entry point for all incoming calls — routes to a role-specific menu."""
    try:
        caller = request.form.get("From", "unknown")
        safe_caller = re.sub(r"[^A-Za-z0-9+\-]", "_", caller)
        logger.info("Incoming call from %s", safe_caller)

        role = get_caller_role(caller)
        if role is None:
            logger.warning("Rejected call from unlisted number: %s", safe_caller)
            vr = VoiceResponse()
            vr.reject()
            return twiml_response(vr)

        return main_menu_twiml(role)
    except Exception:
        logger.exception("Error in /call")
        return error_response()


@ivr_bp.post("/call/route")
@validate_twilio_request
def route():
    """Routes keypad input from the main menu based on caller role."""
    try:
        caller = request.form.get("From", "unknown")
        digit = request.form.get("Digits", "")
        role = get_caller_role(caller)
        logger.info("Main menu digit pressed: %s (role=%s)", digit, role)

        vr = VoiceResponse()

        if role is None:
            vr.reject()
            return twiml_response(vr)

        if digit == "1":
            vr.redirect(f"{Config.BASE_URL}/voicemail")
        elif digit == "6" and role == "bea":
            if is_conference_window_open():
                vr.redirect(f"{Config.BASE_URL}/conference")
            else:
                vr.say("Sorry, you can call your friends between 10 AM and 8 PM. Please try again later.")
                vr.hangup()
        else:
            vr.say("I didn't catch that.")
            vr.redirect(f"{Config.BASE_URL}/call")

        return twiml_response(vr)
    except Exception:
        logger.exception("Error in /call/route")
        return error_response()
