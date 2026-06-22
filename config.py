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

    BASE_URL = require_env("BASE_URL").rstrip("/")

    DATA_DIR = os.getenv("DATA_DIR", os.path.join(os.path.dirname(__file__), "data"))
    RECORDINGS_DIR = os.path.join(DATA_DIR, "recordings")

    SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "dev-secret-change-me")

    GDRIVE_CREDENTIALS_PATH = require_env("GDRIVE_CREDENTIALS_PATH")
    GDRIVE_FOLDER_ID = require_env("GDRIVE_FOLDER_ID")
