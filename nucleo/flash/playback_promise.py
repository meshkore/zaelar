"""nucleo/flash/playback_promise.py — an ENGLISH promise of playback, read from the reply, and the title it carries.

Demo passes 34-51 (2026-09-29, U2): «no, put like a prayer» → «Sure — putting on Like a Prayer now.» and no tool,
nine turns of twenty-one. The promise backstop (`router_guards.promises_music`) only knew the Spanish forms and the
act-repair door needs a card the catalogue names (it answered `none` with the music card open), so the reply stood
alone. Its own module because `router_guards` is a god file under the architecture ratchet: a new grammar goes
beside it, never into it. Read by both channels (the voice provider and its probe mirror).
"""
from __future__ import annotations

import re

# ENGLISH promise of PLAYBACK — «Sure — putting on Like a Prayer now», «Yep, switching it — Like a Prayer coming
# up», «Playing some Madonna now». Demo passes 34-51 (2026-09-29, U2): nine turns of twenty-one promised the song
# and called nothing, and the Spanish table above never opened the backstop, so the reply stood alone. Gated, so a
# verb is not enough: the music card is on screen (the reply is about it) or the words carry a music word —
# «playing number five now» over the video card is not a song. A verb-less claim («There you go — Like a Prayer»)
# counts only over the open music card AND an order to play in his words.
_PLAYBACK_VERB_RE = re.compile(
    r"\b(?:put(?:ting)?(?: it)? on|play(?:ing)?|switch(?:ing)?(?: it| over)?(?: to)?|chang(?:e|ing)(?: it)? to|"
    r"queue(?:ing)?(?: up)?|cue(?:ing)?(?: up)?|spin(?:ning)?(?: up)?)\b", re.I)
_PLAYBACK_CLAIM_RE = re.compile(r"\b(?:there you go|here you go|coming up|it is|on it|got (?:her|him|it|them) going)\b", re.I)
_MUSIC_WORD_RE = re.compile(r"\b(?:music|song|songs|track|album|playlist|artist|band|tune|radio)\b", re.I)
_PLAYBACK_TAIL_RE = re.compile(r"\s*(?:\bfor you\b|\bnow\b|\bcoming up\b|\bit is\b|\bthen\b|\bright away\b|\bagain\b|"
                                r"\bon (?:the )?(?:speakers?|player)\b|[.!?,;:—–-]).*$", re.I)
_PLAYBACK_LEAD_RE = re.compile(r"^(?:(?:no|nah|yeah|yep|yes|ok|okay|sure|right|actually|wait|hmm|umm|uh|so|and|please|johnny)"
                                r"[,.!… —–-]*\s*)+", re.I)
_PLAYBACK_ORDER_RE = re.compile(r"^(?:(?:can|could|would) you\s+)?(?:just\s+)?(?:put(?: it)? on|put|play|switch(?: it)?(?: over)?"
                                 r" to|change(?: it)? to|queue(?: up)?|cue(?: up)?)\s+(?:some |a bit of |a little |me |us )?", re.I)
_PLAYBACK_PRONOUN_RE = re.compile(r"^(?:it|that|this|one|him|her|them|the (?:song|track|music|same)|something|anything)$", re.I)


def promises_playback(reply: str, operator_text: str = "", *, music_open: bool = False) -> bool:
    """The REPLY promises to put something on (English), over the music card or with a music word in the turn.
    Since V2-778 F2-16 a SURE verdict on the reply decides, in any language; this grammar answers when there is none."""
    from nucleo.flash import reply_promise as _rp
    v = _rp.verdict(reply)
    if v is not None:
        return v == "music"
    r = " ".join(str(reply or "").split())
    if not r:
        return False
    if _PLAYBACK_VERB_RE.search(r):
        if music_open or _MUSIC_WORD_RE.search(r) or _MUSIC_WORD_RE.search(str(operator_text or "")):
            return True
        # «play some madonna» — an order to play SOME of a name is music even before the card exists (U1)
        lead = _PLAYBACK_LEAD_RE.sub("", " ".join(str(operator_text or "").split()))
        return bool(re.match(r"(?:put on|play)\s+some\s+\w+", lead, re.I))
    if music_open and _PLAYBACK_CLAIM_RE.search(r):
        lead = _PLAYBACK_LEAD_RE.sub("", " ".join(str(operator_text or "").split()))
        return bool(_PLAYBACK_ORDER_RE.match(lead))
    return False


def music_query(reply: str, operator_text: str) -> str:
    """WHAT to play, from the words that promised it: the title after the verb («putting on Like a Prayer now» →
    «Like a Prayer»), else his order without its filler and its verb («no, put like a prayer» → «like a prayer»).
    Never his sentence whole: «no, put like a prayer» as a search found the wrong thing or nothing."""
    r = " ".join(str(reply or "").split())
    m = _PLAYBACK_VERB_RE.search(r)
    if m:
        rest = _PLAYBACK_TAIL_RE.sub("", r[m.end():].strip(" —–-:,\"'“”")).strip(" —–-:,\"'“”")
        rest = re.sub(r"^(?:some|a bit of|a little|me|us)\s+", "", rest, flags=re.I).strip()
        if len(rest) >= 2 and not _PLAYBACK_PRONOUN_RE.match(rest):
            return rest
    o = _PLAYBACK_LEAD_RE.sub("", " ".join(str(operator_text or "").split()))
    o = _PLAYBACK_ORDER_RE.sub("", o).strip(" .!?…")
    return o
