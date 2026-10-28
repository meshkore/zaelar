"""What already happened, as live-state facts: the open harness goals, the data ops that RAN, the cron line with what
is scheduled, the closed sheets. Moved from `nucleo/flash/live_blocks.py` (refactor2710-08b).
"""
from __future__ import annotations


def harness_lines() -> list[str]:
    """V2-660 — open HARNESS goals travel as a fact WITH the rule (V2-453): a card the turn showed whose
    content is still missing must not be narrated as delivered by the next turn. Zero lines when none, and
    fail-open: a ledger that cannot be read costs the prompt nothing (extracted from `prompt.py`, V2-661)."""
    try:
        from nucleo.circuit import harness
        return list(harness.prompt_lines())
    except Exception:  # noqa: BLE001
        return []


def done_ops_lines() -> list[str]:
    """V2-707 F6 — WHAT THE ENGINE ALREADY DID TO HIS DATA, with its rule beside it (V2-453's lesson: the
    fact alone changes nothing).

    Measured 2026-09-16 (session 080b96a7, i=10817 and i=10853): two `clear_range` sweeps had run, nine rows
    were gone, and the turn said «In this conversation I never confirmed a deletion, so nothing has been
    removed from your calendar». That was a correct deduction from the only ledger it could see — the
    PENDING confirmations — because nothing carried the EXECUTED ones. The instruction matters as much as the
    fact: what he is disputing is not whether he said yes, it is whether it happened, and only one of those
    two is a thing we know.

    Zero lines when nothing ran, and fail-open: a ledger that cannot be read costs the prompt nothing.
    """
    try:
        from nucleo import done_ops as _done
        rows = _done.recent()
        if not rows:
            return []
        import time as _t
        # V2-778 F2-19 — an op the request record already shows (`recent_lines`) is not listed twice; what no row
        # shows (a CLICK on the card opens none) still is, and the two rules below stay whenever they apply.
        shown = _shown_by_requests()
        listed = [d for d in rows if not any(w == d["wid"] and a == d["action"]
                                             and abs(float(d.get("at") or 0) - at) <= 60 for w, a, at in shown)]
        away = sorted({d["wid"] for d in rows if not _is_open(d["wid"])})
        if not listed and not any(d.get("destructive") for d in rows) and not away:
            return []
        bits = []
        for d in listed or rows:
            ago = max(0, int(_t.time() - float(d.get("at") or _t.time())))
            n = d.get("n")
            bits.append(f"«{d['wid']}:{d['action']}»" + (f" ({n} fila/s)" if isinstance(n, int) else "")
                        + f" hace {ago}s")
        head = ("YA EJECUTADO SOBRE SUS DATOS en esta sesión (hechos del sistema, no de la conversación): "
                + "; ".join(bits) + ".")
        if any(d.get("destructive") for d in rows):
            return [head + " Eso YA PASÓ. Si el operador dice que has borrado o cambiado algo, TIENE RAZÓN: "
                    "no razones desde si hubo confirmación o no —eso es otra cosa— ni le digas que no se ha "
                    "tocado nada. Dile QUÉ se ejecutó y ofrécele deshacerlo o revisarlo."]
        # Demo pass 59 (S1): «results:present hace 140s» + «cuéntalo como hecho» over a sheet he had put away,
        # and «so how did the monitors go, show me» got «Done.» with the card still in the dock. Done to the
        # DATA is not on the SCREEN: a card that is not open now says so, with the one call that brings it.
        tail = (f" Ojo: {', '.join(away)} NO está en pantalla ahora — si pide verlo, `show_widget` lo trae; "
                "decir «hecho» sin traerlo es mentirle.") if away else ""
        return [head + " Si pregunta por ello, cuéntalo como hecho en vez de volver a hacerlo." + tail]
    except Exception:  # noqa: BLE001
        return []


def _shown_by_requests() -> list[tuple[str, str, float]]:
    """(widget, action, when) of the inline request rows the turn's record block already reports."""
    try:
        from nucleo.circuit import ledger as _tasks
        out = []
        for r in _tasks.store().tasks_where(states=("done", "failed", "running"), modes=("now",), visible_only=False,
                                            limit=24) or []:
            wa = str(r.get("outcome") or "")
            if r.get("kind") == "inline" and ":" in wa and " " not in wa:
                w, a = wa.split(":", 1)
                out.append((w.split("::", 1)[0], a, float(r.get("finished_at") or r.get("started_at") or 0)))
        return out
    except Exception:  # noqa: BLE001 — nothing readable: list everything, as before
        return []


def _is_open(wid: str) -> bool:
    """Whether a card of this widget (base id or any of its instances) is ON SCREEN now — open minus minimized
    (V2-776 L2, the one reader in `nucleo/truth.py`). Fail-open to True: a state that cannot be read must not
    add a warning that may be false."""
    try:
        from nucleo import truth as _truth
        state = _truth.canvas_state(wid)
    except Exception:  # noqa: BLE001
        return True
    return True if state is None else state in ("visible", "maximized")




def _job_line(j: dict) -> str:
    """One scheduled job for the prompt: its bell, and — when it is an appointment's notice — the appointment."""
    import re as _re
    # A date followed by a time, whatever words sit between them — the notice's text is in HIS language.
    m = _re.search(r"(\d{4}-\d{2}-\d{2})\D{1,16}?(\d{1,2}:\d{2})", str(j.get("prompt") or ""))
    when = f"la cita es el {m.group(1)} a las {m.group(2)}; " if m else ""
    return f"{j.get('name')} ({when}el aviso suena {j.get('schedule')})"


def _cron_line() -> str:
    """One line of proactivity (cron tags) plus anything already scheduled, if present. Concise (V2-027).

    The RULE that "a spoken reminder is not a reminder" comes from the `remember-and-remind-deadline` use case
    (V2-121, run 2026-08-18): when told "write it down for Thursday… and remind me on Wednesday," the brain
    answered "Done" and kept claiming in later turns that it was scheduled, with ZERO mechanism behind it. This
    was not model oversight: the catalog literally said a reminder was "acknowledged without a tool," so the
    measured behavior was what the prompt requested. This says the opposite, using the absolute-date format
    `scheduler.parse_schedule` already understands so a specific day can be EXPRESSED in one pass."""
    line = ('Proactividad (recordatorios/tareas programadas): [[cron.create]]'
            '{"schedule":"30m|every 2h|2026-08-19 09:00|0 9 * * *","prompt":"qué avisar","name":"…"}'
            '[[/cron.create]] · [[cron.cancel:name]]. `schedule` admite un plazo relativo, una FECHA ABSOLUTA '
            '(YYYY-MM-DD HH:MM, para un aviso de una sola vez en un día concreto — la fecha la sacas de la lista '
            'de días de tu ESTADO, no la calcules a ojo) o un cron de 5 campos si es RECURRENTE. '
            'Una ORDEN con plazo NO es pedir un recordatorio: «paga la factura antes del día 5» es HACERLO (y si es irreversible, preguntar antes) — apuntarlo en su lugar es no atenderle. REGLA DURA: si el operador pide que le AVISES/RECUERDES algo en un momento dado, emite la tag EN '
            'ESE TURNO — decir «te lo recuerdo» sin ella no programa nada y es mentirle. Si el compromiso tiene '
            'fecha, apúntalo (widget_data add_meeting): crea su aviso (2h antes; sin hora, a las 9); si lo '
            'quiere otro día u hora, va en `remind` de ESE add_meeting, nunca un cron ni otra cita; '
            'moverlo después es set_reminder. La tag es para avisos SUELTOS sin cita detrás. Si falta el '
            'día o la hora, PREGUNTA antes de programar.')
    try:
        from nucleo.pulse import scheduler
        jobs = scheduler.list_jobs(active_only=True)
        if jobs:
            # The time is when the ALERT rings, not when the thing happens (demo pass 2026-09-28, Z1: «ZAELAR
            # weekly review (2026-09-29 07:00)» — the meeting's own 2-hours-early alert — was read back to him as
            # the meeting at 7). The datum says what it is; the meeting's time lives on the agenda.
            # Saying so was not enough (full16 C1: «review at 7, product at 9, meshcore at 1» — every alert
            # time read as its meeting, and C2 then booked Rowan on top of the 3 pm meeting it «ended at 2»).
            # A notice that belongs to an appointment names the appointment's own time next to its bell.
            # …and it is NOT the day's agenda (full25 Z1: «what's on my plate tomorrow» was answered from this line —
            # two of the four meetings, because six notices is not a calendar). Soonest first, and it says so.
            jobs = sorted(jobs, key=lambda j: str(j.get("next_run") or j.get("schedule") or ""))
            line += (" Ya programado (hora a la que SUENA el aviso, no la de la cita — una lista PARCIAL de avisos, "
                     "NO la agenda: lo que hay un día se lee en la agenda con read_widget, nunca de aquí): "
                     + "; ".join(_job_line(j) for j in jobs[:6]) + ".")
    except Exception:
        pass
    return line


def shelf_lines() -> list[str]:
    """The finished errands' sheets he can ask for by what they show — closed, and one `show_widget` away.

    V2-773 (demo S1, 2026-09-27): the monitor errand had finished, its sheet was closed, and «Show me the
    monitors» read «no monitor widget in your setup» — a second worker went to search the same monitors again.
    The sheet was on disk the whole time; the model had no name for it. Three at most, most recent first,
    open ones left out (they are already on screen)."""
    try:
        from memory import api as _memapi
        from widgets import instances as _inst
        open_now = {str(w).strip() for w in ((_memapi.state() or {}).get("open_widgets") or [])}
        try:   # the state keeps BASE ids; a sheet is an instance (demo pass 135: the open monitor sheet listed as closed)
            from server.voice_api import open_instances
            open_now |= {str(w).strip() for w in open_instances()}
        except Exception:  # noqa: BLE001
            pass
        rows = [r for r in _inst.recent_faces(5) if str(r.get("id")) not in open_now][:3]
    except Exception:  # noqa: BLE001
        return []
    if not rows:
        return []
    names = " · ".join(f"«{str(r['label'])[:60]}» ({r['id']})" for r in rows)
    return [f"HOJAS CERRADAS de encargos ya hechos, que puede pedir por lo que muestran — `show_widget` con ese id "
            f"la trae de vuelta, sin buscar nada de nuevo: {names}."]
