from flask import Response
from twilio.twiml.voice_response import VoiceResponse

from app.utils.audio_shuffle import next_greeting_url
from config import Config


def twiml_response(vr):
    """Return a Flask response with correct Content-Type for TwiML."""
    return Response(str(vr), mimetype="text/xml")


def error_response(message="Sorry, something went wrong. Please try again."):
    """Return a friendly TwiML error that redirects back to the main menu."""
    vr = VoiceResponse()
    vr.say(message)
    vr.redirect(f"{Config.BASE_URL}/call")
    return twiml_response(vr)


def main_menu_twiml():
    """Build and return the main menu TwiML."""
    vr = VoiceResponse()
    gather = vr.gather(
        num_digits=1, action=f"{Config.BASE_URL}/call/route", method="POST", timeout=10
    )
    gather.play(next_greeting_url())
    # If no input, repeat the menu
    vr.redirect(f"{Config.BASE_URL}/call")
    return twiml_response(vr)
