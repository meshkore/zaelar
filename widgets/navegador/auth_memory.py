#
# auth_memory.py: browser-auth MEMORY crumbs (INI-016, auth).
#
# Memory <-> storage split (`zaelar-memory.md` actions <-> memory protocol): the SECRET itself (cookies/tokens)
# NEVER enters memory. It lives in Chromium's persistent on-disk profile (`widgets/_data/navegador/profile/`),
# encrypted at rest by the OS. Memory stores only what zaelar should remember as a human:
#
#   - record_session_established(site) -> recallable EVENT saying there is a session on <site> since <date>, with a
#     per-site `slot` so a re-login SUPERSEDES instead of duplicating. Mirrors `widgets/lifecycle.record_created`.
#   - checkpoint_auth_pending / clear_auth_pending -> DURABLE crumb for a HALF-DONE login. Browser tasks live in
#     RAM and a restart kills them (`tasks.py`), so the checkpoint does NOT persist the task: it leaves a trace in
#     STATE memory (`memory.set_state`, mirroring `nucleo/reset.py`) plus a short event. At startup, zaelar can read
#     `read_auth_pending()` and remember that the operator left a login halfway through.
#
# Sanctioned writer through the `memory.write`/`set_state` facade (async, loop-agnostic queue), just like
# `widgets/lifecycle.py`. Everything is best-effort: a memory failure NEVER breaks the auth flow.
#
from __future__ import annotations

import time

from loguru import logger


def _memory():
    from memory import api as memory
    return memory


def record_session_established(site: str) -> None:
    """Register in memory the fact that `site` has a logged-in session. Recallable; the secret is NOT stored.
    Per-site `slot` means a re-login supersedes the previous fact instead of accumulating duplicates. Best-effort."""
    site = (site or "").strip().lower()
    if not site:
        return
    when = time.strftime("%Y-%m-%d")
    try:
        _memory().write(
            f"[navegador:auth] There is a logged-in session on '{site}' since {when}; the browser enters with the "
            f"operator's account. Credentials live in the browser profile, not here.",
            kind="event", level="mid", importance=0.55, slot=f"navegador.session.{site}",
            meta={"entity": site, "source": "navegador.auth", "said_at": when},
        )
    except Exception as e:  # noqa: BLE001
        logger.warning(f"auth_memory: record_session_established failed: {e}")


def checkpoint_auth_pending(site: str, task_id: str = "", goal: str = "") -> None:
    """Freeze in STATE that a login is half-done (recoverable after crash/restart) and record a short event.
    Mirrors the Reset freeze->record sequence. Best-effort."""
    site = (site or "").strip().lower()
    ts = time.strftime("%Y-%m-%d %H:%M")
    try:
        m = _memory()
        m.set_state({"auth_pendiente": {
            "sitio": site, "tarea": task_id, "objetivo": (goal or "")[:200], "cuando": ts,
        }})
        m.write(
            f"[navegador:auth] A login was left half-done on '{site}' ({ts}); if the operator did not finish it, "
            f"remind them and offer to resume.",
            level="short", kind="event", importance=0.6,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning(f"auth_memory: checkpoint_auth_pending failed: {e}")


def clear_auth_pending() -> None:
    """Clear the half-done-login crumb because the operator finished or cancelled it. Best-effort."""
    try:
        _memory().set_state({"auth_pendiente": None})
    except Exception as e:  # noqa: BLE001
        logger.warning(f"auth_memory: clear_auth_pending failed: {e}")


def read_auth_pending() -> dict | None:
    """Read the half-done-login crumb from STATE for startup notice after restart. Best-effort -> None."""
    try:
        return (_memory().state() or {}).get("auth_pendiente") or None
    except Exception:
        return None
