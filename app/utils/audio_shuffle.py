import os
import random
import threading

_TWILIO_ASSET_BASE = os.environ["TWILIO_ASSET_BASE"].rstrip("/")


class _ClipShuffle:
    def __init__(self, env_var: str):
        self._clips = [
            clip.strip() for clip in os.environ[env_var].split(",") if clip.strip()
        ]
        if not self._clips:
            raise RuntimeError(f"Missing required environment variable: {env_var}")
        self._queue: list[str] = []
        self._lock = threading.Lock()

    def next_url(self) -> str:
        with self._lock:
            if not self._queue:
                shuffled = self._clips[:]
                random.shuffle(shuffled)
                self._queue.extend(shuffled)
            clip = self._queue.pop(0)
        return f"{_TWILIO_ASSET_BASE}/{clip}"


_bea_shuffle = _ClipShuffle("TWILIO_GREETING_CLIPS")
_friend_shuffle = _ClipShuffle("TWILIO_FRIEND_GREETING_CLIPS")


def next_greeting_url(role: str = "bea") -> str:
    if role == "friend":
        return _friend_shuffle.next_url()
    return _bea_shuffle.next_url()
