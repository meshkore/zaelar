"""One sentence that names SEVERAL of his errands is split per errand: each part reaches its own, and the reply
says what was done for each (three-tasks-at-once EN, 2026-10-14 02:44, sandbox 023306-en; nodes 2.643/2.644).

Two turns of the same round, both with a healthy chain:

  · «ok nice. ping me when the game's ready to try, and send the report when it's done. for the monitor used is
    fine, just make sure it's got hdmi at least» — the model called nothing; the promise repair asked the late
    catalogue which card the order was for, got «mensajeria» (0.84), and wrote «Requisitos del monitor: al menos
    HDMI.» as a messaging DRAFT. The monitor hunt never heard of HDMI, and the reply was a bare «Done.» — «wait done
    with what exactly?».
  · «those are too small, need at least 27 inches. hows the game coming?» — the model did send the 27" floor to
    the monitor's worker and said nothing; the status line answered the question alone («Here's where everything
    stands: Build a Super Mario-style … — under way»), so the refinement that DID land was never acknowledged.

The rule is a mechanism over the consequence, not a reading of intent: his sentence is cut on its own punctuation
(sentences, then commas and dashes when one sentence names more than one errand), each part goes to the errand its
words name (`named_errand.named`, the attribution's yardstick — a part that names none rides with the part before
it), a statement reaches that errand's LIVE worker through the same injection `send_to_worker` uses, a question is
answered with that errand's state, and the reply names every errand it has not already named. One errand named →
nothing here: that is `errands_of_a_turn.promised_refinement`'s case.
"""
from __future__ import annotations

import re
import time

from loguru import logger

_SENTENCE = re.compile(r"(?<=[.!?;…])\s+|\n+")
_CLAUSE = re.compile(r"\s*,\s*|\s*[—–]\s*|\s+-\s+")
#: How long one routing stays the answer to «did this turn route his words?» — the turn's own span.
FRESH_S = 90.0
_LAST: dict = {"text": "", "t": 0.0, "parts": [], "said": True}
_SENT: list[tuple[float, str]] = []
#: A send and the status line of the same turn are seconds apart; a send older than this belongs to another turn.
SENT_S = 30.0


def _asks(words: str) -> bool:
    w = str(words or "").strip()
    return w.endswith("?") or w.startswith("¿")


def parts(text: str, errands: list[dict]) -> list[dict]:
    """[{errand, words, asks}] — his sentence cut per errand, in his order. A part names exactly one errand; a clause
    that names several is nobody's (and so is what follows it, until a clause names one again)."""
    from nucleo.turn import named_errand as _ne
    out: list[dict] = []
    for sentence in (s.strip() for s in _SENTENCE.split(str(text or "").replace("...", "…"))):
        if not sentence or not _ne.named(sentence, errands):
            continue
        last = None
        for clause in (c.strip() for c in _CLAUSE.split(sentence)) if len(_ne.named(sentence, errands)) > 1 else [sentence]:
            hits = _ne.named(clause, errands) if clause else []
            if len(hits) > 1:            # «el informe hasta 30.000 y el monitor hasta 150»: whose is which is unsaid
                last = None
                continue
            last = hits[0] if hits else last
            if last is None or not clause:
                continue
            if out and out[-1]["errand"] is last and out[-1]["sentence"] is sentence:
                out[-1]["words"] += f", {clause}"
            else:
                out.append({"errand": last, "words": clause, "sentence": sentence})
    for p in out:
        p["asks"] = _asks(p["words"])
    return out


def _what_was_done(errand: dict, asks: bool) -> str:
    if asks:
        return "asked"
    if errand.get("parked"):
        return "parked"
    if errand.get("ended"):
        return "ended"
    return "starting" if errand.get("starting") else "passed"


def route(operator_text: str) -> list[dict]:
    """Route a sentence naming ≥2 of his errands, part by part; the parts, or [] when it names fewer. Idempotent
    over the same words within `FRESH_S` (both channels' doors may ask). Never raises."""
    text = str(operator_text or "").strip()
    if not text:
        return []
    now = time.monotonic()
    if _LAST["text"] == text and now - _LAST["t"] <= FRESH_S:
        return list(_LAST["parts"])
    out: list[dict] = []
    try:
        from nucleo.turn import named_errand as _ne
        ps = parts(text, _ne.known(with_finished=True))
        if len({str(p["errand"].get("id")) for p in ps}) >= 2:
            from nucleo import dispatch as _d
            for p in ps:
                p["did"] = _what_was_done(p["errand"], p["asks"])
                if p["did"] == "passed":
                    _d.inject_soon(str(p["errand"]["id"]), p["words"])
            out = ps
            _emit(out)
    except Exception as e:  # noqa: BLE001 — the turn goes on with today's doors
        logger.warning(f"split_by_errand: his sentence was not routed per errand — {type(e).__name__}: {e}")
        out = []
    _LAST.update(text=text, t=now, parts=out, said=not out)
    return list(out)


def routed(operator_text: str) -> bool:
    """Did his sentence go out part by part? (routes it on the first ask)."""
    return bool(route(operator_text))


def holds_the_repair(spoken: str, operator_text: str) -> bool:
    """The voice promise repair does not run: the reply ASKS him for the detail it needs (V2-534), or his sentence
    about several errands already went part by part — a card repair would put one errand's words on a card."""
    from nucleo.flash import router as _router
    return _router.asks_for_missing_detail(spoken) or routed(operator_text)


def each_line(spoken: str) -> str:
    """The sentence the reply still owes after a per-errand routing — one item per errand his words named that
    `spoken` does not already name; "" when nothing is owed. Said ONCE per routing."""
    if _LAST["said"] or time.monotonic() - _LAST["t"] > FRESH_S:
        return ""
    _LAST["said"] = True
    from i18n import langs as _lg
    from nucleo.turn import errands_of_a_turn as _eot, named_errand as _ne
    lang = _lg.current_language()
    bare = _is_bare(spoken, lang)
    items, seen = [], set()
    for p in _LAST["parts"]:
        e = p["errand"]
        if str(e.get("id")) in seen or (not bare and _ne.named(spoken, [e])):
            continue
        seen.add(str(e.get("id")))
        state = {"passed": lang.errand_part_passed, "ended": lang.errand_part_done,
                 "parked": lang.errand_waiting_on_you, "starting": lang.errand_under_way}.get(p["did"]) \
            or _eot.errand_state(e)
        items.append(f"{_ne.spoken_name(e)} — {state}")
    return lang.errands_each.format(items="; ".join(items)) if items else ""


def each_said(spoken: str) -> str:
    """`spoken` with the per-errand sentence it owes; a bare ack («Done.») is REPLACED — it said nothing of any."""
    line = each_line(spoken)
    if not line:
        return spoken
    from i18n import langs as _lg
    return line if _is_bare(spoken, _lg.current_language()) else f"{str(spoken).strip()} {line}"


def _is_bare(spoken, lang) -> bool:
    s = str(spoken or "").strip()
    return not s or s in set(lang.acks) | set(lang.data_acks) | {lang.data_ack}


# ── a refinement the model sent itself, beside a status question (the second turn above) ─────────────────────

def note_sent(which: str) -> None:
    """A `send_to_worker` of this turn, so the status line can name the errand it reached (voice executor)."""
    _SENT.append((time.monotonic(), str(which or "")))
    del _SENT[:-8]


def _sent_names() -> list[str]:
    """The errands the turn's sends reached — inside `SENT_S`, a turn's own span — consumed on read. Scoped by the
    clock, not the trace: a send to ONE worker adopts that worker's trace (`_t_send_to_worker`)."""
    now = time.monotonic()
    whiches = [w for t, w in _SENT if now - t <= SENT_S]
    _SENT.clear()
    names: list[str] = []
    try:
        from nucleo import dispatch as _d
        from nucleo.turn import named_errand as _ne
        for which in whiches:
            for tid in _d.resolve_sessions(which or "todo") or []:
                rec = _d.get_record(tid)
                n = _ne.spoken_name({"label": getattr(rec, "label", ""), "title": getattr(rec, "title", ""),
                                     "request": getattr(rec, "goal", "")})
                if n and n not in names:
                    names.append(n)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"split_by_errand: refined errands unreadable — {type(e).__name__}: {e}")
    return names


def status_with_refined(operator_text: str, brief, refined: list[str] | None = None) -> str:
    """The status line a question owes, plus the errands this turn's own `send_to_worker` reached that the line does
    not name — «Here's where everything stands: the game — under way. Done — I've passed that on to «the monitor»».
    `refined=None` reads the voice executor's ledger (`note_sent`). "" when no status is owed."""
    from nucleo.turn import errands_of_a_turn as _eot
    status = _eot.status_owed(operator_text, brief)
    names = _sent_names() if refined is None else list(refined or [])
    if not status:
        return ""
    extra = [n for n in names if n and n.lower() not in status.lower()]
    if not extra:
        return status
    from i18n import langs as _lg
    return f"{status} {_lg.current_language().errand_refined.format(what='; '.join(f'«{n}»' for n in extra[:3]))}"


def forget() -> None:
    _LAST.update(text="", t=0.0, parts=[], said=True)
    _SENT.clear()


def _emit(ps: list[dict]) -> None:
    try:
        from voice.observer import emit
        emit("brain", "🧩 one sentence, several errands — each part to its own", role="system",
             extra={"cat": "flash", "parts": [{"to": str(p["errand"].get("id")), "did": p["did"],
                                               "words": p["words"][:80]} for p in ps[:6]]})
    except Exception as e:  # noqa: BLE001
        logger.debug(f"split_by_errand: emit failed — {e}")
