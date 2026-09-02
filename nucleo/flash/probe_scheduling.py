"""nucleo/flash/probe_scheduling.py — the probe channel's SCHEDULING backstops.

Extracted from `probe.py` (2026-09-02, architecture ratchet: 1248 lines over a 1226 ceiling, of which
`run_turn` alone was 1136 — so the only honest extraction was a slice of that function, not a spare
top-level helper).

WHAT THIS SLICE IS. Three consecutive steps that all answer the same question — «the model talked about a
future notice; did anything actually get scheduled?»:

  1. the model PROMISED a dated reminder in prose and emitted no `[[cron.create]]` → the tag is derived and
     injected (V2-146);
  2. the cron tags in the turn are EXECUTED, not merely captured (V2-121). This step lives apart from the
     `if action == …` dispatch on purpose: a cron tag COEXISTS with a tool call in the same turn — which is
     exactly the turn the use case asks for («apúntame el jueves» → widget_data, «y recuérdamelo el
     miércoles» → cron) — and making them compete for one `action` meant booking the appointment killed
     the notice;
  3. the commitment itself is written to the agenda when the turn promised it and did no data-op (V2-159).

It is a closed unit over `run_turn`'s locals: it reads five of them and its only outward effect besides
its own side effects is APPENDING to `tags`, which the caller passes and keeps. Nothing it binds is read
downstream (verified before the move: `t` is a comprehension target, `_r` is dead after the block).

Every step is marked «espejo del provider — cablear en AMBOS», and that is still true: this module is the
probe half. The voice half lives in `voice/engine/llm/providers/nucleo.py`. Moving the code did not merge
them, and a change to one still has to be made in the other.
"""
from __future__ import annotations


async def run_scheduling_backstops(*, spoken, operator_text, action, tags, sess) -> None:
    """The three scheduling steps, in order. Side effects only; `tags` may be appended to."""
    # PROACTIVIDAD REAL (V2-121, 2026-08-18): las tags de cron se EJECUTAN, no solo se capturan. Va aparte del
    # `if action == …` de abajo a propósito — una tag de cron CONVIVE con una tool en el mismo turno, que es
    # justo el turno que este caso de uso pide («apúntame el jueves» → widget_data add_meeting, «y recuérdamelo
    # el miércoles» → [[cron.create]]); si compitiera por el mismo `action`, apuntar la cita mataría el aviso.
    #
    # Por qué existía el agujero: este módulo es la implementación PARALELA del provider de voz (el fichero lo
    # repite en cada backstop: «cablear en AMBOS»), y el bloque de ejecución solo cubría worker + data-op. El
    # canal `probe` es el que usan los casos de uso, así que el aviso NO PODÍA existir en una corrida por muy
    # bien que el modelo emitiera la tag: `remember-and-remind-deadline` medía un mecanismo inalcanzable.
    # BACKSTOP DE AVISO PROMETIDO (V2-146, espejo del provider — cablear en AMBOS): el modelo prometió el
    # recordatorio en PROSA y no emitió la tag, así que `scheduled_jobs.created` salió vacío mientras el
    # turno decía «te avisaré el miércoles». El ejecutor de abajo funciona (V2-134) y el prompt lo pide con
    # todas las letras: lo que faltaba era hacerlo cuando el modelo no lo hace. Solo con un momento
    # RESOLUBLE — `promises_a_dated_reminder` devuelve "" ante cualquier expresión que no sea inequívoca,
    # porque un aviso mal fechado no se nota hasta el día que no suena.
    if spoken and not any(t.get("action") == "cron.create" for t in tags):
        try:
            from . import router as _routerr
            # V2-153: la decisión ENTERA vive en `dated_reminder_backstop` — antes cada canal componía su
            # propia tag y ninguno miraba lo ya programado, así que dos turnos que prometían el mismo aviso
            # dejaban DOS crons idénticos. Un solo sitio para que la protección no pueda divergir otra vez.
            _cron = _routerr.dated_reminder_backstop(spoken, operator_text, window=sess.window)
            if _cron:
                tags.append({"action": "cron.create", "extra": {"data": _cron}, "backstop": True})
        except Exception:
            pass
    for _t in tags:
        if _t.get("action") not in ("cron.create", "cron.cancel"):
            continue
        try:
            from nucleo import scheduler as _sched
            _ex = _t.get("extra") or {}
            _d = _ex.get("data") or {}
            if _t["action"] == "cron.create":
                # V2-214 (espejo del provider — cablear en AMBOS): si el `prompt` son las palabras del
                # OPERADOR sobre su propia obligación («el jueves tengo que renovar el seguro»), el trabajo
                # se le entrega al agente como un «apunta esto» en vez de un «avísale». El backstop ya
                # componía la forma segura; la tag del modelo entraba cruda por la otra puerta.
                from . import router_guards as _rg_cron
                _r = _sched.create(_rg_cron.safe_reminder_prompt(
                    (_d.get("prompt") or _d.get("task") or "").strip()),
                                   # V2-356 — el HERMANO de la línea de arriba, para el otro campo de la
                                   # misma tag: el `schedule` del modelo entraba igual de crudo, y salió
                                   # «hoy + 5 min» con «wednesday 2026-09-02» delante en el prompt.
                                   _rg_cron.safe_reminder_schedule(
                                       (_d.get("schedule") or _d.get("when") or "").strip(),
                                       spoken, operator_text),
                                   name=(_d.get("name") or "").strip(), repeat=str(_d.get("repeat") or ""))
                _t["executed"] = {"ok": bool(_r.get("ok")), "display": _r.get("display") or "",
                                  "error": _r.get("error") or ""}
            else:
                _t["executed"] = {"ok": bool(_sched.cancel(_ex.get("name") or _d.get("name") or ""))}
        except Exception as _e:  # noqa: BLE001
            _t["executed"] = {"ok": False, "error": str(_e)[:200]}
        # Evento propio (kind `cron`) para que la programación DEJE RASTRO observable, igual que lo deja una
        # data-op o una escalada. Sin él, un aviso correctamente programado es indistinguible de uno que
        # nunca existió salvo consultando la BD — que es justo cómo se coló el fallo de V2-121.
        try:
            from voice.observer import emit as _emit_cron
            _ok = bool((_t.get("executed") or {}).get("ok"))
            _emit_cron("cron", "⏰ tarea programada" if _ok else "⚠️ schedule no reconocido",
                       text=str((_t.get("executed") or {}).get("display")
                                or (_t.get("executed") or {}).get("error") or ""),
                       role="system", extra={"ok": _ok, "op": _t.get("action")})
        except Exception:
            pass
    # BACKSTOP DEL APUNTE CON FECHA (V2-159, espejo del provider — cablear en AMBOS). Hermano del de arriba,
    # para la OTRA mitad del mismo encargo: el caso exige LAS DOS —el compromiso registrado y el aviso—, el
    # prompt lo pide con todas las letras, y la corrida salió con el cron puesto y NINGUNA cita. Solo si el
    # turno no hizo ya la data-op, y solo con un día resoluble: una cita mal fechada es del mismo tamaño que
    # un aviso mal fechado.
    if spoken and action != "widget_data":
        try:
            from . import router as _routern
            _note = _routern.dated_note_backstop(spoken, operator_text, window=sess.window)
            # V2-194: y no dos veces. Su puerta («solo si ESTE turno no hizo ya la data-op») no puede ver
            # una data-op de un turno ANTERIOR, así que la agenda salió con el mismo compromiso dos veces
            # —medido en el sandbox del 2026-08-20 02:34, «Renovar seguro del coche» y «Renovar el seguro
            # del coche» el mismo día—. El hermano tiene esta protección desde V2-153; ésta es peor sin
            # ella, porque un aviso duplicado se oye y una cita duplicada se VE, y se queda.
            if _note and _routern.already_in_agenda(_note):
                _note = None
            if _note:
                import widgets as _wn
                await _wn.dispatch_tag("widget.data", {"id": "agenda", "data": {
                    "action": "add_meeting", "payload": _note}})
                from voice.observer import emit as _emit_note
                _emit_note("widget", "🗓️ cita apuntada por backstop (lo prometió sin emitir la data-op)",
                           text=f"{_note['date']} · {_note['title']}", role="system",
                           extra={"id": "agenda", "act": "add_meeting", "backstop": True})
        except Exception:
            pass
