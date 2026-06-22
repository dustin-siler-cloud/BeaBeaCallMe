import sqlite3
import os
from config import Config

DB_PATH = os.path.join(Config.DATA_DIR, "ivr.db")


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS recordings (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at      TEXT    NOT NULL,
                caller_id       TEXT,
                duration        INTEGER,
                filename        TEXT    NOT NULL,
                file_size       INTEGER,
                twilio_sid      TEXT,
                gdrive_file_id  TEXT
            )
        """)
        conn.commit()


def log_recording(created_at, caller_id, duration, filename, file_size, twilio_sid, gdrive_file_id=None):
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO recordings (created_at, caller_id, duration, filename, file_size, twilio_sid, gdrive_file_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (created_at, caller_id, duration, filename, file_size, twilio_sid, gdrive_file_id),
        )
        conn.commit()
