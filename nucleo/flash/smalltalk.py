"""The PHRASEBOOK: set phrases of a relationship, answered without a model (V2-674).

The operator's words, after a session in English (2026-09-11, sid fdd096a3): *«le digo hola y me dice un
segundo o check-in — ¿qué vas a chequear si te acabo de decir hola?»*. Measured in that session:

  · «Hello and good morning. How are you?» → a 3.4 s model call covered by «Let me explain…»
  · «You were saying?»                     → «One sec, checking…» and then an INVENTED errand about a
                                              WhatsApp message, assembled out of a memory pill
  · «Hey, mate. You there?»                → «Let me check that for you…»

None of those three is a request. They are the connective tissue of a conversation — and the engine already
knows how to answer that class without a model: `presence.py` does it for «¿sigues ahí?» and the action map
does it for a known order. This module is the same idea widened to GREETINGS and the handful of set phrases
that open, close and cushion a conversation.

**Why it is a data table and not a regex.** Zaelar is language agnostic, and a hand-written regex is not:
`presence.py`'s is Spanish + English and cannot grow to forty languages. The phrasebook is DATA hanging off
`LangSpec.smalltalk` — cues and replies per intent — so a new language is a translation, not a code change
(same route the filler pack already has: `i18n/init/fillers.py`). This module only knows how to MATCH, and
what it matches with is handed in.

**Matching is deliberately strict.** The whole utterance must decompose into phatic pieces and nothing else:
every segment is either a cue, a vocative («tío», «mate») or empty. One unknown word and the turn falls
through to the model untouched. The asymmetry is the point — answering «hola» with a model costs 3 s and some
tokens, but answering a real request with «¡Hola! Dime.» is a broken product.

The reply is picked from a pool, avoiding the one just used, so the same greeting twice does not produce the
same sentence: the operator asked for *«una especie de diálogo heurístico, un poco random»*, not a canned line.

⚠️ `im_fine` («bien», «genial») only answers when WE just bounced the question back — otherwise «bien» is an
answer to something we asked and swallowing it would be the V2-665 defect in reverse.
"""
from __future__ import annotations

import random
import re
import unicodedata

_MAX_WORDS = 10          # a phatic exchange is short by nature; beyond this, something real is being said
_MAX_CHARS = 64          # the same bound for scripts that do not separate words (see `classify`)

# Clause separators, NOT an ASCII list. An allowlist of `[a-z]` — the first thing one writes here — deletes a
# Chinese, Arabic or Russian utterance down to the empty string, which would make this module quietly
# unusable in every language but the two it was written in. Everything below is category-driven for the same
# reason; the only enumerated set is this one, and it enumerates CJK/Arabic marks precisely because they are
# the ones Unicode categories alone would not tell apart from a quote.
_SPLIT_CHARS = ".!?;,¡¿\n…。！？；，、‥؟؛"
_SPLIT_RE = re.compile("[" + re.escape(_SPLIT_CHARS) + "]+")
_APOSTROPHES = "'’`´ʼ"


def _norm(text: str) -> str:
    """Lowercase, unaccented, apostrophe-free, punctuation-free — letters, digits and spaces in ANY script.

    Apostrophes are DELETED rather than spaced out so that «how's it going» normalizes to «hows it going»,
    which is the shape a cue list can be written in. Everything else Unicode calls punctuation or a symbol
    becomes a space; letters are kept whatever their alphabet."""
    t = unicodedata.normalize("NFKD", (text or "").lower())
    t = "".join(c for c in t if not unicodedata.combining(c) and c not in _APOSTROPHES)
    t = "".join(c if (c.isalnum() or c.isspace()) else " " for c in t)
    return re.sub(r"\s+", " ", t).strip()


def _strip_vocative(seg: str, vocatives: set[str]) -> str:
    """Drop a leading/trailing address from a segment: «hey mate» is «hey». The assistant's OWN name is
    handled by `presence.assistant_names()` — this is for the generic ones a language uses."""
    words = seg.split()
    while words and words[0] in vocatives:
        words = words[1:]
    while words and words[-1] in vocatives:
        words = words[:-1]
    return " ".join(words)


def _split_joined(seg: str, joiners: set[str]) -> list[str]:
    """«hello and good morning» is two phrases with no punctuation between them — which is exactly how the
    operator said it (2026-09-11). Splitting on the language's own coordinating words recovers both; a
    language that lists none is unaffected, and a piece that is only a joiner disappears, which is right."""
    if not seg or not joiners:
        return [seg]
    parts, cur = [], []
    for w in seg.split():
        if w in joiners:
            parts.append(" ".join(cur))
            cur = []
        else:
            cur.append(w)
    parts.append(" ".join(cur))
    return [p for p in parts if p] or [seg]


def _cue_index(book: dict) -> dict[str, list[str]]:
    """cue → [intent, …]. A cue shared by two intents (Spanish «todo bien» is both a question and an answer)
    keeps both and the gates below decide; there is no silent winner."""
    idx: dict[str, list[str]] = {}
    for intent, spec in (book.get("intents") or {}).items():
        for cue in (spec.get("cues") or ()):
            idx.setdefault(_norm(cue), []).append(intent)
    return idx


def classify(text: str, book: dict, *, bounce_pending: bool = False,
             assistant_names: tuple[str, ...] = ()) -> str:
    """The intent this whole utterance is, or "" when it is not pure small talk.

    The answered intent is the LAST one, because that is where the question lives: «Hola, ¿qué tal?» is a
    `how_are_you`, not a `greeting` — answering the greeting would leave the question hanging.
    """
    intents = book.get("intents") or {}
    if not intents:
        return ""
    n = _norm(text)
    # Two caps, because one of them does not travel: a word count means nothing in a script written without
    # spaces (Chinese, Japanese), where a whole paragraph counts as one «word». The character cap is the one
    # that holds everywhere; the word cap stays because it is the tighter of the two where it applies.
    if not n or len(n.split()) > _MAX_WORDS or len(n) > _MAX_CHARS:
        return ""
    vocatives = {_norm(v) for v in (book.get("vocatives") or ())} | {_norm(a) for a in assistant_names}
    vocatives.discard("")
    idx = _cue_index(book)
    hits: list[str] = []
    # The RAW text is what gets split: `_norm` has already removed every mark a clause boundary is made of,
    # so splitting its output would see one single segment and «hola, ¿qué tal?» would never match.
    joiners = {_norm(j) for j in (book.get("joiners") or ())} - {""}
    for raw_seg in _SPLIT_RE.split(str(text or "")):
        for seg in _split_joined(_norm(raw_seg), joiners):
            seg = _strip_vocative(seg, vocatives)
            if not seg:
                continue                  # an address or empty punctuation carries no request
            candidates = idx.get(seg)
            if not candidates:
                return ""                 # one unknown piece and the whole turn belongs to the model
            chosen = ""
            for intent in candidates:
                gated = bool((intents.get(intent) or {}).get("after_bounce"))
                if gated and not bounce_pending:
                    continue
                chosen = intent
                if gated:
                    break                 # a gate that IS satisfied is the more specific reading
            if not chosen:
                return ""
            hits.append(chosen)
    return hits[-1] if hits else ""


def reply_for(intent: str, book: dict, *, avoid: str = "") -> str:
    """A phrase from the intent's pool, not the one just said. "" when the pool is empty — the caller then
    says nothing and the turn proceeds to the model, which is the honest fallback for a half-filled pack."""
    pool = [p for p in ((book.get("intents") or {}).get(intent) or {}).get("replies", ()) if str(p).strip()]
    if not pool:
        return ""
    return random.choice([p for p in pool if p != avoid] or pool)


def bounces(intent: str, book: dict) -> bool:
    """Did the reply we are about to give hand the question BACK? («¿Y tú qué tal?») Only then does the next
    «bien» mean «I'm fine» rather than an answer to something else."""
    return bool(((book.get("intents") or {}).get(intent) or {}).get("bounces"))


def mirror(text: str, sess, trace_id: str, book: dict, *, bounce_pending: bool = False) -> dict | None:
    """The PROBE channel's answer — the finished response dict, or None to fall through. Deterministic twin
    of the voice lane (V2-539's rule: wire BOTH channels, or the probe hands out verdicts the product never
    gives). It takes the FIRST phrase of the pool instead of a random one: a test channel that rolls dice
    cannot be asserted on."""
    try:
        from nucleo import context_packs
        if context_packs.active_ids():
            return None                   # a guiding phase outranks the phrasebook — see the voice lane
        intent = classify(text, book, bounce_pending=bounce_pending)
        try:
            sess.smalltalk_bounce = False   # see the voice lane: any turn takes the question out of the air
        except Exception:  # noqa: BLE001
            pass
        if not intent:
            return None
        pool = list(((book.get("intents") or {}).get(intent) or {}).get("replies", ()) or ())
        if not pool:
            return None
        phrase = pool[0]
        try:
            sess.smalltalk_bounce = bounces(intent, book)
        except Exception:  # noqa: BLE001
            pass
        from nucleo.flash import dialog
        dialog.push_user(sess.window, text)
        sess.window.append({"role": "assistant", "content": phrase})
        return {"ok": True, "reply": [phrase], "action": "smalltalk", "tool_calls": [], "tags": [],
                "trace": trace_id, "intent": intent}
    except Exception:  # noqa: BLE001 — the phrasebook must never be able to break a turn
        return None
