"""nucleo/acts/card_pass.py — the pieces every bounded pass over ONE card's declared actions shares: what the card
holds, the conversation so far, the card's actions as a block, the `widget_data` tool, the days lookup, the canvas
gate and the timeline line of a pass that gave no call. Moved out of `nucleo/flash/act_repair.py` when V2-851 F2
retired the promise repair; the passes that read them stay (`repair_after_lookup`, `repair_of_a_view`) until F5.
"""
from __future__ import annotations

import json
import re

from nucleo.flash.repair_grounding import in_his_lang, session_lang  # noqa: F401 — pass 102/141


def denies_the_act(spoken: str) -> bool:
    """Do the words say the act cannot be done? Deterministic and narrow: a can't/there's-no shape."""
    return bool(_DENIED_RE.search(spoken or ""))


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


def note(wid: str, why: str, **extra) -> None:
    """The pass ran and gave NO call — said on the timeline, because a silent None here was a turn that
    claimed an act nobody could find (V2-773 audit)."""
    try:
        from voice.observer import emit
        emit("brain", "🔁 la segunda pasada no dio llamada", text=f"{wid}: {why}", role="system",
             extra={"cat": "flash", "widget": wid, "why": why, **extra})
    except Exception:  # noqa: BLE001
        pass


def canvas_holds_the_turn(brief, operator_text: str, wid: str) -> bool:
    """A second pass asks this before asking the model for a card's action (`verdict_card.inner_op_may_run`)."""
    from nucleo.flash import verdict_card as _vc
    held = not _vc.inner_op_may_run(brief, operator_text, builds_payload=True)
    return held and (note(wid, "a sure canvas gesture owns the turn — no inner op") or True)


def actions_block(manifest: dict) -> str:
    rows = []
    for name, spec in (manifest.get("actions") or {}).items():
        spec = spec if isinstance(spec, dict) else {}
        pay = spec.get("payload") if isinstance(spec.get("payload"), dict) else {}
        rows.append(f"- {name}: {str(spec.get('desc') or '')[:200]}"
                    + (f" · payload {json.dumps(pay, ensure_ascii=False)[:220]}" if pay else ""))
    return "\n".join(rows)


def widget_data_tool() -> dict | None:
    try:
        from nucleo.flash import router_catalog as _rc
        return next((t for t in _rc.TOOLS if t.get("function", {}).get("name") == "widget_data"), None)
    except Exception:  # noqa: BLE001
        return None


def tool_named(name: str) -> dict | None:
    try:
        from nucleo.flash import router_catalog as _rc
        return next((t for t in _rc.TOOLS if t.get("function", {}).get("name") == name), None)
    except Exception:  # noqa: BLE001
        return None


# The words that DENY an act (`order_card_after_search`: an answer that refuses an order the brief names); English and
# Spanish.
_DENIED_RE = re.compile(
    r"\b(?:can'?t|cannot|can not|couldn'?t|unable to|not something i can|no way (?:to|i can)|there(?:'s| is) no|"
    r"there(?:'s| is)n'?t (?:a|any)|isn'?t (?:a|any|something)|"
    r"no puedo|no es algo que pueda|no hay (?:forma|manera|ning[uú]n)|no tengo (?:forma|manera)|no existe)\b", re.I)



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


def days() -> str:
    """Today and the next seven days, the same lookup the turn's prompt carries (`prompt.live_state`): «el martes
    que viene» is a LOOKUP, never arithmetic (V2-781 pair 7: the correction picked the 20th for the 13th)."""
    import time as _t
    now = _t.time()
    days = "; ".join(f"{_t.strftime('%A', _t.localtime(now + i * 86400)).lower()} "
                     f"{_t.strftime('%Y-%m-%d', _t.localtime(now + i * 86400))}" for i in range(0, 8))
    return f"\n\nToday first, then the next days: {days}."
