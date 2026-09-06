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

    if not isinstance(res, dict) or res.get("ok") is not False:
        return False
    detail = str(res.get("message") or res.get("error") or "").strip()
    if not detail:
        return False
    wid = (wid or "").strip().lower()
    action = (action or "").strip()
    if _dedup(f"{wid}:{action}:{detail}", _time.time()):
        return False

    # The note is an INSTRUCTION to correct, not a line to read out: the brain says it in the operator's
    # language and in its own voice. The raw detail rides along so it cannot be softened into «hubo un
    # problema» — the operator needs the actionable half («falta el client_id»), which is the whole point.
    note = (f"[SISTEMA] La acción «{action}» sobre «{wid}» NO se ejecutó. Motivo exacto: {detail}. "
            f"Dilo con naturalidad en tu PRÓXIMA respuesta, en el idioma del operador, y NO digas que está "
            f"hecho. Si el motivo indica que falta un paso suyo, dile cuál es.")
    told = False
    try:
        from voice import brain_notes
        brain_notes.push(note)
        told = True
    except Exception:
        pass
    try:
        from voice import proactive
        await proactive.notify("Conector", detail, speak=True, kind="notify")
        told = True
    except Exception:
        pass
    try:
        from voice.observer import emit
        emit("widget", "🩹 data-op fallida → corregida en voz",
             text=detail[:160], extra={"id": wid, "action": action, "told": told, "is_error": True})
    except Exception:
        pass
    return told


async def dispatch_and_report(wid: str, action_name: str, payload: dict) -> None:
    """Dispatch a widget data-op AND announce it if it failed (V2-603).

    The dispatch itself stays detached — the turn must never wait on a widget's network call — but the RESULT
    is no longer discarded. Until now the brain spoke its acknowledgement first and the op resolved after, so a
    failure arrived into a conversation that had already claimed success and nothing ever went back to it.
    Measured 2026-09-06 on `youtube:connect_account`: the widget answered with the exact reason it could not
    act, and the operator was told «Hecho.» three times instead.

    `report_failure` owns the wording, the dedup and the rails; this is only the seam that lets it see the
    result. Never raises: it runs in a detached task, where an exception would be logged nowhere useful."""
    import widgets
    try:
        res = await widgets.dispatch_tag(
            "widget.data", {"id": wid, "data": {"action": action_name, "payload": payload or {}}})
    except Exception:
        return
    try:
        await report_failure(wid, action_name, res)
    except Exception:
        pass
