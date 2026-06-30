import logging

from flask import Blueprint
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse

from app.utils.twilio_validator import validate_twilio_request
from app.utils.twiml import error_response, twiml_response
from config import Config

logger = logging.getLogger(__name__)
conference_bp = Blueprint("conference", __name__)

CONFERENCE_ROOM = "bea-party-line"
MAX_CONFERENCE_MINUTES = 10


@conference_bp.post("/conference")
@validate_twilio_request
def conference():
    """Bea joins the conference room; Twilio dials out to configured participants."""
    try:
        vr = VoiceResponse()
        vr.say("Connecting you now. Please hold.")
        dial = vr.dial()
        dial.conference(
            CONFERENCE_ROOM,
            start_conference_on_enter=True,
            end_conference_on_exit=True,
            max_participants=10,
            time_limit=MAX_CONFERENCE_MINUTES * 60,
        )
        _call_participants()
        return twiml_response(vr)
    except Exception:
        logger.exception("Error in /conference")
        return error_response()


@conference_bp.post("/conference/join")
@validate_twilio_request
def conference_join():
    """TwiML answered by each outbound participant leg — joins the same room."""
    try:
        vr = VoiceResponse()
        dial = vr.dial()
        dial.conference(
            CONFERENCE_ROOM,
            start_conference_on_enter=True,
            end_conference_on_exit=False,
        )
        return twiml_response(vr)
    except Exception:
        logger.exception("Error in /conference/join")
        return error_response()


def _call_participants():
    if not Config.CONFERENCE_PARTICIPANTS:
        logger.warning("No conference participants configured")
        return

    client = Client(Config.TWILIO_ACCOUNT_SID, Config.TWILIO_AUTH_TOKEN)
    for number in Config.CONFERENCE_PARTICIPANTS:
        try:
            client.calls.create(
                to=number,
                from_=Config.TWILIO_PHONE_NUMBER,
                url=f"{Config.BASE_URL}/conference/join",
                method="POST",
            )
        except Exception:
            logger.exception("Failed to dial a conference participant")

    logger.info("Dialed %d conference participant(s)", len(Config.CONFERENCE_PARTICIPANTS))
