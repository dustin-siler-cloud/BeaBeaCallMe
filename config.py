import os
from dotenv import load_dotenv

load_dotenv()


def require_env(key):
    value = os.getenv(key)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {key}")
    return value


class Config:
    TWILIO_ACCOUNT_SID = require_env("TWILIO_ACCOUNT_SID")
    TWILIO_AUTH_TOKEN = require_env("TWILIO_AUTH_TOKEN")
    TWILIO_PHONE_NUMBER = require_env("TWILIO_PHONE_NUMBER")
    TWILIO_ASSET_BASE = require_env("TWILIO_ASSET_BASE")

    BASE_URL = require_env("BASE_URL").rstrip("/")

    DATA_DIR = os.getenv("DATA_DIR", os.path.join(os.path.dirname(__file__), "data"))
    RECORDINGS_DIR = os.path.join(DATA_DIR, "recordings")

    SECRET_KEY = require_env("FLASK_SECRET_KEY")

    GDRIVE_CREDENTIALS_PATH = require_env("GDRIVE_CREDENTIALS_PATH")
    GDRIVE_FOLDER_ID = require_env("GDRIVE_FOLDER_ID")  # Shared Drive ID
    GDRIVE_FOLDER_ID_FROM_BEA = require_env("GDRIVE_FOLDER_ID_FROM_BEA")
    GDRIVE_FOLDER_ID_TO_BEA = require_env("GDRIVE_FOLDER_ID_TO_BEA")

    # The single number that routes to Bea's IVR menu (voicemail + conference)
    BEA_CALLER_ID = require_env("BEA_CALLER_ID")

    # Comma-separated E.164 numbers that route to the friend IVR menu (voicemail only)
    FRIEND_CALLERS = [
        n.strip() for n in os.getenv("FRIEND_CALLERS", "").split(",") if n.strip()
    ]

    # Comma-separated E.164 numbers Twilio dials when Bea starts a group call
    CONFERENCE_PARTICIPANTS = [
        n.strip()
        for n in os.getenv("CONFERENCE_PARTICIPANTS", "").split(",")
        if n.strip()
    ]

    # Comma-separated E.164:Name pairs for friendly filenames e.g. +1234567890:Bea
    CALLER_NAMES = {
        number: name
        for entry in os.getenv("CALLER_NAMES", "").split(",")
        if ":" in entry
        for number, name in [entry.strip().split(":", 1)]
    }

    # Comma-separated E.164 numbers to text when a new voicemail is saved (optional)
    SMS_NOTIFY_NUMBERS = [
        n.strip() for n in os.getenv("SMS_NOTIFY_NUMBERS", "").split(",") if n.strip()
    ]

    # Email notifications on new voicemail via Resend (optional)
    RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
    EMAIL_FROM = os.getenv("EMAIL_FROM", "")
    EMAIL_NOTIFY_TO = [
        n.strip() for n in os.getenv("EMAIL_NOTIFY_TO", "").split(",") if n.strip()
    ]
