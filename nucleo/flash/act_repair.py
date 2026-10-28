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
that card declares; a model that still calls nothing leaves the turn exactly as it was. One model call on the turns
that fail, zero on every other.
"""
from __future__ import annotations

import json, re
from . import canvas_visibility as _cvis, commission_keep as _keep   # a sheet keeps its worker; a lens is no report
from nucleo.turn import promise_kept as _pk   # V2-790: with `outcome`, the pass may also answer `cannot_do`
from .repair_grounding import in_his_lang as _in_his_lang, session_lang as _session_lang  # noqa: F401 — pass 102/141

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
#: What the card holds, so a relative order («move it 30 minutes later») becomes a call (demo run 2026-09-26:
#: the turn had the digest and computed 2:00 PM; this pass had only his words and returned nothing).
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


# The words that DENY an act — the one case said after the repair (`after_the_repair`); English and Spanish.
_DENIED_RE = re.compile(
    r"\b(?:can'?t|cannot|can not|couldn'?t|unable to|not something i can|no way (?:to|i can)|there(?:'s| is) no|"
    r"there(?:'s| is)n'?t (?:a|any)|isn'?t (?:a|any|something)|"
    r"no puedo|no es algo que pueda|no hay (?:forma|manera|ning[uú]n)|no tengo (?:forma|manera)|no existe)\b", re.I)


#: The line after an act the verdict carried out, by what the model's words DID (demo passes 108-109: «which…?»
#: got «I've gone ahead»). Read deterministically (`clarifying`); a claim or a promise gets nothing.
TAILS = {"asked_which": "data_ack_went_with", "asked": "data_ack_went_ahead", "denied": "data_ack"}


async def call_for_promise(operator_text: str, reply: str, widget_id: str, spec=None, *,
                           window=None, outcome: dict | None = None) -> dict | None:
    """`{widget_id, action, payload}` — the call the model should have made — or None. Never raises."""
    try:
        wid = str(widget_id or "").strip().lower()
        if not wid or not (operator_text or "").strip() or operator_text.lstrip().startswith("[SISTEMA]"):
            return None                     # a system note is not his order (V2-781, compare-insurance-quotes)
        from widgets import runtime as _rt
        from nucleo.flash import repair_grounding as _rg
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
        from nucleo.llm.fast_client import FastClient
        await FastClient().complete(
            [{"role": "system", "content": _in_his_lang(_SYS + _pk.offer_line(outcome)).format(wid=wid, actions=_actions_block(manifest), card=card)},
             {"role": "user", "content": f"Operator: «{operator_text.strip()[:400]}»\n"
                                         f"Your reply (no call): «{(reply or '').strip()[:300]}»"
                                         + conversation(window)}],
            spec=spec, max_tokens=300, tools=[tool, *_pk.offer_tools(outcome)], no_thinking=True,
            on_tool_call=lambda name, args: _pk.took(outcome, name, args) or got.append((name, args if isinstance(args, dict) else {})))
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
            if not _rg.recipient_was_named(wid, action, payload, operator_text, window):
                _note(wid, "envío a alguien que nadie nombró", action=action[:40])
                continue
            if not _rg.list_was_named(payload, operator_text, window, digest):   # «Favoritos» nobody said
                _note(wid, "lista que nadie nombró", action=action[:40])
                continue
            return _pk.called(outcome, {"widget_id": wid, "action": action, "payload": payload})
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


_SYS_AFTER_READ = (
    "You are the brain of a voice assistant. The operator gave an ORDER on the card «{wid}». To "
    "fulfil it you first read the card «{read}» — this is what it holds:\n{block}\n\nNow fulfil the "
    "order: make the `widget_data` call with widget_id «{wid}», one of its declared actions and the "
    "payload taken from his words and from what you just read (a message is written by you; a person "
    "is named as he said it). If his sentence does not ask for anything on «{wid}», call nothing. "
    "Write any text you put in the payload (a note, a message, a title) in the OPERATOR's language, "
    "as he said it.\n\nActions of «{wid}»:\n{actions}{card}"
)


_SYS_AFTER_SEARCH = (
    "You are the brain of a voice assistant. The operator's turn asked for a FACT and an ORDER on the card "
    "«{wid}». You searched the web for the fact and answered:\n«{answer}»\n\nNow fulfil the order: make the "
    "`widget_data` call with widget_id «{wid}», one of its declared actions and the payload taken from his "
    "words and from what you found (a date you found is written as YYYY-MM-DD). If his sentence does not ask "
    "for anything on «{wid}», call nothing. Write any text you put in the payload (a note, a title) in the "
    "OPERATOR's language, as he said it.\n\nActions of «{wid}»:\n{actions}{card}"
)


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
        try:
            from nucleo.flash import widget_read as _wr
            digest = str(_wr.read(wid) or "").strip()[:1500]
        except Exception:  # noqa: BLE001
            digest = ""
        card = (_CARD.format(wid=wid, digest=digest) if digest else "") + _days()
        got: list[tuple[str, dict]] = []
        from nucleo.flash import refusal_line as _rline, repair_grounding as _rg
        from nucleo.llm.fast_client import FastClient
        await FastClient().complete(
            [{"role": "system", "content": _SYS_REFUSAL.format(
                wid=wid, action=action, payload=json.dumps(payload or {}, ensure_ascii=False)[:300],
                why=str(why or "")[:300], actions=_actions_block(manifest), card=card, lang=_session_lang())},
             {"role": "user", "content": f"Operator: «{operator_text.strip()[:400]}»"
                                         + (f"\nWhat you just told him: «{said.strip()[:300]}» — if you named which one there, "
                                            f"the correction is THAT one." if (said or "").strip() else "")}],
            spec=spec, max_tokens=_rline.correction_budget(manifest, action), tools=[tool], no_thinking=True,
            on_tool_call=lambda name, args: got.append((name, args if isinstance(args, dict) else {})))
        for name, args in got:
            if name != "widget_data" or not _same_card(str(args.get("widget_id") or ""), wid):
                continue
            if str(args.get("action") or "").strip() != action:
                _note(wid, "la corrección cambiaba de acción", action=str(args.get("action") or "")[:40])
                continue
            fixed = args.get("payload") if isinstance(args.get("payload"), dict) else {}
            if fixed and fixed != (payload or {}) and _rg.refusal_fix_grounded(wid, action, fixed, operator_text, digest):
                return {"widget_id": wid, "action": action, "payload": fixed}
        _note(wid, "el rechazo no tiene corrección", action=action)
        return None
    except Exception:  # noqa: BLE001 — a repair must never take down a live turn
        return None

from nucleo.acts.repair_after_lookup import (  # noqa: E402,F401
    _tool_named, _is_view, call_after_read, same_card_order_after_read, after_a_read, order_card_after_search,
    call_after_search, voice_after_search)
from nucleo.acts.repair_of_a_view import (  # noqa: E402,F401
    denies_the_act, words_shape, _tail, after_the_completion, after_the_repair, _answered_a_question,
    call_for_promise_or_order, call_for_repeated_view, _other_open_cards, _ignored_the_verdict, _verdict_hint,
    call_or_read_for_commission)
