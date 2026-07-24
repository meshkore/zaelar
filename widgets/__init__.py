"""zaelar WIDGETS — isolated visual-widget layer (catalog + per-widget store). Does NOT touch the voice core."""


async def dispatch_tag(action: str, extra: dict) -> None:
    """Route a [[widget.data:ID]]{"action":..,"payload":{..}} tag from the brain to that widget's OWN
    apply_action — the SAME mutation the widget's UI buttons trigger via ctx.action. This is how the brain manages
    a widget's data (e.g. "add this to my agenda") without ever writing code: it just calls the action the
    widget's data.py already exposes. Routed from the brain's provider (voice/engine/llm/providers/nucleo.py),
    which enforces the FAST/CONFIRM/ESCALATE gate (V2-025) before dispatching here. Never raises: a bad/unknown
    action must not take down the brain's turn — the widget's own apply_action rejects it silently."""
    wid = (extra.get("id") or "").strip().lower()
    data = extra.get("data") or {}
    if not wid or not isinstance(data, dict):
        return
    name = str(data.get("action") or "").strip()
    if not name:
        return
    payload = data.get("payload") or {}
    try:
        from .server_api import brain_action
        await brain_action(wid, name, payload if isinstance(payload, dict) else {})
    except Exception:
        pass
