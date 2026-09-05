"""A refusal that can be reported honestly.

REFUSALS NAME THE BOUNDARY. A bare 403 makes the agent guess, and a guessing agent tells the user something
invented — so every refusal carries the path it was asked for, why it was refused, and, when the reason is the
allowlist, which folders ARE available. That is the difference between "I can't" and "I can read Documents and
Downloads; that file is in neither".

It lives in its own module because everything in `daemon.fs` raises it and `daemon.http` catches it: a shared
exception that lives inside one of its users is how two modules end up importing each other.
"""
from __future__ import annotations


class Refusal(Exception):
    """`code` is for the engine to branch on, `message` is for a person to read, `folders` carries the allowlist
    when the reason is that the path is outside it."""

    def __init__(self, code: str, message: str, folders: list[str] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.folders = folders or []

    def as_dict(self) -> dict:
        payload: dict = {"ok": False, "error": self.code, "message": self.message}
        if self.folders:
            payload["folders"] = self.folders
        return payload
