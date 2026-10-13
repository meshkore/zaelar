"""A reply never claims it CHECKED whether a video is AI-made: nothing in the engine can (2026-10-14).

Use case `find-videos-on-a-topic-no-ai-slop`, both languages. He asks for videos «by real people, none of those
AI-made ones with the robotic voice». ES t0: «…te los dejo para elegir, filtrando los que huelen a generado» — no
filter ran, and the first batch held the video he then had to point out himself. EN t2, a chat turn with no op at
all (navigations 0, extractions 0): «the channel is The Frenchie Gardener — a real person filming in his own garden,
no synthetic voice». The model wrote a verification nobody did.

The engine has NO signal for a video's provenance: a search returns title, channel and date, and no card, worker or
provider reports «synthetic voice» or «AI-generated» (measured: `widgets/youtube/actions._a_search`'s row shape).
So the rule bounds the CONSEQUENCE, not the judgement: the model may still pick, rank and guess; what it may not do
is SAY it filtered or verified. A sentence that asserts that is dropped and the one honest caveat is said instead
(`provenance_unchecked`, in the session's language). The day a card returns a real provenance field, this guard is
where it must be read before a claim is allowed.

The vocabulary is the claim's own words in the two languages the product speaks; a sentence that says it CANNOT
check is the caveat itself and stays. Text channel: `honest()` beside the transport receipt. Voice: the words have
streamed, so `voice_owed()` returns the caveat to say after them. Never raises.
"""
from __future__ import annotations

import re
import unicodedata

_AI = r"(?:ai|a\.i\.|ia|i\.a\.|inteligencia artificial|synthetic\w*|sintetic\w*|robotic\w*|robot\w*|generad\w*|" \
      r"generated|computer generated|text to speech|tts|artificial\w*)"
_CLAIM = re.compile(
    r"\b(?:filtr\w*|filter\w*|steer\w*|weed\w*|screen\w*|evit\w*|avoid\w*)\b"
    r"[^.;!?]{0,45}\b" + _AI + r"\b"
    r"|\b(?:no|not|without|zero|sin|nada de|ningun\w*)\s+(?:any\s+|una\s+|un\s+)?(?:" + _AI + r")[\s-]+"
    r"(?:voice\w*|voz|voces|narrat\w*|narrador\w*|voiceover|locucion\w*|made|hech\w*|content|contenido)\b"
    r"|\bnot\s+(?:ai|a\.i\.)[\s-]*(?:made|generated|narrated)\b|\bno\s+(?:es|son|esta|estan)\s+(?:hech\w*|generad\w*)\s+"
    r"(?:con|por)\s+(?:ia|inteligencia artificial)\b"
    r"|\b(?:a\s+)?real\s+(?:person|people|human)\b|\b(?:una\s+)?persona\s+real\b|\bgente\s+(?:de\s+verdad|real)\b")
#: A sentence that says it CANNOT tell is the honest one — never dropped.
_DISCLAIMS = re.compile(r"\b(?:can'?t|cannot|can not|unable|no puedo|no se|imposible)\b[^.;!?]{0,40}"
                        r"\b(?:check|verify|tell|know|comprobar|verificar|saber|distinguir)\b")


def _fold(s: str) -> str:
    n = unicodedata.normalize("NFKD", str(s or ""))
    return "".join(c for c in n if not unicodedata.combining(c)).lower()


def _sentences(text: str) -> list[str]:
    """The reply split into sentences, never inside a «quoted title» (titles end in «!!» and «?» too)."""
    out, cur, depth = [], "", 0
    for i, ch in enumerate(text):
        cur += ch
        depth += (ch == "«") - (ch == "»")
        if ch in ".!?" and depth <= 0 and (i + 1 == len(text) or text[i + 1].isspace()):
            out.append(cur)
            cur = ""
    if cur.strip():
        out.append(cur)
    return out


def claims(text: str) -> bool:
    """Does any sentence of `text` assert a provenance check that nothing performed?"""
    return any(_claims(s) for s in _sentences(str(text or "")))


def _claims(sentence: str) -> bool:
    f = _fold(re.sub(r"«[^»]*»", " ", sentence))      # a title he will read is not our claim
    return bool(_CLAIM.search(f)) and not _DISCLAIMS.search(f)


def _caveat(lang=None) -> str:
    try:
        if lang is None:
            from i18n import langs as _langs
            lang = _langs.current_language()
        return str(getattr(lang, "provenance_unchecked", "") or "")
    except Exception:  # noqa: BLE001
        return ""


def _video_in_play() -> bool:
    """Only over the video player: «a real person» about a contact is not a claim about a video."""
    try:
        from nucleo.flash import card_receipt as _cr
        return any(_cr._base(c) == "youtube" for c in _cr._open_now())
    except Exception:  # noqa: BLE001
        return False


def honest(reply: str, lang=None, *, video: bool | None = None) -> str:
    """The text channel's reply without the claimed check, and with the caveat said once. Unchanged when clean."""
    try:
        if not (_video_in_play() if video is None else video):
            return reply
        text = str(reply or "")
        parts = _sentences(text)
        kept = [s for s in parts if not _claims(s)]
        if len(kept) == len(parts):
            return reply
        line = _caveat(lang)
        body = " ".join(s.strip() for s in kept if s.strip())
        return f"{body} {line}".strip() if line and _fold(line) not in _fold(body) else (body or reply)
    except Exception:  # noqa: BLE001 — the reply as written beats no reply
        return reply


def voice_owed(spoken: str, lang=None, *, video: bool | None = None) -> str:
    """The voice channel's caveat, owed after words that claimed the check (they have streamed already)."""
    try:
        if not (_video_in_play() if video is None else video):
            return ""
        return _caveat(lang) if claims(spoken) and _fold(_caveat(lang)) not in _fold(spoken) else ""
    except Exception:  # noqa: BLE001
        return ""


def said_after(spoken: str, send, speech) -> str:
    """The voice rail's door: say the owed caveat after the streamed words; returns what the turn said in total."""
    line = voice_owed(spoken)
    if not line:
        return spoken
    try:
        send(speech.sanitize(line, drop_metadata=False))
    except Exception as e:  # noqa: BLE001 — the turn's words stand; the timeline says the caveat was lost
        from loguru import logger
        logger.debug(f"unchecked_provenance: caveat not sent — {e}")
        return spoken
    return f"{str(spoken or '').rstrip()} {line}".strip()
