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
    try:
        from .server_api import brain_action
        res = await brain_action(wid, name, payload if isinstance(payload, dict) else {})
        return res if isinstance(res, dict) else {"ok": True}
    except Exception as e:  # noqa: BLE001
        # Still never raises to the brain's turn — but the failure now has a VALUE, not just a silence.
        return {"ok": False, "error": str(e)[:200]}
