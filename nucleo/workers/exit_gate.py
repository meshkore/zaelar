"""nucleo/workers/exit_gate.py — a worker act that LEAVES the machine crosses the message door (V2-851 F2, §4a/§15c).

Measured in F0: a worker's `widget_data` reached `server_api.brain_action` through the SAME consent rule as Flash but
skipped everything `nucleo/acts/message` does around a send — the recipient put back in his word, the held row, the
someone-else's-text check — and `card.licence`; and no worker exit read the taint. This is that door, reused, never
rebuilt; `worker_api.worker_act` asks it before executing, after the consent policy and `on_his_behalf`:

  · `card.licence` at LEAVES and FAST — a vetoed call is refused to the worker with its reason (e.g. the identical
    retry of a refused op);
  · `message.his_recipient` — a contact the worker swapped for one his words never said goes back to HIS word, so
    the card asks «which one»;
  · `message.release` / `asked_if_leaving` — the held row and the leave rule; the stranger's-text half reads THIS
    session's taint, not Flash's window;
  · **taint (§4a)** — `taint_question`: while the session has consumed a stranger's text since its last confirmed
    act, an exit is ASK_CONSENT unless the session runs under an explicit mandate that covers it
    (`nucleo/errands/mandate.py`). Freedom of reasoning, zero freedom of consequence (`party.py`): the worker may
    read anything; what leaves after reading it waits for his yes.

Every exit the worker reaches calls `taint_question`: a leaving `widget_data` (here), `mesh_serve` (the errand text
to a third-party agent) and the browser's submit (`widgets/navegador/click_gate.py`).
"""
from __future__ import annotations

from dataclasses import dataclass

from loguru import logger


@dataclass(frozen=True)
class Exit:
    payload: dict           # the call as it may run (his word put back in place of a swapped recipient)
    question: str = ""      # non-empty: ask him first (the worker's ordinary CONFIRM)
    refused: str = ""       # non-empty: vetoed, said to the worker


def _emit(label: str, text: str, extra: dict) -> None:
    try:
        from voice.observer import emit
        emit("task", label, text=text, role="system", extra=extra)
    except Exception as e:  # noqa: BLE001 — the trace never stops the gate
        logger.debug(f"exit_gate: event not emitted ({e!r})")


def leaves(wid: str, act: str) -> bool:
    """Does this declared action leave the machine (`external.send`)? Unreadable → it leaves (it asks)."""
    try:
        from widgets import effects as _fx
        return bool(_fx.carries(wid, act, _fx.EXTERNAL_SEND))
    except Exception as e:  # noqa: BLE001
        logger.debug(f"exit_gate: effects unread for {wid}:{act} ({e!r})")
        return True


def under_mandate(rec, kind: str, channel: str = "") -> bool:
    """Does the session's mandate cover this exit? `message` reads the errand rule itself (`mandate.covers`); any
    other kind must be named in `may`. No mandate → no."""
    m = getattr(rec, "mandate", None)
    if not isinstance(m, dict) or not m:
        return False
    if kind == "message":
        from nucleo.errands import mandate
        return mandate.covers({"mandate": m}, channel)
    return kind in [str(x) for x in (m.get("may") or [])]


def taint_question(rec, kind: str, action: str, target: str, channel: str = "") -> str:
    """'' when this exit may go; else the question for him — the session read a stranger's text since his last yes."""
    from nucleo.workers import taint
    if not taint.tainted(rec) or under_mandate(rec, kind, channel):
        return ""
    _emit("🛑 sale fuera tras leer texto de terceros — se le pregunta", f"{action} → {target}",
          {"id": str(getattr(rec, "task_id", "")), "exit": kind, "action": action, "target": target[:120]})
    try:
        from i18n import langs as _lg
        return _lg.current_language().worker_confirm_tainted.format(action=action, target=target or "?")
    except Exception:  # noqa: BLE001
        return f"{action} → {target}?"


def gate(rec, payload: dict) -> Exit:
    """The message door for one `widget_data` call of a worker. A call that does not leave passes untouched."""
    from nucleo import on_his_behalf as _ob
    wid, act, inner = _ob._resolve(payload or {})
    if not wid or not act or not leaves(wid, act):
        return Exit(payload)
    said = " ".join(_ob.errand_words(rec))
    from nucleo.acts import card, message
    for at in (card.LEAVES, card.FAST):
        lic = card.licence({"text": said, "brief": None}, wid, act, inner, at=at)
        if lic.verdict == card.DROP:
            _emit(lic.label or "🛑 vetoed", lic.text, {**(lic.extra or {}), "id": str(getattr(rec, "task_id", ""))})
            return Exit(payload, refused=f"{wid}:{act} not run ({lic.clause}): {lic.text}")
    out = dict(payload or {})
    if not str(out.get("action") or "").startswith("rows."):
        mine = message.his_recipient(wid, act, inner, said,
                                     emit=lambda _k, label, text="", **kw: _emit(label, text, kw.get("extra") or {}))
        if mine is not inner:
            out["payload"], inner = mine, mine
    from nucleo.workers import taint
    from widgets import actions as _wa
    who = ", ".join(_ob.who_of(wid, act, inner)) or wid
    channel = str(inner.get("platform") or inner.get("channel") or "")
    stranger = taint.tainted(rec) and not under_mandate(rec, "message", channel)
    mode = message.release(_wa.FAST, wid, act, inner, None)
    mode = message.asked_if_leaving(mode, None, wid, act, payload=inner, said=said, stranger=stranger)
    q = taint_question(rec, "message", act, who, channel)
    if not q and mode == _wa.CONFIRM:
        # the leave rule's question: a recipient his words do not name (with the taint: one only a stranger named)
        try:
            from i18n import langs as _lg
            q = _lg.current_language().worker_confirm_on_behalf.format(action=act, who=who)
        except Exception:  # noqa: BLE001
            q = f"{act} · {who}?"
    return Exit(out, question=q)


def mesh(rec, payload: dict) -> Exit:
    """`mesh_serve`: the errand text leaves to a third-party agent. Outbound scan first (`scan_outbound`, the cluster's
    detector: a hard secret sends nothing, identity terms are redacted), then the one consent rule for this class with
    his standing rules (`errand.mesh_serve`), then the taint. The text that may leave is handed back to the bridge."""
    p = dict(payload or {})
    text = str(p.get("prompt") or p.get("errand") or "")
    try:
        from connectors.meshkore import security
        safe, block = security.scan_outbound(text)
    except Exception as e:  # noqa: BLE001 — a scan that could not run is not a licence to send
        return Exit(p, refused=f"the outbound scan could not run ({type(e).__name__}): nothing was sent")
    if block:
        _emit("🛑 texto de encargo con un secreto — no sale a la red", block,
              {"id": str(getattr(rec, "task_id", "")), "exit": "mesh"})
        return Exit(p, refused=f"the errand text carries a {block}: nothing was sent to a third-party agent — "
                               f"write the request without it")
    p["prompt"] = safe
    from nucleo import consent
    v = consent.decide_act("errand.mesh_serve", channel="mesh", level="standard", licensed=True)
    if v.get("verdict") == consent.REFUSE:
        return Exit(p, refused=f"his rule forbids it: {v.get('why') or 'mesh'} — nothing was sent")
    target = str(p.get("agent") or "") or str(p.get("errand") or "")[:60]
    q = taint_question(rec, "mesh", "mesh serve", target)
    if not q and consent.asks(v):
        try:
            from i18n import langs as _lg
            q = _lg.current_language().worker_confirm_generic.format(action=f"mesh serve → {target}")
        except Exception:  # noqa: BLE001
            q = f"mesh serve → {target}?"
    return Exit(p, question=q)
