"""The widget half of the turn's tool executor (V2-778 F1, 2026-10-01).    def _handle_widget_data_tool(args: dict) -> None:

Split out of `nucleo/flash/tool_executor.py` (1,271 lines) with no behaviour change: the tags the brain emits, the
confirm-gate requests and the widget-data path. `build()` takes the SAME keyword arguments as
`tool_executor.build` (the names these closures close over) plus `_late`, a dict through which `_tag_emit`
reaches `_on_tool_call`, which is built after this half. `tool_executor.build` calls this first and binds every
closure back under its own name, so the order of the executor's code is the order it had in `_run_inner`.
"""
from __future__ import annotations

import time
from types import SimpleNamespace

from loguru import logger

from nucleo.flash import (canvas_license as _canvas_lic,
                          canvas_visibility as _cvis, close_guards as _closeg, data_ops as _data_ops,
                          direct_action as _direct_action, show_target as _show_target)
from nucleo.flash import leave_gate as _leave_gate  # V2-778 F4-33, read as _txw._leave_gate
from voice import brain_notes as _bnotes
from widgets import confirm as _wconfirm


def build(*, self, brain, emit, text, operator_text, _brief, canvas_h, aside, cron_seen, _shown_ids, acted, confirm_state, clarify, _closed_by_tool, _repeat_repair, data_done, deduped, escalate_req, search_req, listing_req, recall_req, read_req, reopen_req, reveal_req, music_req, images_req, style_fired, worker_acted, _frontend, _router, _tool_fired, _data_ops_hechas, _turn_op_tasks,
          _spawn, _say, _resolve_pending_confirm, _confirm_decide, _close_target, _identify, _identify_is_widget, _is_meta_widget_question, _norm_nfkd, _show_guard_target, _show_target_instance, with_also_named, _late):
    """The widget half of ONE turn's executor; returns its closures by name."""
    def _on_tool_call(name: str, args: dict) -> None:
        _late["on_tool_call"](name, args)

    def _tag_emit(action: str, extra: dict) -> None:
        # V2-778 F1 — the body lives in `nucleo/flash/tool_executor_widget_calls.py`; this closure passes what it closed over.
        return _txw_calls._tag_emit(action, extra, _apply_widget_data=_apply_widget_data, _brief=_brief, _is_meta_widget_question=_is_meta_widget_question, _norm_nfkd=_norm_nfkd, _on_tool_call=_on_tool_call, _request_delete_confirm=_request_delete_confirm, _show_guard_target=_show_guard_target, _show_target_instance=_show_target_instance, _shown_ids=_shown_ids, _spawn=_spawn, acted=acted, aside=aside, brain=brain, canvas_h=canvas_h, cron_seen=cron_seen, deduped=deduped, emit=emit, escalate_req=escalate_req, text=text)

    def _request_delete_confirm(widget_id: str, turn_text: str) -> None:
        """FlashBrain pide BORRAR un widget → abre la CONFIRMACIÓN (overlay Sí/No en la tarjeta); el borrado
        real solo ocurre al confirmar. Resuelve el id flojito contra el catálogo (el modelo/STT no siempre
        dan el id exacto)."""
        try:
            wid = (widget_id or "").strip().lower()
            if not wid or not _identify_is_widget(wid):
                wid = _identify(widget_id or turn_text) or wid
            if not wid:
                emit("brain", "⚠️ borrar: no identifiqué el widget", text=widget_id or turn_text[:80])
                return
            # GUARD cerrar≠borrar (V2-045, invariante V2-017): el modelo a veces llama a delete_widget para
            # 'CIERRA el widget de X' (cerrar es reversible, borrar es PARA SIEMPRE). Si el turno dice cerrar y
            # NO dice borrar, es un CLOSE → no abrir confirmación de borrado. Determinista (no depende del LLM).
            from nucleo.flash import router as _router
            if _router.looks_like_close(turn_text):
                _t = _close_target(wid, turn_text)
                if _t["ask"]:                       # V2-259 F3: varias tarjetas de esa pieza → se PREGUNTA
                    clarify["msg"] = _t["ask"]
                    emit("brain", "❓ cerrar: varias tarjetas abiertas", text=wid, role="system",
                         extra={"options": _t["options"]})
                    return
                for _cid in with_also_named(_t.get("ids") or [_t["id"] or wid], turn_text):
                    emit("widget", "close", extra={"id": _cid, "src": "flash"})
                    _canvas_lic.note_operator_close(_cid)                 # V2-650b
                emit("brain", "🙈 cerrar (no borrar) — guard cerrar≠borrar", text=wid, role="system")
                acted["widget"] = True
                acted["closed"] = True
                return
            _wconfirm.request("delete", wid, _say().widget_delete_confirm,
                              notify_ui=_wconfirm.ui_paints(wid))
            confirm_state["opened"] = _say().widget_delete_confirm_named.format(wid=wid)
            emit("brain", "🗑️ confirmación de borrado pedida", text=wid, role="system")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"delete confirm request falló: {e}")

    def _request_restore_confirm(widget_id: str, turn_text: str) -> None:
        """FlashBrain asks to RESTORE a widget to its shipped version (V2-515) → confirm first: discarding
        the operator's fork is destructive for THEIR work. Resolution + registration live in
        widgets/confirm.py::request_restore (widget-domain logic, per this file's ratchet)."""
        try:
            r = _wconfirm.request_restore(widget_id or turn_text)
            if not r:
                clarify["msg"] = _say().widget_restore_nothing
                emit("brain", "⚠️ restaurar: nada que restaurar con ese nombre",
                     text=(widget_id or turn_text)[:80], role="system")
                return
            confirm_state["opened"] = r["question"]
            emit("brain", "⟲ confirmación de restauración pedida", text=r["wid"], role="system")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"restore confirm request failed: {e}")

    def _request_data_confirm(widget_id: str, action_name: str, payload: dict) -> None:
        """El FlashBrain quiere ejecutar una data-op IRREVERSIBLE (`confirm:true` en el manifest, V2-025) →
        abre la CONFIRMACIÓN (overlay Sí/No en la tarjeta) guardando la MUTACIÓN; solo al decir "sí" se
        despacha por `apply_action` — jamás se escala a código. Espejo de `_request_delete_confirm`.

        The VERDICT is `confirm_gate.decide` (V2-707 F6): a radius that contradicts the count in his
        order, or a radius of zero, registers nothing at all — see that module for the measurement."""
        try:
            d = _confirm_decide(widget_id, action_name, payload or {}, text)
            if not d:
                return
            if d["kind"] != "ask":
                clarify["msg"] = d["sentence"]
                emit("brain", "⛔ el alcance no es el que pidió — no abro confirmación"
                     if d["kind"] == "mismatch" else "🫙 nada que borrar — no abro confirmación",
                     text=f"{d['wid']}:{d['action']}", role="system",
                     extra={"cat": "flash", "asked": d.get("asked"), "n": d.get("n")})
                return
            _wconfirm.request("data", d["wid"], d["question"], op=d["op"],
                              notify_ui=_wconfirm.ui_paints(d["wid"]))
            confirm_state["opened"] = d["question"]
            emit("brain", "⚠️ confirmación de acción irreversible pedida",
                 text=f"{d['wid']}:{d['action']}", role="system")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"data confirm request falló: {e}")

    def _request_cluster_confirm(name: str, cluster_id: str, token: str, handle: str | None,
                                 perms: dict | None = None, vis: str = "") -> None:
        """Opening a real socket to an unknown cluster asks the operator FIRST, deterministically — the
        tool's own description ('only if the operator asks') was not enough: a pasted block that merely
        MENTIONED a cluster_id made the model connect anyway and then claim it already had. The Yes/No is
        painted on the ChatWall's native «Clusters» tab, not on a card. Why, and the two bugs behind it:
        `.meshkore/docs/decisions.md` (V2-086) and `decisions-archive.md` (V2-064)."""
        try:
            q = _say().cluster_connect_confirm.format(name=name, cid=cluster_id[:10])
            _payload = {"name": name, "cluster_id": cluster_id, "token": token, "handle": handle}
            if vis:
                _payload["vis"] = vis              # V2-086: cluster PÚBLICO (sin token) → viaja al connect
            if perms:
                _payload["perms"] = perms          # V2-076: la concesión viaja con la conexión → store.set_perms
            _wconfirm.request("data", _wconfirm.NATIVE_CLUSTERS, q,
                             op={"action": "connect_cluster", "payload": _payload})
            confirm_state["opened"] = q
            emit("brain", "🛰 confirmación de conexión a cluster pedida", text=name, role="system")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"cluster confirm request falló: {e}")

    def _resolve_confirm(ok: bool) -> bool:
        """Wrapper de turno sobre `_resolve_pending_confirm` (función de módulo, V2-090 addenda): añade el
        bookkeeping de ESTE turno (`acted["widget"]`) que la versión de módulo no puede conocer. La lógica de
        ejecución vive una sola vez, en `_resolve_pending_confirm` — este turno y el chequeo TEMPRANO de más
        arriba (antes del streaming) llaman a la MISMA función, nunca a una copia."""
        resolved = _resolve_pending_confirm(ok)
        if resolved:
            acted["widget"] = True
        return resolved

    def _apply_widget_data(wid: str, action_name: str, payload: dict, ref: str = "") -> None:
        # V2-778 F1 — the body lives in `nucleo/flash/tool_executor_widget_calls.py`; this closure passes what it closed over.
        return _txw_calls._apply_widget_data(wid, action_name, payload, ref, _apply_widget_data=_apply_widget_data, _brief=_brief, _frontend=_frontend, _request_data_confirm=_request_data_confirm, _spawn=_spawn, _tag_emit=_tag_emit, _turn_op_tasks=_turn_op_tasks, acted=acted, brain=brain, data_done=data_done, deduped=deduped, emit=emit, escalate_req=escalate_req, text=text)

    def _handle_widget_data_tool(args: dict) -> None:
        # V2-778 F1 — the body lives in `nucleo/flash/tool_executor_widget_calls.py`; this closure passes what it closed over.
        return _txw_calls._handle_widget_data_tool(args, _apply_widget_data=_apply_widget_data, _brief=_brief, _frontend=_frontend, _identify=_identify, _repeat_repair=_repeat_repair, _say=_say, _tag_emit=_tag_emit, acted=acted, brain=brain, clarify=clarify, deduped=deduped, emit=emit, escalate_req=escalate_req, text=text)

    def _word_overlap(a: str, b: str) -> int:
        wa = {w for w in (a or "").lower().split() if len(w) > 3}
        wb = {w for w in (b or "").lower().split() if len(w) > 3}
        return len(wa & wb)

    def _says_stop(t: str) -> bool:
        """¿Ha pedido el operador PARAR un proceso, en ESTE turno? Determinista, para gatear lo irreversible.

        Cuidado con «para»: en castellano es preposición mucho más veces que verbo («para nada», «para ti»,
        «no era para ti»), así que NO entra suelta — y de hecho «para» a secas solo calla la voz, nunca detiene
        tareas de fondo (regla del operador). Se piden formas inequívocas: el infinitivo/imperativo de parar con
        o sin pronombre, detener, cancelar, anular, abortar, «deja de», y los equivalentes en inglés.

        V2-585: «para» + DETERMINANTE/cuantificador SÍ es verbo — medido en vivo (sesión 0e3a42d6): «Para
        todas las tareas en curso» y «No, para esa tarea» eran órdenes inequívocas, el modelo llamó a
        stop_worker CORRECTAMENTE y este guarda lo bloqueó como context-bleed; la respuesta fue «Sigo con
        ello» (lo contrario de la orden) y la tarea fantasma corrió 4 min más hasta el timeout. El coste del
        falso positivo es pequeño a propósito: este guarda solo gatea un stop_worker que el modelo YA
        eligió, así que «lo quiero para esta tarde» solo abre la puerta si además el modelo decidió matar —
        y el falso negativo, medido, cuesta minutos de trabajo fantasma y una mentira hablada."""
        n = _norm_nfkd(t or "")
        import re as _re_ss
        return bool(_re_ss.search(
            r"\b(par[ae]r(?:me|te|lo|la|los|las)?|par[ae]l[oa]s?|paralo|parala|"
            r"par[ae]n?\s+(?:el|la|los|las|es[aeo]s?|est[aeo]s?|tod[ao]s?|ambos|ambas)\b|"
            r"det[ei]n(?:er|lo|la|los|las|ga|gan)?|cancel(?:a|ar|alo|ala|o|en)|"
            r"anul(?:a|ar|alo|ala)|abort(?:a|ar|)|deja de|dejalo|"
            r"stop|cancel|abort|kill|halt|call it off)\b", n))
    return SimpleNamespace(_tag_emit=_tag_emit, _request_delete_confirm=_request_delete_confirm, _request_restore_confirm=_request_restore_confirm, _request_data_confirm=_request_data_confirm, _request_cluster_confirm=_request_cluster_confirm, _resolve_confirm=_resolve_confirm, _apply_widget_data=_apply_widget_data, _handle_widget_data_tool=_handle_widget_data_tool, _word_overlap=_word_overlap, _says_stop=_says_stop)
from nucleo.flash import tool_executor_widget_calls as _txw_calls  # noqa: E402 — V2-778 F1, reads this module back
