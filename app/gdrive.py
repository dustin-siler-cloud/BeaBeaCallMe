import logging
import os

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

logger = logging.getLogger(__name__)

_SCOPES = ["https://www.googleapis.com/auth/drive.file"]


def _get_service():
    creds_path = os.environ["GDRIVE_CREDENTIALS_PATH"]
    creds = service_account.Credentials.from_service_account_file(
        creds_path, scopes=_SCOPES
    )
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def upload_recording(local_path: str, filename: str) -> str:
    """Upload a WAV file to the configured Drive folder. Returns the Drive file ID."""
    folder_id = os.environ["GDRIVE_FOLDER_ID"]
    service = _get_service()

    metadata = {"name": filename, "parents": [folder_id]}
    media = MediaFileUpload(local_path, mimetype="audio/wav", resumable=False)

    file = (
        service.files()
        .create(body=metadata, media_body=media, fields="id")
        .execute()
    )
    drive_id = file.get("id")
    logger.info("Uploaded %s to Drive as %s", filename, drive_id)
    return drive_id
