"""i18n.init.smalltalk — the per-language PHRASEBOOK, generated at onboarding (V2-674).

Sibling of `i18n.init.aliases` (V2-101) and the same shape: the hardcoded es/en tables in
`voice/engine/core/langs.py::LangSpec.smalltalk` are a verified-native accelerator for the two languages this
repo SHIPS, and everything else needs a pack generated once, when the operator picks their language.

Why this one IS wired to a generation call while the filler pack (`i18n.init.fillers`) deliberately is not:
a filler that never arrives costs a missing «mmm…» and the turn still works. A phrasebook that never arrives
costs the whole capability — the lane has no cues to match, so every «hello» goes back to paying a model, in
every language but two. The operator's framing was «language agnostic»: the mechanism only earns that word
if the DATA travels.

Fail-open all the way down. No pack → `langs.smalltalk_book()` returns `{}` → the lane declines → the turn
goes to the model exactly as it did before this module existed. Nothing here can make an answer worse; the
worst case is that it does not make one faster.
"""
from __future__ import annotations

import json

from loguru import logger

# The intents worth a pack, with the ENGLISH seed the model translates FROM. Deliberately small: these are
# the phrases that carry no request at all, so a wrong match costs a model call and a right one saves three
# seconds. Anything with cargo («abre la agenda», «¿qué tiempo hace?») is a real turn and never belongs here.
_SEED: dict[str, dict] = {
    "greeting": {
        "when": "somebody says hello and nothing else",
        "cues": ["hello", "hi", "hey", "good morning", "good evening"],
        "replies": ["Hi! Go ahead.", "Hello — what's up?", "Hey! What can I do?", "Hello. Tell me."],
    },
    "how_are_you": {
        "when": "somebody asks the assistant how it is doing",
        "cues": ["how are you", "how is it going", "how are things", "are you all right"],
        "replies": ["Great, thanks — how about you?", "Doing well. And you?", "All good here. How are you?"],
        "note": "every reply must hand the question BACK to the person",
    },
    "im_fine": {
        "when": "the person answers that question about themselves",
        "cues": ["fine", "I'm good", "very well", "not bad", "all good"],
        "replies": ["Glad to hear it. What do you need?", "Good. Go ahead.", "Great. Tell me whenever."],
    },
    "thanks": {
        "when": "somebody thanks the assistant",
        "cues": ["thanks", "thank you", "thanks a lot", "much appreciated"],
        "replies": ["Anytime.", "You're welcome.", "That's what I'm here for.", "My pleasure."],
    },
    "goodbye": {
        "when": "somebody says goodbye",
        "cues": ["bye", "goodbye", "see you later", "good night"],
        "replies": ["See you.", "Talk soon — I'll be here.", "Bye for now.", "Take care."],
    },
}


def _system(lang_name: str) -> str:
    return (
        f"You build a phrasebook for a personal voice assistant that speaks {lang_name}. For each INTENT you "
        f"will get: when it happens, example English CUES (what the person says) and example English REPLIES "
        f"(what the assistant answers).\n"
        f"Return ONLY a JSON object — no prose, no code fences — with two keys:\n"
        f'  "vocatives": 6-10 generic informal ways a {lang_name} speaker ADDRESSES someone («mate», «tío»), '
        f"one or two words each. Empty array if the language does not use them.\n"
        f'  "joiners": the coordinating words that glue two phrases together with no punctuation between '
        f'them ({lang_name}\'s equivalent of «and»), 1-3 of them. Empty array if the language has none.\n'
        f'  "intents": each INTENT key mapped to {{"cues": [...], "replies": [...]}}.\n'
        f"RULES. (1) CUES are what a {lang_name} speaker ACTUALLY SAYS, not a word-for-word translation — "
        f"give 8-14 per intent, including the short and colloquial forms, and every one must be a COMPLETE "
        f"utterance somebody could say on its own. (2) Write cues in LOWERCASE with NO punctuation and NO "
        f"accents or diacritics at all (strip them: they are matched after normalization). (3) REPLIES are "
        f"the assistant SPEAKING: 4-5 per intent, natural, short, warm, varied — they are picked at random, "
        f"so they must all fit the same moment. Replies keep normal spelling, punctuation and accents. "
        f"(4) A cue must belong to ONE intent only. (5) Never invent an intent that is not in the input."
    )


def _parse(raw: str) -> dict:
    """Extract the JSON object and keep ONLY what is well-formed. A half-understood pack is worse than none:
    a cue with no replies would match an utterance and then answer nothing, so an intent missing either side
    is dropped whole rather than merged into the hardcoded table."""
    if not raw:
        return {}
    s = raw.strip()
    if s.startswith("```"):
        s = s.split("```", 2)[1] if s.count("```") >= 2 else s.strip("`")
        if s.lstrip().lower().startswith("json"):
            s = s.lstrip()[4:]
    i, j = s.find("{"), s.rfind("}")
    if i >= 0 and j > i:
        s = s[i:j + 1]
    try:
        d = json.loads(s)
    except Exception:  # noqa: BLE001
        return {}
    if not isinstance(d, dict):
        return {}

    def _strs(v) -> list[str]:
        return [x.strip() for x in v if isinstance(x, str) and x.strip()] if isinstance(v, list) else []

    intents: dict[str, dict] = {}
    for name, spec in (d.get("intents") or {}).items():
        if name not in _SEED or not isinstance(spec, dict):
            continue                      # rule 5, enforced rather than trusted
        cues = [c.lower() for c in _strs(spec.get("cues"))]
        replies = _strs(spec.get("replies"))
        if not cues or not replies:
            continue
        entry: dict = {"cues": cues, "replies": replies}
        # The two behavioural flags are OURS, never the model's: they encode a rule about the conversation
        # (a bounced question, an answer that only means «I'm fine» right after one), not a fact about the
        # language. Handing them to a translator would let a pack quietly change how the lane behaves.
        if name == "how_are_you":
            entry["bounces"] = True
        if name == "im_fine":
            entry["after_bounce"] = True
        intents[name] = entry
    if not intents:
        return {}
    return {"vocatives": [v.lower() for v in _strs(d.get("vocatives"))],
            "joiners": [j.lower() for j in _strs(d.get("joiners"))],
            "intents": intents}


def _generate_sync(code: str) -> dict:
    from i18n.init.generate import language_name
    from nucleo import memllm

    raw = memllm.chat_sync("i18n", _system(language_name(code)),
                           json.dumps(_SEED, ensure_ascii=False),
                           max_tokens=2500, temperature=0.3, timeout=90.0)
    return _parse(raw or "")


async def ensure_smalltalk(code: str) -> dict:
    """Make sure `code` has a phrasebook on disk. Idempotent — a no-op once generated. PRESET languages
    (en/es) never call this: their table is hardcoded and verified native. Returns {code, intents}."""
    import asyncio

    from i18n.init import fillers as _store

    code = (code or "").strip().lower()
    existing = _store.read_smalltalk(code)
    if existing.get("intents"):
        return {"code": code, "intents": len(existing["intents"])}
    logger.info(f"i18n.smalltalk: no phrasebook for '{code}' yet — generating…")
    try:
        book = await asyncio.to_thread(_generate_sync, code)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"i18n.smalltalk[{code}]: generation failed: {str(e)[:160]}")
        book = {}
    if book:
        _store.save_smalltalk(code, book)
    return {"code": code, "intents": len(book.get("intents") or {})}
