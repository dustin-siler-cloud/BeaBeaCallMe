import random

_TWILIO_ASSET_BASE = "https://your-service-name.twil.io"

_GREETING_CLIPS = [
    "IVR-1-Intro-Bluey.mp3",
    "IVR-1-Intro-Goofy.mp3",
    "IVR-1-Intro-KpopJinu.mp3",
    "IVR-1-Intro-KpopZoey.mp3",
    "IVR-1-Intro-Leela.mp3",
    "IVR-1-Intro-Minnie.mp3",
    "IVR-1-Intro-MsRachel.mp3",
    "IVR-1-Intro-ProfFarnsworth.mp3",
    "IVR-1-Intro-Zoidberg.mp3",
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
