"""nucleo/cli/worker_api_exec.py — executing the ALLOW actions a worker requests (moved from worker_api.py by concern).

Every name that lives in `worker_api` is read as `_m.<name>`, so a test patching it there still governs this code.
"""
from __future__ import annotations

import asyncio

from loguru import logger


def _own_sheet(rec) -> str:
    """This errand's results sheet, OPENED NOW if it has none. Delivering into the bare shared `results` let the
    next sheet-less search replace this one (2026-09-27), so the first delivery mints the errand's own box."""
    from nucleo import sheets as _sh
    sid = _sh.sheet_of(rec)
    if not sid:
        try:
            # A REPORT errand's deliverable is the document (V2-644): mint the box, but don't show it over the doc.
            from nucleo import surfaces as _surf
            _sh._sheet_open(rec, show=not _surf.opens_doc(getattr(rec, "surface", "")))
        except Exception:  # noqa: BLE001 — fail-soft: the base sheet is still a place to deliver
            logger.debug("worker_api: could not open the errand's sheet", exc_info=True)
        sid = _sh.sheet_of(rec)
    return sid


def _decide_deadline(payload: dict) -> float | None:
    """Seconds a worker will wait for a bounded decision, bounded by us (V2-726 A1): its Bash timeout would
    otherwise kill it mid-errand with nothing to report."""
    try:
        d = float((payload or {}).get("deadline_s") or 0)
    except (TypeError, ValueError):
        return None
    return max(0.5, min(d, 20.0)) if d > 0 else None


async def _exec_allow(action: str, payload: dict, rec) -> dict:
    payload = payload or {}
    if action == "decide":
        # V2-726 A1 — the bounded-decision door for a headless worker, through this already-audited bridge.
        # In a thread: `decide` is a blocking round trip and this is a coroutine (V2-726 F2).
        from nucleo import jev as _jev
        cands = (payload or {}).get("candidates") or {}
        if not isinstance(cands, dict):
            cands = {str(i + 1): str(c) for i, c in enumerate(cands)}
        try:
            decision = await asyncio.to_thread(
                _jev.decide,
                str((payload or {}).get("purpose") or ""),
                str((payload or {}).get("evidence") or ""),
                cands,
                abstain=bool((payload or {}).get("abstain", True)),
                source=f"worker:{getattr(rec, 'task_id', '')}",
                task_id=str(getattr(rec, "task_id", "")),
                deadline_s=_m._decide_deadline(payload),
                effect_class=str((payload or {}).get("effect_class") or "view"))
        except Exception as e:  # noqa: BLE001 — a chooser may never break a worker
            return {"ok": False, "error": f"decide falló: {type(e).__name__}"}
        # The worker sees only the decision: `decide` returns its own verdict, so the shape holds by construction.
        return {"ok": True, "result": dict(decision)}
    if action == "use_tool" and payload.get("tool") == "web_search":
        from nucleo.workers import web_search_bridge
        return await web_search_bridge.run(payload, rec)
    if action == "schedule":
        # V2-249 — a scheduled reminder must really exist, or it must not be claimed.
        when = str(payload.get("when") or payload.get("schedule") or "").strip()
        what = str(payload.get("prompt") or payload.get("text") or payload.get("what") or "").strip()
        tid = str(getattr(rec, "task_id", "") or "")
        if not what:
            return {"ok": False, "error": "falta `prompt`: qué tiene que decir o hacer zaelar cuando llegue el "
                                          "momento, escrito como se lo dirías a él."}
        if not when:
            return {"ok": False, "error": "falta `when`: cuándo. " + _m._CUANDO_VALE}
        try:
            from nucleo.pulse import scheduler
            # Machine forms first (`parse_schedule`: every/cron/ISO), then spoken ones (`parse_when`).
            spec = when if scheduler.parse_schedule(when) else (scheduler.parse_when(when) or "")
            if not spec:
                # Ambiguous input parses to "": a reminder on a guessed date is worse than none.
                return {"ok": False, "error": f"«{when}» no me dice un momento exacto y no lo adivino: un aviso "
                                              f"sobre una fecha inventada es peor que ninguno. " + _m._CUANDO_VALE}
            # THE CAP, counted over live jobs by attribution: a looping worker cannot fill the agenda.
            mias = [j for j in scheduler.list_jobs() if f"[worker:{tid}]" in str(j.get("name") or "")]
            if len(mias) >= _m._SCHEDULE_CAP:
                return {"ok": False, "error": f"ya has programado {len(mias)} avisos en esta tarea, que es el "
                                              f"tope. Si necesitas otro, cancela uno o dilo en tu entrega."}
            name = f"{(payload.get('name') or what)[:80]} [worker:{tid}]"
            # V2-480: a cron's reader is the AGENT at another time, so the job tells it to NOTIFY (the agenda's rule)
            from widgets.agenda import notice as _notice
            what = _notice.prompt_for({"commitment": what}) or what
            out = await asyncio.to_thread(scheduler.create_unless_ringing, what, spec, name)   # one alarm per instant
            if not out.get("ok"):
                return {"ok": False, "error": f"{out.get('error') or 'no se pudo programar'}. " + _m._CUANDO_VALE}
            # V2-249 — and make it VISIBLE: a row with the real cron id, the proof of the effect.
            try:
                from voice.observer import emit
                emit("task", "⏰ aviso programado",
                     text=f"{out.get('display') or when} — {what[:120]}",
                     extra={"id": tid, "src": f"worker:{tid}", "cron_id": out.get("id"),
                            "when": out.get("display") or when})
            except Exception:  # noqa: BLE001
                pass
            return {"ok": True, "result": {"id": out.get("id"), "cuando": out.get("display") or when,
                                           "que": what,
                                           "ref": f"cron:{out.get('id')}"}}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": f"no pude programarlo: {e}"}
    if action == "read_widget":
        wid = str(payload.get("id") or payload.get("widget_id") or "")
        try:
            from widgets import runtime
            from widgets.server_api import MISSING, run_widget_hook
            man = runtime.get(wid)
            if not man:
                # Before «does not exist», resolve the name through the registry (id, name, alias).
                from widgets import naming as _nm
                _id, _varios = _nm.resolve(wid)
                if _id:
                    wid, man = _id, runtime.get(_id)
                if not man:
                    return {"ok": False, "error": _nm.not_found(wid, _varios)}

            def _call(view_data):
                try:
                    return view_data(q="")
                except TypeError:            # old widgets without a query argument
                    return view_data()

            # the widget DATA (§7.3: view_data), off-loop and with a timeout — not just the manifest.
            data = await run_widget_hook(wid, "view_data", _call)
            # V2-692c — BOUNDED (a 60 KB agenda answer was unreadable for the worker); V2-707 F1 — plus the
            # collections' structure, so a worker can express an operation nobody declared.
            from widgets import rows as _rows
            _schema = _rows.schema(wid)
            from nucleo.workers import widget_view as _wv
            return {"ok": True, "result": {"manifest": man,
                                           **({"collections": _schema} if _schema else {}),
                                           **_wv.bounded(wid, None if data is MISSING else data)}}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": f"read_widget falló: {e}"}
    if action in ("show_widget", "close_widget"):
        wid = payload.get("id") or payload.get("widget_id") or ""
        # V2-359 — a worker's bare `results` means ITS errand's sheet, never the base card on top of it.
        try:
            if str(wid).strip().lower() == "results":
                from nucleo import sheets as _sh
                # showing is a delivery (its own box, minted now); closing never mints one
                _sid = _m._own_sheet(rec) if action == "show_widget" else _sh.sheet_of(rec)
                if _sid:
                    from widgets.results import data as _rd
                    wid = _rd.instance_id(_sid)
        except Exception:
            pass
        # V2-757 — an id outside the CATALOGUE is not mounted and does not answer `ok` (a «--help» card once
        # appeared on his screen); the error names what exists. Close is not validated: closing nothing is harmless.
        if action == "show_widget":
            _base = str(wid).split("::", 1)[0].strip().lower()
            try:
                from widgets import runtime as _rt
                _ids = sorted(str(w.get("id") or "") for w in _rt.catalog() if w.get("id"))
            except Exception:  # noqa: BLE001 — a broken catalogue may not take the worker down
                _ids = []
            if _ids and _base not in _ids:
                return {"ok": False, "error": f"no widget «{wid}» exists — the ones there are: "
                                              + ", ".join(_ids)}
            # The operator closed this card AFTER this errand began: his decision about his screen (pass 82).
            from nucleo import canvas_closes as _closes
            if _closes.closed_after(wid, float(getattr(rec, "started", 0) or 0)):
                return {"ok": False, "error": f"the operator CLOSED «{_base}» after this errand began — do not "
                                              f"reopen it. Your result stays in the card for when he asks; "
                                              f"say in one line that it is ready."}
        try:
            from nucleo.acts import canvas
            _src = f"worker:{getattr(rec, 'task_id', '')}"        # V2-039: provenance — Brain Worker command
            extra = {}
            _tid = getattr(rec, "trace_id", "")                   # V2-044: HTTP handler without context → session trace
            if _tid:
                extra["trace"] = _tid
                extra["span"] = f"worker:{getattr(rec, 'task_id', '')}"
            # a worker's close names its card: with no id the canvas closes EVERY card (refactor2710-04)
            if not str(wid or "").strip():
                return {"ok": False, "error": "close_widget needs the card it closes"}
            canvas.apply("show" if action == "show_widget" else "close", str(wid), src=_src, **extra)
            return {"ok": True, "result": {"widget": wid}}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e)}
    if action == "widget_data":
        # V2-061 — the same path as the FlashBrain's [[widget.data]] tag, provenance sealed as worker:<id> (V2-039).
        wid = str(payload.get("widget_id") or payload.get("id") or "").strip().lower()
        act = str(payload.get("action") or "").strip()
        data_payload = payload.get("payload") if isinstance(payload.get("payload"), dict) else {}
        if not wid or not act:
            return {"ok": False, "error": "widget_data requiere widget_id y action"}
        # V2-259 — the BRIDGE resolves a bare `results` to this errand's sheet; an explicit `sheet` is respected.
        if wid == "results" and not str(data_payload.get("sheet") or "").strip():
            try:
                _own = _m._own_sheet(rec)
            except Exception:  # noqa: BLE001
                _own = ""
            if _own:
                data_payload = {**data_payload, "sheet": _own}
        try:
            from widgets import runtime
            if runtime.get(wid) is None:
                from widgets import naming as _nm
                _id, _varios = _nm.resolve(wid)
                if _id and runtime.get(_id) is not None:
                    wid = _id
                else:
                    return {"ok": False, "error": _nm.not_found(wid, _varios)}
            try:
                from widgets import provenance as _prov
                _prov.note(wid, f"worker:{getattr(rec, 'task_id', '')}")
            except Exception:
                pass
            from widgets.server_api import brain_action
            res = await brain_action(wid, act, data_payload)
            if isinstance(res, dict) and res.get("error"):
                # V2-707 F1 — a refusal carries its diagnostic half: a message with no way out stops a worker.
                out = {"ok": False, "error": str(res.get("error"))}
                for k in ("detail", "message", "options", "names", "n", "collection", "field",
                          "collections", "needs_confirm"):
                    if res.get(k) not in (None, "", [], {}):
                        out[k] = res[k]
                return out
            # Same ceiling as `read_widget`: some actions answer with the whole view.
            from nucleo.workers import widget_view as _wv
            return {"ok": True, "result": {"widget": wid, "action": act, **_wv.bounded(wid, res)}}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": f"widget_data falló: {e}"}
    if action == "spawn":
        return await _m._spawn_child(payload, rec)
    return {"ok": False, "error": "acción ALLOW no ejecutable"}


async def _spawn_child(payload: dict, rec) -> dict:
    """Chain another Brain Worker within quota/depth limits (§v3·J: DENY when exceeded)."""
    depth = int(getattr(rec, "depth", 0) or 0)
    if depth + 1 > _m._MAX_DEPTH:
        return {"ok": False, "error": "límite de profundidad de cadena alcanzado"}
    req = (payload or {}).get("request") or ""
    if not req:
        return {"ok": False, "error": "spawn sin request"}
    try:
        from nucleo.flash import escalate
        cid = escalate.escalate_to_slowbrain(str(req), context={
            "src": "worker", "kind": (payload.get("kind") or "generic"),
            "parent_task_id": rec.task_id, "depth": depth + 1})
        return {"ok": True, "result": {"child_id": cid}}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"spawn falló: {e}"}


from nucleo.cli import worker_api as _m  # noqa: E402 — last, so importing this module first still resolves
