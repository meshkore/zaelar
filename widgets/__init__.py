"""zaelar WIDGETS — isolated visual-widget layer (catalog + per-widget store). Does NOT touch the voice core."""


async def dispatch_tag(action: str, extra: dict) -> dict:
    """Route a [[widget.data:ID]]{"action":..,"payload":{..}} tag from the brain to that widget's OWN
    apply_action — the SAME mutation the widget's UI buttons trigger via ctx.action. This is how the brain manages
    a widget's data (e.g. "add this to my agenda") without ever writing code: it just calls the action the
    widget's data.py already exposes. Routed from the brain's provider (voice/engine/llm/providers/nucleo.py),
    which enforces the FAST/CONFIRM/ESCALATE gate (V2-025) before dispatching here. Never raises: a bad/unknown
    action must not take down the brain's turn — the widget's own apply_action rejects it silently.

    V2-603 — RETURNS THE RESULT. It used to `await brain_action(...)` and drop the value on the floor, so a
    data-op that FAILED was, to the brain, indistinguishable from one that worked. Measured on the operator's
    engine (2026-09-06, session e1acdcca, connecting a YouTube account): `connect_account` answered
    `{"ok": False}` at 11:19:03 — the failure reached observability as `widget/action_failed` and reached
    nobody else — and twelve seconds later the agent said «La autentificación de Google quedó completada».
    Four such claims in ninety seconds, one real action, zero connections.

    The caller is fire-and-forget (`_spawn`), so this value cannot make the turn wait; what it enables is the
    CORRECTION that follows it (`nucleo/flash/data_ops.report_failure`). Shape kept deliberately flat —
    `{"ok": bool, ...}` — because that is what every `apply_action` already answers.
    """
    wid = (extra.get("id") or "").strip().lower()
    data = extra.get("data") or {}
    if not wid or not isinstance(data, dict):
        return {"ok": False, "error": "bad dispatch envelope"}
    name = str(data.get("action") or "").strip()
    if not name:
        return {"ok": False, "error": "no action named"}
    payload = data.get("payload") or {}
    # A CARD of an instancing widget (`results::be35a9-1`) is the base widget with its instance in `q` — the
    # canvas's own convention (it splits `results::<corr>` and hands the suffix over as `q`). Passed through
    # verbatim, the trust boundary's `_safe` stripped the colons into `resultsbe35a9-1`, no such widget, and
    # «Compare them visually» failed on the sheet it had just opened (V2-776, 2026-09-27).
    if "::" in wid:
        wid, _inst = (x.strip() for x in wid.split("::", 1))
        if _inst and isinstance(payload, dict) and not payload.get("sheet") and not payload.get("q"):
            payload = {**payload, "q": _inst}
    # V2-776 K1 — a send that cites a meeting carries the agenda's time, not the model's memory (pass 56: «now
    # at 5:00 PM» over a 16:30 meeting). One seam for every FAST data-op of the model; the UI route is not this.
    try:
        from nucleo.flash import meeting_time as _mt
        _aligned, _why = _mt.align_payload(wid, name, payload if isinstance(payload, dict) else {})
        if _why:
            payload = _aligned
            try:
                from voice.observer import emit as _emit_mt
                _emit_mt("brain", "🕒 hora del mensaje corregida con la agenda", role="system", text=_why,
                         extra={"cat": "flash", "id": wid, "action": name})
            except Exception:  # noqa: BLE001
                pass
    except Exception:  # noqa: BLE001
        pass
    try:
        from .server_api import brain_action
        res = await brain_action(wid, name, payload if isinstance(payload, dict) else {})
        return res if isinstance(res, dict) else {"ok": True}
    except Exception as e:  # noqa: BLE001
        # Still never raises to the brain's turn — but the failure now has a VALUE, not just a silence.
        return {"ok": False, "error": str(e)[:200]}
