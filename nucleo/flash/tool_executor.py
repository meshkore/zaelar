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
from types import SimpleNamespace

from loguru import logger

from nucleo.flash import (build_decision as _build_decision, canvas_license as _canvas_lic,
                          canvas_visibility as _cvis, data_ops as _data_ops,
                          image_turn as _image_turn, listing_turn as _lt,
                          show_target as _show_target, video_turn as _video_turn)
from nucleo.flash import tool_executor_widget as _widget_half
from nucleo.flash.panel_canon import wall_tab_for as _wall_tab_for
from nucleo.flash.surface_ack import saved_state_is_empty as _surface_is_empty
from voice import brain_notes as _bnotes


def build(*, self, brain, emit, text, operator_text, _brief, canvas_h, aside, cron_seen, _shown_ids, acted, confirm_state, clarify, _closed_by_tool, _repeat_repair, data_done, deduped, escalate_req, search_req, listing_req, recall_req, read_req, reopen_req, reveal_req, music_req, images_req, style_fired, worker_acted, _frontend, _router, _tool_fired, _data_ops_hechas, _turn_op_tasks,
          _spawn, _say, _resolve_pending_confirm, _confirm_decide, _close_target, _identify, _identify_is_widget, _is_meta_widget_question, _norm_nfkd, _show_guard_target, _show_target_instance, with_also_named):
    """The executor of ONE turn. Returns the closures the turn calls: `tag_emit`, `apply_widget_data`,
    `on_tool_call`, `resolve_confirm`, `start_web_auth`."""
    _late: dict = {}
    _wh = _widget_half.build(self=self, brain=brain, emit=emit, text=text, operator_text=operator_text, _brief=_brief, canvas_h=canvas_h, aside=aside, cron_seen=cron_seen, _shown_ids=_shown_ids, acted=acted, confirm_state=confirm_state, clarify=clarify, _closed_by_tool=_closed_by_tool, _repeat_repair=_repeat_repair, data_done=data_done, deduped=deduped, escalate_req=escalate_req, search_req=search_req, listing_req=listing_req, recall_req=recall_req, read_req=read_req, reopen_req=reopen_req, reveal_req=reveal_req, music_req=music_req, images_req=images_req, style_fired=style_fired, worker_acted=worker_acted, _frontend=_frontend, _router=_router, _tool_fired=_tool_fired, _data_ops_hechas=_data_ops_hechas, _turn_op_tasks=_turn_op_tasks, _spawn=_spawn, _say=_say, _resolve_pending_confirm=_resolve_pending_confirm, _confirm_decide=_confirm_decide, _close_target=_close_target, _identify=_identify, _identify_is_widget=_identify_is_widget, _is_meta_widget_question=_is_meta_widget_question, _norm_nfkd=_norm_nfkd, _show_guard_target=_show_guard_target, _show_target_instance=_show_target_instance, with_also_named=with_also_named, _late=_late)
    _tag_emit = _wh._tag_emit
    _request_delete_confirm = _wh._request_delete_confirm
    _request_restore_confirm = _wh._request_restore_confirm
    _request_data_confirm = _wh._request_data_confirm
    _request_cluster_confirm = _wh._request_cluster_confirm
    _resolve_confirm = _wh._resolve_confirm
    _apply_widget_data = _wh._apply_widget_data
    _handle_widget_data_tool = _wh._handle_widget_data_tool
    _word_overlap = _wh._word_overlap
    _says_stop = _wh._says_stop

    def _on_tool_call(name: str, args: dict) -> None:
        # V2-778 F1 — the body lives in `nucleo/flash/tool_executor_calls.py`; this closure passes what it closed over.
        return _tx_calls._on_tool_call(name, args, _apply_widget_data=_apply_widget_data, _brief=_brief, _closed_by_tool=_closed_by_tool, _data_ops_hechas=_data_ops_hechas, _finish_web_auth=_finish_web_auth, _handle_widget_data_tool=_handle_widget_data_tool, _norm_nfkd=_norm_nfkd, _request_cluster_confirm=_request_cluster_confirm, _request_delete_confirm=_request_delete_confirm, _request_restore_confirm=_request_restore_confirm, _resolve_confirm=_resolve_confirm, _router=_router, _say=_say, _says_stop=_says_stop, _show_guard_target=_show_guard_target, _show_target_instance=_show_target_instance, _spawn=_spawn, _start_web_auth=_start_web_auth, _tag_emit=_tag_emit, _tool_fired=_tool_fired, _word_overlap=_word_overlap, acted=acted, brain=brain, clarify=clarify, confirm_state=confirm_state, deduped=deduped, emit=emit, escalate_req=escalate_req, images_req=images_req, listing_req=listing_req, music_req=music_req, operator_text=operator_text, read_req=read_req, recall_req=recall_req, reopen_req=reopen_req, reveal_req=reveal_req, search_req=search_req, self=self, style_fired=style_fired, text=text, worker_acted=worker_acted)

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
    _late["on_tool_call"] = _on_tool_call
    return SimpleNamespace(tag_emit=_tag_emit, apply_widget_data=_apply_widget_data, on_tool_call=_on_tool_call, resolve_confirm=_resolve_confirm, start_web_auth=_start_web_auth)
from nucleo.flash import tool_executor_calls as _tx_calls  # noqa: E402 — V2-778 F1, reads this module back
