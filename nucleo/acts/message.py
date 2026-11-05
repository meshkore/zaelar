"""The message door (refactor2710-06 T-02): an act that LEAVES — a send, a reply, a forward — and when it may go.

One rule set for every channel the cards declare (mail, chat, the cluster through its own card):

  · **his order over a row he has SEEN is the yes** (V2-800, CRIT-C9): `held` / `ordered` / `confirmed` / `release`.
    A widget whose action delivers a held row exposes `held_row(action, payload)` in its data module; the turn's
    verdict must surely name that very act, and the ONE consent rule decides with `his_yes=True` (his standing «ask»,
    a missing fact, a doubt and the radius still stop). The act itself runs in a worker (V2-852 M2), so the turn
    records its reading over that row (`note_his_order`) and the worker's exit door reads it with no brief.
  · **who it goes to is never a doubt** (the operator, 2026-10-15): a send that names a WHO runs without a question
    only when that person is in HIS words, this turn or his recent ones — `is_his` / `unnamed_recipients`.
  · **a stranger's words are data** (V2-778 F4-33, CRIT-E12): with someone else's text in the context, a send runs
    without a question only when the verdict surely names it or his own words name its recipient — `needs_asking` /
    `asked_if_leaving`.
  · **the ordered act runs when the model only prepared it** (live bench E3): `ordered_instead` / `run_ordered`.
  · **a reply to someone else is a forward** (demo pass 110 E3): `forward_of` / `forward_instead` — read off the
    directory (exactly one person named, not the sender), never off phrasing.
"""
from __future__ import annotations

import time as _time

from loguru import logger

from nucleo.acts.message_names import TOK as _TOK, fold as _fold, names_someone_else as _names_someone_else

#: How sure the verdict's ACTION reading must be to back a send with a stranger's text in the context.
SURE = 0.9
#: How far back his words still name the person a send goes to: the conversation's own span.
RECENT_S = 900.0
_RECIPIENT_KEYS = ("to", "contact", "recipient", "chat")
#: The payload keys a send names its person under — read by whoever renders a send's echo for a chosen person.
RECIPIENT_KEYS = _RECIPIENT_KEYS


def _note(what: str) -> None:
    logger.debug(f"acts.message: {what}")


# ── the held row: his order over what he saw (`nucleo/acts/message_held.py`) ────────────────────────────────
from nucleo.acts.message_held import (  # noqa: E402,F401
    held, note_his_order, ordered, confirmed, release)


# ── whose recipient ────────────────────────────────────────────────────────────────────────────────────────

def is_his(recipient, texts, *, found: bool = False) -> bool:
    """THE reading of «did he name this recipient» (V2-849 D5), one for every door that asks it — Flash's send gate
    and a worker's act in his name (`on_his_behalf.worker_question`, V2-851 F2):

      · the recipient — a name as a contiguous phrase, a handle or an address literally, a phone by its digits — is in
        his words (`on_his_behalf.named`, the worker door's yardstick);
      · or ONE word of his words that the recipient's name carries leads, through the directory, to this person and to
        nobody else: «quinn» for `quinn@example.com` (demo pass 141), «Raquel» once one Raquel is his.

    A shared word alone is not naming when the directory gives that word to OTHER people: «mamá» shares a word with
    «Francisco Vecino Mama» and thirteen rows carry it — so the send asks. Somebody the directory does not hold at all
    is named by a shared word, as before («invite paco» for a guest «Paco Pérez»): there is nobody to confuse him with
    — unless the recipient was `found` by the agent rather than composed from his words (a worker's search result:
    «Fontanero Urgencia Madrid» shares «fontanero» and «madrid» with «necesito un fontanero… Madrid centro»). A name
    the agent found and his directory does not hold is his only when his words name it whole.
    Unreadable → not named (the send asks)."""
    from nucleo import on_his_behalf as _ob
    said = [str(t or "") for t in texts or () if str(t or "").strip()]
    if _ob.named(str(recipient or ""), said):
        return True
    words = set()
    for t in said:
        words |= set(_TOK.findall(_fold(t)))
    try:
        from widgets import directory
        rows = directory.resolve(str(recipient or ""), tolerant=False)
        names = {_fold(n) for c in rows for n in directory.names(c)} or {_fold(recipient)}   # V2-850: every name
        ids = {str(c.get("id") or "") for c in rows if c.get("id")}
        # V2-854 — his words naming somebody ELSE whole outrank a word they share with this person: with winners by
        # margin, «Pablo» alone can lead to his favorite «Pablo FF» while he said «Pablo Hernandez». A run of two or
        # three of his words that the directory gives to one other person is not naming this one.
        if _names_someone_else(said, ids, directory):
            return False
        for tok in {t for n in names for t in _TOK.findall(n)} & words:
            hits = directory.resolve(tok, tolerant=False)
            if (len(hits) == 1 and _fold(hits[0].get("name")) in {_fold(c.get("name")) for c in rows} | names) \
                    or (not hits and not rows and not found):
                return True
        # V2-852 — a word of HIS that the directory leads to this person and nobody else names them, whether the
        # directory knows that word as a name or as one he gave (an alias, «Raquel» → «Rakel Karó»): one resolver
        # answers «who did he mean» for the send and for this door
        for tok in {t for t in words if len(t) >= 3}:
            hits = directory.resolve(tok, tolerant=False)
            if ids and len(hits) == 1 and str(hits[0].get("id") or "") in ids:
                return True
        return False
    except Exception as e:  # noqa: BLE001
        _note(f"directory unread ({e!r})")
        return False


def his_recipient(widget_id: str, action: str, payload, said: str, emit=None):
    """`payload` with `contact` put back in HIS word when the call names somebody his words never did (V2-850).

    Measured on a cloud session (2026-11-04): «manda un mensaje a raquel» — four Raquels in his directory — became
    `draft {contact: "Rakel Karó"}`, a chat name nobody said. The card resolved it, never asked «which Raquel?», and
    the ask-once memory (V2-849) never ran. The contact a card receives is the name «as he said it» (its manifest);
    when the model swapped it, the word of his sentence that names people goes back in, so the card asks among them.
    A `relation` call («mamá») is his word already; a recipient his words do name is untouched. Never raises."""
    if not isinstance(payload, dict) or str(payload.get("relation") or "").strip():
        return payload
    try:   # V2-851 F2e: read the call as the card will — `name` for `contact` slipped past this reader, and sent
        from widgets import contract
        payload = contract.fold_aliases(str(widget_id or "").split("::", 1)[0], action, payload)
    except Exception as e:  # noqa: BLE001
        _note(f"aliases unread ({e!r})")
    who = str(payload.get("contact") or "").strip()
    if not who or "@" in who or not str(said or "").strip() or is_his(who, [said]):
        return payload
    try:
        from widgets.contactos import data as _ct
        rows = _ct.people_named(said, limit=8)
    except Exception as e:  # noqa: BLE001
        _note(f"people unread ({e!r})")
        return payload
    words = _TOK.findall(_fold(said))
    counts = {w: sum(w in _TOK.findall(_fold(r.get("name"))) for r in rows) for w in words}
    word = max(counts, key=counts.get, default="")
    if not word or not counts[word]:
        return payload
    if callable(emit):
        emit("brain", "🛑 destinatario que él no nombró — vuelve su palabra y la tarjeta pregunta cuál",
             text=f"{widget_id}:{action} «{who}» → «{word}»", role="system",
             extra={"cat": "flash", "id": widget_id, "model": action, "was": who, "his": word})
    return {**payload, "contact": word}


def asked_which(reply: str, said: str) -> bool:
    """Did our reply ask him WHICH of the people his word names? Then it is a question, not a promise left unkept, and
    his answer is remembered like the card's own question (V2-850, `directory.asked`).

    Measured on his engine (2026-11-04): «manda un mensaje a raquel…» → «which Raquel — Salvador, Jofre, or Diaz?»,
    no call, and the turn end added «I haven't done it — I couldn't carry it out from here»; his answer would then
    have been forgotten, because only the send door recorded a question. Read off the directory, never off phrasing:
    the reply names two or more of the rows his word reaches, each by a word of its own name. Never raises."""
    if not str(reply or "").strip() or not str(said or "").strip():
        return False
    try:
        from widgets.contactos import data as _ct
        rows = _ct.people_named(said, limit=8)
        if len(rows) < 2:
            return False
        words = _TOK.findall(_fold(said))
        counts = {w: sum(w in _TOK.findall(_fold(r.get("name"))) for r in rows) for w in words}
        word = max(counts, key=counts.get, default="")
        if not word or counts[word] < 2:
            return False
        said_back = set(_TOK.findall(_fold(reply)))
        named = [r for r in rows if (set(_TOK.findall(_fold(r.get("name")))) - {word}) & said_back]
        if len(named) < 2:
            return False
        from widgets import directory
        directory.asked(word, named)
        return True
    except Exception as e:  # noqa: BLE001
        _note(f"which-question unread ({e!r})")
        return False


def _named_by_him(payload, said: str) -> bool:
    """Is EVERY recipient this send carries named in his own words? One only the stranger's text names is not."""
    if not isinstance(payload, dict) or not str(said or "").strip():
        return False
    found = False
    for k in _RECIPIENT_KEYS:
        v = str(payload.get(k) or "").strip()
        if not v:
            continue
        if not is_his(v, [said]):
            return False
        found = True
    return found


def unnamed_recipients(widget_id: str, action: str, payload, said: str = "") -> list[str]:
    """The recipients of this act his words (this turn or his last `RECENT_S`) do not name — [] when it names nobody
    (a reply goes to whoever wrote) or every one is his."""
    from nucleo import his_words, on_his_behalf as _ob
    who = _ob.who_of(widget_id, action, payload)
    if not who:
        return []
    texts = [str(said or "")] + his_words.since(_time.time() - RECENT_S)
    return [w for w in who if not is_his(w, texts)]


def _surely_named(brief, sure: float = SURE) -> bool:
    try:
        from nucleo.turn import brief as _tb
        _c, info = _tb.read(brief, _tb.TARGET_KEY, "", min_confidence=sure)
        return bool(info is not None and info.get("used"))
    except Exception as e:  # noqa: BLE001
        _note(f"brief unread ({e!r})")
        return False


def needs_asking(brief, widget_id: str, action: str, *, payload=None, said: str = "", stranger=None) -> bool:
    """True when the send goes to somebody his words never named, or when a stranger's words are in the context and
    neither the verdict surely backs THIS send nor his own words name its recipient. `stranger` is the context's
    taint when the caller holds its own (a worker session, V2-851 F2); None reads Flash's window."""
    try:
        if confirmed(widget_id, action, payload, brief):
            return False
        if unnamed_recipients(widget_id, action, payload, said):
            return True
        from nucleo import untrusted as _u
        if not (_u.present() if stranger is None else stranger):
            return False
        from nucleo.flash import direct_action as _da
    except Exception as e:  # noqa: BLE001 — an unreadable rule asks
        _note(f"send rule unread ({e!r})")
        return True
    wid, name = _da.from_brief(brief)
    if wid and name == action and _da._base_of(wid) == _da._base_of(widget_id) and _surely_named(brief):
        return False
    return not _named_by_him(payload, said)


def asked_if_leaving(mode, brief, widget_id: str, action: str, *, emit=None, payload=None, said: str = "",
                     stranger=None):
    """`mode`, or CONFIRM when this FAST act leaves and `needs_asking`. Never raises: an unreadable rule asks."""
    from widgets import actions as _wa
    try:
        from nucleo.flash import frontend as _fe
        if mode != _wa.FAST or not _fe.at_least_sensitive(widget_id, action):
            return mode
        if not needs_asking(brief, widget_id, action, payload=payload, said=said, stranger=stranger):
            return mode
    except Exception as e:  # noqa: BLE001
        _note(f"leave gate unread ({e!r})")
    if callable(emit):
        emit("brain", "🛑 acto que sale fuera sin un destinatario que él nombrara (o con texto de un tercero) — se pregunta",
             text=f"{widget_id}:{action}", role="system", extra={"cat": "flash", "id": widget_id, "model": action})
    return _wa.CONFIRM


from nucleo.acts.message_repair import (  # noqa: E402,F401 — the model's call that falls short of his order
    forward_instead, forward_of, ordered_instead, run_ordered)
