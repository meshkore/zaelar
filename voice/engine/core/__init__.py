"""Common core: config, profiles, generic registry, logging, state machine."""
from .config import ZAELAR_ROOT, SETTINGS
from .logging import JsonlEventLog, setup_console_logging
from .profile import PROFILE
from .registry import Registry
from .state import State, StateMachine

__all__ = [
    "SETTINGS",
    "ZAELAR_ROOT",
    "PROFILE",
    "Registry",
    "JsonlEventLog",
    "setup_console_logging",
    "State",
    "StateMachine",
]
