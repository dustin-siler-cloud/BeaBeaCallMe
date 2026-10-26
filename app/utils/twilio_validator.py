import logging
from functools import wraps

from flask import abort, request
from twilio.request_validator import RequestValidator

from config import Config

logger = logging.getLogger(__name__)
validator = RequestValidator(Config.TWILIO_AUTH_TOKEN)


def validate_twilio_request(f):
    """Decorator that rejects requests not originating from Twilio.

    Reconstructs the public HTTPS URL using BASE_URL so the signature
    matches what Twilio signed, regardless of how the request arrives
    locally (e.g. via Tailscale Funnel forwarding HTTP internally).
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        # Build the public URL Twilio signed against
        public_url = Config.BASE_URL + request.full_path.rstrip("?")
        post_data = request.form.to_dict()
        signature = request.headers.get("X-Twilio-Signature", "")

        if not validator.validate(public_url, post_data, signature):
            logger.warning(
                "Rejected request with invalid Twilio signature from %s (url=%s)",
                request.remote_addr,
                public_url,
            )
            abort(403)

        return f(*args, **kwargs)
    return decorated


