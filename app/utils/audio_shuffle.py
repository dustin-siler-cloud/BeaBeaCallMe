import os
import random

_TWILIO_ASSET_BASE = os.environ["TWILIO_ASSET_BASE"].rstrip("/")

_GREETING_CLIPS = [
    "IVR-1-Intro-Clip1.mp3",
    "IVR-1-Intro-Clip2.mp3",
    "IVR-1-Intro-Clip3.mp3",
    "IVR-1-Intro-Clip4.mp3",
    "IVR-1-Intro-Clip5.mp3",
    "IVR-1-Intro-Clip6.mp3",
    "IVR-1-Intro-Clip7.mp3",
    "IVR-1-Intro-Clip8.mp3",
    "IVR-1-Intro-Clip9.mp3",
]

_queue: list[str] = []


def _refill() -> None:
    shuffled = _GREETING_CLIPS[:]
    random.shuffle(shuffled)
    _queue.extend(shuffled)


def next_greeting_url() -> str:
    if not _queue:
        _refill()
    clip = _queue.pop(0)
    return f"{_TWILIO_ASSET_BASE}/{clip}"
