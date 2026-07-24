"""Minimal session state for the assistant (user name + language)."""
STATE = {"user_name": "", "voice": 0}


def reset_session_state():
    """Deliberate no-op: user_name and the chosen voice PERSIST across reconnects (a reconnect is the normal
    way to apply settings — losing who you are on every reconnect was worse). Kept as the hook every new
    connection calls, so per-session transient state added later has one obvious place to be cleared."""
    pass
