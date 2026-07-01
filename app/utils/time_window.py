from datetime import datetime, time
from zoneinfo import ZoneInfo

_EASTERN = ZoneInfo("America/New_York")

CONFERENCE_WINDOW_START = time(10, 0)
CONFERENCE_WINDOW_END = time(20, 0)


def is_conference_window_open() -> bool:
    """True between 10:00 AM and 8:00 PM Eastern, regardless of server/container timezone."""
    now = datetime.now(_EASTERN).time()
    return CONFERENCE_WINDOW_START <= now < CONFERENCE_WINDOW_END
