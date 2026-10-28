"""Every errand one turn asks for either STARTS or is SAID not to have started (three-tasks-at-once, 2026-10-10).

A turn can carry several errands — «hazme un informe, búscame un monitor y móntame un juego» — and three doors
used to drop one of them without a word, each for a reason that is right on its own case:

  · the LISTING lane is skipped when the turn also escalated, because two workers on the SAME hunt race each other
    — and a DIFFERENT hunt (the monitor beside a report and a game) was dropped with it;
  · a turn whose yes/no resolved a parked errand cleared all of its escalations, because «it answers what is
    parked» — and an unrelated errand ordered in the same breath vanished;
  · the per-turn cap (the worker pool) dropped the fourth errand silently.

The rules are here, once, and both channels call them: a hunt that is not one of the escalations rides as one
more; what the answer resolved is taken out and the rest stays; what the pool cannot take is named back to him.
«Same errand» is the dedup's own yardstick (`matching.containment`), never a second one.
"""
from __future__ import annotations

#: Errands one turn may open — the worker pool's default width (`dispatch._max_parallel`), as before.
MAX_ERRANDS = 3


def same_errand(a: str, b: str) -> bool:
    """The dedup's measure: is the smaller set of content words inside the bigger one?"""
    from nucleo import matching
    wa, wb = matching.content_words(a), matching.content_words(b)
    return bool(wa and wb) and matching.containment(wa, wb) >= matching.SAME_ERRAND


#: Our own wrapper around a listing hunt. Its words are the ENGINE's, not his: «real», «price», «link» are in every
#: listing errand's goal, so «autonomía real y precio» named the monitor hunt while he asked about the car report
#: (three-tasks-at-once ES, 2026-10-11 02:04 — five turns with monitor rows glued to answers about the report).
LISTING_PREFIX = "Find real marketplace listings for: "


def listing_errand(listing: dict) -> str:
    """A `search_listings` call written as an errand for a worker: the hunt and the bounds he gave."""
    q = str((listing or {}).get("query") or "").strip()
    bounds = [f"max price {listing['price_max']}" if listing.get("price_max") not in (None, "") else "",
              f"min price {listing['price_min']}" if listing.get("price_min") not in (None, "") else "",
              f"condition: {listing['condition']}" if str(listing.get("condition") or "").strip() else ""]
    bounds = [b for b in bounds if b]
    return (f"{LISTING_PREFIX}{q}" + (f" ({'; '.join(bounds)})" if bounds else "")
            + ". Put the real candidates, with price and link, on the results sheet.") if q else ""


def ask_of(request: str) -> str:
    """What HE asked for, out of an errand's goal: a listing hunt is its query, without our wrapper and bounds.
    Any other goal is returned whole — those are written from his words (`errand_title`'s rule)."""
    r = str(request or "")
    if not r.startswith(LISTING_PREFIX):
        return r
    q = r[len(LISTING_PREFIX):]
    for cut in (" (", ". Put the real"):
        q = q.split(cut, 1)[0]
    return q.strip()


def listing_rides(listing: dict | None, requests: list[str]) -> str:
    """The listing hunt as ONE MORE errand when the turn escalated others and it is none of them; "" otherwise.

    Alone, the hunt is the fast lane's (`listing_turn.voice_turn`). Beside an escalation of the SAME hunt it stays
    dropped — two workers racing one hunt is the defect the skip was written for."""
    reqs = [r for r in (requests or []) if str(r or "").strip()]
    if not listing or not reqs:
        return ""
    q = str(listing.get("query") or "").strip()
    if not q or any(same_errand(q, r) for r in reqs):
        return ""
    return listing_errand(listing)


def beside_an_answer(resolved: str, requests: list[str], *, declined: bool = False) -> list[str]:
    """The turn's escalations that are NOT the errand its yes/no just resolved — those are still orders. After a
    «no» to a build, the same errand asked without the build is one of them (`declined_build`)."""
    from nucleo.turn import declined_build
    return [r for r in (requests or []) if r and not (resolved and same_errand(r, resolved)
                                                      and not (declined and declined_build.still_wanted(r, resolved)))]


def keep_beside_an_answer(escalate_req: dict, resolved: str | None, *, declined: bool = False) -> None:
    """The voice turn's `escalate_req`, cut down to what the answer did not resolve (the confirmed errand is
    relaunched by `resolve_confirm`; re-escalating it would open it twice). `resolved=None` — an answer that names
    no errand, a click held in the browser — keeps today's rule: the turn opens nothing new."""
    rest = ([] if resolved is None
            else beside_an_answer(resolved, [escalate_req.get("v"), *(escalate_req.get("more") or [])], declined=declined))
    escalate_req["v"], escalate_req["more"] = (rest[0] if rest else None), rest[1:]


def not_started_line(dropped: list[str]) -> str:
    """The sentence that names, in his language, the errands this turn did NOT start. "" when none."""
    items = [str(d).strip().rstrip(".")[:90] for d in (dropped or []) if str(d or "").strip()]
    if not items:
        return ""
    from i18n import langs as _lg
    return _lg.current_language().errands_not_started.format(what="; ".join(f"«{i}»" for i in items))


def status_owed(operator_text: str, brief) -> str:
    """Where each live errand is, in one sentence — owed when the turn asked to be TOLD and the model went mute.

    EN twin (sandbox 20261010-145237-en): three errands live, «How's everything going?», the model called
    `send_to_worker` twice and said nothing, and our holding line answered «Alright, give me a moment to look into
    that» — an empty wait to a status question, with every errand's phase in the turn's own state. The line names
    each live errand by its label (its request when it has none yet) and its phase. "" when the verdict did not ask
    for words, or nothing is live — the caller then keeps its own line."""
    from nucleo.turn import brief as _tb
    if brief is None:
        return ""
    words, _i = _tb.read(brief, _tb.WORDS_KEY, "")
    kind, _k = _tb.read(brief, _tb.REQUEST_KEY, "")
    if words != "tell" and kind != "question":
        return ""
    from nucleo.turn import named_errand as _ne
    errands = _ne.known()
    live = [e for e in errands if not e["parked"]]
    # A question that NAMES an errand is about THAT errand (EN round 20:00: «the jump, did you make it higher?»
    # got the report's and the monitor's phases three times) — parked ones included, so «waiting on you» is said.
    # «How's everything going?» still asks about all of them, whatever else the sentence names.
    asked = [] if _ne.asks_about_all(operator_text) else _ne.named(operator_text, errands)
    if not (asked or live):
        return ""
    from i18n import langs as _lg
    items = [status_item(e, errand_state(e)) for e in asked or live]
    return _lg.current_language().errands_status.format(items="; ".join(items))


def status_item(e: dict, state: str) -> str:
    """One errand in a status sentence: its name QUOTED, as every line of ours names his errands («…»), so a title in
    another language («The Dark Side of the Moon») reads as the name it is, then where it stands."""
    from nucleo.turn import named_errand as _ne
    return f"«{_ne.spoken_name(e)}» — {state}"


def errand_state(e: dict) -> str:
    """Where ONE errand is, in his language: waiting on him, its own milestone note or phase, or «under way» — never
    a browser micro-step, our plumbing (card ids, the sheet's columns) or a note in another language."""
    from i18n import langs as _lg
    from nucleo.flash import speakable_note as _sn
    from nucleo.workers import progress as _progress
    lang = _lg.current_language()
    if e.get("waiting_on"):
        return lang.errand_waiting_on_you
    _ph = "" if _progress.is_mechanical(e.get("phase") or "") else str(e.get("phase") or "")   # a click is the card's
    said = [p.strip().rstrip("…. ") for p in (_ph, str(e.get("note") or ""))]
    return next((p for p in said if _sn.speakable(p, _lg.current_code(), strict=True)), "") or how_far(e, lang)


def how_far(e: dict, lang) -> str:
    """With no milestone to say, the FACTS that move between two asks — its plan step, or how long it has run —
    never the same fixed line (three-tasks-at-once EN, 2026-10-15: «under way, nothing new yet» for the game and
    the monitor, turn after turn, while both were working)."""
    done, total, secs = int(e.get("done") or 0), int(e.get("total") or 0), int(e.get("secs") or 0)
    if total and 0 < done < total:
        return lang.errand_step_of.format(done=done, total=total)
    return lang.errand_running_for.format(min=secs // 60) if secs >= 60 else lang.errand_under_way


def promised_refinement(operator_text: str, spoken: str, brief=None) -> str:
    """The LIVE errand a promise with no tool call is about — the one his sentence names most — or "".

    three-tasks-at-once (ES, 2026-10-11 02:04): «¿y al juego le puedes poner monedas?» → «Voy con ello, le añado
    monedas» and no call at all; the promise backstops only re-escalate a web-looking order, so a refinement of a
    running errand was promised and dropped. Bounded on the consequence: his own words go to the errand they name,
    through the same injection `send_to_worker` uses. A parked errand is left to the confirmation gate, which folds
    the words into it. Whether an act was owed is the brief's verdict (`reply.owes_an_act`), never our words."""
    from nucleo.turn import reply as _reply
    if not _reply.owes_an_act(brief):
        return ""
    from nucleo.turn import our_question as _oq        # his answer to our phase's question is not for the errand
    operator_text = _oq.without_its_answer(operator_text, spoken)
    if not operator_text:
        return ""
    from nucleo.turn import named_errand as _ne
    top = _ne.strongest(operator_text)
    # a STARTING errand has no session to inject into yet: its id would resolve to whatever else is live
    return str(top["id"]) if top and not top["parked"] and not top.get("starting") else ""


def words_for(operator_text: str, spoken: str) -> str:
    """What of his sentence a live errand may hear: all of it, minus the answer to a question OUR phase asked
    (`our_question`, search-restaurant-occasion 2026-10-14). Both injection sites send this, never his raw turn."""
    from nucleo.turn import our_question as _oq
    return _oq.without_its_answer(operator_text, spoken, quiet=True)

