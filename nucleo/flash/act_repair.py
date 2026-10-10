"""nucleo/flash/act_repair.py — the model PROMISED to act on a card and called nothing: ask it once more, for the call.

Measured on the operator's engine (V2-764, 2026-09-24), with a clean window per phrase: «Busca en torrent la serie
Sherlock» → *«Voy a por la serie Sherlock en torrent y te enseño el catálogo en cuanto lo tenga»* and NO tool;
«Hazme una lista de torrents de documentales de la NASA» → the same. The card was known (the turn's own verdict
names it — `build_decision.named_card`), the action existed (`archivos:torrent_search`, declared), and the model
even SAID which one it meant. What it did not produce was the call.

Sibling of `second_pass.promise_repair` (V2-717), which covers a promise to LOOK by reading the widget. This one
covers a promise to DO: one small non-streamed pass with the model that just failed, offered ONE tool
(`widget_data`) and the named card's own declared actions, told what it said. It extracts the payload itself — a
search query is free text no enumeration can fill, which is why the verdict alone (`direct_action.complete`) cannot
close this. The call it returns goes through the caller's `apply_widget_data`, the same `action_mode_now` gate
every model call goes through: nothing new is allowed to run, a declared action stops going unrun.

Bounded on purpose: only when the turn called NOTHING and promised; only a card the verdict names; only an action
that card declares; a model that still calls nothing leaves the turn exactly as it was. It costs one model call on
the turns that fail, and zero on every other turn.
"""
from __future__ import annotations

import json
import re

#: What the repair tells the model. Short on purpose: the ask is «make the call you promised», not a new turn.
_SYS = (
    "You are the brain of a voice assistant. On the previous turn you answered WITHOUT calling any "
    "tool. Read what you said: if you PROMISED to do something on the card «{wid}» or CLAIMED to "
    "have done it (a draft ready, an appointment moved, something opened or changed), make NOW "
    "exactly the `widget_data` call that fulfils it, with widget_id «{wid}», one of the declared "
    "actions below, and the payload taken from the operator's words and from what the card holds (a "
    "relative time — «half an hour later» — is computed from the appointment that is there). If you "
    "only ANSWERED, PROPOSED or ASKED — without promising or claiming an act — or if no action fits, "
    "call nothing. OFFERING to do it («want me to book it?», «¿quieres que lo reserve?») is NOT "
    "doing it: wait for his yes. But if you CLAIMED one act and also offer ANOTHER («moved to 2:45; "
    "shall I tell Rowan?»), make the call for the one you claimed. Write any text you put in the "
    "payload (a note, a message, a title) in the OPERATOR's language, as he said it.\n\nActions of "
    "«{wid}»:\n{actions}{card}"
)
#: What the card holds, so a relative order («move it 30 minutes later») can be turned into a call. The
#: demo run (2026-09-26): the model computed «It's now at 2:00 PM, running until 2:45» in the turn — it had the
#: digest — and this pass, which had only his words, could not, and returned nothing in silence.
_CARD = "\n\nWHAT THE CARD «{wid}» HOLDS NOW:\n{digest}"


def conversation(window, n: int = 6) -> str:
    """The last turns, as the model that spoke them saw them — so a repair pass knows what «the new time», «that
    one» or «it» is (demo pass 2026-09-28, C5: «send rowan a telegram with the new time» reached a pass that saw
    only his sentence and the messaging card; the time lived two turns back, on the agenda)."""
    try:
        rows = [m for m in (window or []) if (m or {}).get("role") in ("user", "assistant")][-n:]
        lines = [f"{'Operator' if m['role'] == 'user' else 'You'}: {str(m.get('content') or '').strip()[:300]}"
                 for m in rows if str(m.get("content") or "").strip()]
        return ("\n\nTHE CONVERSATION SO FAR (latest last):\n" + "\n".join(lines)) if lines else ""
    except Exception:  # noqa: BLE001
        return ""


def _note(wid: str, why: str, **extra) -> None:
    """The pass ran and gave NO call — said on the timeline, because a silent None here was a turn that
    claimed an act nobody could find (V2-773 audit)."""
    try:
        from voice.observer import emit
        emit("brain", "🔁 la segunda pasada no dio llamada", text=f"{wid}: {why}", role="system",
             extra={"cat": "flash", "widget": wid, "why": why, **extra})
    except Exception:  # noqa: BLE001
        pass


def _actions_block(manifest: dict) -> str:
    rows = []
    for name, spec in (manifest.get("actions") or {}).items():
        spec = spec if isinstance(spec, dict) else {}
        pay = spec.get("payload") if isinstance(spec.get("payload"), dict) else {}
        rows.append(f"- {name}: {str(spec.get('desc') or '')[:200]}"
                    + (f" · payload {json.dumps(pay, ensure_ascii=False)[:220]}" if pay else ""))
    return "\n".join(rows)


def _widget_data_tool() -> dict | None:
    try:
        from nucleo.flash import router_catalog as _rc
        return next((t for t in _rc.TOOLS if t.get("function", {}).get("name") == "widget_data"), None)
    except Exception:  # noqa: BLE001
        return None


# The words that DENY an act — the one case the repaired act has to be said after (see `after_the_repair`).
# English and Spanish, the two languages the demo and the operator's sessions are measured in.
_DENIED_RE = re.compile(
    r"\b(?:can'?t|cannot|can not|couldn'?t|unable to|not something i can|no way (?:to|i can)|there(?:'s| is) no|"
    r"there(?:'s| is)n'?t (?:a|any)|isn'?t (?:a|any|something)|"
    r"no puedo|no es algo que pueda|no hay (?:forma|manera|ning[uú]n)|no tengo (?:forma|manera)|no existe)\b", re.I)


def denies_the_act(spoken: str) -> bool:
    """Do the model's words say the act cannot be done? Deterministic and narrow: a can't/there's-no shape."""
    return bool(_DENIED_RE.search(spoken or ""))


#: The line after an act the verdict carried out, by what the model's words DID (demo passes 108-109): «which…?» was
#: answered with «I've gone ahead, as you asked» — a go-ahead nobody gave. The shape is read deterministically from
#: the model's own words in the session language (`clarifying`): no trip on the tail, and the Jev brief is fired
#: before the reply exists. A claim or a promise has no shape here and gets nothing.
TAILS = {"asked_which": "data_ack_went_with", "asked": "data_ack_went_ahead", "denied": "data_ack"}


def words_shape(spoken: str) -> str:
    """"asked_which" (a missing detail), "asked" (any other question), "denied", or "" — the key of `TAILS`."""
    s = spoken or ""
    if "?" in s:
        from nucleo.flash import clarifying as _cl
        return "asked_which" if _cl.asks_for_missing_detail(s) else "asked"
    return "denied" if denies_the_act(s) else ""


def _tail(shape: str) -> str:
    from i18n import langs as _langs
    line = str(getattr(_langs.current_language(), TAILS.get(shape, ""), "") or "").strip() if shape else ""
    return " " + line if line else ""


def after_the_completion(spoken: str, widget_id: str = "", action: str = "") -> str:
    """What the VOICE adds when the VERDICT carried out an order the model's words only ASKED about.

    Demo passes 76 S3 and 90 S2 (2026-10-03): «Compare them visually.» — the model called nothing and asked «Which
    view do you want them in, side by side?»; the verdict set `layout: compare` and the sheet changed, and the last
    thing heard was the question (incident T509). Unlike a repaired LOOK (`after_the_repair` stays silent: its answer
    comes from the op's data), a completed view changes the screen and has no answer of its own — so a question is
    followed by the went-ahead line. Words that did not ask need nothing."""
    shape = words_shape(spoken)
    if shape not in ("asked", "asked_which"):
        return ""
    from widgets import effects as _fx
    if widget_id and action and _fx.carries(widget_id, action, _fx.OUTPUT_ANSWER):
        return ""                           # its answer is composed from the data — see `after_the_repair`
    return _tail(shape)


def after_the_repair(spoken: str, promised: bool, widget_id: str = "", action: str = "") -> str:
    """What the VOICE adds once the second pass has carried out an order the model's words DENIED.

    Demo pass 31 (2026-09-28, E4): «leave that inworld one as unread» — the model called nothing and said «there's
    no unread toggle for a mail message»; the verdict's second pass then marked it unread. The action was done and
    the last thing heard was that it could not be. The text channel drops the model's words and lets the result
    speak; the voice cannot unsay what already streamed, so it says what happened after it — the same rule as a
    worker stopped by the backstop («never a silent kill»). Nothing is added when the words already promised the
    act, or when nothing was said (the ordinary data ack covers that)."""
    # One rule (demo passes 55-56, 2026-09-29): the words already carry the act unless they DENIED it. «Right… I
    # left the Inworld one unread — it's back to showing as new.» and «Yep — putting Madonna on.» both got a
    # «Done.» stapled on, because the promise table is Spanish and neither is a refusal. A claim or a promise in
    # any language needs nothing after it; a denial does, and a question gets «went ahead» (below).
    if not (spoken or "").strip():
        return ""
    shape = words_shape(spoken)
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
        return _tail(shape)
    except Exception:  # noqa: BLE001
        return ""


def _recipient_was_named(wid: str, action: str, payload: dict, operator_text: str, window) -> bool:
    """An outbound message a repair invents must go to someone his words or the conversation carry (V2-781: «avísame
    cuando esté» became `send_to {"contact": "zaelar"}`, the assistant's own name)."""
    try:
        from widgets import effects as _fx
        if not _fx.carries(wid, action, _fx.EXTERNAL_SEND):
            return True
        who = str(payload.get("contact") or payload.get("to") or "").strip().lower()
        heard = " ".join([operator_text or ""] + [str((m or {}).get("content") or "") for m in (window or [])
                                                  if (m or {}).get("role") == "user"]).lower()
        return not who or who in heard
    except Exception:  # noqa: BLE001
        return True


async def call_for_promise(operator_text: str, reply: str, widget_id: str, spec=None, *,
                           window=None) -> dict | None:
    """`{widget_id, action, payload}` — the call the model should have made — or None. Never raises."""
    try:
        wid = str(widget_id or "").strip().lower()
        if not wid or not (operator_text or "").strip():
            return None
        from widgets import runtime as _rt
        manifest = _rt.get(wid) or {}
        declared = manifest.get("actions") or {}
        tool = _widget_data_tool()
        if not declared or not tool:
            return None
        got: list[tuple[str, dict]] = []
        digest = ""
        try:
            from nucleo.flash import widget_read as _wr
            digest = str(_wr.read(wid) or "").strip()[:1500]
        except Exception:  # noqa: BLE001 — without the card the pass still runs on his words
            digest = ""
        card = (_CARD.format(wid=wid, digest=digest) if digest else "") + _days()
        from nucleo.flash.fast_client import FastClient
        await FastClient().complete(
            [{"role": "system", "content": _SYS.format(wid=wid, actions=_actions_block(manifest), card=card)},
             {"role": "user", "content": f"Operator: «{operator_text.strip()[:400]}»\n"
                                         f"Your reply (no call): «{(reply or '').strip()[:300]}»"
                                         + conversation(window)}],
            spec=spec, max_tokens=300, tools=[tool], no_thinking=True,
            on_tool_call=lambda name, args: got.append((name, args if isinstance(args, dict) else {})))
        for name, args in got:
            if name != "widget_data":
                continue
            if str(args.get("widget_id") or "").strip().lower() != wid:
                _note(wid, "la llamada nombra otra tarjeta", other=str(args.get("widget_id") or "")[:40])
                continue
            action = str(args.get("action") or "").strip()
            if action not in declared:
                _note(wid, "acción no declarada", action=action[:40])
                continue
            payload = args.get("payload") if isinstance(args.get("payload"), dict) else {}
            if not _recipient_was_named(wid, action, payload, operator_text, window):
                _note(wid, "envío a alguien que nadie nombró", action=action[:40])
                continue
            return {"widget_id": wid, "action": action, "payload": payload}
        if not got:
            _note(wid, "el modelo no llamó a nada")
        return None
    except Exception:  # noqa: BLE001 — a repair must never take down a live turn
        return None


_SYS_REPEAT = (
    "You are the brain of a voice assistant. The operator gave an order and your only call was "
    "`{repeated}` on the card «{wid}» — it only LOOKED (a view or a query that was already there or "
    "that changes nothing): it fulfilled nothing. The order, read separately, is `{verdict}` on "
    "«{wid}». If his words ask for that, make NOW exactly the `widget_data` call with widget_id "
    "«{wid}» and action «{verdict}», with the payload taken from his words, from the conversation "
    "and from what the card holds (a note he dictates is written by you; a person is named as he "
    "said it). If his words do NOT ask for that, call nothing. Write any text you put in the payload "
    "(a note, a message, a title) in the OPERATOR's language, as he said it.\n\nActions of "
    "«{wid}»:\n{actions}{card}"
)


_SYS_REFUSED = (
    "You are the brain of a voice assistant. The operator gave an order and you called nothing: you "
    "answered «{said}». The order, read separately, is `{verdict}` on the card «{wid}» — an action "
    "that card DOES have, declared below. If his words ask for that, make NOW exactly the "
    "`widget_data` call with widget_id «{wid}» and action «{verdict}», with the payload taken from "
    "his words, from the conversation and from what the card holds (a note he dictates is written by "
    "you; a person is named as he said it). If his words do NOT ask for that, call nothing. Write "
    "any text you put in the payload (a note, a message, a title) in the OPERATOR's language, as he "
    "said it.\n\nActions of «{wid}»:\n{actions}{card}"
)


def _answered_a_question(brief, reply: str) -> bool:
    """A SURE question (the brief) answered by a reply that promised nothing and refused nothing (`reply_promise`).
    «none» also covers a report of something done («Hecho»), so the question half is what keeps a CLAIM repairable."""
    try:
        from nucleo.flash import reply_promise as _rp, turn_brief as _tb
        kind, info = _tb.read(brief, _tb.REQUEST_KEY, "", min_confidence=0.8) if brief is not None else ("", None)
        return bool(info) and str(kind or "") == "question" and _rp.verdict(reply) == "none" \
            and not denies_the_act(reply)
    except Exception:  # noqa: BLE001
        return False


async def call_for_promise_or_order(operator_text: str, reply: str, widget_id: str, verdict: str = "", spec=None, *,
                                    window=None, brief=None) -> dict | None:
    """`call_for_promise`, and when the words promised nothing — they REFUSED — the verdict's call.

    Demo pass 41 (2026-09-29, E3): «send the invoice to quinn…» over the open receipt → «I can't send it myself —
    sending mail isn't something I can do on my end», no call, the verdict reading `mensajeria:forward`. The promise
    pass asks «did you promise an act?», and a refusal did not, so it rightly called nothing — and the mail never
    went. A refusal of an action the card DECLARES, for an order the verdict names, is one more question to the
    model, with the action named. Bounded like the others: one card, its declared action, the caller's gate."""
    if _answered_a_question(brief, reply):           # V2-781 T529: an answer to a question is left alone
        return None
    got = await call_for_promise(operator_text, reply, widget_id, spec, window=window)
    # V2-781 T518: «make it last until one» — the promise pass read «I'll open it so you can see it» and picked
    # `open_meeting` with the verdict at `agenda:move_meeting` 0.98. The verdict completes the model (CRIT-K2): a
    # view the pass chose over a real op the verdict names is asked once more, for that op.
    if got and verdict and got["action"] != verdict and _is_view(got["widget_id"], got["action"]) \
            and not _is_view(got["widget_id"], verdict):
        return await call_for_repeated_view(operator_text, widget_id, got["action"], verdict, spec,
                                            window=window) or got
    if got or not verdict:
        return got
    said = " ".join(str(reply or "").split())[:300]
    return await call_for_repeated_view(operator_text, widget_id, "", verdict, spec, window=window,
                                        _sys=_SYS_REFUSED.replace("{said}", said.replace("{", "(").replace("}", ")")))


async def call_for_repeated_view(operator_text: str, widget_id: str, repeated: str, verdict: str, spec=None, *,
                                 window=None, _sys: str = "") -> dict | None:
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
        if not wid or not verdict or not (operator_text or "").strip():
            return None
        from widgets import runtime as _rt
        manifest = _rt.get(wid) or {}
        declared = manifest.get("actions") or {}
        tool = _widget_data_tool()
        if verdict not in declared or not tool:
            return None
        digest = ""
        try:
            from nucleo.flash import widget_read as _wr
            digest = str(_wr.read(wid) or "").strip()[:1500]
        except Exception:  # noqa: BLE001
            digest = ""
        card = (_CARD.format(wid=wid, digest=digest) if digest else "") + _days()
        got: list[tuple[str, dict]] = []
        from nucleo.flash.fast_client import FastClient
        await FastClient().complete(
            [{"role": "system", "content": (_sys or _SYS_REPEAT).format(wid=wid, repeated=repeated, verdict=verdict,
                                                                     actions=_actions_block(manifest), card=card)},
             {"role": "user", "content": f"Operator: «{operator_text.strip()[:400]}»" + conversation(window)}],
            spec=spec, max_tokens=400, tools=[tool], no_thinking=True,
            on_tool_call=lambda name, args: got.append((name, args if isinstance(args, dict) else {})))
        for name, args in got:
            if (name == "widget_data" and str(args.get("widget_id") or "").strip().lower() == wid
                    and str(args.get("action") or "").strip() == verdict):
                payload = args.get("payload") if isinstance(args.get("payload"), dict) else {}
                return {"widget_id": wid, "action": verdict, "payload": payload}
        _note(wid, "el modelo no hizo la llamada del veredicto", action=verdict)
        return None
    except Exception:  # noqa: BLE001
        return None


_SYS_AFTER_READ = (
    "You are the brain of a voice assistant. The operator gave an ORDER on the card «{wid}». To "
    "fulfil it you first read the card «{read}» — this is what it holds:\n{block}\n\nNow fulfil the "
    "order: make the `widget_data` call with widget_id «{wid}», one of its declared actions and the "
    "payload taken from his words and from what you just read (a message is written by you; a person "
    "is named as he said it). If his sentence does not ask for anything on «{wid}», call nothing. "
    "Write any text you put in the payload (a note, a message, a title) in the OPERATOR's language, "
    "as he said it.\n\nActions of «{wid}»:\n{actions}{card}"
)


async def call_after_read(operator_text: str, read_widget: str, widget_id: str, spec=None, *,
                          window=None) -> dict | None:
    """The turn READ one card to get what an order on ANOTHER card needed — and the read path ends the turn with
    words only. `{widget_id, action, payload}` for the order, or None. Never raises.

    Demo pass 2026-09-28 (full20 C5): «send rowan a telegram with the new time» — the model read the agenda for the
    new time (sensible), and the read's answer pass, which has no tools, said «I can't send a Telegram, I don't have
    any messaging tool available here». The order stood; this pass carries it out with what was read."""
    try:
        wid = str(widget_id or "").strip().lower()
        rid = str(read_widget or "").strip().lower()
        if not wid or not rid or wid == rid or not (operator_text or "").strip():
            return None
        from widgets import runtime as _rt
        manifest = _rt.get(wid) or {}
        declared = manifest.get("actions") or {}
        tool = _widget_data_tool()
        if not declared or not tool:
            return None
        from nucleo.flash import widget_read as _wr
        block = str(_wr.read(rid) or "").strip()[:1500] or "(vacía)"
        digest = str(_wr.read(wid) or "").strip()[:800]
        card = (_CARD.format(wid=wid, digest=digest) if digest else "") + _days()
        got: list[tuple[str, dict]] = []
        from nucleo.flash.fast_client import FastClient
        await FastClient().complete(
            [{"role": "system", "content": _SYS_AFTER_READ.format(wid=wid, read=rid, block=block,
                                                                  actions=_actions_block(manifest), card=card)},
             {"role": "user", "content": f"Operator: «{operator_text.strip()[:400]}»" + conversation(window)}],
            spec=spec, max_tokens=400, tools=[tool], no_thinking=True,
            on_tool_call=lambda name, args: got.append((name, args if isinstance(args, dict) else {})))
        for name, args in got:
            action = str(args.get("action") or "").strip()
            if name == "widget_data" and str(args.get("widget_id") or "").strip().lower() == wid and action in declared:
                payload = args.get("payload") if isinstance(args.get("payload"), dict) else {}
                return {"widget_id": wid, "action": action, "payload": payload}
        _note(wid, "tras leer, el modelo no hizo la llamada de la orden", read=rid)
        return None
    except Exception:  # noqa: BLE001
        return None


def _is_view(wid: str, action: str) -> bool:
    try:
        from nucleo.flash import data_ops as _dops
        return bool(_dops.is_view_op(wid, action))
    except Exception:  # noqa: BLE001
        return False


def same_card_order_after_read(brief, read_widget: str, reply: str = "") -> str:
    """The verdict's action when the turn READ the very card the order is on and stopped there, or "".

    V2-781 T518 (EN `agenda-everyday-edits`): «There's no piano on Tuesday October 13» — the verdict read
    `agenda:cancel_meeting` at 1.00, the model said «let me check» (reply_promise=act), read the agenda and the
    read's answer pass, which has no tools, said «Got it — no piano on the 13th» over a series that still held it.
    The brief called the sentence a `comment`, so the order gate stayed shut. A statement about his own card IS an
    order on it when a SURE verdict names a real op there and the model itself promised to act — never for a
    question, which a read answers."""
    try:
        from nucleo.flash import reply_promise as _rp, turn_brief as _tb
        target, t_info = _tb.read(brief, _tb.TARGET_KEY, "", min_confidence=0.85)
        owner, _sep, act = str(target or "").rpartition(":")
        rid = str(read_widget or "").split("::")[0].strip().lower()
        if not (t_info and owner and act) or owner.split("::")[0].lower() != rid or _is_view(rid, act):
            return ""
        kind, k_info = _tb.read(brief, _tb.REQUEST_KEY, "")
        if str(kind or "") == "question":
            return ""
        sure_order = str(kind or "") == "order" and bool(k_info)
        return act if (sure_order or _rp.verdict(reply) == "act") else ""
    except Exception:  # noqa: BLE001
        return ""


async def after_a_read(brief, operator_text: str, read_widget: str, reply: str = "", spec=None, *,
                       window=None) -> dict | None:
    """The order a READ was serving, carried out — `{widget_id, action, payload}` or None. ONE door for both
    channels: the voice read lane and the probe's light route used to differ (only the voice had it).

    Another card («send rowan a telegram with the new time», full20 C5) → `call_after_read`; the same card the
    verdict names (T518) → the verdict's call, asked once like a repeated view."""
    try:
        from nucleo.flash import direct_action as _da
        other = _da.order_card_after_read(brief, operator_text, read_widget)
        if other:
            return await call_after_read(operator_text, read_widget, other, spec, window=window)
        act = same_card_order_after_read(brief, read_widget, reply)
        if act:
            rid = str(read_widget or "").split("::")[0]
            return await call_for_repeated_view(operator_text, rid, "read_widget", act, spec, window=window)
        return None
    except Exception:  # noqa: BLE001 — a repair must never take down a live turn
        return None


_SYS_AFTER_SEARCH = (
    "You are the brain of a voice assistant. The operator's turn asked for a FACT and an ORDER on the card "
    "«{wid}». You searched the web for the fact and answered:\n«{answer}»\n\nNow fulfil the order: make the "
    "`widget_data` call with widget_id «{wid}», one of its declared actions and the payload taken from his "
    "words and from what you found (a date you found is written as YYYY-MM-DD). If his sentence does not ask "
    "for anything on «{wid}», call nothing. Write any text you put in the payload (a note, a title) in the "
    "OPERATOR's language, as he said it.\n\nActions of «{wid}»:\n{actions}{card}"
)


def order_card_after_search(brief, answer: str = "") -> str:
    """The card an ORDER is on when the turn SEARCHED the web for the fact it needed, or "".

    V2-781 T515 (2026-10-03): «Can you set a reminder for the premiere day?» — the model searched again for the
    date, and the search's answer pass, which has no tools, said «I can't actually set reminders myself»; the
    brief had read `request_type=order` and `catalog_widget=agenda` (0.91). The ES twin read `wants_words=tell` on
    the same order and `request_type=question` on «¿te enteras de cuándo se estrena y me avisas?» — answered «avisarte
    no puedo». So: a card the brief names, and either a SURE order or an answer that refuses an act. A question
    answered with its fact never reaches here."""
    try:
        from nucleo.flash import build_decision as _bd, turn_brief as _tb
        kind, info = _tb.read(brief, _tb.REQUEST_KEY, "", min_confidence=0.8)
        if not ((str(kind or "") == "order" and info) or denies_the_act(answer)):
            return ""
        return str(_bd.named_card(brief) or "").split("::")[0]
    except Exception:  # noqa: BLE001
        return ""


async def call_after_search(operator_text: str, answer: str, brief, spec=None, *, window=None) -> dict | None:
    """The order half of a turn that searched for its fact — `{widget_id, action, payload}` or None. Never raises.

    The sibling of `call_after_read`: the search's answer pass has no tools, so an order beside the question
    («find out when it premieres and remind me») was answered with the fact and then refused. One bounded pass:
    the card the brief names, its declared actions, the caller's usual gate."""
    try:
        wid = order_card_after_search(brief, answer)
        if not wid or not (operator_text or "").strip() or not (answer or "").strip():
            return None
        from widgets import runtime as _rt
        manifest = _rt.get(wid) or {}
        declared = manifest.get("actions") or {}
        tool = _widget_data_tool()
        if not declared or not tool:
            return None
        from nucleo.flash import widget_read as _wr
        digest = str(_wr.read(wid) or "").strip()[:800]
        card = (_CARD.format(wid=wid, digest=digest) if digest else "") + _days()
        said = " ".join(str(answer).split())[:600].replace("{", "(").replace("}", ")")
        got: list[tuple[str, dict]] = []
        from nucleo.flash.fast_client import FastClient
        await FastClient().complete(
            [{"role": "system", "content": _SYS_AFTER_SEARCH.format(wid=wid, answer=said, actions=_actions_block(manifest),
                                                                    card=card)},
             {"role": "user", "content": f"Operator: «{operator_text.strip()[:400]}»" + conversation(window)}],
            spec=spec, max_tokens=400, tools=[tool], no_thinking=True,
            on_tool_call=lambda name, args: got.append((name, args if isinstance(args, dict) else {})))
        for name, args in got:
            action = str(args.get("action") or "").strip()
            if name == "widget_data" and str(args.get("widget_id") or "").strip().lower() == wid and action in declared:
                payload = args.get("payload") if isinstance(args.get("payload"), dict) else {}
                return {"widget_id": wid, "action": action, "payload": payload}
        _note(wid, "tras buscar, el modelo no hizo la llamada de la orden")
        return None
    except Exception:  # noqa: BLE001
        return None


async def voice_after_search(operator_text: str, spoken_text: str, brief, spec, *, window, apply, send, emit,
                             acted: dict, done: dict) -> bool:
    """The VOICE channel's half of `call_after_search`: run the order, mark the turn as having acted, say what
    happened after a refusal that already streamed (`after_the_repair`), and leave one timeline line."""
    got = await call_after_search(operator_text, spoken_text, brief, spec, window=window)
    if not got:
        return False
    apply(got["widget_id"], got["action"], got["payload"])
    acted["widget"] = done["v"] = True
    line = after_the_repair(spoken_text, False, got["widget_id"], got["action"]).strip()
    if line:
        send(line)
    emit("brain", "🔁 buscó para una orden — la llamada, con lo encontrado", role="system",
         text=f"{got['widget_id']}:{got['action']}", extra={"cat": "flash", "widget": got["widget_id"],
                                                          "action": got["action"]})
    return True


def without_the_denial(spoken: str) -> str:
    """`spoken` minus the sentences that deny an act the turn then carried out (the text channel can unsay)."""
    kept = []
    for p in re.split(r"(?<=[.!?])\s+", str(spoken or "").strip()):
        if p and denies_the_act(p):
            # «I can't set reminders myself, but I've got the date: …» — the half after «but» is the answer
            m = re.search(r"[,;—-]\s*(?:but|pero|aunque)\s+(.*)$", p, re.I)
            p = (m.group(1)[:1].upper() + m.group(1)[1:]) if m and not denies_the_act(m.group(1)) else ""
        if p:
            kept.append(p)
    return " ".join(kept).strip()


_SYS_COMMISSION = (
    "You are the brain of a voice assistant. The operator gave an ORDER that names the card «{wid}», "
    "and the turn was about to send it to a background process of SEVERAL MINUTES. Before spending "
    "them, decide with what the card holds: (1) if a declared action of «{wid}» fulfils the order, "
    "call `widget_data` with it; (2) if the ANSWER is in what the card keeps (its appointments and "
    "free slots, its contacts, its files…), call `read_widget` with widget_id «{wid}» and the "
    "concrete question to resolve against it (with the absolute date and the time range he said) — "
    "only if that tool is offered to you; (3) only if the outside world is needed — the web, booking "
    "on an external site, searching products — call nothing. A message to a contact is the card's "
    "send action, with the text written by you from what he wants to say, and `contact` is the "
    "person's NAME as he said it («Rowan»), never their @user, phone or email: the card resolves it "
    "in its directory. An order to DO something (send, write, note down, move) is fulfilled with its "
    "action even if it depends on a fact the card keeps: the card checks it when it runs and says if "
    "it is missing — reading to check first does not fulfil the order. But FINDING, searching or "
    "telling him something (a free slot, a date, a fact) is KNOWING it: it is read, and nothing he "
    "did not ask for is noted down or sent — «find me a slot to talk with Rowan» is neither booking "
    "nor writing to Rowan. The COMMISSION was written by another step and may carry a miscopied "
    "fact: a time, a date or a name that a card on his screen holds is taken from the CARD, not from "
    "the commission. Write any text you put in the payload (a note, a message, a title) in the "
    "OPERATOR's language, as he said it.\n\nActions of «{wid}»:\n{actions}{card}"
)


def _tool_named(name: str) -> dict | None:
    try:
        from nucleo.flash import router_catalog as _rc
        return next((t for t in _rc.TOOLS if t.get("function", {}).get("name") == name), None)
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
        if not wid or not (operator_text or "").strip():
            return None
        from widgets import runtime as _rt
        manifest = _rt.get(wid) or {}
        # The read option only for a card that can ANSWER (`widget_read.can_answer`): a messaging card gets the
        # call («message Rowan on Telegram» → send_to) and never a read it cannot serve.
        from nucleo.flash import widget_read as _wr0
        tools = [t for t in (_tool_named("widget_data"),
                             _tool_named("read_widget") if (may_read and _wr0.can_answer(wid)) else None) if t]
        if not manifest or not tools:
            return None
        digest = ""
        try:
            from nucleo.flash import widget_read as _wr
            digest = str(_wr.read(wid) or "").strip()[:1500]
        except Exception:  # noqa: BLE001
            digest = ""
        card = (_CARD.format(wid=wid, digest=digest) if digest else "") + _other_open_cards(wid)
        got: list[tuple[str, dict]] = []
        from nucleo.flash.fast_client import FastClient
        _msgs = [{"role": "system", "content": _SYS_COMMISSION.format(wid=wid, actions=_actions_block(manifest), card=card)},
                 {"role": "user", "content": f"Operator: «{operator_text.strip()[:400]}»\n"
                                             f"The commission that was going to a worker: «{(commission or '').strip()[:300]}»"
                                             + _verdict_hint(verdict_action, manifest)
                                             + conversation(window)}]
        await FastClient().complete(
            _msgs, spec=spec, max_tokens=300, tools=tools, no_thinking=True,
            on_tool_call=lambda name, args: got.append((name, args if isinstance(args, dict) else {})))
        declared = manifest.get("actions") or {}
        if _ignored_the_verdict(got, wid, verdict_action, declared):
            # Demo pass 92, R3: the hint was there (agenda:find_free, 0.75) and the pass called show_day again — one
            # day, «I can only see the start of it». ONE more ask, naming the action as the one to call; whatever it
            # answers then is taken (the verdict completes the pass, it never runs blind).
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
            if name == "read_widget":
                q = str(args.get("question") or "").strip() or operator_text.strip()
                return {"kind": "read", "widget_id": wid, "question": q[:300]}
            if name == "widget_data" and str(args.get("action") or "").strip() in declared:
                payload = args.get("payload") if isinstance(args.get("payload"), dict) else {}
                return {"kind": "call", "widget_id": wid, "action": str(args["action"]).strip(), "payload": payload}
        _note(wid, "el encargo sigue su camino al worker" if not got else "la llamada no era de esta tarjeta")
        return None
    except Exception:  # noqa: BLE001 — never take down a live turn
        return None


_SYS_REFUSAL = (
    "You are the brain of a voice assistant. To do what the operator said you called `widget_data` "
    "with the action «{action}» on the card «{wid}» and the payload {payload}, and the card REFUSED "
    "it: «{why}». Correct that call: the SAME action on the SAME card, with the missing or "
    "mismatched fact taken from his words and from what the card holds. A reference by quality («the "
    "best deal», «the cheapest», «the one tomorrow») is resolved by READING the card and passing "
    "that item's title or number; a relative time is computed from what is there. If that still "
    "cannot tell, call nothing. Write any text you put in the payload (a note, a message, a title) "
    "in {lang}, as he said it — whatever language the refusal or the actions are written in."
    "\n\nActions of «{wid}»:\n{actions}{card}"
)


def _days() -> str:
    """Today and the next seven days, the same lookup the turn's prompt carries (`prompt.live_state`): «el martes
    que viene» is a LOOKUP, never arithmetic (V2-781 pair 7: the correction picked the 20th for the 13th)."""
    import time as _t
    now = _t.time()
    days = "; ".join(f"{_t.strftime('%A', _t.localtime(now + i * 86400)).lower()} "
                     f"{_t.strftime('%Y-%m-%d', _t.localtime(now + i * 86400))}" for i in range(0, 8))
    return f"\n\nToday first, then the next days: {days}."


def _session_lang() -> str:
    """The session's language by name (demo pass 102: «the operator's language» let a Spanish refusal win)."""
    try:
        from i18n import langs as _lg
        return str(_lg.current_language().name or "the operator's language")
    except Exception:  # noqa: BLE001
        return "the operator's language"


def _same_card(asked: str, wid: str) -> bool:
    a, w = (asked or "").strip().lower(), (wid or "").strip().lower()
    return bool(a) and (a == w or a.split("::")[0] == w.split("::")[0])


async def call_for_refusal(operator_text: str, widget_id: str, action: str, payload: dict, why: str,
                           spec=None, *, said: str = "") -> dict | None:
    """The corrected payload for a call the card REFUSED, or None. Never raises.

    Demo pass 2026-09-28: «open the one that's the best deal» reached `results:detail` with nothing the sheet
    could match (its badge says «Best value»), and «move it half an hour later» reached `move_meeting` with field
    names it did not read. Both refusals were true and both went to a note for the NEXT turn, so the operator got
    silence and then, one order later, an apology stapled to an unrelated answer. The refusal is exactly what the
    model needs to get it right, and it arrives while the turn is still his: one small pass, with the reason and
    the card in front, allowed to re-issue ONLY the same action on the same card — so it passes the same gate the
    refused call already passed, and it can change what the call says, never what it does."""
    try:
        wid = str(widget_id or "").strip().lower()
        action = str(action or "").strip()
        if not wid or not action or not (operator_text or "").strip():
            return None
        from widgets import runtime as _rt
        manifest = _rt.get(wid.split("::")[0]) or _rt.get(wid) or {}
        tool = _widget_data_tool()
        if action not in (manifest.get("actions") or {}) or not tool:
            return None
        digest = ""
        try:
            from nucleo.flash import widget_read as _wr
            digest = str(_wr.read(wid) or "").strip()[:1500]
        except Exception:  # noqa: BLE001
            digest = ""
        card = (_CARD.format(wid=wid, digest=digest) if digest else "") + _days()
        got: list[tuple[str, dict]] = []
        from nucleo.flash.fast_client import FastClient
        await FastClient().complete(
            [{"role": "system", "content": _SYS_REFUSAL.format(
                wid=wid, action=action, payload=json.dumps(payload or {}, ensure_ascii=False)[:300],
                why=str(why or "")[:300], actions=_actions_block(manifest), card=card, lang=_session_lang())},
             {"role": "user", "content": f"Operator: «{operator_text.strip()[:400]}»"
                                         + (f"\nWhat you just told him: «{said.strip()[:300]}» — if you named which one there, "
                                            f"the correction is THAT one." if (said or "").strip() else "")}],
            spec=spec, max_tokens=300, tools=[tool], no_thinking=True,
            on_tool_call=lambda name, args: got.append((name, args if isinstance(args, dict) else {})))
        for name, args in got:
            if name != "widget_data" or not _same_card(str(args.get("widget_id") or ""), wid):
                continue
            if str(args.get("action") or "").strip() != action:
                _note(wid, "la corrección cambiaba de acción", action=str(args.get("action") or "")[:40])
                continue
            fixed = args.get("payload") if isinstance(args.get("payload"), dict) else {}
            if fixed and fixed != (payload or {}):
                return {"widget_id": wid, "action": action, "payload": fixed}
        _note(wid, "el rechazo no tiene corrección", action=action)
        return None
    except Exception:  # noqa: BLE001 — a repair must never take down a live turn
        return None


async def probe_call_for_promise(operator_text: str, reply: str, spec=None, *, wait_s: float = 3.0,
                                 window=None) -> dict | None:
    """The text channel's mirror: it has no brief in flight, so it fires one and waits for it (bounded) —
    only on the turn that already promised and called nothing. Same verdict, same repair, never raises."""
    try:
        import asyncio
        from nucleo import jev as _jev
        from nucleo.flash import build_decision as _bd, turn_brief as _tb
        handle = _tb.ask_for_turn(operator_text, last_reply="")
        if handle is None:
            return None
        waited = 0.0
        while not _jev._is_ready(handle) and waited < wait_s:
            await asyncio.sleep(0.05)
            waited += 0.05
        wid = _bd.named_card(handle)
        return await call_for_promise(operator_text, reply, wid, spec=spec, window=window) if wid else None
    except Exception:  # noqa: BLE001
        return None
