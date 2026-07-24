"""Conversation state machine: Idle / Listening / Thinking / Speaking / Interrupted.

Maps LiveKit's fine-grained agent/user states onto the five product states, adds
the derived ``Interrupted`` (user speaks over the agent = barge-in), and calls a
sink on every transition (logged + mirrored to the browser).
"""
from __future__ import annotations

from enum import Enum
from typing import Callable


class State(str, Enum):
    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"
    INTERRUPTED = "interrupted"


_AGENT_MAP = {
    "initializing": State.IDLE,
    "listening": State.LISTENING,
    "thinking": State.THINKING,
    "speaking": State.SPEAKING,
}


class StateMachine:
    def __init__(self, on_change: Callable[[State], None] | None = None) -> None:
        self._state = State.IDLE
        self._on_change = on_change

    @property
    def state(self) -> State:
        return self._state

    def _set(self, new: State) -> None:
        if new == self._state:
            return
        self._state = new
        if self._on_change:
            self._on_change(new)

    def on_agent_state(self, new_state: str) -> None:
        mapped = _AGENT_MAP.get(new_state)
        if mapped is not None:
            self._set(mapped)

    def on_user_state(self, new_state: str) -> None:
        # Barge-in: user starts talking while the agent is speaking.
        if new_state == "speaking" and self._state == State.SPEAKING:
            self._set(State.INTERRUPTED)
