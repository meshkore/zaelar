"""card_commission.py — a commission that names one of OUR cards is a read or a declared call before it is a
worker; and a read the verdict says to SHOW brings its card (V2-773, the demo's final pass).

Two measured turns on the operator's live engine, 2026-09-26, both on the calendar with the agenda CLOSED:

  · «Find me a free 45-minute slot tomorrow afternoon to talk with Ethan» — the catalogue verdict named the
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

from typing import Callable


def named_or_catalogue(brief, operator_text: str, *, wait_s: float = 2.5) -> str:
    """The card an order names — by the brief, or by ONE late catalogue question when the brief could not know.

    The brief asks `screen_action` while cards are open and `catalog_widget` only when nothing is, on purpose
    (V2-726). So an order for a CLOSED card while other cards are open reads as a confident «none» and names
    nobody: demo v3, C5 — «Message Ethan on Telegram» with the agenda open — read `none` 0.91, the model
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
        if str(choice or "") != "none" or not (isinstance(info, dict) and info.get("used")):
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
        named = cat if cat and cat != "none" and conf >= _jev.MIN_CONFIDENCE else ""
        try:
            from voice.observer import emit as _emit
            _emit("brain", "🧭 catálogo tardío (la pantalla dijo «none»)", role="system",
                  text=f"{cat or '?'} ({conf:.2f}) → {named or 'nadie'}", extra={"cat": "flash", "card": named, "choice": cat, "confidence": conf})
        except Exception:  # noqa: BLE001
            pass
        return named
    except Exception:  # noqa: BLE001
        return ""


async def before_worker(escalate_req: dict, read_req: dict, *, brief, operator_text: str, spec, emit,
                        present: Callable, apply_widget_data: Callable) -> str:
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
        got = await _repair.call_or_read_for_commission(operator_text, str(escalate_req.get("v") or ""), card,
                                                        spec=spec)
        if not got:
            return ""
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
                     apply_widget_data: Callable) -> bool:
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
        if not (acted.get("show_suppressed") or (spoken_text and _router.promises_action(spoken_text))
                or _da.names_an_order(brief, sure=0.8) or named_or_catalogue(brief, operator_text) == wid
                or (spoken_text and _da.names_an_order(brief)) or empty):
            return False
        said = spoken_text or (f"(Abrí la tarjeta «{wid}» y está VACÍA: aún no he hecho lo que pidió.)" if empty else "")
        got = await _repair.call_for_promise(operator_text, said, wid, spec=spec)
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
