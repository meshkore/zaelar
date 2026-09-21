"""A RECEIPT for a transactional op: nothing is called done until the change is on the screen (V2-743).

Measured on the operator's engine, 2026-09-21, session bcd4aba1 — `agenda:clear_range` over 47 appointments:

    i=687  2948.168  brain   ✅ acción irreversible confirmada   agenda:clear_range
    i=689  2948.169  widget  action                              agenda:clear_range      ← dispatched
    i=700  2949.026  transcript zaelar  «Hecho.»                                          ← +0.86 s
    i=706  2956.175  widget  action_failed  widget 'agenda' timed out after 8s             ← +8.0 s

Three separate defects stacked into one sentence:

1. «Hecho.» is a CANNED line fired by the confirm gate the instant the operator says yes (`providers/nucleo.py`,
   the early-confirm branch). It is spoken 0.86 s after the dispatch and 7 s before any outcome exists. It was
   never a report; it was an acknowledgement of the *yes*, wearing the words of a report.

2. The op did not fail. `widgets/server_api` runs a widget hook in a bounded pool under an 8 s timeout, and a
   thread cannot be killed — so the hook KEPT RUNNING and finished the deletion. The operator watched the rows
   disappear about ten seconds later and told us so: «se han borrado, pero se han borrado después de, por lo
   menos, diez segundos, desde que tú me dijeras que habías terminado». A pool timeout is therefore NOT a
   verdict on the work. It is the absence of one.

3. Nothing ever went back to correct the claim. `data_ops.report_failure` only speaks when the result carries
   `ok: False`; a pool timeout carries `{"error": …}` and no `ok` at all, so it returned at its first line.
   `server_api.brain_action` had already got this right for observability (`error or ok is False`) — two readers
   of the same result shape disagreeing, which is why the failure was visible in the timeline and invisible to
   the operator.

His instruction names the rule exactly: «ese arnés debería haberse dado cuenta que tenía que revisar tanto la
memoria como el widget de la pantalla y no haber dicho que está hecho hasta que estuviera todo terminado.
Incluso previamente le tenía que avisar al usuario, me pongo a hacerlo ahora mismo y te aviso.»

So a confirmed irreversible op now runs on three beats instead of one:

    START      the turn says it is GOING to do it (`work_started`), never that it is done.
    SETTLE     when the dispatch resolves, the outcome is read — and a pool timeout falls through to…
    WITNESS    …a re-read of the widget's own `view_data()`, compared against the signature taken before the
               op. The view is what the SCREEN shows and it is derived from the store, so one read answers
               both halves he named. Changed → it landed. Unchanged → it did not.

Only then is anything said. What is spoken is the widget's own `message` where it has one, because the widget
is the only layer that knows what it did.

SCOPE, deliberately narrow: this rides the CONFIRMED path only — an irreversible op a human already said yes
to. Those are rare, already gated, and the ones where a false «Hecho.» costs something. Every fast data-op
keeps its existing shape (speak first, correct on failure, V2-603): paying two extra widget reads on each of
them would buy nothing and slow the common turn.
"""
from __future__ import annotations

import json as _json

#: How a bounded-pool timeout announces itself (`widgets/server_api._run_widget`). Matched on substring and not
#: on equality because the message carries the configured ceiling («timed out after 8s»).
_TIMEOUT_MARK = "timed out after"


def is_pool_timeout(res) -> bool:
    """Did the widget hook outlive the pool's ceiling? Then the RESULT is unknown — the work may well have
    finished, because the thread keeps running after the wait gives up. Never read as a failure."""
    if not isinstance(res, dict):
        return False
    return _TIMEOUT_MARK in str(res.get("error") or "")


def failed(res) -> bool:
    """Did the widget REFUSE or break? The same reading `server_api.brain_action` uses for its `action_failed`
    event — `ok: False` OR a bare `error` — minus the pool timeout, which is not a verdict at all.

    The disagreement between those two readings is the whole of defect 3 above: the timeline knew and the
    operator did not."""
    if not isinstance(res, dict):
        return False
    if is_pool_timeout(res):
        return False
    return res.get("ok") is False or bool(res.get("error"))


def landed(res) -> bool:
    """Did it plainly succeed? Only an explicit `ok: True` counts — silence is not success, which is the
    sentence this whole module exists to stop saying."""
    return isinstance(res, dict) and res.get("ok") is True


def signature(view) -> str:
    """A cheap, order-stable fingerprint of what the widget is SHOWING. Compared before and after, it answers
    «did anything change?» without this module needing to know what `clear_range` means — which it must not,
    because the next action to need a witness will not be this one.

    `view_data()` is the widget's own render payload, so a field that moves on its own (a clock, a «last
    refreshed at») would make every witness read CHANGED. That is the failure direction we can afford: a
    false «it landed» over an op that did land 99 times out of 100 is a nuisance; a false «it did not» would
    send the operator looking for a deletion that already happened."""
    try:
        return _json.dumps(view, sort_keys=True, ensure_ascii=False, default=str)[:20000]
    except Exception:  # noqa: BLE001
        return ""


async def read_signature(wid: str) -> str:
    """Signature of the widget's CURRENT view. Runs through the same isolated pool every widget read uses, so
    a broken card degrades this witness instead of hanging the task that carries it."""
    try:
        from widgets import server_api as _api
        res = await _api.run_widget_hook(wid, "view_data", lambda fn: fn())
        if res is _api.MISSING:
            return ""
        return signature(res)
    except Exception:  # noqa: BLE001
        return ""


def verdict(res, *, before: str, after: str) -> str:
    """`"ok"` | `"failed"` | `"unknown"` — what actually happened, from the result AND the witness.

    The witness only speaks where the result does not: on a pool timeout. `before`/`after` equal means the
    screen did not move, and an op that changed nothing after being confirmed is a failure the operator has
    to hear about, however the wait ended. Empty signatures (a widget with no `view_data`, a read that threw)
    mean we have no witness — `unknown` is then the honest answer, and `unknown` never claims success."""
    if failed(res):
        return "failed"
    if landed(res):
        return "ok"
    if is_pool_timeout(res):
        if not before or not after:
            return "unknown"
        return "ok" if before != after else "failed"
    return "unknown"


def spoken_line(wid: str, action: str, res, outcome: str, lang) -> str:
    """What the operator HEARS when the receipt settles, in the engine's language.

    The widget's own `message` wins wherever it has one (house convention since V2-463): it is the only layer
    that knows what it did. `error` never reaches the mouth — it is diagnostic and frequently addressed to the
    MODEL, and V2-652 measured one of those retry instructions being read aloud as zaelar's own words."""
    res = res if isinstance(res, dict) else {}
    said = str(res.get("message") or "").strip()
    if said:
        return said
    if outcome == "ok":
        return str(getattr(lang, "data_ack", "") or "Hecho.")
    if outcome == "failed":
        detail = str(res.get("error") or "").strip()
        base = str(getattr(lang, "op_failed", "") or "No he podido completarlo.")
        return f"{base} {detail}".strip() if detail and not is_pool_timeout(res) else base
    return str(getattr(lang, "op_unknown", "") or "Lo he lanzado, pero no he podido confirmar que quedara hecho.")


async def settle(wid: str, action: str, res, *, before: str) -> str:
    """Close the receipt: witness what is needed, tell the operator, return the outcome.

    Best-effort from end to end — this runs inside the detached task that dispatched the op, where a raised
    exception is logged nowhere useful. The one thing it will not do is stay silent about a `failed`.
    """
    after = await read_signature(wid) if is_pool_timeout(res) else ""
    out = verdict(res, before=before, after=after)
    try:
        from voice.observer import emit as _emit
        _emit("widget", "🧾 recibo de la orden confirmada",
              text=f"{wid}:{action} → {out}",
              extra={"id": wid, "action": action, "outcome": out,
                     "witnessed": bool(after), "is_error": out != "ok"})
    except Exception:  # noqa: BLE001
        pass
    if out == "ok":
        # Silence is right here ONLY because the change is on his screen — the visible effect is the answer
        # (V2-633), and he asked for the confirmation beat, not for a second one. The note still goes to the
        # model so the next turn knows it finished and does not re-promise it.
        _note(f"[SISTEMA] La acción «{action}» sobre «{wid}» SÍ se completó. No la repitas ni vuelvas a "
              f"prometerla; si él pregunta, confirma que está hecha.")
        return out
    try:
        # `i18n.langs`, NOT the `voice.engine.core.langs` shim its neighbours here still use: that shim exists
        # because reaching into the motor for one sentence is the debt V2-676 moved the table to pay, and the
        # dependency ratchet counts a NEW reach — correctly — as the debt growing back. Same object either way.
        from i18n import langs as _langs
        _lang = _langs.current_language()
    except Exception:  # noqa: BLE001
        _lang = None
    line = spoken_line(wid, action, res, out, _lang)
    _note(f"[SISTEMA] La acción «{action}» sobre «{wid}» NO quedó confirmada ({out}). Dilo con naturalidad en "
          f"tu PRÓXIMA respuesta, en el idioma del operador, y NO digas que está hecha.")
    try:
        from voice import proactive
        await proactive.notify("Agenda" if wid == "agenda" else wid.capitalize(), line, speak=True, kind="notify")
    except Exception:  # noqa: BLE001
        pass
    return out


def _note(text: str) -> None:
    try:
        from voice import brain_notes
        brain_notes.push(text)
    except Exception:  # noqa: BLE001
        pass
