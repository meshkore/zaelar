"""A data-op that outlives the turn is WORK IN PROGRESS, not a failure and not a success (node 2.917).

Live, 2026-10-28 17:15: «quítalas todas» over 175 Google rows ran for minutes; the pool answered «timed out after
8s», the turn had no verdict, and the model told the operator «the calendar only lets me cancel them one at a time»
while the rows kept disappearing behind his back. V2-743 already settles a CONFIRMED op this way (start → settle →
witness); this is the same beat for every fast data-op: the turn is told the op is still running (so the next reply
says so, never «done»), the real result is awaited through `widgets.server_api.wait_pending`, and only then the
operator hears the widget's own line — or its refusal — and the request row is settled.
"""
from __future__ import annotations

from loguru import logger


def _note(text: str, wid: str, action: str, row: str) -> None:
    """The op's state on its request's row; the late line is said by `_say`, never twice (V2-851)."""
    from nucleo.events import task_event          # never raises
    task_event.told(text, task_id=row, key=f"op:{wid}:{action}", speak=False)


def _emit(label: str, wid: str, action: str, text: str = "", **extra) -> None:
    """A status line about the op (brain family): never a canvas op, which only `nucleo.acts.canvas.apply` writes."""
    try:
        from voice.observer import emit
        emit("brain", label, text=text[:160], role="system", extra={"cat": "flash", "id": wid, "action": action, **extra})
    except Exception:  # noqa: BLE001
        pass


def _done_line(wid: str, res: dict) -> str:
    """The widget's own line where it has one; else the count it reports; else the plain acknowledgement."""
    from i18n import langs as _langs
    from nucleo.flash import refusal_line as _rl
    said = _rl.speakable(wid, res).strip()
    if said:
        return said
    n = res.get("removed") if isinstance(res.get("removed"), int) else res.get("count")
    if isinstance(n, int) and n > 0:
        return _langs.words("data_done_count", default="Done — {n} items.").replace("{n}", str(n))
    return str(getattr(_langs.current_language(), "data_ack", "") or "Done.")


async def still_running(wid: str, action: str, res: dict, *, seal=None, row: str = "") -> dict:
    """Wait for the hook that outlived the turn and tell the operator what it did. Returns the real result (or the
    timeout result when it never answered). Best-effort end to end: runs in the op's detached task."""
    from nucleo.flash import data_ops as _ops
    from widgets import server_api as _api
    _emit("⏳ data-op sigue en marcha — el turno no la espera", wid, action, text=str(res.get("error") or ""))
    _note(f"The action «{action}» on «{wid}» is still running (longer than the turn): not done, not refused; "
          f"he is told when it ends.", wid, action, row)
    real = await _api.wait_pending(str(res.get("pending") or ""))
    if real is None:
        _emit("⌛ data-op sin respuesta tras la espera", wid, action, is_error=True)
        _settle(row, "unverifiable", "the op never answered")
        return res
    if isinstance(real, dict) and (real.get("ok") is False or (real.get("error") and real.get("ok") is None)):
        try:
            from voice.observer import emit as _ev
            _ev("widget", "action_failed", text=str(real.get("message") or real.get("error") or "")[:160],
                extra={"id": wid, "action": action, "error": str(real.get("error") or ""), "is_error": True})
        except Exception as e:  # noqa: BLE001
            logger.debug(f"op_pending: late failure event not emitted: {e!r}")
        _settle(row, "unmet", str(real.get("message") or real.get("error") or "")[:200])
        _seal(seal, False)
        from nucleo.flash import refusal_line as _rl
        await _say(wid, action, _rl.speakable(wid, real).strip() or _ops._failed_line(), row)
        return real
    line = _done_line(wid, real if isinstance(real, dict) else {})
    _emit("✅ data-op terminada tarde — dicha ahora", wid, action, text=line)
    _settle(row, "met", line[:200])
    _seal(seal, True)
    _note(f"The action «{action}» on «{wid}» finished and he was told: «{line}».", wid, action, row)
    await _say(wid, action, line, row)
    return real


async def _say(wid: str, action: str, line: str, row: str) -> None:
    """The op's late line, out of turn, on its request's row (V2-851 F2). Best-effort."""
    try:
        from nucleo.pulse import notices
        await notices.notify(wid.capitalize(), line, task_id=row, key="" if row else f"op:{wid}:{action}:{line[:40]}",
                             kind="info")
    except Exception as e:  # noqa: BLE001
        logger.debug(f"op_pending: late line not delivered: {e!r}")


def _settle(row: str, verdict: str, outcome: str) -> None:
    if row:
        from nucleo import circuit as _circuit   # the one writer of «done»; it logs and returns on a bad verdict
        _circuit.settle(row=row, verdict=verdict, outcome=outcome)


def _seal(seal, ok: bool) -> None:
    if callable(seal):
        seal(ok)
