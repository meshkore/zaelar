"""The turn's tool executor — what a tool call or a tag of the fast brain DOES (V2-778 F1-10, 2026-10-01).

Moved out of `voice/engine/llm/providers/nucleo.py::_run_inner`, where these closures lived as ~1,200 lines of
the 3,500-line turn coroutine. The bodies are the SAME code, byte for byte apart from one level of indentation:
`build()` receives, as keyword arguments, exactly the names they used to close over — the turn's mutable state
(`acted`, `data_done`, the `*_req` slots…), its immutable inputs (`text`, `_brief`, `brain`, `emit`…) and the
few helpers that belong to the motor (`_spawn`, `_say`, the widget-intent readers, the confirm gate), which are
INJECTED so this module never imports `voice.engine`. That is what lets another channel (the text probe) build
the same executor with its own motor, instead of keeping a twin that drifts (ALERT 5).

`build()` must be called once per turn, after the last rebinding of any name it captures (in the provider:
after the vault intercept, which may redact `text`).
"""
from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace

from loguru import logger

from nucleo.flash import (build_decision as _build_decision, canvas_license as _canvas_lic,
                          canvas_visibility as _cvis, close_guards as _closeg, data_ops as _data_ops,
                          direct_action as _direct_action, image_turn as _image_turn, listing_turn as _lt,
                          show_target as _show_target, video_turn as _video_turn)
from nucleo.flash.panel_canon import wall_tab_for as _wall_tab_for
from nucleo.flash.surface_ack import saved_state_is_empty as _surface_is_empty
from voice import brain_notes as _bnotes
from widgets import confirm as _wconfirm


def build(*, self, brain, emit, text, operator_text, _brief, canvas_h, aside, cron_seen, _shown_ids, acted, confirm_state, clarify, _closed_by_tool, _repeat_repair, data_done, deduped, escalate_req, search_req, listing_req, recall_req, read_req, reopen_req, reveal_req, music_req, images_req, style_fired, worker_acted, _frontend, _router, _tool_fired, _data_ops_hechas, _turn_op_tasks,
          _spawn, _say, _resolve_pending_confirm, _confirm_decide, _close_target, _identify, _identify_is_widget, _is_meta_widget_question, _norm_nfkd, _show_guard_target, _show_target_instance, with_also_named):
    """The executor of ONE turn. Returns the closures the turn calls: `tag_emit`, `apply_widget_data`,
    `on_tool_call`, `resolve_confirm`, `start_web_auth`."""
    def _tag_emit(action: str, extra: dict) -> None:
        if action in ("deep",):
            # legacy Hermes escalation tag — el cerebro v2 no lo enseña; si aparece, se trata como escalada.
            if escalate_req["v"] is None:
                escalate_req["v"] = (extra.get("request") or "").strip() or text
            return
        if action in ("json_leak_dropped",):
            from voice.tag_protocol import parse_json
            leaked = parse_json(extra.get("text") or "")
            if isinstance(leaked, dict) and isinstance(leaked.get("name"), str):
                a = leaked.get("arguments")
                if isinstance(a, str):
                    a = parse_json(a) or {}
                _on_tool_call(leaked["name"], a if isinstance(a, dict) else {})
            elif isinstance(leaked, dict) and leaked.get("request"):
                _on_tool_call("escalate_to_slowbrain", leaked)
            elif isinstance(leaked, dict) and leaked.get("directive"):
                _on_tool_call("set_style_directive", leaked)
            else:
                if escalate_req["v"] is None:
                    escalate_req["v"] = text
            return
        if action in ("unknown_tag_dropped",):
            logger.warning(f"unknown_tag_dropped: {(extra.get('text') or '')[:120]!r}")
            return
        if action == "aparte":
            # V2-657 — sanctioned silence: an in-window turn addressed to somebody else in the room.
            # Handled (no mute backstop, no hollow repair); resolved after the stream.
            aside["v"] = True
            return
        if action == "widget.data":
            # Camino de RESERVA (V2-026): el tag inline sigue soportado, pero el camino PRINCIPAL de las
            # data-ops es la tool `widget_data` (function-calling, fiable). Ambos convergen en _apply_widget_data.
            data = extra.get("data") or {}
            _apply_widget_data(str(extra.get("id") or ""), str(data.get("action") or ""),
                               data.get("payload") or {})
            return
        if action == "delete":
            # BORRAR es cosa del FlashBrain (rápido, determinista) PERO con confirmación (V2-017). Si el
            # modelo emitió el tag en vez de la tool, lo tratamos igual: abre la confirmación (overlay Sí/No
            # en la tarjeta), nunca borra directo.
            _request_delete_confirm(extra.get("id") or "", text)
            acted["widget"] = True
            return
        if action in ("create", "modify", "push"):
            # Boundary duro: crear/modificar/entregar datos a un widget → SlowBrain (escribe código), nunca el
            # Flash. Borrar NO entra aquí (es determinista y lo hace el Flash tras confirmar, arriba).
            logger.warning(f"nucleo(flash) intentó [[{action}]] — bloqueado, escalando")
            if escalate_req["v"] is None:
                escalate_req["v"] = text
            return
        if action.startswith("cluster."):
            try:
                from connectors import meshkore
                _spawn(meshkore.dispatch_tag(action, extra), "cluster")
            except Exception:
                pass
            return
        if action.startswith("architect."):
            try:
                from connectors import architect
                _spawn(architect.dispatch_tag(action, extra), "architect")
            except Exception:
                pass
            return
        if action.startswith("msg."):
            try:
                from connectors import messaging
                _spawn(messaging.dispatch_tag(action, extra), "messaging")
            except Exception:
                pass
            return
        if action in ("cron.create", "cron.cancel"):
            # Proactividad PROPIA (V2-005): re-cableado al scheduler del loop orquestador (NO al cron de
            # Hermes, que muere en V2-009). Persistido en memory.journal; lo dispara nucleo/loop.py.
            if action == "cron.create":
                cron_seen["v"] = True          # V2-146: el backstop de abajo no duplica lo que ya se pidió
            try:
                from nucleo import scheduler as _sched
                d = extra.get("data") or {}
                if action == "cron.create":
                    # V2-214 (impl PARALELA — cablear en AMBOS): las palabras del OPERADOR sobre su propia
                    # obligación se envuelven en un «AVÍSALE»; una orden ya dirigida al agente se deja igual.
                    from nucleo.flash import router_guards as _rg_cron
                    r = _sched.create(
                        _rg_cron.safe_reminder_prompt((d.get("prompt") or d.get("task") or "").strip()),
                        _rg_cron.safe_reminder_schedule((d.get("schedule") or d.get("when") or "").strip(), "", text),  # V2-356
                        name=(d.get("name") or "").strip(), repeat=str(d.get("repeat") or ""))
                    emit("cron", "⏰ tarea programada" if r.get("ok") else "⚠️ schedule no reconocido",
                         text=r.get("display") or r.get("error") or "", role="system",
                         extra={"ok": bool(r.get("ok")), "op": action})
                else:
                    _sched.cancel(extra.get("name") or d.get("name") or "")
                    emit("cron", "🗑️ tarea cancelada", role="system", extra={"ok": True, "op": action})
            except Exception as e:  # noqa: BLE001
                logger.warning(f"nucleo cron {action} failed: {e}")
            return
        # show / close / move → acción de canvas.
        # GUARD close sin orden (V2-635, espejo del GUARD 2 de stop_worker): «Johnny eres tonto» acabó en
        # un [[close]] que NADIE pidió (34386d8f). Gramática (looks_like_close ya excluye negaciones y
        # narraciones): sin verbo de cerrar EN el turno del operador, el close del modelo es arrastre.
        # `named` = `closes_the_named_card` already told the op inside the card from the card named to close
        # (full18 V7: this guard dropped exactly that close, and the video card stayed over everything).
        # …and neither is any close of a card his words CALL by its name (full18 C6: «close the calendar and the
        # messages» — the verdict read `mensajeria:close`, the chat inside, and this guard kept the card open).
        if (action == "close" and not (extra or {}).get("named")
                and not _direct_action._says_the_name(_bnotes.operator_half(text), str((extra or {}).get("id") or ""))
                and _direct_action.order_is_inside(_brief, str((extra or {}).get("id") or ""))):
            # V2-770 — the order is an action INSIDE the card («ciérrala» over a detail card): not this tag.
            emit("brain", "🛡️ close ignorado — la orden es una acción DENTRO de la tarjeta",
                 text=(text or "")[:120], role="system", extra={"cat": "flash", "kind_diag": "close_inside_card"})
            deduped["v"] = True
            return
        if action == "close" and not _closeg.looks_like_close(text):
            # ...unless the shared reader licenses it: Jev independently reads a close order with
            # confidence (T-jev-show-close) — two readers agreeing forgives a grammar miss. A "neither"
            # or unsure verdict keeps the discard below, bit-for-bit.
            _has_order, _order_src = _show_target.close_has_order(text, canvas_h)
            if not _has_order:
                emit("brain", "🛡️ close ignorado — el operador no ha pedido cerrar nada (context-bleed)",
                     text=(text or "")[:120], role="system", extra={"cat": "flash", "kind_diag": "close_without_order"})
                deduped["v"] = True
                return
            emit("brain", "🔓 close licenciado por Jev (la gramática no veía orden, dos lectores de acuerdo)",
                 text=(text or "")[:120], role="system", extra={"cat": "flash", "kind_diag": "close_jev_licensed"})
        if action == "show":
            contextual = _show_guard_target(text, brain._window, brain._last_action)
            if contextual:
                extra = {**(extra or {}), "id": contextual}
            # V2-776 — the CARD, as the tool path resolves it: `[[show:results]]` with the monitor sheet open
            # put the bare, empty base beside it (verification 2026-09-27, «Compare them visually»).
            _tid = str((extra or {}).get("id") or "").strip()
            if _tid and "::" not in _tid:
                try:
                    _r_tag = _show_target_instance(_tid, _bnotes.operator_half(text), brain._last_spoken or "")
                    if not _r_tag.get("ask") and _r_tag.get("id"):
                        extra = {**(extra or {}), "id": _r_tag["id"]}
                except Exception:  # noqa: BLE001
                    pass
        # GUARD anti-clutter (2026-07-12): el modelo tiende a emitir [[show:navegador]] al pedir una búsqueda,
        # abriendo el navegador VACÍO ("Nuevo navegador") ADEMÁS de la tarjeta de la tarea → dos/tres cajas de
        # navegador en pantalla. La búsqueda se ve en SU tarjeta (navegador::tN, la abre la tarea sola); el
        # navegador "a pelo" no es una superficie que el operador pida. Lo ignoramos (no rompe: la tarjeta manda).
        if action == "show" and str(extra.get("id") or "").strip().lower() == "navegador":
            emit("brain", "🚫 [[show:navegador]] ignorado (la tarjeta de la tarea es la superficie)", role="system")
            return
        # El modelo a veces emite [[show:X]] cuando el operador solo PREGUNTA por un widget ("¿por qué abriste
        # proyectos?") → abría un widget espurio en mitad de otra conversación (bug 2026-07-12). Una pregunta
        # META sobre una acción pasada NO es una orden de mostrar → ignora el show del modelo.
        # V2-776 — HIS words only (V2-678): the composed turn carries our `[SISTEMA]` notes, and a note about a
        # closed errand read as a meta question and dropped «Show me the monitors» (verification 2026-09-27).
        if action == "show" and _is_meta_widget_question(_norm_nfkd(_bnotes.operator_half(text))):
            emit("brain", "🚫 show ignorado (pregunta META sobre un widget, no una orden)",
                 text=str(extra.get("id") or ""), role="system")
            return
        # DEDUP de show por id en el MISMO turno (test post-P1/P2: el modelo emitía [[show:X]] dos veces →
        # doble evento). desktop.show ya es idempotente (reusa la tarjeta), pero no floodeamos el bus/SSE.
        if action == "show":
            _sid = str(extra.get("id") or "").strip().lower()
            if _sid and _sid in _shown_ids:
                return
            _shown_ids.add(_sid)
            extra["reason"] = "turn-order"       # V2-723: the guards above ARE the turn's license
            # V2-770 — showing a card that is ALREADY open, on a turn whose verdict names an action INSIDE it
            # («ábreme la ficha del dentista» → `agenda:open_meeting`), is not the act: the turn stays open to
            # the verdict's completion and the promise repair below.
            if _direct_action.order_is_inside(_brief, _sid):
                emit("brain", "🪟 show de una tarjeta ya abierta — la orden es una acción DENTRO",
                     text=_sid, role="system", extra={"cat": "flash", "kind_diag": "show_inside_card"})
                extra["src"] = "flash"
                emit("widget", action, extra=extra)
                return
        acted["widget"] = True
        if action == "show" and extra.get("id"):
            # V2-776 — WHICH card, as the tool path records it: without the id the after-show repair never ran
            # for a tag show, and «Show me a chart of Apple stock today» left the Markets card EMPTY (demo v7).
            acted["widget_id"] = acted.get("widget_id") or str(extra.get("id"))
        if action == "close":
            acted["closed"] = True                   # el backstop de cierre corto no re-cierra (ver post-stream)
            _canvas_lic.note_operator_close(str(extra.get("id") or ""))   # V2-650b: reopen needs his words
        extra["src"] = "flash"                       # V2-039: procedencia — esta orden viene del FlashBrain
        # REGISTRO DE ÓRDENES DE CANVAS (2026-08-09, petición del operador): el evento se lleva la FRASE que
        # lo provocó. Cuando se abre el widget EQUIVOCADO, la pregunta siempre es «¿de qué texto salió esto?»
        # — y hasta ahora había que reconstruirla saltando al evento `transcript` anterior o abriendo la vista
        # de trazas. Con el texto pegado al propio evento, la fila ya dice orden + objetivo + origen.
        emit("widget", action, text=(text or "").strip()[:160], extra=extra)

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
        """Ejecuta una data-op según su modo (V2-025): FAST → despacha ya (apply_action / mailbox del owner);
        CONFIRM → abre confirmación con la mutación guardada (se ejecuta al decir "sí"); ESCALATE/None (acción
        no declarada o vía de escape) → escala al SlowBrain. Punto de convergencia de la tool y el tag."""
        from widgets import actions as _wactions
        wid = (wid or "").strip().lower()
        # V2-773 — a data-op on a BASE id lands on its one open instance (a worker's sheet `results::9194df-1`
        # is the only «results» the model can name); several instances keep today's path.
        try:
            from server.voice_api import open_instances as _open_inst
            from widgets import instances as _inst_dt
            wid = _inst_dt.data_target(wid, _open_inst()) or wid
        except Exception:  # noqa: BLE001
            pass
        action_name = (action_name or "").strip()
        # E5 (demo passes 36/42, 2026-09-29): «close my mail» → the model called the card's own `close` VIEW
        # action (back to the chat list) over a SURE close verdict, and the card stayed. The card's close, once.
        if _direct_action.close_op_is_the_card(_brief, action_name):
            _tag_emit("close", {"id": _show_target.close_target(wid)})
            acted["widget"] = True
            emit("brain", "🔁 data-op «close» sobre un cierre seguro — cierra la tarjeta", text=wid, role="system",
                 extra={"cat": "flash", "widget": wid, "action": "close"})
            return
        # V2-757 — THE TAIL OF A SENTENCE IS NOT AN ORDER. Here because this is where the tool and the
        # tag converge: a rule installed in one of two branches is this repo's own named way of fixing
        # half a defect. The why and the measurement: `direct_action.a_fragment_moves_nothing`.
        if (_frag_why := _direct_action.a_fragment_moves_nothing(
                _bnotes.operator_half(text), brief=_brief,
                last_reply=getattr(brain, "_last_reply", "") or "")):
            emit("brain", "🧩 trozo de frase — no mueve nada en pantalla",
                 text=f"{_bnotes.operator_half(text).strip()[:80]} → {wid}:{action_name}",
                 role="system", extra={"cat": "flash", "why": _frag_why,
                                       "id": wid, "action": action_name})
            return
        mode = _frontend.action_mode_now(wid, action_name, payload)   # V2-712: decidido para ESTA llamada
        # TWO READERS DISAGREE ON AN ACT THAT LEAVES (demo pass 2026-09-28, full12 E3): «draft a short reply
        # saying i'll send the meet link…» — the verdict read `mensajeria:draft` at 1.00, the model called
        # `reply`, V2-712 ran it without a question (clear order, resolved target) and a real email went to a
        # third party. V2-754 lets a valid model call beat a disagreeing verdict because a wrong verdict costs
        # a reversible view; for an act of level ≥ sensitive the costs are reversed, so the verdict's action
        # runs instead — and if it cannot, he is asked. Agreement, or no verdict at all, changes nothing.
        if mode == _wactions.FAST and _frontend.at_least_sensitive(wid, action_name):
            _vdis = _direct_action.completes(_brief, wid, model_action=action_name)
            if _vdis:
                emit("brain", "🛑 acto que sale fuera y el veredicto dice otra cosa — corre el veredicto",
                     text=f"{wid}: modelo={action_name} · veredicto={_vdis}", role="system",
                     extra={"cat": "flash", "id": wid, "model": action_name, "verdict": _vdis})
                # the model already wrote the content: it travels to the verdict's action, filtered to what
                # that action declares (a reply's `text` is a draft's `text`)
                _vkeys = set(_direct_action._payload_spec(wid, _vdis))
                _vpay = {k: v for k, v in (payload or {}).items() if k in _vkeys and str(v or "").strip()}
                # …and the recipient his sentence names, which the model's call for the OTHER action did not
                # carry (full18 E3: `reply` has no recipient; the verdict's `forward` needs one)
                _vpay.update(_direct_action.person_fill(wid, _vdis, _vpay, _bnotes.operator_half(text)))
                if _vpay:
                    acted["widget"] = True
                    _gate_card = wid          # this gate's own, already-decided card
                    _apply_widget_data(_gate_card, _vdis, _vpay)
                    return
                if _direct_action.complete(_brief, operator_text=_bnotes.operator_half(text), emit=emit,
                                           present=_cvis.present, apply_widget_data=_apply_widget_data,
                                           widget_id=wid, instead_of=action_name, require_order=False):
                    acted["widget"] = True
                    return
                mode = _wactions.CONFIRM
            elif _direct_action.verdict_elsewhere(_brief, wid):
                # …and an act that leaves which the verdict does not back at all — it surely names an action on
                # ANOTHER card (full19 C2: «find me a free 45 minutes… to talk with rowan» → agenda:find_free,
                # and the model also wrote to Rowan). DROPPED, and the model told: asked instead, the pending
                # question was what «ok book it» answered one turn later — two Telegrams to Rowan he never
                # ordered (demo pass 45, 2026-09-29, C2→C5). An act he did not ask for is not offered either.
                emit("brain", "🛑 acto que sale fuera sin respaldo del veredicto — no se ejecuta",
                     text=f"{wid}:{action_name} · veredicto en otra tarjeta", role="system",
                     extra={"cat": "flash", "id": wid, "model": action_name})
                try:
                    from voice import brain_notes as _bn_drop
                    _bn_drop.push(f"[SISTEMA] La acción «{action_name}» sobre «{wid}» NO se ejecutó: el operador "
                                  f"no la pidió (su orden era otra). No digas que se ha enviado ni lo ofrezcas; "
                                  f"si él te lo pide explícitamente, llama entonces a «{action_name}».")
                except Exception:  # noqa: BLE001
                    pass
                return

        def _log_dataop(m: str) -> None:
            """REGISTRO DE ACCIONES DE WIDGET (2026-08-09, petición del operador). Hasta ahora una data-op
            («sube el volumen», «maximiza», «marca hecha la tarea») solo dejaba rastro cuando el widget
            GUARDABA (`widget/data` desde `widgets/store.py`), una fila genérica con el id y nada más — sin
            el nombre de la acción, sin quién la pidió y sin la frase. Y encima está clasificada como ruido,
            así que por defecto ni se ve. Aquí se registra la ORDEN en sí: qué acción, sobre qué widget, en
            qué modo (fast/confirm/escalate) y con la FRASE que la originó, para poder atar una acción
            equivocada con el texto exacto que la produjo. La fila del store se queda como está (es el efecto,
            no la orden)."""
            # V2-678 — HIS words, not the composed turn: this row is the audit trail that ties a wrong
            # action to the sentence that produced it, and with the notes glued on it named ours.
            emit("widget", f"data:{action_name}", text=_bnotes.operator_half(text).strip()[:160],
                 extra={"id": wid, "action": action_name, "mode": m, "src": "flash", "item": ref,
                        "payload": payload if isinstance(payload, dict) else {}})   # V2-653: the order's content

        if mode == _wactions.FAST:
            # GUARD anti context-bleed (round headless V2-038 #1): el modelo a veces RE-emite la data-op del
            # turno ANTERIOR junto a la acción de ESTE ("borra el reloj" arrastró el add_meeting del dentista
            # → cita DUPLICADA). Una mutación IDÉNTICA a la recién ejecutada (<120s), cuyo contenido el turno
            # actual NI MENCIONA, es arrastre → se ignora. Determinista: "apunta otra vez lo del dentista" SÍ
            # menciona el contenido → pasa.
            # V2-650: unless the turn ITSELF orders the production again — «reproduce la lista» /
            # «dale al play» share zero words with {"playlist": "true-blue"}, so payload overlap
            # alone ate three explicit replays of a playback that had failed in silence.
            # V2-707 F0 — and it only guards a mutation that REALLY HAPPENED: the seal is stamped from the
            # RESULT (see `_seal` below), never before dispatching. Until F0 a refused op was remembered as
            # executed and its corrected retry was eaten here — deterministically, because an empty payload
            # joins no values and `_word_overlap` is then 0 against any sentence, so the hatch never opens.
            # The incident, turn by turn: `test_a_refused_action_is_not_remembered_as_done.py`.
            # V2-717: the predicate lives in `data_ops.is_context_bleed` — and a VIEW-op is never a drag.
            if _data_ops.is_context_bleed(brain._last_dataop, wid, action_name, payload, _bnotes.operator_half(text)):
                emit("brain", "🛡️ data-op del turno anterior re-emitida — ignorada (context-bleed)",
                     # …and it SAYS what it threw away. The sibling guards in `_handle_widget_data_tool`
                     # carry the discarded payload; this one carried only «agenda:cancel_meeting», so the
                     # live incident could not be diagnosed from the timeline at all.
                     text=f"{wid}:{action_name}", role="system",
                     extra={"id": wid, "action": action_name, "payload": payload or {}})
                deduped["v"] = True
                return
            # V2-773 — the SAME op the widget just refused, with the SAME payload, is the model re-reading the
            # failure note, not a corrected call: it cannot succeed where it just failed, and it dragged a photo
            # `select` through two chart turns. A corrected retry carries a different payload and runs.
            if _data_ops.is_identical_retry_of_refused(wid, action_name, payload):
                emit("brain", "🛡️ reintento idéntico de una op rechazada — ignorado", text=f"{wid}:{action_name}",
                     role="system", extra={"id": wid, "action": action_name, "payload": payload or {}})
                deduped["v"] = True
                return
            acted["widget"] = True
            data_done["v"] = True
            data_done.setdefault("ops", []).append((wid, action_name))
            _log_dataop("fast")
            try:
                from widgets import provenance as _prov
                _prov.note(wid, "flash")             # V2-039: el cambio de datos que viene = ordenado por FlashBrain
            except Exception:
                pass

            def _seal(ok: bool, _w=wid, _a=action_name, _p=dict(payload or {})) -> None:
                """Remember this mutation ONLY if it happened. A refusal leaves no trace to drag — but it is
                remembered as REFUSED, so the identical re-emit cannot run again (V2-773)."""
                if ok:
                    brain._last_dataop = (_w, _a, _p, time.time())
                else:
                    _data_ops.remember_refusal(_w, _a, _p)

            # V2-778 F0-4 — an op that could not start is NOT done: `start_op` says so, and the turn forgets
            # it, so «Done.» never stands over an op that never ran.
            _op_task = _data_ops.start_op(
                wid, action_name, payload or {}, seal=_seal, text=lambda: _bnotes.operator_half(text),
                said=lambda: getattr(brain, "_last_spoken", ""), spawn=_spawn)
            if _op_task is not None:
                _turn_op_tasks.append((wid, _op_task))
            else:
                _ops_left = data_done.get("ops", [])
                if (wid, action_name) in _ops_left:
                    _ops_left.remove((wid, action_name))
                data_done["v"] = bool(_ops_left)
            # An action whose output only exists ON SCREEN (`present.mount`, declared or derived) brings its
            # card, through the one door. «Show me a chart of Apple stock» ran markets:show and the card never
            # opened — «Apple's chart is on screen» over an empty canvas (demo run, 2026-09-26). The door
            # refuses an open card, so this never raises one he is reading.
            try:
                from widgets import effects as _fx
                if _fx.carries(wid, action_name, _fx.PRESENT_MOUNT):
                    _cvis.present(wid, reason="producer-mount", action=action_name, src="flash", emit=emit)
                # A LENS on a closed card brings the card (V2-773 final pass, C2): «Show me that time in my
                # calendar» ran `agenda:show_day` — a view-op, writes nothing — over a canvas with no agenda
                # on it, and the day changed on a card nobody could see. The model chose to change what
                # THIS card displays, on his order: that is a turn-order for the card. A write is not this
                # (it may run behind the screen on purpose); a lens nobody can see is a silent nothing.
                elif (_fx.carries(wid, action_name, _fx.DATA_READ) and not _cvis.is_open(wid)
                      and not _canvas_lic.closing_turn(_brief, wid)):   # V2-773 E5: a close never brings the card
                    _cvis.present(wid, reason="turn-order", action=action_name, src="flash", emit=emit)
            except Exception:
                pass
        elif mode == _wactions.CONFIRM:
            acted["widget"] = True
            _log_dataop("confirm")
            _request_data_confirm(wid, action_name, payload or {})
        else:
            logger.warning(f"nucleo(flash) widget.data {mode or 'no-declarada'} ({wid}:{action_name}) — escalando")
            _log_dataop("escalate")
            if escalate_req["v"] is None:
                escalate_req["v"] = text

    def _handle_widget_data_tool(args: dict) -> None:
        """Tool `widget_data` (V2-026, camino PRINCIPAL de las data-ops): resuelve el widget y la REFERENCIA a
        item en lenguaje natural a un id REAL (nunca inventado), y despacha por `_apply_widget_data`. Si la
        referencia es ambigua o no existe, PREGUNTA en vez de actuar sobre el item equivocado."""
        from widgets import refs, runtime
        wid = (args.get("widget_id") or "").strip().lower()
        action_name = (args.get("action") or "").strip()
        ref = (args.get("item") or "").strip()
        payload = args.get("payload") if isinstance(args.get("payload"), dict) else {}
        if wid and runtime.get(wid) is None:            # id flojito del modelo → resuélvelo contra el catálogo
            wid = _identify(wid) or _identify(ref) or _identify(text) or wid
        if not wid or not action_name:
            return
        # GUARD (2026-07-16): un "abre/muéstrame el widget X" PURO (sin verbo de cambio) NUNCA debe ejecutar un
        # data-op — el modelo cuela una acción inventada ('unhide') o incluso ALUCINA un add_meeting ("abre la
        # agenda" → añadía "Reunión con Axa Seguros"). Se redirige a MOSTRAR la tarjeta (misma ruta que [[show]]).
        from nucleo.flash import router as _router
        # V2-545 — what a pure show order may run is decided by the ACTION, not by the words. The widget
        # declares which of its actions are display-only (`"view": true`); one of those IS the right answer
        # to «ábreme el Telegram» (show_view) or «abre el mensaje de Francisco» (open), so it runs — and the
        # card is shown too, which is the other half of what was asked and removes the card-vs-inside
        # guess. Anything else on a pure show is the invented mutation this guard exists for.
        # The discarded action goes in the event: the previous version logged only the widget id, so three
        # live turns of «ábreme el Telegram» → «Aquí lo tienes» over an unmoved card left no trace of WHAT
        # had been thrown away, and the model was suspected before the guard was.
        if _router.is_pure_show_request(text) and runtime.get(wid) is not None:
            # …salvo que el veredicto nombre esta acción: lo elegido del manifiesto no es inventado (V2-753).
            if _router.show_request_blocks_data_action(text, wid, action_name, payload) \
                    and not _direct_action.endorses(_brief, wid, action_name):
                emit("brain", "🪟 'abrir/mostrar' puro → show (no data-op inventada)",
                     text=f"{wid} (descartada {action_name})", role="system",
                     extra={"id": wid, "action": action_name, "payload": payload or {}})
                _tag_emit("show", {"id": wid})
                return
            emit("brain", "🪟 'abrir/mostrar' puro + acción de VISTA → la tarjeta Y la vista",
                 text=f"{wid}:{action_name}", role="system",
                 extra={"id": wid, "action": action_name, "payload": payload or {}})
            _tag_emit("show", {"id": wid})
        # GUARD cerrar≠data-op (sesión 22:40 2026-07-16, espejo del guard cerrar≠borrar): «Vale, ciérralo» →
        # el modelo ejecutó `widget_data(youtube, mute)` (una data-op DECLARADA) en vez de emitir [[close]] →
        # el vídeo quedó MUTEADO, no cerrado, y el operador tuvo que corregir. Una orden CORTA que es
        # claramente CERRAR (verbo de cerrar, sin verbo de borrar, ≤5 palabras — sin más sustancia que el
        # pronombre/el widget) se redirige DETERMINISTA a la tag de canvas. Una frase larga con "cierra"
        # dentro ("cierra la sesión de spotify del widget") NO entra aquí (pasa a su data-op normal).
        if (_closeg.is_short_close_order(text) and runtime.get(wid) is not None   # V2-713 R3: extraída
                and _direct_action.from_brief(_brief) != (wid, action_name)):   # V2-770: both readers agree
            emit("brain", "🙈 orden corta de CERRAR → close (no data-op)", text=f"{wid} (era {action_name})",
                 role="system")
            _tag_emit("close", {"id": wid})
            return
        # GUARD V2-635 (espejo del de [[close]] en _tag_emit): la data-op «close» VACÍA contenido. Sin verbo
        # de cerrar = arrastre, salvo que el veredicto de pantalla nombre esta acción (V2-753, 46dcfcb4).
        if action_name == "close" and not _closeg.dataop_close_licensed(text, wid, brief=_brief, emit=emit):
            deduped["v"] = True
            return
        if _frontend.action_mode(wid, action_name) is None:   # acción no declarada → canvas, reparación Jev o escala
            # GUARD frontera CANVAS vs DATOS (diag sesiones-largas 2026-07-15): a profundidad, el modelo a
            # veces cuela el SHOW/CLOSE como pseudo data-op (`widget_data(clock, action="show")` ante
            # "muéstrame un reloj"). Antes se curaba por el DESVÍO no-declarada→escalate→show-guard (frágil y
            # caro); ahora se mapea DIRECTO a la tag de canvas — misma ruta que [[show]]/[[close]] (dedup,
            # guards anti-clutter/meta, ack "nunca mudo"). Solo si el widget existe de verdad.
            # La DECISIÓN vive en `frontend.resolve_undeclared_action` (compartida con el espejo del probe):
            # verbo de canvas → tag; si no, Jev elige entre las acciones DECLARADAS y la llamada sigue su
            # flujo normal (modos FAST/CONFIRM/ESCALATE intactos); sin veredicto → escala como hoy.
            _kind, _val = _frontend.resolve_undeclared_action(
                wid, action_name, text, brief=_brief, blocking_ok=False)
            if _kind == "canvas":
                emit("brain", "🪟 widget_data con verbo de CANVAS → tag determinista",
                     text=f"{wid}:{action_name}→{_val}", role="system")
                _tag_emit(_val, {"id": wid})
                return
            if _kind == "repair":
                emit("brain", "🔧 acción inventada reparada por Jev → declarada",
                     text=f"{wid}:{action_name}→{_val}", role="system",
                     extra={"id": wid, "action": _val, "invented": action_name})
                action_name = _val
            else:
                if escalate_req["v"] is None:
                    escalate_req["v"] = text
                return
        res = refs.resolve(wid, action_name, ref, payload, order=_bnotes.operator_half(text))
        # El mis-ruteo por PRONOMBRE SUELTO (o una referencia que no resuelve) sobre un widget que ni
        # está en pantalla ni se nombra: el incidente, la trampa de las acciones de CREAR y la razón de
        # escalar el turno CRUDO están en `frontend.absent_widget_misroute` — la MISMA función que usa
        # el probe, donde vivía copiada y hubo que arreglarla dos veces por separado.
        # An AMBIGUOUS reference found this card's own rows — it is a «which one?», never a worker's job
        # (demo run: «Move it 30 minutes later» over two same-named meetings started a Brain Worker).
        if _frontend.absent_widget_misroute(wid, action_name, ref, resolved=res.ok or res.needs == "ambiguous",
                                            named_widget=_identify(text), payload=payload):
            emit("brain", "🧭 data-op en widget ausente/no-nombrado (pronombre/ítem sin anclar) → escala con contexto",
                 role="system", text=f"{wid}:{action_name}:{ref or '∅'}", extra={"needs": res.needs})
            acted["widget"] = True
            if escalate_req["v"] is None:
                escalate_req["v"] = text
            return
        if not res.ok:
            acted["widget"] = True                      # lo ATENDIMOS (preguntando) — no caer a escalate/fallback
            # V2-754 — antes de preguntar «¿cuál?»: si el veredicto nombra OTRA acción de esta tarjeta, la duda
            # era la acción, no el ítem (`play_item` sobre «volver al catálogo» con `show_tab` a 0,96 en el brief).
            if _direct_action.complete(_brief, operator_text=_bnotes.operator_half(text), emit=emit,
                                       present=_cvis.present, apply_widget_data=_apply_widget_data,
                                       widget_id=wid, instead_of=action_name, require_order=False):
                return
            cands = ", ".join(res.candidates[:3])
            clarify["msg"] = (_say().ask_which_item.format(cands=cands) if cands
                              else _say().ask_which_item_bare)
            emit("brain", "❓ referencia de item sin resolver", role="system",
                 text=f"{wid}:{action_name}:{ref or '∅'}", extra={"needs": res.needs, "cands": res.candidates[:4]})
            return
        # V2-740 — ¿de QUIÉN era la orden, con dos tarjetas que saben hacer lo mismo? El porqué y la
        # forma del plan, en `frontend.card_decision`; el probe toma la misma por la misma función.
        _cd = _frontend.card_decision(wid, action_name, brief=_brief, ask_phrase=_say().ask_which_item,
                                      payload=payload)
        if _cd["label"]:
            emit("brain", _cd["label"], role="system", text=_cd["text"], extra=_cd["extra"])
        if _cd["ask"]:
            acted["widget"] = True; clarify["msg"] = _cd["ask"]; return
        # V2-754 — una llamada VÁLIDA del modelo corre aunque el veredicto discrepe (a 0,99 habría REINICIADO el
        # vídeo); la discrepancia se registra, que es lo que permitirá medir a quién creer.
        if (_dis := _direct_action.completes(_brief, _cd["card"], model_action=action_name)):
            from nucleo.flash import turn_brief as _tb_vw
            _vw_words = str(_tb_vw.read(_brief, _tb_vw.WORDS_KEY, "")[0] or "")
            if ((_data_ops.repeats_last_view(brain._last_dataop, _cd["card"], action_name, res.payload)
                 or _data_ops.a_view_where_the_verdict_acts(_cd["card"], action_name, _dis, _vw_words))
                    and _direct_action.complete(_brief, operator_text=_bnotes.operator_half(text), emit=emit,
                                                present=_cvis.present, apply_widget_data=_apply_widget_data,
                                                widget_id=_cd["card"], instead_of=action_name,
                                                require_order=False)):
                emit("brain", "⚖️ el modelo solo miró (o repitió la vista) — completa el veredicto", role="system",
                     text=f"{_cd['card']}: modelo={action_name} · veredicto={_dis}",
                     extra={"cat": "flash", "id": _cd["card"], "model": action_name, "verdict": _dis})
                acted["widget"] = True
                return
            # A QUESTION the verdict is sure of, over a WRITE the model made on the same card (full19 C2: «find me
            # a free 45 minutes…» → verdict find_free 0.91, model add_meeting): the write is the costly mistake
            # — it lands in his calendar — so the answer runs instead. `output.answer` is declared, never guessed.
            # full52 V5: «go back to the list of videos» → verdict youtube:show_tab 0.97, model clear_search (which
            # ERASES the results band), and «put on number five» then had no list. A LENS the verdict is sure
            # of changes nothing; a model call that changes the card's state, over it, is the costly reading.
            if (_data_ops.is_view_op(_cd["card"], _dis) and not _data_ops.is_view_op(_cd["card"], action_name)
                    and _direct_action._action_sure(_brief, floor=0.9)
                    and _direct_action.complete(_brief, operator_text=_bnotes.operator_half(text), emit=emit,
                                                present=_cvis.present, apply_widget_data=_apply_widget_data,
                                                widget_id=_cd["card"], instead_of=action_name,
                                                require_order=False)):
                emit("brain", "👁 la vista segura gana a un cambio de estado — corre el veredicto", role="system",
                     text=f"{_cd['card']}: modelo={action_name} · veredicto={_dis}",
                     extra={"cat": "flash", "id": _cd["card"], "model": action_name, "verdict": _dis})
                acted["widget"] = True
                return
            from widgets import effects as _fx_q
            if (_fx_q.carries(_cd["card"], _dis, _fx_q.OUTPUT_ANSWER)
                    and _fx_q.carries(_cd["card"], action_name, _fx_q.DATA_WRITE)
                    and _direct_action._action_sure(_brief)):
                # full51 C2: when the verdict cannot be completed alone (`find_free` needs the length and the
                # afternoon only a model reads), the WRITE still ran — «Call with Rowan» booked at 15:45 over
                # the 15:00 meeting, nobody having asked to book. The write never runs; the verdict's call is
                # asked of the model after the turn (the repeated-view repair pass).
                if not _direct_action.complete(_brief, operator_text=_bnotes.operator_half(text), emit=emit,
                                               present=_cvis.present, apply_widget_data=_apply_widget_data,
                                               widget_id=_cd["card"], instead_of=action_name,
                                               require_order=False):
                    _repeat_repair["v"] = (_cd["card"], action_name, _dis)
                emit("brain", "❓ la pregunta gana a la escritura — corre el veredicto", role="system",
                     text=f"{_cd['card']}: modelo={action_name} · veredicto={_dis}",
                     extra={"cat": "flash", "id": _cd["card"], "model": action_name, "verdict": _dis})
                acted["widget"] = True
                return
            # …and a REPEATED view with a verdict that needs a written payload (full20 E3: `open` again, verdict
            # `forward`): the view runs, and one repair pass after the turn asks for the verdict's call.
            if (_data_ops.repeats_last_view(brain._last_dataop, _cd["card"], action_name, res.payload)   # full37 E2:
                    or _data_ops.a_view_where_the_verdict_acts(_cd["card"], action_name, _dis, _vw_words)):  # a lens
                _repeat_repair["v"] = (_cd["card"], action_name, _dis)
            emit("brain", "⚖️ el modelo y el veredicto discrepan — corre el modelo", role="system",
                 text=f"{_cd['card']}: modelo={action_name} · veredicto={_dis}",
                 extra={"cat": "flash", "id": _cd["card"], "model": action_name, "verdict": _dis})
        # V2-756 — y lo que el modelo dejó VACÍO se rellena con sus palabras antes de que el widget lo
        # rechace: «Pausa el vídeo. Vuelve al catálogo.» llamó a `show_tab` sin `tab` y volvió
        # `unknown_tab`. Solo AÑADE una clave ausente, y solo por un alias declarado o un número dicho.
        if (_fill := _direct_action.fill_missing(_cd["card"], action_name, res.payload,
                                                 _bnotes.operator_half(text))):
            res.payload.update(_fill)
            emit("brain", "🧩 el modelo dejó la clave vacía — la rellenan sus palabras", role="system",
                 text=f"{_cd['card']}:{action_name} {_fill}", extra={"cat": "flash", "id": _cd["card"],
                 "action": action_name, "fill": _fill})
        _apply_widget_data(_cd["card"], action_name, res.payload, ref)

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

    def _on_tool_call(name: str, args: dict) -> None:
        # NINGUNA tool se ejecuta desde un fragmento superado: mientras el modelo generaba, el operador siguió
        # hablando, así que esta decisión se tomó sobre media frase. Abrir un widget o lanzar un worker con
        # criterios a medias es peor que no hacer nada — el turno completo llega enseguida.
        if self._superseded():
            emit("brain", "🧩 tool ignorada — la frase seguía", text=name, role="system",
                 extra={"cat": "flash", "fragment": (getattr(self, "_turn_text", "") or "")[:120]})
            return

        # Recorded AFTER the superseded gate on purpose: a tool that never ran is not something this turn did,
        # so it must not weigh on the end-of-turn flow-merge decision (V2-123, `_merge_target`).
        try:
            brain._turn_tools.add(name)
            brain._turn_calls.append({"name": name, "args": dict(args or {})})
        except Exception:
            pass

        # ESCOTILLA de la selección progresiva (V2-096 F2): el modelo dice que le falta una familia. Se apunta
        # para que el turno la RECOMPONGA con esa familia cargada — un viaje extra MEDIBLE en vez de una
        # capacidad negada en silencio, que es el fallo que de verdad rompe una conversación. No es una tool
        # real: no hace nada, solo marca.
        if name == "need_capability":
            _fam = str((args or {}).get("family") or "").strip()
            if _fam:
                self._need_family = _fam
            emit("brain", "🔓 el modelo pide una familia que se había recortado", text=_fam, role="system",
                 extra={"cat": "flash", "family": _fam, "retry": True})
            return

        # Alimenta la capa `recent` del turno siguiente: una conversación que ya iba de widgets no debería
        # perderlos porque el turno siguiente no los nombre.
        try:
            from nucleo.flash import tool_selection as _tsel2
            _fams = _tsel2.families_used([name])
            if _fams:
                prev = list(getattr(brain, "_recent_tool_families", None) or ())
                brain._recent_tool_families = list(dict.fromkeys(list(_fams) + prev))[:3]
        except Exception:
            pass
        if name == "widget_data":
            # V2-391 — VARIAS, no una: lo decide `data_ops` (ahí está el porqué y qué sigue bloqueado).
            if not _data_ops.admite_data_op(args, _data_ops_hechas):
                return
            _data_ops_hechas.append(args)     # y `_tool_fired` ya no lo lee nadie: la cuenta es esta
            _handle_widget_data_tool(args)
        elif name == "escalate_to_slowbrain":
            req = (args.get("request") or "").strip() or text
            # V2-227: la superficie declarada se guarda POR petición. Solo se puebla desde la llamada real
            # del modelo; los caminos de respaldo de este fichero (el tag filtrado, los backstops) no la
            # conocen y dejan que `surfaces.resolve()` la derive del kind — que es para lo que existe.
            _sf = str(args.get("surface") or "").strip()
            if _sf:
                escalate_req["surface"][req] = _sf
            escalate_req.setdefault("done_when", {})[req] = args.get("done_when")   # V2-776 L1: the spec rides
            if escalate_req["v"] is None:
                escalate_req["v"] = req
            elif (args.get("request") or "").strip():
                # Una 2ª (3ª…) llamada del MODELO en el mismo turno = otra tarea. Se exige `request` propio:
                # sin él la llamada cae a `text`, que es la MISMA frase, y duplicaríamos la tarea principal.
                # El tope existe porque el destinatario es un pool de workers reales (`dispatch._max_parallel`,
                # 3 por defecto): un modelo que se atasque enumerando no debe poder abrir una tarea por ítem.
                if len(escalate_req["more"]) < 2 and req not in escalate_req["more"] and req != escalate_req["v"]:
                    escalate_req["more"].append(req)
        elif name == "web_search":
            q = (args.get("query") or "").strip() or text
            # TURN-BLEED: el modelo a veces re-emite la búsqueda del turno ANTERIOR junto a la de este (visto:
            # "precio bitcoin" colado en el turno "¿cuándo es el eclipse?"). Nos quedamos con la query que MÁS
            # se parece al turno ACTUAL, no con la primera (que puede ser la vieja) → no buscamos lo que no es.
            if search_req["v"] is None or _word_overlap(q, text) > _word_overlap(search_req["v"], text):
                search_req["v"] = q
        elif name == "search_listings":
            # V2-556 — UNA por turno; la forma de la petición es del módulo (`listing_turn.request_from`).
            listing_req["v"] = listing_req["v"] or _lt.request_from(args, text)
        elif name == "recall":
            # V2-056: el MODELO decide recordar (V2-022 aplicado a la memoria). Se resuelve tras el stream,
            # fuera del event loop; la heurística needs_recall queda como prefetch.
            if recall_req["v"] is None:
                recall_req["v"] = (args.get("query") or "").strip() or text
        elif name == "read_widget":
            # V2-668: el MODELO decide LEER lo que guarda un widget (la hora de una cita con la agenda
            # cerrada). Se resuelve tras el stream, en el turno, sin abrir nada — hermana de recall.
            if read_req["v"] is None:
                read_req["v"] = {"widget_id": (args.get("widget_id") or "").strip(),
                                 "question": (args.get("question") or "").strip()}
        elif name == "reopen_task":
            # V2-728: «lo del piso que te dije» — SQLite + un viaje a Jev, así que tras el stream.
            if reopen_req["v"] is None:
                reopen_req["v"] = (args.get("query") or "").strip() or text
        elif name == "reveal_secret":
            # V2-060: el operador pide un SECRETO guardado. Se resuelve tras el stream; el valor NUNCA entra en
            # un prompt del modelo → el provider lo entrega OUT-OF-BAND (voz/pantalla). Aquí solo se captura QUÉ.
            if reveal_req["v"] is None:
                reveal_req["v"] = (args.get("label") or "").strip() or text
        elif name == "play_music":
            # V2-041: una acción de música por turno. Ruta LIGERA como web_search: se resuelve tras el stream,
            # FUERA del event loop.
            _mq = {"query": (args.get("query") or "").strip(),
                   "action": (args.get("action") or "play").strip().lower()}
            if music_req["v"] is None:
                music_req["v"] = _mq
            else:
                # COLAPSO determinista de VARIAS play_music en un turno (V2-047 F4, sesión 23:15: el modelo
                # no-razonador emite play Y queue a la vez para «luego pon X» → si gana el 'play' reproduce en
                # vez de encolar). Con música YA sonando, un `queue` MANDA sobre un `play` (añades, no
                # reemplazas); sin nada sonando, se queda la primera. Sobre el ESTADO del rail + la acción que
                # el propio modelo eligió — no una tabla de palabras.
                try:
                    from nucleo import rails as _rails_m
                    _playing = _rails_m.get("music.playing") is not None
                except Exception:
                    _playing = False
                if _playing and _mq["action"] == "queue" and music_req["v"].get("action") != "queue":
                    music_req["v"] = _mq
                # BUG real 2026-07-23: "pon música de Queen y súbele el volumen al máximo" — el modelo emite
                # play(Queen) + volume_up en el MISMO turno; antes la 2ª se tiraba en silencio mientras el
                # modelo SÍ decía "subo el volumen" (confabulación: la voz prometía algo que el código no
                # hacía). Una 2ª llamada de CONTROL puro (sin query, verbo de ajuste) tras un play/queue NO se
                # descarta: se guarda como `followup` y se ejecuta EN SECUENCIA tras el play (abajo).
                elif (not _mq["query"] and _mq["action"] in
                      ("volume_up", "volume_down", "pause", "resume", "stop", "next", "previous")):
                    music_req["followup"] = _mq
        elif name == "play_video":
            # V2-045: VÍDEO = widget youtube (VER); una por turno. Cuerpo + LICENCIA V2-635 («Muy bien,
            # señora.» recargaba el que sonaba) en `video_turn.voice_execute` — una impl, ambos canales.
            if "play_video" not in _tool_fired:
                _tool_fired.add("play_video")
                _video_turn.voice_execute(args, text, emit, _apply_widget_data, deduped,
                                          last_reply=brain._last_reply or "", brief=_brief)
        elif name == "show_images":
            # V2-457: FOTOS = visor `imagenes` (VER), tercera hermana de play_music/play_video. Una por
            # turno; se EJECUTA tras el stream (buscar es red) y se dice allí si el modelo calló.
            if "show_images" not in _tool_fired:
                _tool_fired.add("show_images")
                images_req["v"] = _image_turn.request_from([{"name": name, "args": args}])
                _cvis.present("imagenes", reason="turn-order", src="flash", emit=emit)
                emit("brain", "🖼️ fotos → visor imagenes", text=images_req["v"]["query"][:80], role="system")
        elif name == "show_widget":
            # MOSTRAR un widget (incl. JUEGOS) como TOOL de 1ª clase — más fiable que el tag [[show]] cuando la
            # palabra colisiona con play_music/play_video ('juega al snake'). Converge en la MISMA ruta de canvas
            # ([[show:id]], dedup/idempotente). Resuelve el id: exacto del catálogo o fuzzy con runtime.identify.
            if "show_widget" not in _tool_fired:
                _tool_fired.add("show_widget")
                _wid = (args.get("widget_id") or "").strip()
                # GUARD (V2-567): una orden de CERRAR no se contesta con un show. Medido en vivo: «Cierra los
                # contactos» → el modelo llamó show_widget(mensajeria); contactos lo cerró el backstop, así que
                # UNA orden produjo DOS mutaciones. El probe ya tenía la regla escrita («un canvas:show ESPURIO
                # en un turno de cerrar SÍ debe corregirse») y este canal no la aplicaba. El show se descarta y
                # el backstop de cierre de más abajo hace el cierre — una orden, una mutación. V2-750 — AND THE GRAMMAR ONLY PROPOSES BELOW. Measured (session b41925f6): «vamos a HACER una cosa, ábreme el WIDGET de vídeo» matched `hacer una cosa, abreme el widget` and built a duplicate video player called `entonces-vamos-cosa`, while this same turn's verdict said `catalog_widget=youtube` at 1.00 and nobody read it. `build_decision` composes that verdict with `build_or_use`: it VETOES a create over a card we already have, and REACHES the generator where no table of ours can read the script (zh/ja/hi 6/9 → 9/9, node 2.68).
                if _router.show_contradicts_the_order(text) or _canvas_lic.closing_turn(_brief, _wid):
                    emit("brain", "🚧 show_widget descartado: la orden dice CERRAR, no abrir",
                         text=(_wid or "?")[:40], role="system")
                # GUARD: CREAR un widget nuevo NO es show → escala al generador (el modelo elige show_widget para
                # 'créame un widget de X' e `identify` devuelve un widget EXISTENTE equivocado). Backstop determinista.
                elif (_bd := _build_decision.decide(text, brief=_brief, proposed=_router.looks_like_create_widget(text)))[0]:
                    if escalate_req["v"] is None:
                        escalate_req["v"] = text
                    emit("brain", "🏗️ show_widget→CREATE: se escala al generador (no es un show)", text=_bd[1][:60], role="system")
                else:
                    from widgets import runtime
                    # Resolver CON CERTEZA (V2-082) — the whole resolution lives in
                    # show_target.resolve_show since V2-650b (ratchet extraction, guard passed in).
                    _res, _open, _recent = _show_target.resolve_show(
                        _wid, text, brain._window, brain._last_action, _show_guard_target)
                    _rid = _res.get("match") or ""
                    _rid = _rid if (_rid and runtime.get(_rid.split("::", 1)[0]) is not None) else ""
                    _sys = _res.get("system")
                    # V2-650b: a widget the operator JUST closed does not reopen over chatter — the
                    # model re-emitted its DISCARDED show and the card came back over nobody's order.
                    if _rid and not _canvas_lic.reopen_license(_rid, text, _open, _recent):
                        emit("brain", "🛡️ show de un widget recién cerrado sin pedirlo — ignorado "
                             "(context-bleed)", text=_rid, role="system")
                        deduped["v"] = True
                    elif _rid:
                        # V2-300 — la BASE con una instancia viva delante resuelve a la INSTANCIA: en la
                        # ronda 24 el modelo mostró `results` con la hoja del encargo abierta al lado y el
                        # canvas abrió la caja PELADA, vacía. Misma decisión y mismo dueño que el cierre
                        # (`_close_target` → `instances.resolve_close`); con varias abiertas se pregunta.
                        _r2 = _show_target_instance(_rid, text, brain._last_spoken or "")
                        if _r2.get("ask"):
                            clarify["msg"] = _r2["ask"]
                            emit("brain", "🤔 show_widget con varias hojas → pregunto", text=_rid,
                                 role="system")
                        else:
                            _rid = _r2.get("id") or _rid
                            # V2-605: the choice was FORCED (we had already asked and he did not pick) → the
                            # ack has to name it, or an undisclosed decision costs the next three turns.
                            acted["show_chose"] = str(_r2.get("chose") or "")
                            _tag_emit("show", {"id": _rid})
                            # V2-209: QUÉ se abrió, no solo QUE se abrió. Sin el id, el ack de más abajo no
                            # puede distinguir «aquí lo tienes» de «te lo abro y sigo con ello», que es la
                            # diferencia entre informar y afirmar una entrega que no ha ocurrido.
                            acted["widget_id"] = _rid
                            emit("brain", "🪟 show_widget → canvas", text=_rid, role="system",
                                 extra={"empty": _surface_is_empty(_rid)})
                    elif _wall_tab_for(_sys, text):
                        # It named the CHAT, or the widget catalogue (V2-761: «ábreme las apps») — two
                        # tabs of the native wall, not widgets → open the wall on that tab.
                        emit("panel", "open", extra={"tab": _wall_tab_for(_sys, text), "src": "flash"})
                        emit("brain", f"🗂️ show_widget→{_sys} (superficie de sistema)", role="system")
                        acted["widget"] = True
                    else:
                        # V2-082: NO se fabrica un widget cuando no hay match. Si nombró una pieza de sistema o
                        # nada reconocible → se PREGUNTA con naturalidad, jamás se escala al generador ni se abre
                        # el "más parecido". (Crear solo con crea/genera/hazme/modifica, ya filtrado arriba.)
                        clarify["msg"] = (_say().open_no_such_piece if _sys is None
                                          else _say().open_system_piece)
                        emit("brain", "🤔 show_widget sin match → pregunto (no fabrico widget)",
                             text=str(_sys or "—"), role="system")
        elif name == "show_panel":
            # V2-079: abre el PANEL nativo lateral (ChatWall) en una pestaña por voz — 'enséñame los procesos',
            # 'los crons', 'ábreme el chat'. NO es un widget del canvas: se emite un evento `panel` que el
            # frontend (sse.js) traduce a store.setChatTab + setChatOpen. UI nativa e intocable.
            if "show_panel" not in _tool_fired:
                _tool_fired.add("show_panel")
                _tab = _router._canon_panel(args.get("panel"))
                if _tab == "apps":      # V2-761: «¿qué apps tengo CUSTOMIZADAS?» → the Custom sub-tab
                    _tab = _wall_tab_for("apps", _router.operator_words(operator_text, text))
                # 2026-08-10: también CIERRA. Antes solo abría, así que «cierra el chat» no tenía a dónde ir y
                # el turno acababa en un «vale, cerrado» que era falso.
                _act = _router._canon_panel_action(args.get("action"))
                emit("panel", _act, extra={"tab": _tab, "src": "flash"})
                emit("brain", f"🗂️ show_panel → panel nativo ({_act})", text=_tab, role="system")
                acted["widget"] = True     # cuenta como acción de UI (ack "nunca mudo" + no escala espurio)
        elif name == "manage_widget_alias":
            # V2-082: añade/quita un NOMBRE/ALIAS de un widget por voz ("añade el alias WhatsApp a mensajería").
            # Escritura QUIRÚRGICA del manifest (no regenera código), con guard de colisión. Resuelve el widget
            # por id exacto o por nombre/alias (mismo resolver de certeza). Este bucle de tool-calls es SÍNCRONO
            # (como _apply_widget_data) → la escritura va inline (I/O de fichero de ms, no un await).
            if "manage_widget_alias" not in _tool_fired:
                _tool_fired.add("manage_widget_alias")
                from widgets import aliases as _al, runtime as _rt_al
                _awid = (args.get("widget_id") or "").strip()
                _alias = (args.get("alias") or "").strip()
                _op = "remove" if str(args.get("op") or "add").lower().startswith(("rem", "quit", "borr")) else "add"
                _rid = _awid if (_awid and _rt_al.get(_awid) is not None) else \
                    ((_rt_al.identify(_awid or text) or {}).get("match") or "")
                if not _rid:
                    clarify["msg"] = _say().alias_which_widget
                elif not _alias:
                    clarify["msg"] = _say().alias_which_name
                else:
                    _res = (_al.remove if _op == "remove" else _al.add)(_rid, _alias)
                    acted["widget"] = True
                    if _res.get("ok") and not _res.get("unchanged"):
                        clarify["msg"] = (_say().alias_removed.format(alias=_alias) if _op == "remove"
                                          else _say().alias_added.format(wid=_rid, alias=_alias))
                    elif _res.get("unchanged"):
                        clarify["msg"] = (_say().alias_unchanged_had_not if _op == "remove"
                                          else _say().alias_unchanged_had).format(wid=_rid)
                    else:
                        clarify["msg"] = _res.get("error") or _say().alias_failed
                    emit("brain", f"🏷️ manage_widget_alias {_op} → {_rid}", text=_alias, role="system")
        elif name == "close_widget":
            # Each CARD once, not the tool once: «close the calendar and the messages» may be two calls.
            if _show_target.close_dispatch(args, _tag_emit, emit, text=_bnotes.operator_half(text),
                                           done=_closed_by_tool):
                _tool_fired.add("close_widget")
                acted["widget"] = True
        elif name == "fullscreen_widget":
            # BUG 2026-07-23: sin tool, el modelo confabulaba éxito. Cuerpo (resolución V2-609 + licencia y
            # dirección V2-635: «pausa el vídeo» disparaba fullscreen; «minimiza» ya no cae en el toggle al
            # revés) en `show_target.fullscreen_dispatch` — una decisión, ambos canales.
            if "fullscreen_widget" not in _tool_fired:
                _tool_fired.add("fullscreen_widget")
                _show_target.fullscreen_dispatch(args, text, _tag_emit, emit, deduped)
        elif name == "arrange_canvas":
            # V2-588: «ordena los widgets» tenía TODO el tramo de abajo construido (botón ⤢, Desktop.arrange,
            # POST /api/canvas/arrange, handler SSE) y NINGUNA cara hacia el modelo — que llegó a afirmar en
            # vivo «no hay un botón en el front-end para eso» (falso) y a improvisar re-abriendo tarjetas.
            # Acción del CANVAS entero: sin id que resolver, el mismo emit que el endpoint REST.
            if "arrange_canvas" not in _tool_fired:
                _tool_fired.add("arrange_canvas")
                emit("widget", "arrange", extra={"src": "flash"})
                emit("brain", "▦ arrange_canvas → canvas", role="system")
                acted["widget"] = True
        elif name == "reply_message":
            # V2-051: responder un mensaje del buzón. Converge en la data-op `reply` de `mensajeria`
            # (confirm:true) → el gate CONFIRM lee el borrador y pide OK antes de ENVIAR. Una por turno.
            if "reply_message" not in _tool_fired:
                _tool_fired.add("reply_message")
                try:
                    _n = int(args.get("n"))
                except (TypeError, ValueError):
                    _n = None
                _rtext = (args.get("text") or "").strip()
                if _n is not None and _rtext:
                    _apply_widget_data("mensajeria", "reply", {"n": _n, "text": _rtext})
                else:
                    clarify["msg"] = _say().reply_which_message
        elif name == "delete_widget":
            _request_delete_confirm((args.get("widget_id") or "").strip(), text)
        elif name == "restore_widget":
            _request_restore_confirm((args.get("widget_id") or "").strip(), text)
        elif name == "confirm_widget_delete":
            confirm_state["handled"] = _resolve_confirm(bool(args.get("confirmed")))
        elif name == "set_style_directive":
            # V2-046 A1 + V2-633 — the whole path (identity actions first, style FLAGS for the engine's
            # mouths applied synchronously, rule text persisted off-loop) lives in
            # `nucleo/flash/style_directive.py`, extracted paying the ratchet. True = identity consumed it.
            directive = (args.get("directive") or "").strip()
            if directive:
                style_fired["v"] = True
                from nucleo.flash import style_directive as _styled
                if _styled.handle(directive, text, brain, emit, _spawn): return
        elif name == "authenticate_web":
            # Guard DETERMINISTA (V2-022): si además de entrar hay una TAREA ("entra en mi Gmail y BÓRRAME…"),
            # no es un login → es una tarea con sesión → escala al navegador (que resuelve el login como parte
            # de la tarea). authenticate_web es SOLO para login puro ("conéctame a Wallapop").
            # V2-176: la DECISIÓN (cuál de los cuatro caminos es) vive en `nucleo/flash/web_auth.decide`,
            # compartida con el canal de texto — la cadena estaba solo aquí, así que el otro canal no tenía
            # ninguna. Los EFECTOS se quedan donde estaban: cada canal emite lo suyo y este además es el que
            # tiene `escalate_req`.
            from nucleo.flash import web_auth as _wa_v
            _site = (args.get("site") or "").strip()
            _kind_v, _site_resolved = _wa_v.decide(_site, text)
            if _kind_v == _wa_v.KIND_MUSIC:
                # INVARIANTE (2026-07-16): un servicio de MÚSICA (Spotify) se conecta en el widget `musica`
                # (su tarjeta OAuth), NUNCA por el navegador. El routing del titular anterior insistía en authenticate_web
                # para "conéctame a mi cuenta de Spotify" pese a la descripción → el guard lo redirige aquí.
                _cvis.present("musica", reason="turn-order", src="flash", emit=emit)
                emit("brain", "🎵 conectar música → tarjeta del widget musica (no navegador)", text=_site or text[:60], role="system")
            elif _kind_v == _wa_v.KIND_MESSAGING:
                # INVARIANTE (V2-045, espejo del guard de música): WhatsApp/Telegram se VINCULAN por QR DENTRO
                # del widget `mensajeria`, NUNCA por login de navegador. 'conéctame/abre WhatsApp' → mostrar el
                # widget (ahí está el QR), no abrir un Chromium en whatsapp.com.
                _cvis.present("mensajeria", reason="turn-order", src="flash", emit=emit)
                emit("brain", "💬 conectar mensajería → QR del widget mensajeria (no navegador)", text=_site or text[:60], role="system")
            elif _kind_v == _wa_v.KIND_TASK:
                if escalate_req["v"] is None:
                    escalate_req["v"] = text
                emit("brain", "🔐→🧭 login+tarea → escalado (no solo auth)", role="system")
            else:
                _start_web_auth(_site_resolved)
        elif name == "login_done":
            _finish_web_auth()
        elif name == "connect_cluster":
            # V2-064: la tubería real (bridge.dispatch/dispatch_tag) ya existía — lo que faltaba era esta tool
            # PARA que el FlashBrain pudiera invocarla. No conecta directo: pide confirmación determinista
            # primero (ver _request_cluster_confirm) — la descripción de la tool sola no bastó para que el
            # modelo distinguiera una orden real de un texto pegado que solo mencionaba un cluster_id/token.
            _ccid = (args.get("cluster_id") or "").strip()
            _ctok = (args.get("token") or "").strip()
            # V2-086 — DOS clases de cluster. Antes la condición era `_ccid and _ctok`, así que un cluster
            # PÚBLICO (MeshKore Commons: tokenless por diseño) se descartaba en silencio: la tool se llamaba,
            # no pasaba nada y el operador no recibía ni un "no puedo". Ahora basta el cluster_id cuando el
            # cluster es público; el token solo es obligatorio en los privados.
            # ⚠️ THE NAME IS `_cluster_vis`, NOT `_cvis`, AND THAT IS THE WHOLE POINT (V2-758).
            # `_cvis` is this module's alias for `nucleo.flash.canvas_visibility` (top of the file). Assigning
            # to that name ANYWHERE in this function makes it LOCAL for the WHOLE function — so the three
            # branches above that call `_cvis.present(...)` (show_images, the music guard, the messaging
            # guard) raised `UnboundLocalError` before this line ever ran. Measured on his engine
            # 2026-09-23: nine turns, every one of them reported to him as «Cerebro rápido caído — turno
            # degradado» while DeepSeek was answering perfectly. A local that shadows a module alias is not
            # a style problem: it silently kills every earlier use of that module in the same scope.
            _cluster_vis = (args.get("vis") or "").strip().lower()
            if _cluster_vis not in ("public", "private", ""):
                _cluster_vis = ""
            if _ccid and not _ctok and not _cluster_vis:
                _cluster_vis = "public"   # id sin token = solo puede ser un cluster abierto
            if _ccid and (_ctok or _cluster_vis == "public"):
                _cname = (args.get("name") or "meshcore").strip() or "meshcore"
                _chandle = (args.get("handle") or "").strip() or None
                # PERMISOS al conectar (V2-076): si el operador concede código, se persiste con la conexión.
                _cperms = None
                if bool(args.get("code")):
                    _cperms = {"workers": True, "code": True, "repo": (args.get("repo") or "").strip() or None}
                _request_cluster_confirm(_cname, _ccid, _ctok, _chandle, perms=_cperms,
                                         vis=("public" if _cluster_vis == "public" else ""))
        elif name == "cluster_send":
            # V2-086: enviar al cluster, ahora como tool de 1ª clase (antes iba por widget_data sobre el
            # widget `cluster-registro`, que ya no existe). Sale por el MISMO camino que el tag
            # [[cluster.send]] → `bridge.dispatch_tag`, así que hereda el guard de salida (un secreto duro
            # bloquea el envío) y el journal. No pide confirmación: es una comunicación normal que el
            # operador acaba de pedir, como escribir en un chat.
            _stext = (args.get("text") or "").strip()
            if _stext:
                _sto = (args.get("to") or "").strip()
                _scl = (args.get("cluster") or "").strip()
                if not _scl:
                    try:
                        from connectors import meshkore as _mk2
                        _live = [c for c in _mk2.get_manager().clusters() if c.get("connected")]
                        _scl = _live[0]["name"] if len(_live) == 1 else ""
                    except Exception:
                        _scl = ""
                if _scl:
                    _data = {"text": _stext}
                    if _sto:
                        _data["to"] = _sto
                    try:
                        from connectors import meshkore as _mk3
                        _spawn(_mk3.dispatch_tag(f"cluster.send:{_scl}", {"data": _data}), "cluster-send")
                        emit("brain", "🛰 mensaje enviado al cluster", role="system",
                             text=f"{_scl}{('→' + _sto) if _sto else ''}")
                    except Exception as _e:  # noqa: BLE001
                        logger.warning(f"cluster_send falló: {_e}")
                else:
                    emit("brain", "🛰 cluster_send sin cluster resuelto (¿varios o ninguno?)", role="system")
        elif name == "set_cluster_objective":
            # T-02 (auditoría 2026-07-26): antes NADA escribía nunca capsule.objective — el guard
            # `perms.gate_dev_by_objective` (V2-076) dejaba el dev-worker de CUALQUIER cluster con permiso
            # 'code' permanentemente inerte por falta de una vía para fijarlo. Sin confirm-gate (a diferencia
            # de connect_cluster): esto es solo bookkeeping declarativo del operador, no toca la red ni
            # ejecuta nada — reversible llamando de nuevo con objective vacío.
            _ocluster = (args.get("cluster") or "").strip()
            _opeer = (args.get("peer") or "").strip()
            _oobjective = (args.get("objective") or "").strip()
            if _ocluster and _opeer:
                async def _persist_objective(cluster: str, peer: str, objective: str) -> None:
                    try:
                        from connectors.meshkore import capsule as _capsule
                        await asyncio.to_thread(_capsule.patch, cluster, peer, objective=objective)
                        emit("brain", ("🎯 objetivo de cluster fijado" if objective else
                                      "🎯 objetivo de cluster borrado"),
                             text=f"{cluster}·{peer}: {objective}"[:160], role="system")
                    except Exception as e:  # noqa: BLE001
                        logger.warning(f"set_cluster_objective no persistido (voz sigue): {e}")
                _spawn(_persist_objective(_ocluster, _opeer, _oobjective), "cluster-objective")
            else:
                clarify["msg"] = _say().objective_which_peer
        elif name == "send_to_worker":
            # V2-038 (↓): refina/amplía un worker vivo → INYECTA (no relanza). Fire-and-forget marshalado al
            # loop del server (§v3·O: nunca await de una op de worker en el turno).
            which = (args.get("which") or "").strip()
            msg = (args.get("message") or "").strip()
            if msg:
                try:
                    from nucleo import dispatch as _d
                    _d.inject_soon(which or "todo", msg)
                    worker_acted["v"] = "inject"
                    emit("brain", "↪️ inyección a worker", text=f"{which}: {msg}"[:120], role="system")
                    # Observability (V2-090 gap): this correction continues a LIVE task — its own dialogue
                    # exchange should show up INSIDE that task's flow instead of opening a fresh one. Only
                    # when the target is unambiguous (resolve_sessions picks exactly one): with several live
                    # sessions, forcing a merge would be guessing which one this belongs to.
                    try:
                        # ⚠️ Found by ruff F821 (2026-09-05): `_trace` was never in scope here, so this
                        # whole merge — documented as working since V2-090 — died as a NameError inside
                        # this very except, every time. The audited fail-open class, live in the hot path.
                        from voice import trace as _trace
                        _targets = _d.resolve_sessions(which or "todo")
                        if len(_targets) == 1:
                            _target_trace = _d.trace_of(_targets[0])
                            if _target_trace:
                                _trace.adopt(_target_trace)
                    except Exception:
                        pass
                except Exception as e:  # noqa: BLE001
                    logger.warning(f"send_to_worker falló: {e}")
        elif name == "stop_worker":
            which = (args.get("which") or "").strip()
            # ── GUARD 1: NO SE MATA A QUIEN ACABAS DE CONTESTAR (2026-08-14, sesión b70a45d0) ──────────────
            # El turno emitió `answer_worker` con la autorización que el worker llevaba 30 s esperando («Sí,
            # autorizado: borra TODA la agenda») Y `stop_worker` detrás → la tarea murió `ok:False` con la
            # respuesta ya entregada, y le dijo al operador «Vale, se lo digo» — falso al decirlo; la agenda
            # nunca se vació. Contestar y matar en el MISMO turno es incoherente: gana la respuesta (no destructiva).
            if worker_acted["v"] == "answer":
                emit("brain", "🛡️ stop_worker ignorado — este turno ACABA de responder al worker",
                     text=f"{which or 'todo'}", role="system",
                     extra={"cat": "flash", "kind_diag": "stop_after_answer"})
                return
            # ── GUARD 2: MATAR EXIGE QUE EL OPERADOR LO HAYA DICHO ────────────────────────────────────────
            # Mismo espíritu que el guarda de context-bleed de las data-ops (~L797), para lo irreversible:
            # sin orden de parar EN el turno del operador, el `stop_worker` es arrastre del anterior. En la
            # sesión, el stop nació de una queja de DOS TURNOS ANTES sobre widgets («los dos navegadores no se
            # tenían que haber abierto»), cancelada por barge-in — el modelo la arrastró y la hizo un hachazo.
            # OJO con «para»: en castellano es preposición mucho más a menudo que verbo («para nada», «para
            # ti»), y por eso no entra suelto — de hecho «para» a secas solo calla la voz, nunca para tareas
            # (regla del operador). Se piden formas inequívocas.
            if not _says_stop(text):
                emit("brain", "🛡️ stop_worker ignorado — el operador no ha pedido parar nada (context-bleed)",
                     text=(text or "")[:120], role="system",
                     extra={"cat": "flash", "kind_diag": "stop_without_order", "which": which or "todo"})
                return
            try:
                from nucleo import dispatch as _d
                # GUARD matar-TODO (sesión 23:15 2026-07-16, T49): ante «si solo es una tarea» el modelo llamó
                # stop_worker(todo) y mató las DOS sesiones vivas — incluida la de la ITV que SÍ trabajaba
                # (el operador se quejaba de VENTANAS duplicadas, no de procesos). Matar es irreversible →
                # "todo" con VARIAS tareas de objetivos DISTINTOS exige que el operador lo haya dicho de
                # verdad (todo/todas/ambos… en su turno, es/en); si no, se resuelve a la sesión que CASE con
                # el texto (`resolve_sessions`) y, sin match claro, NO se mata nada (se pregunta).
                import re as _re_stop
                _w = which or "todo"
                if _w == "todo":
                    _live = _d.pending_summaries()
                    _goals = {(s.get("request") or "")[:60] for s in _live}
                    _says_all = bool(_re_stop.search(r"\b(todo|todos|todas|ambos|ambas|all|both|everything)\b",
                                                     _norm_nfkd(text)))
                    if len(_goals) > 1 and not _says_all:
                        _match = _d.resolve_sessions(text)
                        if len(_match) == 1:
                            _w = _match[0]
                        else:
                            clarify["msg"] = _say().stop_which_worker
                            worker_acted["v"] = "stop"      # atendido (preguntando), sin matar a ciegas
                            emit("brain", "🛑 stop_worker(todo) RETENIDO (varias tareas distintas, sin 'todo' "
                                 "explícito)", text=text[:100], role="system")
                            return
                tids = _d.cancel_soon(_w)
                if _w == "todo":     # «para todo y quédate tranquilo» → además LIMPIA las marcas de trabajo
                    from nucleo import reset as _reset_mod
                    _reset_mod.abandon_work_soon(source="voz")     # mismo núcleo que Reset; ver su docstring
                worker_acted["v"] = "stop"
                emit("brain", "🛑 stop worker", text=f"{_w} → {tids}"[:120], role="system")
            except Exception as e:  # noqa: BLE001
                logger.warning(f"stop_worker falló: {e}")
        elif name == "answer_worker":
            ans = (args.get("answer") or "").strip()
            if ans:
                try:
                    from nucleo import worker_api as _wapi
                    if _wapi.answer_active_soon(ans):
                        worker_acted["v"] = "answer"
                        emit("brain", "💬 respuesta a worker", text=ans[:120], role="system")
                except Exception as e:  # noqa: BLE001
                    logger.warning(f"answer_worker falló: {e}")

    def _finish_web_auth() -> None:
        """El operador dijo por voz que ya inició sesión → encola `auth_done` a la tarea que esperaba login
        (mismo desenlace que el botón «Ya he iniciado sesión» de la tarjeta). Operator-only por construcción."""
        from nucleo.flash import web_auth as _wa_f
        _wa_f.finish("voz")     # V2-176: un solo cuerpo, compartido con el canal de texto

    def _start_web_auth(site: str) -> bool:
        """Abre la ventana REAL del navegador para que el operador inicie sesión en `site` (operator-only por
        construcción: es un tool del FlashBrain, y el canal de cluster no tiene tools). Crea la tarjeta de la
        tarea, la muestra y encola `authenticate` al owner del navegador. El owner relanza headed y, al terminar
        (auth_done), vuelve a headless con la sesión en el perfil. NUNCA tecleamos credenciales aquí.
        Bug 2026-07-23: sin `site` (el backstop no reconoció ningún sitio en el texto) esto abría SIEMPRE
        wallapop.com por defecto — un login a un sitio que nadie pidió. Sin sitio reconocido, no hay NADA que
        abrir: no adivinamos. Devuelve False (no se abrió nada) para que el llamador no cante "login por
        fallback" sobre una acción que no ocurrió."""
        from nucleo.flash import web_auth as _wa_s
        return bool(_wa_s.start(site))   # V2-176: un solo cuerpo, compartido con el canal de texto
    return SimpleNamespace(tag_emit=_tag_emit, apply_widget_data=_apply_widget_data, on_tool_call=_on_tool_call, resolve_confirm=_resolve_confirm, start_web_auth=_start_web_auth)
