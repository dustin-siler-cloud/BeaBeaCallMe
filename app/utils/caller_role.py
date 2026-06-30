from config import Config


def get_caller_role(caller: str) -> str | None:
    """Returns 'bea', 'friend', or None for a caller not on either allow list."""
    if caller == Config.BEA_CALLER_ID:
        return "bea"
    if caller in Config.FRIEND_CALLERS:
        return "friend"
    return None
