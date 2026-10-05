"""card_commission.py — a commission that names one of OUR cards is a read or a declared call before it is a
worker; and a read the verdict says to SHOW brings its card (V2-773, the demo's final pass).

Two measured turns on the operator's live engine, 2026-09-26, both on the calendar with the agenda CLOSED:

  · «Find me a free 45-minute slot tomorrow afternoon to talk with Rowan» — the catalogue verdict named the
    agenda (0.79 after its description learnt to say «huecos libres»), the model called `escalate`, and a
    Brain Worker spent three minutes on a question the card answers in one read. The two rungs before it
    (`direct_action.take_rung`, the act-repair pass) only see a card named through `screen_action`, which
    exists only while the card is OPEN.
  · «Show me that time in my calendar» — the model READ the agenda and answered in words; the canvas verdict
    had said `show` (0.74) and the card he asked to see stayed closed.

Both are the same shape as V2-741: the engine had paid for a verdict and then let the expensive path run. The
decision here is the model's, with the card in front (`act_repair.call_or_read_for_commission`): it may call a
declared action, read the card, or call nothing — and nothing keeps today's path, the worker. Extracted from
the voice provider for the reason the architecture ratchet keeps giving: that file grows only by extraction.
"""
from __future__ import annotations

import re

from typing import Callable


#: The late catalogue question names a card for a repair that acts IN THE MODEL'S PLACE, on a card nobody sees
#: yet — so it needs more than the classifier's «not a shrug». Demo pass 35 (2026-09-29, B1): «find me the
#: wallpaper cosmic eye in the sky» read `navegador` at 0.63; the repair ran a browser search, and that card sat
#: on the canvas until the end of the demo. Every late read that named the right card across passes 20-35 was
#: at 0.74 or more.
LATE_CATALOGUE_MIN = 0.7


def named_or_catalogue(brief, operator_text: str, *, wait_s: float = 3.5) -> str:
    """The card an order names — by the brief, or by ONE late catalogue question when the brief could not know.

    The brief asks `screen_action` while cards are open and `catalog_widget` only when nothing is, on purpose
    (V2-726). So an order for a CLOSED card while other cards are open reads as a confident «none» and names
    nobody: demo v3, C5 — «Message Rowan on Telegram» with the agenda open — read `none` 0.91, the model
    answered from the agenda and nothing was sent. When the screen verdict is a sure «none» and nothing was
    called, one bounded catalogue question (the same criteria, the same reader) says which closed card it is.
    Returns "" when unsure or when nothing can be asked; never waits past `wait_s`; never raises."""
    try:
        from nucleo import jev as _jev
        from nucleo.flash import build_decision as _bd, turn_brief as _tb
        card = _bd.named_card(brief)
        if card:
            return card
        choice, info = _tb.read(brief, _tb.TARGET_KEY, "")
        # …or when the screen verdict is UNSURE (demo pass 2026-09-28, R3: «find me five days in her vacation where
        # i'm free» read `agenda:show_day` at 0.40 — unsure, so no card, and the commission went to a five-minute
        # worker for what the agenda answers). A sure answer naming an action was handled above; only a sure
        # «none» and an unsure anything are left, and both mean «the screen question could not say».
        if not isinstance(info, dict) or (info.get("used") and str(choice or "") != "none"):
            return ""
        q = _tb.catalog_question()
        if not q or not (operator_text or "").strip():
            return ""
        import concurrent.futures as _cf
        with _cf.ThreadPoolExecutor(max_workers=1) as ex:
            fut = ex.submit(_jev.choose_sync, "catalog_widget", operator_text, instructions=q["instructions"],
                            criteria=q["criteria"], question_id="catalog_widget")
            v = fut.result(timeout=wait_s)
        cat = str((v or {}).get("choice") or "").strip()
        conf = float((v or {}).get("confidence") or 0.0)
        named = cat if cat and cat != "none" and conf >= LATE_CATALOGUE_MIN else ""
        try:
            from voice.observer import emit as _emit
            _emit("brain", "🧭 catálogo tardío (la pantalla dijo «none»)", role="system",
                  text=f"{cat or '?'} ({conf:.2f}) → {named or 'nadie'}", extra={"cat": "flash", "card": named, "choice": cat, "confidence": conf})
        except Exception:  # noqa: BLE001
            pass
        return named
    except Exception:  # noqa: BLE001
        return ""


#: A card whose rows only a TURN TOOL can fill: its declared `show` carries no search of its own, so a commission
#: pass that asks it to show «a query» is the tool's request, not a data-op (demo pass 62, B1: «find me the wallpaper
#: cosmic eye in the sky by tyler young» became a Brain Worker; passes 56-59 ran it as `show_images` in 3 s).
TOOL_FILLED = {"imagenes": "show_images"}


#: A card whose catalogue only a SEARCH fills, and the declared action+key that runs it (demo pass 93, V1).
SEARCH_FILLED = {"youtube": ("search", "query")}


def search_to_fill(card: str, operator_text: str) -> dict | None:
    """The search a card that has never been filled stands for, when a promise put it on screen empty.

    Demo pass 93 (2026-10-03), V1 «Show me a catalog of SpaceX Starship test videos.»: the model called nothing and
    promised; the promise backstop showed the YouTube card — EMPTY — and «Play video number 2» then had nothing to
    play («no search results available»), and the whole V block failed behind it. The picture viewer already has this
    rule (`picture_search_for`); the video catalogue is the same shape: the card's only way to hold anything is its
    search, and his sentence is what to search for."""
    base = _base_card(card)
    if base not in SEARCH_FILLED or not (operator_text or "").strip():
        return None
    try:
        from nucleo import truth as _truth
        view = _truth.widget_view(base) or {}
    except Exception:  # noqa: BLE001
        return None
    if view.get("searched_at"):
        return None                      # it already holds a catalogue: showing it is the whole order
    action, key = SEARCH_FILLED[base]
    return {"widget_id": base, "action": action, "payload": {key: " ".join(operator_text.split())[:160]}}


def _base_card(card: str) -> str:
    return str(card or "").split("::", 1)[0].strip().lower()


def _viewer_empty() -> bool:
    try:
        from widgets import store as _st
        return not ((_st.load("imagenes") or {}).get("items") or [])
    except Exception:  # noqa: BLE001
        return False


def picture_search_for(card: str, operator_text: str, commission: str = "") -> dict | None:
    """The `show_images` request an order on the EMPTY picture viewer stands for — whichever path reached the card
    (a commission, a promise with no tool). None when the card is not the viewer or it already holds pictures.
    The query is the commission's first sentence, else his own sentence: measured on B1's (pass 67), the full
    sentence finds «Cosmic Eye in the Sky by Tyler Young», 3000×1694, first."""
    if TOOL_FILLED.get(str(card or "").split("::", 1)[0]) != "show_images" or not _viewer_empty():
        return None
    first = re.split(r"(?<=[.!?])\s", str(commission or "").strip(), maxsplit=1)[0][:160]
    q = " ".join((first or operator_text or "").split())[:200]
    if not q:
        return None
    from nucleo.flash import image_turn as _it
    if _it._WALLPAPER_INTENT_RE.search(operator_text or "") and not _it._WALLPAPER_INTENT_RE.search(q):
        q = f"{q} wallpaper"
    return {"query": q, "n": _it.DEFAULT_N, "more": False}


def picture_named_by(operator_text: str, brief=None) -> dict | None:
    """The picture search his words ask for when they NAME the picture viewer (its name or alias: «wallpaper»,
    «fondo de pantalla», «fotos») and it is empty — whatever tool the model reached for (demo passes 60-69, B1: a
    worker, a promise, a commission, a product-listing search, in turn) — or the one the verdict surely names
    (`picture_by_verdict`). None otherwise."""
    try:
        from widgets import runtime as _rt
        card = str(_rt.identify_named(operator_text or "") or "")
    except Exception:  # noqa: BLE001
        card = ""
    return (picture_search_for(card, operator_text) if card else None) or picture_by_verdict(brief, operator_text)


def picture_by_verdict(brief, operator_text: str) -> dict | None:
    """The picture search a SURE verdict on the viewer's `show`/`add` stands for, when the model reached elsewhere.

    Demo pass 110, I2: «cool, show me a few more of those» right after the F40 photos — the verdict read
    `imagenes:add` at 0.99, the model (whose window did not hold I1's photos yet: that search was still loading)
    said «let me pull a few more 27-inch 4K options» and a listing search opened a SECOND monitors sheet, which then
    broke I3, I4 and the whole S block. `add` is more of the search under way or last made; `show`, on an EMPTY
    viewer only, is his words."""
    if brief is None:
        return None
    try:
        from nucleo.flash import direct_action as _da, turn_brief as _tb
        _c, info = _tb.read(brief, _tb.TARGET_KEY, "", min_confidence=0.9)
        wid, action = _da.from_brief(brief)
        if info is None or not info.get("used") or TOOL_FILLED.get(_base_card(wid)) != "show_images":
            return None
        from nucleo.flash import image_turn as _it
        if action == "add":
            q = _it.LAST_QUERY.get("q") or ""
            if not q:
                from widgets import store as _st
                q = str((_st.load("imagenes") or {}).get("query") or "")
            return {"query": q[:160], "n": _it.DEFAULT_N, "more": True} if q.strip() else None
        if action == "show":                 # a viewer that holds pictures already shows them: only an empty one
            return picture_search_for("imagenes", operator_text)
    except Exception:  # noqa: BLE001
        return None
    return None


def picture_search_for_empty_show(widget_id: str, action: str, payload: dict | None, operator_text: str) -> dict | None:
    """The `show_images` request a model's own `show`/`add` on the viewer WITHOUT pictures stands for.

    Demo pass 82 (2026-10-03), I1 «show me a red ferari f40»: the model called `imagenes:show` with no items. The
    viewer still held B1's nebula photos, so neither the empty-viewer rule nor the commission pass caught it, the
    card answered «no llegó ninguna imagen», the in-turn correction repeated the same call, and the whole I block
    went wrong after it. A `show` with nothing to show is asking to FIND them — whatever the viewer holds now."""
    if TOOL_FILLED.get(str(widget_id or "").split("::", 1)[0].strip().lower()) != "show_images":
        return None
    if str(action or "") not in ("show", "add"):
        return None
    pl = payload if isinstance(payload, dict) else {}
    if pl.get("items"):
        return None
    q = " ".join(str(pl.get("query") or pl.get("title") or operator_text or "").split())[:160]
    if not q:
        return None
    from nucleo.flash import image_turn as _it
    if _it._WALLPAPER_INTENT_RE.search(operator_text or "") and not _it._WALLPAPER_INTENT_RE.search(q):
        q = f"{q} wallpaper"
    return {"query": q, "n": _it.DEFAULT_N, "more": str(action) == "add"}


def _as_tool_request(got: dict, operator_text: str) -> dict | None:
    """`{query, n, more}` for the turn tool that fills this card, or None when the call is an ordinary data-op."""
    if TOOL_FILLED.get(str(got.get("widget_id") or "")) != "show_images":
        return None
    action = str(got.get("action") or "")
    pl = got.get("payload") if isinstance(got.get("payload"), dict) else {}
    if pl.get("items"):
        return None
    if action not in ("show", "add"):
        # Demo pass 63, B1: the pass called `wallpaper` straight away, with the viewer EMPTY — nothing to set. Any
        # order on an empty viewer is first a search (the operator then picks: «set the first one»).
        if not _viewer_empty():
            return None
    q = " ".join(str(pl.get("query") or pl.get("title") or
                     (pl.get("item") if not str(pl.get("item") or "").strip().isdigit() else "") or "").split())[:160]
    if not q and action not in ("show", "add"):
        q = " ".join(str(operator_text or "").split())[:160]
    if not q:
        return None
    from nucleo.flash import image_turn as _it
    if _it._WALLPAPER_INTENT_RE.search(operator_text or "") and not _it._WALLPAPER_INTENT_RE.search(q):
        q = f"{q} wallpaper"          # the wallpaper intent picks big landscape files (`image_turn.execute`)
    return {"query": q, "n": _it.DEFAULT_N, "more": str(got.get("action")) == "add"}


async def before_worker(escalate_req: dict, read_req: dict, *, brief, operator_text: str, spec, emit,
                        present: Callable, apply_widget_data: Callable, window=None,
                        images_req: dict | None = None) -> str:
    """Try the card the catalogue verdict names. Returns "call", "read" or "" (the worker keeps the errand).

    The caller owns the precondition — a commission survived every guard and nothing in the turn acted — and
    the two rungs before this one found no OPEN card. Never raises: a second pass never breaks a turn."""
    try:
        from nucleo import danger as _danger
        from nucleo.flash import act_repair as _repair, build_decision as _bd
        card = named_or_catalogue(brief, operator_text)
        if not card or _danger.is_dangerous(operator_text):
            return ""
        # Any card the verdict names may take the CALL; the read half is offered only to one that can answer.
        # An order the verdict reads as owing NO words («send rowan a telegram with the new time», wants_words=act)
        # is not answered by a read: offering one made the pass check the directory instead of sending (C5, 2/4).
        from nucleo.flash import turn_brief as _tbw
        _w, _wi = _tbw.read(brief, _tbw.WORDS_KEY, "")
        may_read = not (_wi is not None and str(_w or "") == "act")
        from nucleo.flash import direct_action as _da_cc
        _v_card, _v_act = _da_cc.from_brief(brief)
        got = await _repair.call_or_read_for_commission(operator_text, str(escalate_req.get("v") or ""), card,
                                                        spec=spec, window=window, may_read=may_read,
                                                        verdict_action=_v_act if _base_card(_v_card) == _base_card(card)
                                                        else "")
        if (not got or got.get("kind") != "call") and images_req is not None:
            # Demo pass 66, B1: the catalogue named the viewer and the pass still sent «find me the wallpaper cosmic
            # eye…» to a worker. An empty viewer's only way to hold anything is the picture search.
            _pic = picture_search_for(card, operator_text, str(escalate_req.get("v") or ""))
            if _pic:
                got = {"kind": "call", "widget_id": card, "action": "show", "payload": {"query": _pic["query"]}}
        if not got:
            return ""
        _tool = _as_tool_request(got, operator_text) if got["kind"] == "call" and images_req is not None else None
        if _tool:
            images_req["v"] = _tool
            escalate_req["v"], escalate_req["more"] = None, []
            emit("brain", "🎯 la herramienta del turno en vez de un worker (la tarjeta del catálogo)",
                 text=f"{got['widget_id']} ← show_images «{_tool['query'][:100]}»", role="system",
                 extra={"cat": "flash", "widget": got["widget_id"], "tool": "show_images"})
            return "call"
        if got["kind"] == "call":
            present(got["widget_id"], reason="turn-order", src="flash", emit=emit)
            apply_widget_data(got["widget_id"], got["action"], got["payload"])
            escalate_req["v"], escalate_req["more"] = None, []
            emit("brain", "🎯 acción declarada en vez de un worker (la tarjeta del catálogo)",
                 text=f"{got['widget_id']}:{got['action']}", role="system",
                 extra={"cat": "flash", "widget": got["widget_id"], "action": got["action"]})
            return "call"
        if got["kind"] == "read":
            if read_req.get("v") is None:
                read_req["v"] = {"widget_id": got["widget_id"], "question": got["question"]}
            escalate_req["v"], escalate_req["more"] = None, []
            emit("brain", "🎯 lectura de la tarjeta en vez de un worker",
                 text=f"{got['widget_id']} ← {got['question'][:100]}", role="system",
                 extra={"cat": "flash", "widget": got["widget_id"], "question": got["question"][:200]})
            return "read"
    except Exception:  # noqa: BLE001
        pass
    return ""


async def instead_of_a_search(query: str, *, brief, operator_text: str, spec, window=None) -> dict | None:
    """The card that ANSWERS a search the model sent to the web — `{"kind": "call"|"read", …}`, or None (it searches).

    Demo pass 109, C2: «find me a free 45 minutes tomorrow afternoon… after my last meeting», the verdict at
    `agenda:find_free` 1.00, and the model called `web_search`: timer websites, «those results were just time and
    timer tools», and the find_free a repair ran afterwards was never heard. Only when the verdict SURELY names an
    action whose result IS the reply (`output.answer`); the card's own pass then fills the call. Never raises."""
    try:
        from nucleo.flash import act_repair as _repair, turn_brief as _tb
        from widgets import effects as _fx
        choice, info = _tb.read(brief, _tb.TARGET_KEY, "", min_confidence=0.9)
        owner, _, action = str(choice or "").rpartition(":")
        wid = _base_card(owner)
        if not (info and wid and action and _fx.carries(wid, action, _fx.OUTPUT_ANSWER)):
            return None
        return await _repair.call_or_read_for_commission(operator_text, query, wid, spec=spec, window=window,
                                                         verdict_action=action)
    except Exception:  # noqa: BLE001
        return None


async def voice_instead_of_a_search(search_req: dict, read_req: dict, *, brief, operator_text: str, spec, window,
                                    emit, present: Callable, apply_widget_data: Callable, acted: dict, done: dict) -> str:
    """The VOICE half of `instead_of_a_search`: the call runs (its answer is then composed from its data, like any
    `output.answer` op), or the read is queued — and the search is dropped. Returns "call", "read" or ""."""
    if search_req.get("v") is None:
        return ""
    got = await instead_of_a_search(search_req["v"], brief=brief, operator_text=operator_text, spec=spec, window=window)
    if not got:
        return ""
    emit("brain", "🎯 la tarjeta responde lo que el modelo iba a buscar en la web", role="system",
         text=f"{got['widget_id']}:{got.get('action') or 'read'} ← {str(search_req['v'])[:100]}",
         extra={"cat": "flash", "widget": got["widget_id"]})
    search_req["v"] = None
    if got["kind"] == "call":
        present(got["widget_id"], reason="turn-order", src="flash", emit=emit)
        apply_widget_data(got["widget_id"], got["action"], got["payload"])
        acted["widget"] = done["v"] = True
    elif read_req.get("v") is None:
        read_req["v"] = {"widget_id": got["widget_id"], "question": got["question"]}
    return got["kind"]


def present_if_show(read_req: dict, *, brief, operator_text: str, is_open: Callable, present: Callable,
                    emit) -> bool:
    """A read whose turn the verdict reads as «canvas: show», over a CLOSED card, brings the card through the
    one door. A question with no show in it («when is the dentist?») stays a read. True when presented."""
    try:
        from nucleo.flash import turn_brief as _tb, widget_read as _wread
        wid = _wread.resolve(str((read_req.get("v") or {}).get("widget_id") or ""), operator_text)
        if not wid or is_open(wid):
            return False
        if _tb.read(brief, _tb.CANVAS_KEY, "neither")[0] != "show":
            return False
        return bool(present(wid, reason="turn-order", src="flash", emit=emit))
    except Exception:  # noqa: BLE001
        return False


async def after_show(acted: dict, *, brief, operator_text: str, spoken_text: str, spec, emit, present: Callable,
                     apply_widget_data: Callable, window=None) -> bool:
    """The turn SHOWED a card and said it would do something on it — the show is not the act (V2-773, email
    block). Two measured turns: «Show me only the emails from today that need my attention» opened the messaging
    card from the catalogue and promised «let me pull your inbox up and flag what needs you» — no `show_view`;
    «Open the most important one» over the open card had its spurious `escalate` turned into a show the door
    suppressed («already open»), the reply said «Opening that one now», and nothing opened. Both had the card
    in front and a promise (or a verdict naming the action); one pass asks for the call. True when a call ran."""
    try:
        from nucleo import danger as _danger
        from nucleo.flash import act_repair as _repair, clarifying as _cl, direct_action as _da, router as _router
        wid = str(acted.get("widget_id") or "").strip().lower()
        if not wid or _danger.is_dangerous(operator_text):
            return False
        # A SILENT show is not exempt (demo M1, 2026-09-27): «Show me a chart of Apple stock today» — the catalogue
        # named `markets` (0.99), the model called show_widget and said nothing, and the card came up EMPTY: no
        # `show` with the symbol, and «the last month instead» then failed on «no chart on screen yet». The
        # promise reading needs words; the catalogue and the verdict do not.
        spoken_text = (spoken_text or "").strip()
        if spoken_text and _cl.asks_for_missing_detail(spoken_text):
            return False
        # …or the card was named by the catalogue for an order with more in it than «open it» (demo v3, E1:
        # «Show me only the emails from today that need my attention» opened the card and DENIED the filter
        # its own action declares). The pass is told to call nothing when the show was the whole order.
        # …or the card it opened is EMPTY (demo pass 2026-09-28, M1: «how's apple stock doing today, show me the
        # chart» → show_widget(markets), no symbol, no words, no verdict naming the action, and an empty chart).
        # An empty card is never the whole answer to words that asked for something; the pass judges what is due.
        from nucleo.flash import surface_ack as _sa
        empty = _sa.nothing_to_show(wid)
        # …or it SPOKE on a turn the verdict reads as an order (demo pass 2026-09-28, E2: «open the most important
        # one» → the card came up and «…so I'm opening that one», which no promise wording table knows). The pass
        # judges its own reply — a promise or a claim gets its call, an answer or an offer does not — so the
        # reading of the words is its job, not a verb table's.
        # …or an ORDER whose words name no card at all (demo pass 65, E2: «open it» after «did inworld send me
        # something?» brought the mail card up and said «Here you go.» — the receipt stayed shut; the card was closed
        # when the brief fired, so no verdict could name `open`). The card came up by CONTEXT, which is a guess at the
        # object, never the act; «show me the calendar» names its card and is left alone.
        by_context = _da.reads_as_order(brief) and not _da.named_cards(operator_text)
        if not (acted.get("show_suppressed") or (spoken_text and _router.promises_action(spoken_text))
                or _da.names_an_order(brief, sure=0.8) or named_or_catalogue(brief, operator_text) == wid
                or (spoken_text and _da.names_an_order(brief)) or empty or by_context):
            return False
        said = spoken_text or (f"(Abrí la tarjeta «{wid}» y está VACÍA: aún no he hecho lo que pidió.)" if empty else "")
        got = await _repair.call_for_promise(operator_text, said, wid, spec=spec, window=window)
        # A bare `show` is the card coming up, which already happened; a `show` WITH content («markets:show
        # {symbol: AAPL}») is the order itself.
        if not got or (str(got.get("action") or "") in ("show", "open_widget") and not got.get("payload")):
            return False
        present(got["widget_id"], reason="turn-order", src="flash", emit=emit)
        apply_widget_data(got["widget_id"], got["action"], got["payload"])
        emit("brain", "🔁 abrió la tarjeta y prometió más — la llamada, en una segunda pasada",
             text=f"{got['widget_id']}:{got['action']}", role="system",
             extra={"cat": "flash", "widget": got["widget_id"], "action": got["action"],
                    "suppressed": bool(acted.get("show_suppressed"))})
        return True
    except Exception:  # noqa: BLE001
        return False


def question_left_to_a_lens(brief, *, ops: list, acted: dict, operator_text: str = "") -> str:
    """The card to READ when a QUESTION was answered by a lens alone — "" otherwise.

    Demo pass 2026-09-28: «johnny what do i have tomorrow» → `agenda:show_day` and silence (C1); «what's on my plate
    tomorrow» → «Let me pull your day up.» + the same view, and no answer (Z1). A view is where he LOOKS; a question
    wants the answer SAID. The read's second pass is told what was already said and stays silent when that already
    answers (`speak`), so this needs no reading of the reply's wording — only the verdict («question») and the fact
    that everything the turn did was a lens."""
    try:
        from nucleo.flash import data_ops as _do, turn_brief as _tb
        kind, info = _tb.read(brief, _tb.REQUEST_KEY, "")
        words, winfo = _tb.read(brief, _tb.WORDS_KEY, "")
        # a question, or an order that owes words (R3 «…and tell me the dates», M1 «how's apple doing, show me the
        # chart» — both read as orders, both answered with a view and silence)
        # …or, with BOTH readings unsure, his own question mark (demo pass 66, R2: «and when does anna's vacation
        # start? show me in the calendar» → show_day on 20 December and «Done.»; request_type 0.42, words 0.02).
        # Punctuation, not vocabulary: every language the STT writes marks a question the same way.
        asked = "?" in (operator_text or "") or "¿" in (operator_text or "")
        # ⚠️ An UNSURE reading is `(fallback, {…, "used": False})` — not `(fallback, None)` (`jev.read`). The pass-66
        # version tested `info is None`, which only an ABSENT verdict gives, so with both readings unsure it never
        # fired and R2 came back as «Done.» again in pass 92 (2026-10-03). Its test stubbed `read` with None: a test
        # that re-implemented the reader, not one that read it. «Not used» is what unsure means.
        sure_kind = bool((info or {}).get("used"))
        sure_words = bool((winfo or {}).get("used"))
        if not ((sure_kind and str(kind or "") == "question")
                or (sure_words and str(words or "") == "tell")
                or (not sure_kind and not sure_words and asked)):
            return ""
        ops = [o for o in (ops or []) if isinstance(o, dict)]
        if any(not _do.is_view_op(str(o.get("widget_id") or ""), str(o.get("action") or "")) for o in ops):
            return ""
        wid = str((ops[-1].get("widget_id") if ops else acted.get("widget_id")) or "").strip()
        if not wid and not ops and not acted.get("widget"):
            # NO call at all — the model answered from memory (demo pass 94, Z1: «what's on my plate tomorrow» →
            # «three things» without the 3 pm meeting, no read). The card the catalogue names is read, and the
            # read's second pass corrects what was said against the data (the data wins, pass 84).
            wid = named_or_catalogue(brief, operator_text)
        if not wid:
            return ""
        from nucleo.flash import widget_read as _wr
        return wid if _wr.can_answer(wid.split("::")[0]) or _wr.read(wid) else ""
    except Exception:  # noqa: BLE001
        return ""

