"""The tool catalogue as a dict: tool name → the door that runs it (refactor2710-05 T-01).

`_on_tool_call` used to be one `if name == …: … elif …` chain of 32 arms. Each arm is now a function here, named as
the tool the model calls, and `CATALOG` is built from those functions — the names are not written twice, and the
model's tool list (`router.tools`) is checked against it (`test_the_tool_catalog_is_a_dict`). An arm takes the call's
`args` and `c`, the turn's context (every keyword `_on_tool_call` receives, read as `c.<name>`); a module-level name
of `nucleo/flash/tool_executor_calls.py` is read through `_x`, looked up at call time, so a patch there still governs.
"""
from __future__ import annotations

from nucleo.acts import search as _search


def _calls():
    from nucleo.flash import tool_executor_calls
    return tool_executor_calls


def need_capability(args: dict, c) -> None:
    _fam = str((args or {}).get("family") or "").strip()
    if _fam:
        c.self._need_family = _fam
    c.emit("brain", "🔓 el modelo pide una familia que se había recortado", text=_fam, role="system",
         extra={"cat": "flash", "family": _fam, "retry": True})
    return


def widget_data(args: dict, c) -> None:
    _x = _calls()
    # Demo pass 82, I1: `imagenes:show` with no pictures is the picture SEARCH (card_commission), not a data-op.
    if c.images_req["v"] is None:
        from nucleo.flash import card_commission as _cc
        _pic = _cc.picture_search_for_empty_show(str(args.get("widget_id") or ""), str(args.get("action") or ""),
                                                 args.get("payload"), c.operator_text or c.text)
        if _pic:
            c._tool_fired.add("show_images")
            c.images_req["v"] = _pic
            _x._tx._cvis.present("imagenes", reason="turn-order", src="flash", emit=c.emit)
            c.emit("brain", "🖼️ fotos → visor imagenes (un show vacío del visor es la búsqueda)",
                 text=_pic["query"][:80], role="system")
            return
    # V2-391 — VARIAS, no una: lo decide `data_ops` (ahí está el porqué y qué sigue bloqueado).
    if not _x._tx._data_ops.admite_data_op(args, c._data_ops_hechas, c._brief):
        return
    c._data_ops_hechas.append(args)     # y `_tool_fired` ya no lo lee nadie: la cuenta es esta
    c._handle_widget_data_tool(args)


def escalate_to_slowbrain(args: dict, c) -> None:
    _x = _calls()
    # V2-778 F1 — the body lives in `nucleo/flash/tool_executor_calls.py`; this branch passes what it reads.
    return _x._t_escalate_to_slowbrain(args=args, escalate_req=c.escalate_req, text=c.text)


def web_search(args: dict, c) -> None:
    _x = _calls()
    q = (args.get("query") or "").strip() or c.text
    # Demo pass 89, F2: beside the right documento:goto the model searched «proveedores de internet…» — not
    # one word of his turn. A search sharing NOTHING with his words, on a sure card order, is dropped.
    if not _x.a_search_is_his(q, c.operator_text or c.text, c._brief, c._word_overlap):
        c.emit("brain", "🔎 búsqueda descartada: no comparte ni una palabra con su frase (orden sobre una tarjeta)",
             text=q[:120], role="system", extra={"cat": "flash", "query": q[:200]})
        return
    # TURN-BLEED: the previous turn's search re-emitted; keep the query closest to THIS turn.
    if c.search_req["v"] is None or c._word_overlap(q, c.text) > c._word_overlap(c.search_req["v"], c.text):
        c.search_req["v"] = q


def search_listings(args: dict, c) -> None:
    _x = _calls()
    # V2-556 — UNA por turno; la forma de la petición es del módulo (`listing_turn.request_from`).
    c.listing_req["v"] = c.listing_req["v"] or _search.request_from(args, c.text)


def recall(args: dict, c) -> None:
    # V2-056: the MODEL decides to recall; resolved after the stream (needs_recall stays a prefetch).
    if c.recall_req["v"] is None:
        c.recall_req["v"] = (args.get("query") or "").strip() or c.text


def read_widget(args: dict, c) -> None:
    # V2-668: el MODELO decide LEER lo que guarda un widget; tras el stream, sin abrir nada — hermana de recall.
    if c.read_req["v"] is None:
        c.read_req["v"] = {"widget_id": (args.get("widget_id") or "").strip(),
                         "question": (args.get("question") or "").strip()}


def resume_task(args: dict, c) -> None:
    _x = _calls()
    _x._resume_turn.from_tool(args, escalate_req=c.escalate_req, operator_text=c.operator_text,
                              apply_widget_data=c._apply_widget_data, emit=c.emit, acted=c.acted)


def reopen_task(args: dict, c) -> None:
    if c.reopen_req["v"] is None:
        c.reopen_req["v"] = (args.get("query") or "").strip() or c.text


def reveal_secret(args: dict, c) -> None:
    # V2-060: a stored SECRET; its value NEVER enters a prompt — delivered out-of-band after the stream.
    if c.reveal_req["v"] is None:
        c.reveal_req["v"] = (args.get("label") or "").strip() or c.text


def play_music(args: dict, c) -> None:
    _x = _calls()
    return _x._t_play_music(args=args, music_req=c.music_req, _brief=c._brief, _apply_widget_data=c._apply_widget_data, esc=c.escalate_req,
                         acted=c.acted, clarify=c.clarify, emit=c.emit, ask_phrase=c._say().ask_which_item, text=c.operator_text)


def play_video(args: dict, c) -> None:
    _x = _calls()
    # V2-045: VIDEO = youtube widget, one per turn; body + licence V2-635 in `video_turn.voice_execute`.
    if "play_video" not in c._tool_fired:
        c._tool_fired.add("play_video")
        _x._tx._video_turn.voice_execute(args, c.text, c.emit, c._apply_widget_data, c.deduped,
                                  last_reply=_x._prior_line.of(c.brain), brief=c._brief)


def show_images(args: dict, c) -> None:
    _x = _calls()
    # V2-457: PHOTOS = `imagenes` viewer, one per turn; run after the stream (search is network).
    if "show_images" not in c._tool_fired:
        c._tool_fired.add("show_images")
        c.images_req["v"] = _x._tx._image_turn.request_from([{"name": c.name, "args": args}])
        _x._tx._cvis.present("imagenes", reason="turn-order", src="flash", emit=c.emit)
        c.emit("brain", "🖼️ fotos → visor imagenes", text=c.images_req["v"]["query"][:80], role="system")


def show_widget(args: dict, c) -> None:
    _x = _calls()
    # V2-778 F1 — the body lives in `nucleo/flash/tool_executor_calls.py`; this branch passes what it reads.
    return _x._t_show_widget(
        args=args, _brief=c._brief, _router=c._router, _say=c._say, _show_guard_target=c._show_guard_target,
        _show_target_instance=c._show_target_instance, _tag_emit=c._tag_emit, _tool_fired=c._tool_fired, acted=c.acted,
        brain=c.brain, clarify=c.clarify, deduped=c.deduped, emit=c.emit, escalate_req=c.escalate_req, text=c.text)


def show_panel(args: dict, c) -> None:
    _x = _calls()
    # V2-778 F1 — the body lives in `nucleo/flash/tool_executor_calls.py`; this branch passes what it reads.
    return _x._t_show_panel(
        args=args, _router=c._router, _tool_fired=c._tool_fired, acted=c.acted, emit=c.emit, operator_text=c.operator_text,
        text=c.text)


def manage_widget_alias(args: dict, c) -> None:
    _x = _calls()
    # V2-778 F1 — the body lives in `nucleo/flash/tool_executor_calls.py`; this branch passes what it reads.
    return _x._t_manage_widget_alias(
        args=args, _say=c._say, _tool_fired=c._tool_fired, acted=c.acted, clarify=c.clarify, emit=c.emit, text=c.text)


def close_widget(args: dict, c) -> None:
    _x = _calls()
    # Each CARD once, not the tool once: «close the calendar and the messages» may be two calls.
    if _x._tx._show_target.close_dispatch(args, c._tag_emit, c.emit, text=_x._tx._bnotes.operator_half(c.text),
                                   done=c._closed_by_tool, clarify=c.clarify):
        c._tool_fired.add("close_widget")
        c.acted["widget"] = True


def fullscreen_widget(args: dict, c) -> None:
    _x = _calls()
    # BUG 2026-07-23: without a tool the model claimed success. Body (V2-609 + V2-635 licence and
    # direction) in `show_target.fullscreen_dispatch` — one decision, both channels.
    if "fullscreen_widget" not in c._tool_fired:
        c._tool_fired.add("fullscreen_widget")
        _x._tx._show_target.fullscreen_dispatch(args, c.text, c._tag_emit, c.emit, c.deduped)


def arrange_canvas(args: dict, c) -> None:
    _x = _calls()
    # V2-778 F1 — the body lives in `nucleo/flash/tool_executor_calls.py`; this branch passes what it reads.
    return _x._t_arrange_canvas(_tool_fired=c._tool_fired, acted=c.acted, emit=c.emit)


def reply_message(args: dict, c) -> None:
    _x = _calls()
    # V2-778 F1 — the body lives in `nucleo/flash/tool_executor_calls.py`; this branch passes what it reads.
    return _x._t_reply_message(
        args=args, _apply_widget_data=c._apply_widget_data, _say=c._say, _tool_fired=c._tool_fired, clarify=c.clarify)


def delete_widget(args: dict, c) -> None:
    c._request_delete_confirm((args.get("widget_id") or "").strip(), c.text)


def restore_widget(args: dict, c) -> None:
    c._request_restore_confirm((args.get("widget_id") or "").strip(), c.text)


def confirm_widget_delete(args: dict, c) -> None:
    _x = _calls()
    c.confirm_state["handled"] = _x._t_confirm(args, c.operator_text or c.text, c._resolve_confirm, c.clarify, c.emit)


def set_style_directive(args: dict, c) -> None:
    _x = _calls()
    # V2-778 F1 — the body lives in `nucleo/flash/tool_executor_calls.py`; this branch passes what it reads.
    return _x._t_set_style_directive(
        args=args, _spawn=c._spawn, brain=c.brain, emit=c.emit, style_fired=c.style_fired, text=c.text)


def authenticate_web(args: dict, c) -> None:
    _x = _calls()
    # V2-778 F1 — the body lives in `nucleo/flash/tool_executor_calls.py`; this branch passes what it reads.
    return _x._t_authenticate_web(
        args=args, _start_web_auth=c._start_web_auth, emit=c.emit, escalate_req=c.escalate_req, text=c.text)


def login_done(args: dict, c) -> None:
    c._finish_web_auth()


def connect_cluster(args: dict, c) -> None:
    _x = _calls()
    # V2-778 F1 — the body lives in `nucleo/flash/tool_executor_calls.py`; this branch passes what it reads.
    return _x._t_connect_cluster(args=args, _request_cluster_confirm=c._request_cluster_confirm)


def cluster_send(args: dict, c) -> None:
    _x = _calls()
    # V2-778 F1 — the body lives in `nucleo/flash/tool_executor_calls.py`; this branch passes what it reads.
    return _x._t_cluster_send(args=args, _spawn=c._spawn, emit=c.emit)


def set_cluster_objective(args: dict, c) -> None:
    _x = _calls()
    # V2-778 F1 — the body lives in `nucleo/flash/tool_executor_calls.py`; this branch passes what it reads.
    return _x._t_set_cluster_objective(args=args, _say=c._say, _spawn=c._spawn, clarify=c.clarify, emit=c.emit)


def send_to_worker(args: dict, c) -> None:
    _x = _calls()
    # V2-778 F1 — the body lives in `nucleo/flash/tool_executor_calls.py`; this branch passes what it reads.
    return _x._t_send_to_worker(args=args, emit=c.emit, worker_acted=c.worker_acted, fired=c._tool_fired)


def stop_worker(args: dict, c) -> None:
    _x = _calls()
    _prior = _x._prior_line.of(c.brain)      # outside the call: a source guard unlifts a call with no nested parens
    # V2-778 F1 — the body lives in `nucleo/flash/tool_executor_calls.py`; this branch passes what it reads.
    return _x._t_stop_worker(args=args, _norm_nfkd=c._norm_nfkd, _say=c._say, _says_stop=c._says_stop, clarify=c.clarify,
                          emit=c.emit, text=c.text, worker_acted=c.worker_acted, brief=c._brief, prior=_prior)


def answer_worker(args: dict, c) -> None:
    _x = _calls()
    # V2-778 F1 — the body lives in `nucleo/flash/tool_executor_calls.py`; this branch passes what it reads.
    return _x._t_answer_worker(args=args, emit=c.emit, worker_acted=c.worker_acted, fired=c._tool_fired)


#: tool name → its door. Built from the functions above: one name per arm, written once.
CATALOG = {f.__name__: f for f in (
    need_capability, widget_data, escalate_to_slowbrain, web_search, search_listings, recall, read_widget,
    resume_task, reopen_task, reveal_secret, play_music, play_video, show_images, show_widget, show_panel,
    manage_widget_alias, close_widget, fullscreen_widget, arrange_canvas, reply_message, delete_widget,
    restore_widget, confirm_widget_delete, set_style_directive, authenticate_web, login_done, connect_cluster,
    cluster_send, set_cluster_objective, send_to_worker, stop_worker, answer_worker,
)}
