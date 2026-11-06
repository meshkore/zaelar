"""nucleo/request/send_task_words.py — what his words alone resolve of a send, and the send as the worker's data.

The third piece of `nucleo/request/send_task`: `hold` turns our own prose question about a card's leaving act into a
send task's question (`ask_outside_door.held`); `payload_from_words` gives the person his word names for an act the
turn never called; `brief_block` hands a Brain Worker that takes a send row its slots as data, with the one call that
sends — resources, never a script.
"""
from __future__ import annotations

from nucleo.request import base, note
from nucleo.request.send_task import NONE, _question, _schedule, artefact, missing, retain


def payload_from_words(wid: str, action: str, said: str, dictated: str = "") -> dict:
    """What his words alone resolve of the act's slots: the person, as the word of his sentence that names exactly
    one of his people (`contactos.people_named`, the rows the people block showed) — {} when nothing resolves."""
    from nucleo.workers import exit_slots
    slots = exit_slots.declared(base(wid), action)
    who_key = next((str(d.get("key") or s) for s, d in slots.items() if d.get("from") == "his_words"), "")
    if not who_key:
        return {}
    word, rows = his_word_for_people(said, dictated)
    return {who_key: word} if word and len(rows) == 1 else {}


def without(said: str, dictated: str) -> str:
    """His sentence without the words he DICTATED (the run `send_task.his_text` matches, in order): the words that may
    name the person. Measured live (2026-11-06): «send Andrew an email saying: test six…» resolved the contact «test
    test» from the dictated text and the mail went to a stranger. Folded tokens; `said` itself when nothing is cut."""
    from nucleo.acts.message_names import TOK, fold
    have = TOK.findall(fold(str(said or "")))
    want = TOK.findall(fold(str(dictated or "")))
    if not want:
        return str(said or "")
    # the LAST occurrence of the run: the dictated text closes the order («…saying: <text>»)
    for start in range(len(have) - len(want), -1, -1):
        if have[start:start + len(want)] == want:
            return " ".join(have[:start] + have[start + len(want):])
    keep, i = [], 0                              # a run with gaps (a model trims «uh»): drop its matched tokens
    for tok in have:
        if i < len(want) and tok == want[i]:
            i += 1
            continue
        keep.append(tok)
    return " ".join(keep) if i == len(want) else str(said or "")


def his_word_for_people(said: str, dictated: str = "") -> tuple[str, list]:
    """(the word of his sentence that names people, the directory rows it reaches) — the same reading
    `message.his_recipient` makes, over his words WITHOUT what he dictated; ("", []) when they name nobody."""
    try:
        from nucleo.acts.message_names import TOK, fold
        from widgets.contactos import data as _ct
        said = without(said, dictated)
        rows = _ct.people_named(said, limit=8)
        words = TOK.findall(fold(said))
        counts = {w: sum(w in TOK.findall(fold(r.get("name"))) for r in rows) for w in words}
        word = max(counts, key=counts.get, default="")
        if not word or not counts[word]:
            return "", []
        return word, [r for r in rows if word in TOK.findall(fold(r.get("name")))]
    except Exception as e:  # noqa: BLE001
        note(e)
        return "", []


def hold(wid: str, leaves: list, said: str, question: str, *, brief=None) -> str:
    """Our own question about a card's leaving act, asked in prose (`ask_outside_door.held`), becomes a send task's
    question: the act is the card's send that declares slots, the person is his word (asked WHICH among the people
    it reaches when several), the words are asked when they are the slot that lacks. The `ask_id`, or "" when the
    card's acts declare no slots (the caller keeps its utterance)."""
    from nucleo.workers import exit_slots
    act = next((a for a in leaves if any(d.get("from") == "his_words"
                                          for d in exit_slots.declared(base(wid), a).values())), "")
    if not act:
        return ""
    word, rows = his_word_for_people(said)
    who_key = next(str(d.get("key") or s) for s, d in exit_slots.declared(base(wid), act).items()
                   if d.get("from") == "his_words")
    payload = {who_key: word} if word and len(rows) == 1 else {}
    uid = retain(wid, act, payload, said, reading=brief)
    if not uid:
        return ""
    art = artefact(uid)
    if len(rows) > 1:
        cands = [str(r.get("name") or "") for r in rows if r.get("name")]
        return _question(uid, art, "recipient", who_key, question, cands)
    slot, key = missing(art)
    if not slot:
        _schedule(uid)                     # nothing lacks: the question was the model's, not the task's
        return ""
    return _question(uid, art, slot, key, question)


def brief_block(uid: str) -> str:
    """The send's data for a Brain Worker that takes this row (the words to compose): each slot with its value and
    source, and the one call that sends — resources, never a script (`worker_brief.send_task_*`). '' off a send row."""
    art = artefact(uid)
    if not art or not art.get("slots"):
        return ""
    try:
        from i18n import langs
        head = str(langs.words("worker_brief.send_task_head", default="") or "")
        line = str(langs.words("worker_brief.send_task_slot", default="") or "")
        do = str(langs.words("worker_brief.send_task_do", default="") or "")
        if not (head and line and do):
            return ""
        import json
        payload = dict(art.get("payload") or {})
        rows = []
        for slot, d in art["slots"].items():
            v = payload.get(str(d.get("key") or slot))
            src = str(d.get("source") or NONE)
            rows.append(line.format(slot=slot, value=(v if v else "—"),
                                    source=("compose" if src == NONE and d.get("rule") == "composed" else src)))
        call = json.dumps({"widget_id": art.get("widget"), "action": art.get("action"),
                           "payload": {**payload, **{str(d.get("key") or s): "<…>" for s, d in art["slots"].items()
                                                     if not payload.get(str(d.get("key") or s))}}},
                          ensure_ascii=False)
        return "\n".join([head, *rows, do.format(call=call)])
    except Exception as e:  # noqa: BLE001
        note(e)
        return ""


#: The marks a model's output quotes his words between. Punctuation, not vocabulary (as `ask_outside_door`'s «?»).
_QUOTES = (('"', '"'), ("«", "»"), ("“", "”"), ("‘", "’"))


def quoted_his(said: str, model_text: str) -> str:
    """The words the model QUOTED that are his own (`send_task.his_text`): the longest quoted span of `model_text`
    that is a run of the words of `said`, in order — the dictated text, read off punctuation and his words, never off a
    verb. Measured on his engine (2026-11-06): the escalation «…with exactly this body: "prueba uno…"», the reply
    «Sending it now — …"test two of the linear send, ignore it"…», the answer turn «Sending "prueba tres, ignóralo"»:
    every time the model had the words and quoted them, and never called the door. "" when nothing quoted is his."""
    from nucleo.request.send_task import his_text
    text = str(model_text or "")
    best = ""
    for opening, closing in _QUOTES:
        start = 0
        while True:
            i = text.find(opening, start)
            if i < 0:
                break
            j = text.find(closing, i + 1)
            if j < 0:
                break
            span = text[i + 1:j].strip()
            if len(span) > len(best) and his_text(span, said):
                best = span
            start = j + 1
    return best


def identified(brief) -> tuple[str, str]:
    """The send the turn's brief surely identifies: `(card, leaving act)` — the `screen_action` verdict naming an act
    that leaves, else the `end_state` verdict naming a card's `<collection>` that a leaving act's declared end state
    fills (the send of that card: the act whose slots name his person). ("", "") when the brief names none."""
    try:
        from nucleo.circuit import spec as _spec
        from nucleo.turn import brief as _tb, verdicts
        from nucleo.workers import exit_slots
        from widgets import effects
        choice, info = verdicts.read(brief, _tb.TARGET_KEY, None)
        wid, _sep, act = str(choice or "").partition(":")
        if info and wid and act and effects.leaves(base(wid), act):
            return wid, act
        choice, info = verdicts.read(brief, _spec.END_KEY, None)
        wid, _sep, coll = str(choice or "").partition(":")
        if not (info and wid and coll) or str(choice) == "none":
            return "", ""
        from nucleo import on_his_behalf as _ob
        from nucleo.request.ending import leaving_acts
        cands = [a for a in leaving_acts(wid)
                 if str((_spec.template_of(wid, a) or {}).get("collection") or "") == coll
                 and any(d.get("from") == "his_words" for d in exit_slots.declared(wid, a).values())]
        # the card says which of them a bare order means (`"primary": true` on the action), else the first declared
        primary = [a for a in cands if (_ob._spec(wid, a) or {}).get("primary") is True]
        if primary or cands:
            return wid, (primary or cands)[0]
    except Exception as e:  # noqa: BLE001
        note(e)
    return "", ""


def from_verdict(wid: str, act: str, said: str, model_text: str, *, reading=None, emit=None,
                 asked_line: str = "", on_missing: str = "ask") -> tuple[str, str]:
    """The send the verdict identified, as a task — whatever the model did instead of calling the door (an escalation,
    a promise, a question in prose). Its slots come from his words (the person) and from the words the model quoted
    of his (the text). Returns `(uid, how)`: `run` (every slot his: the task runs), `asked` (one slot lacks: the row
    waits on its question, `asked_line` when the mouth already said one), `worker` (`on_missing="worker"`: a Brain
    Worker composes what lacks on this row), or ("", "") when the act declares no slots."""
    from nucleo.request import send_task
    text_key = next((str(d.get("key") or s) for s, d in send_task_slots(wid, act).items()
                     if d.get("rule" if "rule" in d else "from") == "composed"), "")
    quoted = quoted_his(said, model_text) if text_key else ""
    payload = dict(payload_from_words(wid, act, said, quoted))     # the person, never from the dictated words
    if quoted:
        payload[text_key] = quoted
    if on_missing == "worker":
        uid = retain(wid, act, payload, said, reading=reading, emit=emit)
        if not uid:
            return "", ""
        if missing(artefact(uid))[0]:
            return uid, "worker"
        send_task._said_started(uid, wid, act, artefact(uid))
        _schedule(uid)
        return uid, "run"
    word, rows = his_word_for_people(said, quoted)
    if word and len(rows) > 1:                      # his word names several people: the row asks WHICH, with them
        uid = retain(wid, act, payload, said, reading=reading, emit=emit)
        if not uid:
            return "", ""
        art = artefact(uid)
        who_key = next((str(d.get("key") or s) for s, d in art.get("slots", {}).items()
                        if d.get("rule") == "his_words"), "contact")
        q = asked_line or send_task._missing_line(art, "recipient")
        _question(uid, art, "recipient", who_key, q, [str(r.get("name") or "") for r in rows if r.get("name")])
        if not asked_line:
            send_task._said_asked(wid, act, q)
        return uid, "asked"
    uid = send_task.commission(wid, act, payload, said, reading=reading, emit=emit, asked_line=asked_line)
    if not uid:
        return "", ""
    return uid, ("asked" if missing(artefact(uid))[0] else "run")


def send_task_slots(wid: str, act: str) -> dict:
    from nucleo.workers import exit_slots
    return exit_slots.declared(base(wid), act)


def by_verdict(brief, *, said: str, model_text: str, escalate_req: dict, worker_acted: dict, replacing: bool = False,
               emit=None, on_missing: str = "ask", asked_line: str = "") -> tuple[str, str]:
    """THE reading of the turn's close and of its escalation: the send the brief identified becomes a send task unless
    the turn already retained one (the model called the door), addressed a live worker (his answer or words reached
    it, and nothing replaces it), or the brief names no send. `(uid, how)` as `from_verdict`, or ("", "")."""
    try:
        if (escalate_req or {}).get("send_task") or ((worker_acted or {}).get("v") and not replacing):
            return "", ""
        wid, act = identified(brief)
        if not wid:
            return "", ""
        from nucleo.turn import brief as _tb
        got = from_verdict(wid, act, said, model_text, reading=_tb.carried(brief) or None, emit=emit,
                           asked_line=asked_line, on_missing=on_missing)
        if got[0]:
            escalate_req["send_task"] = True
            if emit is not None:
                emit("brain", "📨 the send the verdict identified is its task — whatever the model did instead",
                     text=f"{wid}:{act} · {got[1]}", role="system",
                     extra={"cat": "flash", "task_id": got[0], "widget": wid, "act": act, "how": got[1]})
        return got
    except Exception as e:  # noqa: BLE001 — never takes the turn down; the model's own route stands
        note(e)
        return "", ""


def ends_asking(reply: str) -> bool:
    """Does the reply close on a question? Punctuation, not vocabulary (the same mark `ask_outside_door` reads)."""
    last = str(reply or "").rstrip().rstrip("»\"'”)")[-1:]
    return bool(last) and last in "?？؟"
