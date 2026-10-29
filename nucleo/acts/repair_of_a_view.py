"""The second pass when the model only viewed, promised or commissioned what the verdict reads as an order, and how
the repaired act is said after the words.
Moved from `nucleo/flash/act_repair.py` (refactor2710-05 T-04); its names are read through `_ar`."""
from __future__ import annotations

from nucleo.flash import act_repair as _ar


def denies_the_act(spoken: str) -> bool:
    """Do the model's words say the act cannot be done? Deterministic and narrow: a can't/there's-no shape."""
    return bool(_ar._DENIED_RE.search(spoken or ""))


def words_shape(spoken: str) -> str:
    """"asked_which" (a missing detail), "asked" (any other question), "denied", or "" — the key of `TAILS`."""
    s = spoken or ""
    from nucleo.flash import clarifying as _cl
    if "?" in s:
        return "asked_which" if _cl.asks_for_missing_detail(s) else "asked"
    return "denied" if _ar.denies_the_act(s) else ""


def _tail(shape: str) -> str:
    from i18n import langs as _langs
    line = str(getattr(_langs.current_language(), _ar.TAILS.get(shape, ""), "") or "").strip() if shape else ""
    return " " + line if line else ""


def after_the_completion(spoken: str, widget_id: str = "", action: str = "") -> str:
    """What the VOICE adds when the VERDICT carried out an order the model's words only ASKED about.

    Demo passes 76 S3 and 90 S2 (2026-10-03): «Compare them visually.» — the model called nothing and asked «Which
    view do you want them in, side by side?»; the verdict set `layout: compare` and the sheet changed, and the last
    thing heard was the question (incident T509). Unlike a repaired LOOK (`after_the_repair` stays silent: its answer
    comes from the op's data), a completed view changes the screen and has no answer of its own — so a question is
    followed by the went-ahead line; a denial by «Done.» (p130 V2: «no such video» over it playing). Others: nothing."""
    shape = _ar.words_shape(spoken)
    if not shape:
        return ""
    from widgets import effects as _fx
    if widget_id and action and _fx.carries(widget_id, action, _fx.OUTPUT_ANSWER):
        return ""                           # its answer is composed from the data — see `after_the_repair`
    return _ar._tail(shape)


def after_the_repair(spoken: str, promised: bool, widget_id: str = "", action: str = "") -> str:
    """What the VOICE adds once the second pass has carried out an order the model's words DENIED.

    Demo pass 31 (2026-09-28, E4): «leave that inworld one as unread» — the model called nothing and said «there's
    no unread toggle for a mail message»; the verdict's second pass then marked it unread. The action was done and
    the last thing heard was that it could not be. The text channel drops the model's words and lets the result
    speak; the voice cannot unsay what already streamed, so it says what happened after it — the same rule as a
    worker stopped by the backstop («never a silent kill»). Nothing is added when the words already promised the
    act, or when nothing was said (the ordinary data ack covers that)."""
    # One rule (demo passes 55-56, 2026-09-29): the words carry the act unless they DENIED it («Yep — putting
    # Madonna on.» got a «Done.» stapled on). A claim or promise needs nothing; a denial does; a question below.
    if not (spoken or "").strip():
        return ""
    shape = _ar.words_shape(spoken)
    # …but a QUESTION is still a question when it also promises (pass 114, C5: «want me to fire it off… I'll send it
    # as soon as you confirm?» — sent by the repair, and the last thing heard asked).
    if not shape or (promised and shape not in ("asked", "asked_which")):
        return ""
    try:
        # …and a repaired LOOK changes nothing to acknowledge (demo pass 42, C2: «…want me to put it on your calendar
        # at 4?» + a repaired `find_free` → «…at 4?Done.»). Its answer, if one is owed, comes from the op's data.
        from nucleo.flash import data_ops as _dops
        if widget_id and action and _dops.is_view_op(widget_id, action):
            return ""
    except Exception:  # noqa: BLE001
        pass
    try:
        return _ar._tail(shape)
    except Exception:  # noqa: BLE001
        return ""


def _answered_a_question(brief, reply: str) -> bool:
    """A SURE question (the brief) answered by a reply that refused nothing: the brief decides (refactor2710-03)."""
    try:
        from nucleo.turn import brief as _tb
        kind, info = _tb.read(brief, _tb.REQUEST_KEY, "", min_confidence=0.8) if brief is not None else ("", None)
        return bool(info) and str(kind or "") == "question" and not _ar.denies_the_act(reply)
    except Exception:  # noqa: BLE001
        return False


async def call_for_promise_or_order(operator_text: str, reply: str, widget_id: str, verdict: str = "", spec=None, *,
                                    window=None, brief=None, outcome: dict | None = None) -> dict | None:
    """`call_for_promise`, and when the words promised nothing — they REFUSED — the verdict's call.

    Demo pass 41 (2026-09-29, E3): «send the invoice to quinn…» over the open receipt → «I can't send it myself —
    sending mail isn't something I can do on my end», no call, the verdict reading `mensajeria:forward`. The promise
    pass asks «did you promise an act?», and a refusal did not, so it rightly called nothing — and the mail never
    went. A refusal of an action the card DECLARES, for an order the verdict names, is one more question to the
    model, with the action named. Bounded like the others: one card, its declared action, the caller's gate."""
    if _ar._answered_a_question(brief, reply) or _ar._keep.keeps_the_worker(brief, widget_id) or _ar.canvas_holds_the_turn(brief, operator_text, widget_id):  # T529, C6
        return None
    got = _ar._cvis.unless_a_view(await _ar.call_for_promise(operator_text, reply, widget_id, spec, window=window, **({"outcome": outcome} if outcome is not None else {})), brief, outcome)   # V2-820
    # V2-781 T518: «make it last until one» — the pass picked `open_meeting` over `agenda:move_meeting` 0.98. The
    # verdict completes the model (CRIT-K2): a view chosen over the op the verdict names is asked once more.
    if got and verdict and got["action"] != verdict and _ar._is_view(got["widget_id"], got["action"]) \
            and not _ar._is_view(got["widget_id"], verdict):
        return await _ar.call_for_repeated_view(operator_text, widget_id, got["action"], verdict, spec,
                                            window=window, brief=brief) or got
    if got or not verdict:
        return got
    said = " ".join(str(reply or "").split())[:300]
    return _ar._pk.called(outcome, await _ar.call_for_repeated_view(operator_text, widget_id, "", verdict, spec, window=window, brief=brief,
                      _sys=_ar._SYS_REFUSED.replace("{said}", said.replace("{", "(").replace("}", ")"))))


async def call_for_repeated_view(operator_text: str, widget_id: str, repeated: str, verdict: str, spec=None, *,
                                 window=None, _sys: str = "", brief=None) -> dict | None:
    """The model's only call RE-OPENED what was already on screen, and the verdict names an action on that card
    that needs a payload only a model can write — ask once, for that call. `{widget_id, action, payload}` or None.

    Demo pass 2026-09-28 (full20 E3): «send the invoice to quinn, tell him we're already trying inworld and he
    should book it» over the open Inworld invoice → the model called `open` (again), the verdict read
    `mensajeria:forward` at 0.61. The verdict alone cannot complete a forward — the note to Quinn has to be
    written — so the turn ended having done nothing. Bounded like `call_for_promise`: one card, its declared
    action, the caller's usual gate. Never raises."""
    try:
        wid = str(widget_id or "").strip().lower()
        verdict = str(verdict or "").strip()
        if not wid or not verdict or not (operator_text or "").strip() or operator_text.lstrip().startswith("[SISTEMA]") or _ar.canvas_holds_the_turn(brief, operator_text, wid):
            return None
        from widgets import runtime as _rt
        manifest = _rt.get(wid) or {}
        declared = manifest.get("actions") or {}
        tool = _ar._widget_data_tool()
        if verdict not in declared or not tool:
            return None
        digest = ""
        try:
            from nucleo.flash import widget_read as _wr
            digest = str(_wr.read(wid) or "").strip()[:1500]
        except Exception:  # noqa: BLE001
            digest = ""
        card = (_ar._CARD.format(wid=wid, digest=digest) if digest else "") + _ar._days()
        got: list[tuple[str, dict]] = []
        from nucleo.llm.fast_client import FastClient
        await FastClient().complete(
            [{"role": "system", "content": _ar._in_his_lang(_sys or _ar._SYS_REPEAT).format(wid=wid, repeated=repeated, verdict=verdict,
                                                                     actions=_ar._actions_block(manifest), card=card)},
             {"role": "user", "content": f"Operator: «{operator_text.strip()[:400]}»" + _ar.conversation(window)}],
            spec=spec, max_tokens=400, tools=[tool], no_thinking=True,
            on_tool_call=lambda name, args: got.append((name, args if isinstance(args, dict) else {})))
        for name, args in got:
            if (name == "widget_data" and str(args.get("widget_id") or "").strip().lower() == wid
                    and str(args.get("action") or "").strip() == verdict):
                payload = args.get("payload") if isinstance(args.get("payload"), dict) else {}
                return {"widget_id": wid, "action": verdict, "payload": payload}
        _ar._note(wid, "el modelo no hizo la llamada del veredicto", action=verdict)
        return None
    except Exception:  # noqa: BLE001
        return None


def _other_open_cards(wid: str, *, limit: int = 2, chars: int = 900) -> str:
    """What the OTHER cards on his screen hold — the facts a commission on this card usually refers to.

    Demo pass 43 (2026-09-29), C5: «send rowan a telegram with the new time» — the meeting had just been moved to
    4:30 on the open agenda (silently: no words in the window said so), the model's escalation said «17:00», and
    this pass, which saw only the messaging card and that brief, wrote Rowan «moved to 5:00 PM». The time was on
    the screen, in another card."""
    try:
        from memory import api as _memapi
        from nucleo.flash import widget_read as _wr
        ids = [str(x).split("::")[0].lower() for x in ((_memapi.state() or {}).get("open_widgets") or [])]
        out = []
        for other in dict.fromkeys(i for i in ids if i and i != wid):
            if len(out) >= limit:
                break
            if not _wr.can_answer(other):
                continue
            digest = str(_wr.read(other) or "").strip()[:chars]
            if digest:
                out.append(f"\n\nWHAT «{other}» HOLDS, ALSO ON HIS SCREEN (the source of a fact the order names — a time, "
                           f"a date —, above what the commission says). It is the state NOW, with the changes he "
                           f"already asked for in the conversation ALREADY APPLIED: a time from here is the final "
                           f"one, nothing is added to or taken from it again:\n{digest}")
        return "".join(out)
    except Exception:  # noqa: BLE001
        return ""


def _ignored_the_verdict(got: list, wid: str, verdict_action: str, declared: dict) -> bool:
    """The pass called a DIFFERENT declared action on the card the verdict names an action of."""
    a = str(verdict_action or "").strip()
    if not a or a not in declared:
        return False
    calls = [str(x.get("action") or "").strip() for n, x in got
             if n == "widget_data" and str(x.get("widget_id") or "").strip().lower() == wid]
    return bool(calls) and a not in calls


def _verdict_hint(action: str, manifest: dict) -> str:
    """One line naming the action the engine's own reading of the order chose on this card, when it declares it.

    Demo passes 88/89 (2026-10-03), R3 «find a five-day period during her vacation when my calendar is clear»: the
    verdict read `agenda:find_free` (0.73-0.80) and this pass, not told, called `show_day` — a view of ONE day — and
    the answer was «I can't map out five days from just this». The verdict completes the pass; it never overrules a
    call that fits better."""
    a = str(action or "").strip()
    if not a or a not in (manifest.get("actions") or {}):
        return ""
    return (f"\nThe engine's reading of this order names the action «{a}» on this card — use it, with every value "
            f"the conversation already gave (dates, names), unless it clearly cannot do what he asked.")


async def call_or_read_for_commission(operator_text: str, commission: str, widget_id: str, spec=None, *,
                                      window=None, may_read: bool = True, verdict_action: str = "") -> dict | None:
    """A commission that names one of our cards, before it costs a worker (V2-773 final pass, C1): «Find me a
    free 45-minute slot tomorrow afternoon» was delegated to a Brain Worker (three minutes) when the agenda was
    the whole answer. One pass with the card in front decides: `{"kind": "call", widget_id, action, payload}`,
    `{"kind": "read", widget_id, question}`, or None — and None keeps today's path, the worker. Never raises."""
    try:
        wid = str(widget_id or "").strip().lower()
        if not wid or not (operator_text or "").strip() or _ar.canvas_holds_the_turn(None, operator_text, wid):
            return None
        from widgets import runtime as _rt
        manifest = _rt.get(wid) or {}
        # The read option only for a card that can ANSWER (`widget_read.can_answer`): a messaging card gets the
        # call («message Rowan on Telegram» → send_to) and never a read it cannot serve.
        from nucleo.flash import widget_read as _wr0
        tools = [t for t in (_ar._tool_named("widget_data"),
                             _ar._tool_named("read_widget") if (may_read and _wr0.can_answer(wid)) else None) if t]
        from nucleo.flash import compose_rung as _compose
        if tools and _compose.prose_action(wid):
            tools.append(_compose.tool())   # a card that holds prose: its text may be WRITTEN now (2026-10-22)
        if not manifest or not tools:
            return None
        digest = ""
        try:
            from nucleo.flash import widget_read as _wr
            digest = str(_wr.read(wid) or "").strip()[:1500]
        except Exception:  # noqa: BLE001
            digest = ""
        card = (_ar._CARD.format(wid=wid, digest=digest) if digest else "") + _ar._other_open_cards(wid)
        got: list[tuple[str, dict]] = []
        from nucleo.llm.fast_client import FastClient
        _msgs = [{"role": "system", "content": _ar._in_his_lang(_ar._SYS_COMMISSION).format(wid=wid, actions=_ar._actions_block(manifest), card=card)},
                 {"role": "user", "content": f"Operator: «{operator_text.strip()[:400]}»\n"
                                             f"The commission that was going to a worker: «{(commission or '').strip()[:300]}»"
                                             + _ar._verdict_hint(verdict_action, manifest)
                                             + _ar.conversation(window)}]
        await FastClient().complete(
            _msgs, spec=spec, max_tokens=300, tools=tools, no_thinking=True,
            on_tool_call=lambda name, args: got.append((name, args if isinstance(args, dict) else {})))
        declared = manifest.get("actions") or {}
        if _ar._ignored_the_verdict(got, wid, verdict_action, declared):
            # Demo pass 92, R3: hint agenda:find_free 0.75, the pass called show_day again. ONE more ask naming the
            # action; whatever it answers is taken (the verdict completes the pass, never runs blind).
            got.clear()
            await FastClient().complete(
                _msgs + [{"role": "user", "content": f"Call «{verdict_action}» on «{wid}» — that is the action this "
                                                     f"order needs; fill its payload from the operator's words and the "
                                                     f"conversation."}],
                spec=spec, max_tokens=300, tools=tools, no_thinking=True,
                on_tool_call=lambda name, args: got.append((name, args if isinstance(args, dict) else {})))
        for name, args in got:
            if str(args.get("widget_id") or "").strip().lower() != wid:
                continue
            if (_c := _compose.decision(name, args, wid)):
                return _c
            if name == "read_widget":
                q = str(args.get("question") or "").strip() or operator_text.strip()
                return {"kind": "read", "widget_id": wid, "question": q[:300]}
            if name == "widget_data" and str(args.get("action") or "").strip() in declared:
                payload = args.get("payload") if isinstance(args.get("payload"), dict) else {}
                return {"kind": "call", "widget_id": wid, "action": str(args["action"]).strip(), "payload": payload}
        _ar._note(wid, "el encargo sigue su camino al worker" if not got else "la llamada no era de esta tarjeta")
        return None
    except Exception:  # noqa: BLE001 — never take down a live turn
        return None
