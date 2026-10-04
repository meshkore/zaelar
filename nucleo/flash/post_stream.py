"""What the voice turn does AFTER the model has streamed: the post-stream chain (V2-778 F1-10b, 2026-10-01).

Moved out of `voice/engine/llm/providers/nucleo.py::_run_inner`: the ordered backstops and second passes that
run once the fast model has answered — the pure-show guard, the commission and picture passes, the escalation
fragment drop, the promise and act repairs, the close license, vault reveal, memory recall, web search, listings,
music, the confirm gates, the acks — up to the holding line of an escalation with no words. The code is the SAME,
byte for byte apart from one indentation level and the turn's tag buffer: `buf` belongs to the provider (its
`take`/`speak` rebind it), so the two places that reset it and the listing pass that feeds it call
`_buf_reset()` / `_buf_add()` instead.

`run()` receives, as keyword arguments, exactly the names the chain used to read from the turn, plus the motor
helpers it used (injected, so this module never imports `voice.engine`). It returns what the rest of the turn
reads from it: `spoken_text` and `_op_text`. It is ONE module for now; splitting it by family is owed (the size
ratchet names it).
"""
from __future__ import annotations

import asyncio
import time

from loguru import logger

from nucleo.flash import (canvas_license as _canvas_lic, canvas_visibility as _cvis, close_guards as _closeg,
                          data_ops as _data_ops, direct_action as _direct_action,
                          escalation_guard as _eguard, harness_turn as _ht, image_turn as _image_turn,
                          listing_turn as _lt, reminder_guards as _rg, show_target as _show_target,
                          task_recall as _trecall)
from nucleo.flash.panel_canon import wall_tab_for as _wall_tab_for
from voice import brain_notes as _bnotes
from widgets import confirm as _wconfirm


async def run(*, FastClient, _apply_widget_data, _ask_waiting, _auth_pending, _brief, _cover_work, _data_ops_hechas, _dialog, _filler_audio, _has_workers, _prev_pending, _prompt_mod, _repeat_repair, _resolve_confirm, _router, _shown_ids, _tag_emit, _tool_fired, _turn_op_tasks, acted, aside, attention, brain, canvas_h, clarify, confirm_state, cron_seen, data_done, emit, escalate_req, had_pending_confirm, images_req, listing_req, llm_metrics, music_req, operator_text, read_req, recall_req, reopen_req, reveal_req, search_req, send, speak, spec, speech, spoken, style_fired, take, text, worker_acted,
              _say, _close_target, _identify, _identify_system, _show_guard_target, _show_target_instance, with_also_named, _buf_reset, _buf_add) -> dict:
    """The post-stream chain of ONE turn. Returns `{"spoken_text", "_op_text"}`."""
    # V2-778 F2-16 — did the reply promise something? Asked ONCE, off the loop, now that the words are final; every
    # promise reader below finds the verdict cached (the phrase tables answer only if it cannot).
    from nucleo.flash import reply_promise as _reply_promise
    await _reply_promise.prefetch("".join(spoken).strip(), operator_text)
    # V2-778 F1 — holding the model to its words (pure show, ghost worker, third rung, promises) lives in
    # `nucleo/flash/post_stream_words.py`.
    _blk = await _ps_words.hold_the_model_to_its_words(
        _apply_widget_data=_apply_widget_data,
        _brief=_brief,
        _data_ops_hechas=_data_ops_hechas,
        _has_workers=_has_workers,
        _prompt_mod=_prompt_mod,
        _repeat_repair=_repeat_repair,
        _router=_router,
        _show_guard_target=_show_guard_target,
        _tag_emit=_tag_emit,
        _tool_fired=_tool_fired,
        _turn_op_tasks=_turn_op_tasks,
        acted=acted,
        brain=brain,
        canvas_h=canvas_h,
        clarify=clarify,
        cron_seen=cron_seen,
        data_done=data_done,
        emit=emit,
        escalate_req=escalate_req,
        images_req=images_req,
        listing_req=listing_req,
        music_req=music_req,
        operator_text=operator_text,
        read_req=read_req,
        recall_req=recall_req,
        reopen_req=reopen_req,
        reveal_req=reveal_req,
        search_req=search_req,
        send=send,
        speak=speak,
        spec=spec,
        speech=speech,
        spoken=spoken,
        text=text,
        worker_acted=worker_acted,
    )
    if '_named_by_verdict' in _blk:
        _named_by_verdict = _blk['_named_by_verdict']
    if '_no_tool' in _blk:
        _no_tool = _blk['_no_tool']
    if '_op_text' in _blk:
        _op_text = _blk['_op_text']
    if 'spoken_text' in _blk:
        spoken_text = _blk['spoken_text']
    # U2 (demo passes 34-51, 2026-09-29): «Sure — putting on Like a Prayer now» and no call — an ENGLISH promise
    # of playback, read here with the same gate the branch below applies (music card open, or a music word).
    # V2-778 F1 — the light lanes the model chose (playback, closes, secret, recall, read, search, music) live in
    # `nucleo/flash/post_stream_lanes.py`.
    _blk = await _ps_lanes.run_the_light_lanes(
        FastClient=FastClient,
        _apply_widget_data=_apply_widget_data,
        _brief=_brief,
        _buf_add=_buf_add,
        _buf_reset=_buf_reset,
        _cardc=locals().get('_cardc'),
        _close_target=_close_target,
        _cover_work=_cover_work,
        _identify=_identify,
        _identify_system=_identify_system,
        _named_by_verdict=_named_by_verdict,
        _no_tool=_no_tool,
        _op_text=_op_text,
        _prompt_mod=_prompt_mod,
        _router=_router,
        _rv=locals().get('_rv'),
        _say=_say,
        _show_target_instance=_show_target_instance,
        _shown_ids=_shown_ids,
        _t=locals().get('_t'),
        _tag_emit=_tag_emit,
        _tool_fired=_tool_fired,
        _turn_op_tasks=_turn_op_tasks,
        acted=acted,
        attention=attention,
        brain=brain,
        clarify=clarify,
        data_done=data_done,
        emit=emit,
        escalate_req=escalate_req,
        images_req=images_req,
        listing_req=listing_req,
        music_req=music_req,
        operator_text=operator_text,
        read_req=read_req,
        recall_req=recall_req,
        reopen_req=reopen_req,
        reveal_req=reveal_req,
        search_req=search_req,
        send=send,
        speak=speak,
        spec=spec,
        speech=speech,
        spoken=spoken,
        spoken_text=spoken_text,
        take=take,
        text=text,
        with_also_named=with_also_named,
    )
    if 'spoken_text' in _blk:
        spoken_text = _blk['spoken_text']

    # RED DETERMINISTA de confirmación (V2-017): si había un borrado pendiente y el modelo NO lo resolvió por tool, pero el operador dijo claramente sí/no → resuélvelo igual (no depende del LLM, como hard_interrupt).
    # V2-778 F1 — settling what is pending (confirmations, a waiting worker, a stop, the question owed): `post_stream_settle.py`.
    if data_done["v"] and not spoken_text and _turn_op_tasks:   # demo pass 104 C5: no «Done.» over a refusal
        spoken_text = await _data_ops.say_refusal_instead(_turn_op_tasks, data_done, send, speech) or spoken_text
    _blk = await _ps_settle.settle_what_is_pending(
        _ans=locals().get('_ans'),
        _ask_waiting=_ask_waiting,
        _auth_pending=_auth_pending,
        _brief=_brief,
        _dialog=_dialog,
        _filler_audio=_filler_audio,
        _langs=locals().get('_langs'),
        _prev_pending=_prev_pending,
        _r=locals().get('_r'),
        _resolve_confirm=_resolve_confirm,
        _router=_router,
        _shown_ids=_shown_ids,
        acted=acted,
        aside=aside,
        brain=brain,
        clarify=clarify,
        confirm_state=confirm_state,
        data_done=data_done,
        emit=emit,
        escalate_req=escalate_req,
        had_pending_confirm=had_pending_confirm,
        llm_metrics=llm_metrics,
        music_req=music_req,
        operator_text=operator_text,
        search_req=search_req,
        send=send,
        speech=speech,
        spoken_text=spoken_text,
        style_fired=style_fired,
        text=text,
        worker_acted=worker_acted,
    )
    if 'spoken_text' in _blk:
        spoken_text = _blk['spoken_text']
    return {"spoken_text": spoken_text, "_op_text": _op_text}


# V2-778 F1 — the chain's three moved blocks; module imports at the end (they read this module back).
from nucleo.flash import post_stream_lanes as _ps_lanes  # noqa: E402
from nucleo.flash import post_stream_settle as _ps_settle  # noqa: E402
from nucleo.flash import post_stream_words as _ps_words  # noqa: E402
