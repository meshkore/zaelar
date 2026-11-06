"""nucleo/request/send_task_words.py — what his words alone resolve of a send, and the send as the worker's data.

The third piece of `nucleo/request/send_task`: `hold` turns our own prose question about a card's leaving act into a
send task's question (`ask_outside_door.held`); `payload_from_words` gives the person his word names for an act the
turn never called; `brief_block` hands a Brain Worker that takes a send row its slots as data, with the one call that
sends — resources, never a script.
"""
from __future__ import annotations

from nucleo.request import base, note
from nucleo.request.send_task import NONE, _question, _schedule, artefact, missing, retain


def payload_from_words(wid: str, action: str, said: str) -> dict:
    """What his words alone resolve of the act's slots: the person, as the word of his sentence that names exactly
    one of his people (`contactos.people_named`, the rows the people block showed) — {} when nothing resolves."""
    from nucleo.workers import exit_slots
    slots = exit_slots.declared(base(wid), action)
    who_key = next((str(d.get("key") or s) for s, d in slots.items() if d.get("from") == "his_words"), "")
    if not who_key:
        return {}
    word, rows = his_word_for_people(said)
    return {who_key: word} if word and len(rows) == 1 else {}


def his_word_for_people(said: str) -> tuple[str, list]:
    """(the word of his sentence that names people, the directory rows it reaches) — the same reading
    `message.his_recipient` makes; ("", []) when his words name nobody."""
    try:
        from nucleo.acts.message_names import TOK, fold
        from widgets.contactos import data as _ct
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
