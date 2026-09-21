"""How many data-ops of widget ejecuta UN turn, and cuales (V2-391).

La regla era «UNA by turn», in the two canales, and su reason esta measured: the model small a veces DUPLICA
a `add_meeting` (cita doble) or ENUMERA actions ante «muestrame the agenda» (done/drop/snooze…). Las two son
reales and the two siguen bloqueadas here.

Lo that the regla no contemplaba es that a veces VARIAS son the request. Medido in
`build-a-video-playlist-from-links` (2026-08-27 13:36): the operator pega DOS enlaces and says «montame a lista
with ellos»; `add` only admite a video, so that two enlaces son two llamadas — and only entro the first
(`widget_ops: add: 1`). Despues the `next` is encontro the lista with a only video, the widget devolvio «No there is
mas videos», and the turn anuncio that sonaba the second igualmente: the titulo it sabia by the URL, no by the
lista. 1/5 in result by a alucinacion that empieza siendo a cap nuestro.

El criterion new es mas ESTRECHO that the viejo justo donde importa, and mas wide only donde no: is admiten
varias of the MISMO widget and the MISMA action with payloads DISTINTOS. Un duplicado exacto is colapsa (the cita
doble) and a action DISTINTA sobre the same widget no entra (the enumeracion). El cap continues puesto by if the
model is desboca.

Nota of security: here only llegan the FAST — a action irreversible es CONFIRM and continues necesitando the si
of the operator, so that ampliar esto no amplia it that is can romper without permission.

Vive in su own module and no inside of `router_guards` by the trinquete of file-dios: it that importa es
that the decision sea UNA and shared by the two canales, no in what file esta. `router_guards` already estaba
in su cap, and the trinquete pide extraer, no subirlo.
"""
from __future__ import annotations

import json as _json

from nucleo.flash import op_receipt as _receipt

#: Techo of data-ops by turn. Cinco enlaces pegados of a vez es a request; cincuenta es a model roto.
MAX_DATA_OPS = 5


def _ident(args: dict) -> tuple[str, str, str]:
    """La identidad of a data-op: widget + action + payload, comparable."""
    a = args if isinstance(args, dict) else {}
    pl = a.get("payload") if isinstance(a.get("payload"), dict) else {}
    return (str(a.get("widget_id") or "").strip().lower(),
            str(a.get("action") or "").strip(),
            _json.dumps(pl, sort_keys=True, ensure_ascii=False, default=str))


def admite_data_op(args: dict, ya: list[dict]) -> bool:
    """¿Se ejecuta ESTA data-op, habiendo ejecutado already `already`? Decision shared by the two canales."""
    wid, accion, payload = _ident(args)
    if not wid or not accion:
        return False
    if len(ya) >= MAX_DATA_OPS:
        return False
    for previa in ya:
        p_wid, p_accion, p_payload = _ident(previa)
        if (wid, accion, payload) == (p_wid, p_accion, p_payload):
            return False                      # duplicado exacto → la cita doble
        if wid == p_wid and accion != p_accion:
            return False                      # otra acción sobre el mismo widget → la enumeración
    return True


# ---------------------------------------------------------------------------------------------------
# V2-603 — A DATA-OP THAT FAILED MUST CORRECT THE CLAIM IT ALREADY MADE.
#
# Data-ops are dispatched fire-and-forget (`_spawn` in the brain's provider), which is right: the turn must
# not wait on a widget's network call. The consequence nobody had closed is that the turn SPEAKS FIRST and the
# op resolves after — so when it fails, the spoken sentence is already wrong and nothing ever revisits it.
#
# Measured on the operator's engine (2026-09-06, session e1acdcca, connecting a YouTube account):
# `connect_account` returned `{"ok": False, "error": "sin app OAuth registrada para YouTube…"}`. The exact
# words of the real problem existed, in-process, at 11:19:03. The operator was never told; he was told
# «La autentificación de Google quedó completada», then «Hecho.», then «Te conecto YouTube ahora mismo».
#
# The rails are the ones a finished background worker already uses (`nucleo/flash/escalate.py`): speak it
# through `voice/proactive` AND leave a `[SISTEMA]` note so the NEXT turn also knows. Nothing here invents
# wording for the failure — the widget's own `error`/`message` is what the operator hears, because the widget
# is the only layer that knows why it could not act.
# ---------------------------------------------------------------------------------------------------

#: Failures already announced (wid:action:error → ts), so a card that retries on a timer cannot turn one
#: broken connector into a monologue. Same shape as susurro's repair dedup.
_RECENT_FAILURES: dict[str, float] = {}
_FAILURE_COOLDOWN_S = 90.0


def _dedup(key: str, now: float) -> bool:
    """True if this exact failure was announced within the cooldown. Prunes as it goes."""
    for k, ts in list(_RECENT_FAILURES.items()):
        if now - ts > _FAILURE_COOLDOWN_S:
            _RECENT_FAILURES.pop(k, None)
    if key in _RECENT_FAILURES:
        return True
    _RECENT_FAILURES[key] = now
    return False


async def report_failure(wid: str, action: str, res: dict) -> bool:
    """Announce a FAST data-op that came back `ok: False`. Returns True if the operator was told.

    Best-effort by contract: this runs inside the detached task that dispatched the op, so an exception here
    must not surface anywhere. Silence on a failure is the defect being closed, but a crash while reporting
    one would be worse than the original."""
    import time as _time

    # V2-743 — `error` counts too, and a POOL TIMEOUT does not. Until today this line read only `ok is False`,
    # so `{"error": "widget 'agenda' timed out after 8s"}` — which carries no `ok` at all — returned here and
    # the operator was never told anything (measured 2026-09-21, session bcd4aba1: the timeout reached the
    # timeline and never reached him). `server_api.brain_action` had always read the same result as
    # `error or ok is False` for its `action_failed` event; the two readers disagreed and the quieter one won.
    # The timeout is excluded on purpose: the hook keeps running after the wait gives up, so it is not a
    # verdict — `op_receipt` witnesses those against the widget's own view.
    if not isinstance(res, dict):
        return False
    if _receipt.is_pool_timeout(res) or not _receipt.failed(res):
        return False
    detail = str(res.get("message") or res.get("error") or "").strip()
    if not detail:
        return False
    # V2-652 — the two keys have two AUDIENCES, and only one of them is the operator. `message` is the
    # widget's speakable sentence (the house convention since V2-463/V2-650b); `error` is diagnostic and
    # often literally addressed to the MODEL («vuelve a llamar a add_meeting con el título…»). Measured
    # 2026-09-10 (session 7f77e2cc): that exact retry instruction was spoken aloud and painted into the
    # chat as zaelar's own words, twice. A bare `error` still corrects the model through the note below —
    # it is never voiced and never becomes agent speech.
    speakable = str(res.get("message") or "").strip()
    wid = (wid or "").strip().lower()
    action = (action or "").strip()
    if _dedup(f"{wid}:{action}:{detail}", _time.time()):
        return False

    # The note is an INSTRUCTION to correct, not a line to read out: the brain says it in the operator's
    # language and in its own voice. The raw detail rides along so it cannot be softened into «hubo un
    # problema» — the operator needs the actionable half («falta el client_id»), which is the whole point.
    # V2-707 F0 — and it says that the CORRECTED call will run. `contract.guard` refuses a destructive action
    # whose selector arrived empty and hands back the menu precisely so the next turn can name one; until now
    # nothing here told the model that re-calling was the expected move, while the anti-drag guard was quietly
    # eating the re-call. A retry instruction and a retry guard that contradict each other leave the model
    # with no legal move at all — which is what the timeline of 2026-09-16 shows it concluding.
    note = (f"[SISTEMA] La acción «{action}» sobre «{wid}» NO se ejecutó. Motivo exacto: {detail}. "
            f"Dilo con naturalidad en tu PRÓXIMA respuesta, en el idioma del operador, y NO digas que está "
            f"hecho. Si el motivo indica que falta un paso suyo, dile cuál es. Si lo que falta es un dato que "
            f"puedes poner tú (cuál de los items, un campo vacío), vuelve a llamar a «{action}» con ese dato "
            f"relleno: la llamada corregida SÍ se ejecuta, no es una repetición.")
    told = False
    try:
        from voice import brain_notes
        brain_notes.push(note)
        told = True
    except Exception:
        pass
    if speakable:
        try:
            from voice import proactive
            await proactive.notify("Conector", speakable, speak=True, kind="notify")
            told = True
        except Exception:
            pass
    try:
        from voice.observer import emit
        emit("widget", "🩹 data-op fallida → corregida en voz" if speakable
             else "🩹 data-op fallida → nota al modelo (motivo interno, no se habla)",
             text=detail[:160], extra={"id": wid, "action": action, "told": told,
                                       "spoken": bool(speakable), "is_error": True})
    except Exception:
        pass
    return told


async def dispatch_and_report(wid: str, action_name: str, payload: dict, *, seal=None, receipt: bool = False) -> None:
    """Dispatch a widget data-op AND announce it if it failed (V2-603).

    The dispatch itself stays detached — the turn must never wait on a widget's network call — but the RESULT
    is no longer discarded. Until now the brain spoke its acknowledgement first and the op resolved after, so a
    failure arrived into a conversation that had already claimed success and nothing ever went back to it.
    Measured 2026-09-06 on `youtube:connect_account`: the widget answered with the exact reason it could not
    act, and the operator was told «Hecho.» three times instead.

    `report_failure` owns the wording, the dedup and the rails; this is only the seam that lets it see the
    result. Never raises: it runs in a detached task, where an exception would be logged nowhere useful.

    `seal` (V2-707 F0) is called with whether the op actually HAPPENED, and it is the only place that can
    know: the caller dispatches and returns. The anti-drag guard's memory is written through it, so a
    mutation the door refused is never remembered as executed — see the note at the call site."""
    import widgets
    # V2-743 — the WITNESS is taken BEFORE the op or it witnesses nothing. Only on the `receipt` path (an
    # irreversible action a human already confirmed): paying an extra widget read on every fast data-op would
    # buy nothing and slow the common turn.
    before = await _receipt.read_signature(wid) if receipt else ""
    try:
        res = await widgets.dispatch_tag(
            "widget.data", {"id": wid, "data": {"action": action_name, "payload": payload or {}}})
    except Exception:
        return
    if callable(seal):
        try:
            seal(not (isinstance(res, dict) and res.get("ok") is False))
        except Exception:
            pass
    if receipt:
        # The receipt OWNS the outcome on this path — success, failure and the unknown a pool timeout leaves
        # behind — so `report_failure` must not also speak about the same op.
        try:
            await _receipt.settle(wid, action_name, res, before=before)
        except Exception:
            pass
        return
    try:
        await report_failure(wid, action_name, res)
    except Exception:
        pass


# ── Is this data-op a DRAG from the previous turn? (V2-038 guard, extracted V2-717) ─────────────────────────

def word_overlap(a: str, b: str) -> int:
    wa = {w for w in (a or "").lower().split() if len(w) > 3}
    wb = {w for w in (b or "").lower().split() if len(w) > 3}
    return len(wa & wb)


def is_view_op(wid: str, action: str) -> bool:
    """A LENS, by the widget's own declaration (`"view": true`, V2-545) — the same predicate the canvas arbiter
    reads. Nothing here infers from the name."""
    if not (wid and action):
        return False
    try:
        from widgets import actions as _wactions, runtime
        spec = ((runtime.get(wid.split("::", 1)[0]) or {}).get("actions") or {}).get(action)
        return _wactions.is_view(spec, action)
    except Exception:  # noqa: BLE001
        return False


def is_context_bleed(last, wid: str, action: str, payload: dict | None, said: str, *, now: float | None = None) -> bool:
    """The V2-038 anti-drag rule, unchanged for what it was built for: a MUTATION identical to the one that
    just ran (<120 s), whose content the turn does not even mention, is the model dragging the previous
    turn's op («borra el reloj» dragged the dentist's `add_meeting` → a duplicate appointment). The hatches —
    the sentence names the payload's content, or explicitly orders the replay (V2-650) — stay as they were.

    V2-717 — a VIEW-op is never a drag. Session c502d3ff (2026-09-17): `mensajeria:open {}` ran at 55 s; at
    125 s, 131 s and 171 s the model re-emitted it — «Let me check your Telegram to see what Ivan asked»,
    «Let me open Telegram…», «Let me actually open Telegram now…» — and this guard ate all three as bleed.
    The sentence went out; the act did not. Three promises in a row with nothing behind them, until the
    120 s window simply expired at 197 s and the op went through. It could not be otherwise: the hatch is
    payload-word overlap and a lens carries an empty payload, so for `open`/`show_view`/`close` the hatch can
    never open, whatever the operator says. The guard exists to stop a duplicated WRITE; a lens writes
    nothing and re-opening what is open costs nothing — there is no harm for it to prevent there."""
    import time as _t
    if not last:
        return False
    try:
        l_wid, l_action, l_payload, l_ts = last
    except (TypeError, ValueError):
        return False
    if l_wid != wid or l_action != action or l_payload != (payload or {}):
        return False
    if ((now if now is not None else _t.time()) - l_ts) >= 120:
        return False
    if is_view_op(wid, action):
        return False
    if word_overlap(" ".join(str(v) for v in (payload or {}).values()), said) > 0:
        return False
    try:
        from nucleo.flash import canvas_license as _lic
        if _lic.replay_license(wid, action, said):
            return False
    except Exception:  # noqa: BLE001
        pass
    return True
