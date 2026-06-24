import os
import random
import threading

_TWILIO_ASSET_BASE = os.environ["TWILIO_ASSET_BASE"].rstrip("/")

_GREETING_CLIPS = [
    clip.strip()
    for clip in os.environ["TWILIO_GREETING_CLIPS"].split(",")
    if clip.strip()
]

if not _GREETING_CLIPS:
    raise RuntimeError("Missing required environment variable: TWILIO_GREETING_CLIPS")

_queue: list[str] = []
_lock = threading.Lock()


def _refill() -> None:
    shuffled = _GREETING_CLIPS[:]
    random.shuffle(shuffled)
    _queue.extend(shuffled)


def next_greeting_url() -> str:
    with _lock:
        if not _queue:
            _refill()
        clip = _queue.pop(0)
    return f"{_TWILIO_ASSET_BASE}/{clip}"
