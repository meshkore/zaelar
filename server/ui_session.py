"""server/ui_session.py — the credential of the operator's own screen (2026-10-14).

One random value per boot, held ONLY in this process's memory: never on disk, never in an environment variable,
so a worker (whose reads are free and whose environment is inherited) has nowhere to find it. It travels to the
browser as an HttpOnly, SameSite=Strict cookie, minted by `server/operator_gate.py` only to a process the engine
did not spawn. His page then sends it on every same-origin fetch without any frontend code knowing about it.

A restart mints a new value; the old cookie stops matching, and his next click is admitted the slow way
(`peer_process`) and re-minted — nothing to reload.
"""
from __future__ import annotations

import hmac
import secrets

COOKIE = "zaelar_ui"
_SECRET = secrets.token_urlsafe(32)


def holds(value: str | None) -> bool:
    return bool(value) and hmac.compare_digest(str(value), _SECRET)


def mint(response) -> None:
    response.set_cookie(COOKIE, _SECRET, httponly=True, samesite="strict", path="/")
