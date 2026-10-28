"""flash/show_target.py — resolving WHICH widget a "show me" turn means.

Extracted from `probe.py` (architecture ratchet, 2026-08-29): the three functions are one concern —
mirroring `providers/nucleo.py`'s show-guard/identify with the open>recent>catalogue precedence — and
they never touch the probe session state. Kept as a parallel impl of the voice path ON PURPOSE (see
each docstring); keep in sync with `providers/nucleo.py`.
"""
from __future__ import annotations

def _ctx_ids() -> tuple[list, list]:
    """(open_ids, recent_ids) from STATE to narrow `runtime.identify` (V2-078) — MIRROR of
    `providers/nucleo.py::_identify`. On a tie, the item on screen / used recently wins. Best-effort (missing state → ([], []))."""
    try:
        from memory import api as _memapi
        _st = _memapi.state() or {}
        return (_st.get("open_widgets") or []), (_st.get("recent_widgets") or [])
    except Exception:
        return [], []


def _identify_ctx(rt, query: str) -> str | None:
    """`rt.identify(query, open_ids, recent_ids)['match']` with state context — the resolver with the same
    open>recent>catalogue narrowing used by voice. `rt` is the `widgets.runtime` module already imported by the caller."""
    _o, _r = _ctx_ids()
    return (rt.identify(query, open_ids=_o, recent_ids=_r) or {}).get("match")


# The three verb shapes `_show_target` reads, as constants so the Jev show-license below vetoes
# on the SAME shapes instead of a second copy that drifts (a "créame" Jev false-positive must die
# on the same pattern the grammar dies on).
_NEGATED_SHOW_RE = r"\b(no|sin|tampoco|nunca|ni)\b[^.?!]{0,18}\b(abr|muestr|ensen|pon|saca|sube|ver)"
_CREATE_RE = r"\b(crea|crear|cree|haz|hacer|genera|generar|nuev|construy|dise|monta|make|create|build|new)"
_SHOW_VERB_RE = r"\b(abr|muestr|ensen|pon|saca|sube)|quiero ver|ver mi|ense"


def _norm_ascii(text: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFKD", text or "") if not unicodedata.combining(c)).lower()


def _vetoed_show(text: str) -> bool:
    """True when the turn can never license a show: creating is not showing, and a negated show
    ("no me abras") is not an order — a cheap model's opinion never beats either. Same two shapes
    `_show_target` returns None on, so the license and the grammar agree on what is not a show."""
    import re
    n = _norm_ascii(text)
    if re.search(_NEGATED_SHOW_RE, n):
        return True
    if re.search(_CREATE_RE, n):
        return True
    try:
        from . import router as _router
        if _router.looks_like_create_widget(text):
            return True
    except Exception:
        pass
    return False


# Extraído de `probe.py` en la pasada del trinquete (2026-09-02). Vive aquí porque es donde un lector ya lo
# buscaba: `delivery.py` lo nombra «show_target._running_goals» desde antes de que estuviera aquí.
def _running_goals() -> list[str]:
    """The goals of the errands actually IN FLIGHT right now — what a new request has to be compared against.

    `has_active()` answers whether anything is running; this answers WHAT. Best-effort: an unreadable registry
    returns [], and `nothing_running_for` treats «cannot tell» as «assume it is this one», so a failure here
    keeps the old conduct rather than escalating twice.
    """
    try:
        from nucleo import dispatch as _disp_g
        return [str(r.get("request") or "") for r in _disp_g.pending_summaries()]
    except Exception:
        return []


def model_named(wid_arg: str) -> str:
    """The card the model NAMED, when it is one we have: an exact catalog id, or an INSTANCE id verbatim (V2-773 —
    the model can only name one it was told about, and the alias resolver would read it as noise). "" otherwise —
    an alias or a garbled id leaves the target missing, and only then may a guard fill it in (V2-807 T-06)."""
    w = str(wid_arg or "").strip()
    if not w:
        return ""
    try:
        from widgets import runtime
        if runtime.get(w) is not None:
            return w
        if "::" in w and runtime.get(w.split("::", 1)[0]) is not None:
            return w
    except Exception as e:  # noqa: BLE001
        from loguru import logger
        logger.debug(f"show_target: catalog unreadable — {e}")
    return ""


def named_or_guess(model_id, guess, *, bases_only: bool = False) -> str:
    """The card the model NAMED, else the guard's guess (`guess()`) — a guess FILLS a missing target, it never
    replaces a present one (V2-807 T-06). `model_id` is the id, or the tag's `extra` dict carrying it. `bases_only`
    for a channel that resolves catalog ids only."""
    if isinstance(model_id, dict):
        model_id = model_id.get("id")
    named = model_named(str(model_id or ""))
    if named and not (bases_only and "::" in named):
        return named
    return str(guess() or "")


def verdict_denies_show(brief) -> bool:
    """Did the brief SURELY read the canvas as anything but a show (neither, close…)? Then a show grammar's guess
    over the same words is overruled (V2-807 T-06; CRIT-K1). Absent or unsure verdict → False, today's path."""
    try:
        from nucleo.flash import turn_brief as _tb
        verb, info = _tb.read(brief, _tb.CANVAS_KEY, "")
        return bool(isinstance(info, dict) and info.get("used")) and str(verb or "") not in ("", "show")
    except Exception as e:  # noqa: BLE001
        from loguru import logger
        logger.debug(f"show_target: canvas verdict unreadable — {e}")
        return False


def show_proposed(brief, router, text: str) -> bool:
    """May a promise backstop SHOW a card on this turn? A sure `canvas=show` verdict, or the show grammar when no
    sure verdict says otherwise (V2-807 T-06: «Why are you opening a browser? I asked for the draft» re-opened the
    browser from its own noun in his complaint)."""
    try:
        from nucleo.flash import direct_action as _da
        if _da.verdict_shows(brief):
            return True
    except Exception as e:  # noqa: BLE001
        from loguru import logger
        logger.debug(f"show_target: show verdict unreadable — {e}")
    return bool(router.looks_like_show_strict(text)) and not verdict_denies_show(brief)


def resolve_show(wid_arg: str, text: str, window, last_action, guard_target) -> tuple:
    """The voice provider's show_widget RESOLUTION, moved here whole (V2-650b, paid to the provider's
    size ratchet): open/recent context from memory state, then contextual target → exact catalog id →
    the certainty resolver (V2-082). `guard_target` is passed IN by the caller (it lives in the
    provider's widget_intent module — importing it here would add a new upward dependency the V2-569
    direction ratchet freezes). Returns `(res, open_ids, recent_ids)`; `res` carries `match` and
    `system`, exactly the shape the caller branched on before the move."""
    from widgets import runtime
    try:
        from memory import api as _memapi
        _st = _memapi.state() or {}
        open_ids, recent_ids = _st.get("open_widgets") or [], _st.get("recent_widgets") or []
    except Exception:
        open_ids, recent_ids = [], []
    res = {}
    try:
        # V2-807 T-06 — THE CARD THE MODEL NAMED WINS. The guard used to run first and REPLACE it: «Where is it?
        # Open it» with `show_widget(documento)` was rewritten to the browser, because the deictic «it» walked back
        # to his previous line — a complaint that NAMED the browser. A word-level guess may fill in a missing
        # target; it never replaces a present one (a text guard never contradicts the verdict, CRIT-K2).
        named = model_named(wid_arg)
        if named:
            res = {"match": named, "system": None}
        elif (contextual := guard_target(text, window, last_action)):
            res = {"match": contextual, "system": None}
        else:                                                    # name/alias → real id or system surface
            res = runtime.identify(wid_arg or text, open_ids=open_ids, recent_ids=recent_ids) or {}
    except Exception:
        res = {"match": wid_arg if runtime.get(wid_arg) is not None else None, "system": None}
    return res, open_ids, recent_ids


def show_card(rid: str, text: str = "") -> str:
    """The CARD id a backstop should show — narrows a base to its live instance, never asks (V2-605 F2).

    The asking door is `show_instance`; this is for the deterministic backstops, which have no conversation to
    hold. Fail-soft to the base: an unreadable canvas must not change what a backstop shows.
    """
    try:
        from server.voice_api import open_instances
        from widgets import instances as _inst
        return _inst.show_id(rid, open_instances(), text)
    except Exception:  # noqa: BLE001
        return rid


def fullscreen_target(widget_id: str, text: str = "") -> str:
    """WHICH card a `fullscreen_widget` call means — ONE decision, read by both channels (V2-252).

    Order of resolution: the id the model gave (exact, then `identify` over it or the turn text), and finally
    **the card that IS at full screen right now**, reported by the canvas in `state.maximized_widget`.

    That last step is the whole point (V2-609). `widget_id` used to be REQUIRED and «sal de pantalla
    completa» names no widget, so the model had nothing legal to pass — and instead of asking, it answered
    «Hecho.» having emitted no tool at all (measured live 2026-09-07 18:54:27; the engine's own friction
    detector logged «data-op fantasma» and was in cooldown). The operator's point is exactly right: with one
    card at full screen, the target is not ambiguous, it is *obvious* — and the canvas already knew it. A
    verb whose object the system can see and the model cannot is a verb the model will decline to use.

    Returns "" when nothing resolves. Deliberately never falls back to "the only open widget": leaving full
    screen when nothing is at full screen would TOGGLE a card INTO it — the exact opposite of the order.
    """
    rid = (widget_id or "").strip()
    try:
        from widgets import runtime as rt
    except Exception:
        return rid
    if rid:
        # He named something: exact id, else resolve THAT name. Never the turn text — see below.
        try:
            if rt.get(rid) is not None:
                return rid
            m = _identify_ctx(rt, rid) or ""
            if m and rt.get(m) is not None:
                return m
        except Exception:
            pass
        return ""
    # No name given. `identify` over the TURN TEXT would answer here — with one card open it narrows to
    # that card and «sal de pantalla completa» resolves to it happily (verified: it does). That is the one
    # answer this function must never give: nothing is at full screen, so toggling that card would put it
    # INTO full screen — the exact opposite of the order, on the operator's own most common canvas. An
    # empty argument means «the one that is at full screen» and nothing else; when there is none, the
    # honest result is nothing, and the caller asks.
    try:
        from memory import api as _memapi
        maxw = str(((_memapi.state() or {}).get("maximized_widget") or "")).strip()
        if maxw and rt.get(maxw) is not None:
            return maxw
    except Exception:
        pass
    return ""


def close_target(widget_id: str) -> str:
    """The card `close_widget` means: the one it names, or — empty — the card his last turn acted on, else the
    only one open. "" when that cannot be said (the tag's own resolution then asks)."""
    wid = (widget_id or "").strip()
    try:
        from nucleo import canvas_focus
        from server.voice_api import open_instances
        ids = [str(i) for i in open_instances() if str(i)]
    except Exception:  # noqa: BLE001
        return wid
    if wid:
        # the PIECE named, the CARD closed: «results» with its one sheet `results::c79ebf-1` open is that sheet
        # (demo pass 2026-09-28, S4: the close went to the bare id and the sheet stayed on screen)
        same = [i for i in ids if i.split("::", 1)[0] == wid.split("::", 1)[0]]
        if wid not in ids and len(same) == 1:
            return same[0]
        if "::" not in wid and len(same) > 1:
            # Several of the piece open (demo passes 38/45/47, 2026-09-29, S4: the base shell beside the sheet, or
            # a phantom base card): the one his last turn acted on, else the ONE instance beside a bare shell.
            # Two real sheets and no focus keep the bare id — the tag's own resolution asks.
            inst = [i for i in same if "::" in i]
            if len(inst) == 1:          # pass 119 S4: a focused bare shell took the close and the sheet stayed
                return inst[0]
            focus = canvas_focus.last_turn_card(same)
            if focus:
                return focus
        return wid
    from nucleo.turn import brief as _brief
    if _brief.names_elsewhere(_brief.of_this_turn()):   # refactor2710-07: he named something that is not a card here
        return ""
    return canvas_focus.last_turn_card(ids) or (ids[0] if len(ids) == 1 else "")


def close_dispatch(args: dict, tag_emit, emit, text: str = "", done=None, clarify=None) -> str:
    """The provider's `close_widget` branch body, shared with the probe: close or put away a card through the
    SAME canvas route the [[close]] tag and the canvas minimize already take. Returns the card, or "".

    A close also takes the OTHER open cards his sentence names (`widgets.instances.also_named`), as the [[close]]
    tag path already did: «close the calendar and the messages» closed the calendar only (demo pass 2026-09-28,
    C6). `done` is the turn's set of cards already closed — each card once, never a second close of the same."""
    rid = close_target(str(args.get("widget_id") or ""))
    if not rid:
        return ""
    if (_b := __import__("nucleo.turn.brief", fromlist=["x"])).names_elsewhere(_b.of_this_turn(), against_a_call=True):
        emit("brain", "🚫 close vetoed: he named no card on screen", text=rid, role="system")
        return ""
    # Several cards of the piece open and no word to tell them apart: the close ASKS which (node 2.645). `rid` is
    # returned so the turn counts the call as handled — its answer is the question in `clarify`, never a close.
    from nucleo.acts import close_target as _close_which
    _act, _q = _close_which.probe_action(args, rid, text) if clarify is not None else ("", "")
    if _q:
        clarify["msg"] = _q
        return rid
    rid = _act.split(":", 2)[2] if _act.startswith("canvas:close:") else rid   # a title word named one sheet
    done = done if done is not None else set()
    mode = str(args.get("mode") or "close").strip().lower()
    targets = [rid]
    if mode != "minimize" and text:
        try:
            from server.voice_api import open_instances
            from widgets import instances as _inst
            targets += [x for x in _inst.also_named(text, open_instances(), exclude=[rid]) if x not in targets]
            stay = {_inst.base_of(k) for k in _inst.kept_named(text, open_instances())}   # «…keep the calendar up»
            targets = [t for t in targets if _inst.base_of(t) not in stay]
        except Exception:  # noqa: BLE001
            pass
    # V2-787 — ONE door decides a close: the canvas route this call goes through. When that route REFUSES
    # (`False`: no close order in his words, or the order is an action inside the card) the close did not
    # happen, so this branch neither claims it on the timeline nor counts the call as an act. Before, the
    # refusal and «🪟 close_widget(close) → canvas» were logged in the same turn and the card stayed open:
    # the trace contradicted itself and the turn was counted as having closed something.
    refused = attempted = 0
    for t in targets:
        if t in done:
            continue
        done.add(t)
        attempted += 1
        if tag_emit("minimize" if mode == "minimize" else "close", {"id": t}) is False:
            refused += 1
            continue
        emit("brain", f"🪟 close_widget({mode}) → canvas", text=t, role="system")
    return "" if attempted and refused == attempted else rid


def fullscreen_dispatch(args: dict, text: str, tag_emit, emit, deduped: dict, brief=None) -> None:
    """The provider's whole `fullscreen_widget` branch body (extracted paying the architecture ratchet,
    V2-635): resolve the card (V2-609, above) and route by what the turn actually SAYS. Measured 2026-09-09
    (session 34386d8f): «Johnny pausa el vídeo» became fullscreen (pure drag — no screen-size words at all),
    and «minimiza el vídeo» became fullscreen TWICE, because the toggle was the only route and on a
    non-maximized card the toggle does the exact opposite. Shrink orders now ride the canvas `minimize`
    event (desktop.shrink: exit fullscreen → restore maximize → rail chip); a call licensed by nothing is
    discarded and counts as handled (`deduped`) — same posture as stop_worker's GUARD 2."""
    from nucleo.acts import canvas as _door
    verdict = _door.size_ordered(text, brief=brief)
    if not verdict:
        emit("brain", "🛡️ fullscreen_widget ignorado — el turno no habla de tamaño de pantalla (context-bleed)",
             text=(text or "")[:120], role="system",
             extra={"cat": "flash", "kind_diag": "fullscreen_without_order"})
        deduped["v"] = True
        return
    # V2-759 — THE DIRECTION IS AN ARGUMENT NOW. `mode` says which way; the licence above still decides
    # whether the turn talks about screen size at all (a bleed stays discarded in either direction).
    mode = str(args.get("mode") or "").strip().lower()
    rid = fullscreen_target((args.get("widget_id") or "").strip(), text)
    if mode == "off":
        # Leaving never needs a name: an empty id means «whichever card covers the screen», and the desktop's
        # exit is idempotent — a card that is not full screen is left exactly as it is, never shrunk to the rail
        # and never blown up (the two things the old toggle and `minimize` could do to a normal card).
        tag_emit("fullscreen", {"id": rid, "on": False})
        if not rid and not _anything_at_full_screen():   # refactor2710-03: the exit had nothing to act on
            from i18n import langs as _langs
            from nucleo.turn import reply as _reply
            _reply.note(_reply.Outcome("cannot", "canvas", "unfullscreen",
                                       reason=str(_langs.current_language().fullscreen_nothing)))
        emit("brain", "⤡ fullscreen_widget(off) → salir de pantalla completa", text=rid or "(la que esté)",
             role="system")
        return
    if not rid:
        return
    if verdict == "minimize":
        tag_emit("minimize", {"id": rid})
        emit("brain", "⤵️ fullscreen_widget con orden de ENCOGER → canvas minimize", text=rid, role="system")
        return
    tag_emit("show", {"id": rid})     # por si no estaba abierto todavía
    # `on: True` only when the model SAID so: then entering twice is a no-op instead of the toggle taking it
    # back out. With no `mode` (an older call shape) the event keeps its old meaning, toggle included.
    tag_emit("fullscreen", {"id": rid, **({"on": True} if mode == "on" else {})})
    emit("brain", "⛶ fullscreen_widget → canvas", text=rid, role="system")


def _anything_at_full_screen() -> bool:
    """A card the canvas reports maximized, or one his own order put at full screen. Unreadable → True (an unread
    canvas proves nothing, so nothing is claimed)."""
    try:
        from memory import api as _memapi
        from nucleo import canvas_focus as _cf
        return bool(str((_memapi.state() or {}).get("maximized_widget") or "").strip() or _cf.ordered_fullscreen())
    except Exception:  # noqa: BLE001
        return True


def fullscreen_exit_due(text: str, *, fired: bool) -> str:
    """The DECISION behind `fullscreen_exit_backstop`, with no side effect: the card to bring back, or "".
    Separate so the text channel reads the same answer the voice acts on (V2-252 — one decision, both
    channels); the conditions are documented on the function below."""
    if fired:
        return ""
    try:
        from nucleo.acts import canvas as _door
        if _door.size_ordered(text) != "minimize":
            return ""
        from memory import api as _memapi
        return str(((_memapi.state() or {}).get("maximized_widget") or "")).strip()
    except Exception:  # noqa: BLE001 — a backstop never adds an exception to a turn
        return ""


def fullscreen_exit_backstop(text: str, *, fired: bool, tag_emit, emit) -> bool:
    """V2-759 — «Y sal de pantalla completa.» answered «Ya está, fuera de pantalla completa.» with NOTHING
    called. Twice now: V2-609 (2026-09-07) and again 2026-09-24, and in both the engine's own friction
    detector logged «data-op fantasma» in the same second while nobody repaired it. Making the argument
    optional (V2-609) and the direction explicit (above) both improve the odds; neither makes the claim true.

    So when the model called nothing, the exit is completed here — and it is safe to complete, which is what
    makes it a mechanism and not a verb table deciding intent. Three conditions, all required:
      · the turn is one the EXISTING licence already reads as leaving or shrinking (`minimize`) — no new words;
      · a card IS covering the screen, according to the canvas itself (`state.maximized_widget`), a fact and
        not a reading;
      · the consequence is the one idempotent exit: that card goes back to where it was, and nothing else
        on the screen moves.
    Returns whether it acted."""
    maxw = fullscreen_exit_due(text, fired=fired)
    if not maxw:
        return False
    tag_emit("fullscreen", {"id": maxw, "on": False})
    emit("brain", "⤡ salida de pantalla completa COMPLETADA — el modelo lo dijo y no llamó a nada",
         text=maxw, role="system", extra={"cat": "flash", "kind_diag": "fullscreen_exit_backstop"})
    return True


# ── Jev canvas verdict (T-jev-show-close): the VERB before the model writes text ──
#
# Division of labor, read before wiring a second caller: Jev names ONLY the verb
# (show / close / neither) — one cheap Choice call, fired early, resolved at the backstop.
# The TARGET stays where it already lives: `resolve_show` above (+ `_identify_ctx`) for opens,
# `close_guards` + `canvas_license` for closes. No new judgement rails: a confident "neither"
# never vetoes the deterministic grammar (a close verb on the turn beats a cheap model's shrug),
# and a confident verb never opens/closes anything by itself — the existing executor does that,
# through the same tags, license and guards as today's path.
CANVAS_INSTRUCTIONS = ("Does the user's turn ask to change what is visible on the widget canvas? "
                        "SHOW means putting a widget or card on screen; CLOSE means taking one off; the other "
                        "gestures change how big a card is, or lay all the cards out. Anything else — questions, chatter, orders that act "
                        "inside a card — is neither.")
CANVAS_VERBS = {
    "show": "the turn asks to show, open, display or bring up a widget or card",
    # V2-781: «remove the third one in the list» read `close` at 0.98 and shut the video card — removing a ROW
    # of a card is an order inside it. Measured with the real verdict before and after this wording.
    "close": "the turn asks to close, hide or take a whole widget or card off the screen",
    # demo pass 2026-09-28 (human script): «can you make it bigger, like full screen» → «There you go — it's full
    # screen now» with no call, and the verdict could only say `neither`. The gestures that change a card's size
    # are canvas gestures too.
    "fullscreen": "the turn asks to make a card full screen or bigger",
    "exit_fullscreen": "the turn asks to leave full screen / go back to the normal size",
    "minimize": "the turn asks to put a card away, minimise it or tuck it aside without closing it",
    # demo pass 2026-09-28 (full21 C5b): «tidy up the screen a bit» → «screen's sorted» with no call, and the verdict
    # could only say `neither`. Laying out every card is a canvas gesture too.
    "arrange": "the turn asks to tidy, arrange, organise or lay out the cards on the screen (all of them)",
    "neither": "the turn asks for nothing about showing, closing, resizing or arranging widgets — removing, "
               "skipping or moving ONE ITEM of a card's list (the third video, the one by X, a row) is neither",
}


def resolve_canvas_verb(handle: dict | None, *, min_confidence: float | None = None):
    """(see below) — since V2-726 F1 the handle may be the TURN BRIEF, which carries this verdict
    under its own key alongside the turn's other questions instead of on a second round trip. A
    single-question handle still reads exactly as before, so both channels and every existing test
    keep working; the brief is simply the shape the voice path now passes in."""
    from nucleo import jev as _jev
    mc = _jev.MIN_CONFIDENCE if min_confidence is None else min_confidence
    verdict = _jev.peek(handle)
    if isinstance(verdict, dict) and "_latency_ms" in verdict:      # a brief, not a lone question
        from nucleo.flash import turn_brief as _tb
        return _jev.read(handle, _tb.CANVAS_KEY, "neither", min_confidence=mc)
    return _resolve_canvas_verb_single(handle, min_confidence=mc)


def _resolve_canvas_verb_single(handle: dict | None, *, min_confidence: float | None = None):
    """Fire-time canvas verb shared by BOTH channels (voice provider and probe read this, never
    a second implementation): Jev's verb when ready AND sure, else "neither" — i.e. today's path,
    bit-for-bit. Returns `(verb, verdict)`; verdict carries `used` for the observability trail."""
    from nucleo import jev as _jev
    mc = _jev.MIN_CONFIDENCE if min_confidence is None else min_confidence
    return _jev.resolve_choice(handle, "neither", min_confidence=mc)


def show_from_verb(text: str, canvas_handle: dict | None = None) -> tuple[str | None, str]:
    """The ONE Jev show-license reader for both channels' show backstops (voice provider guard +
    probe escalate/search backstop — never a second implementation).

    Grammar already missed (the caller read its own guard first and got nothing): a confident Jev
    "show" verdict LICENSES resolving the target through the existing `runtime.identify`
    (open > recent > catalogue, same narrowing as `_show_target`). A verb WITHOUT a resolvable
    target executes nothing — (None, "none") — and so do the vetoes (create / negated show),
    an unsure verdict, and a missing handle (Jev off/slow/failed, `ZAELAR_JEV=0` included):
    every one of those keeps today's path bit-for-bit. Returns `(widget_id_or_None, source)`
    with source "jev" | "none" — the emit trail says which reader moved, so a misfire is
    attributable. Grammar hits never reach this function (the caller returns those as "grammar").
    """
    verb, info = resolve_canvas_verb(canvas_handle)
    if verb != "show" or not (info or {}).get("used"):
        return None, "none"
    if _vetoed_show(text):
        return None, "none"
    try:
        from widgets import runtime as _rt
        wid = _identify_ctx(_rt, text)
        if wid and _rt.get(wid) is not None:
            return wid, "jev"
    except Exception:
        pass
    return None, "none"
