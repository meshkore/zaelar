"""Make FILENAMES and addresses speakable — the other half of the last chokepoint before the voice (V2-649).

Measured live (session `653f8346`, 2026-09-10, 00:37-00:43): the torrent client declined an `.mkv` and its
refusal NAMED the file, which is right on a screen and unreadable out loud. The voice said

    «Minions.and.Monsters.2026.1080p.WEBRip.AAC5.1.10bits.x265-Rapta.mkv»

three times — dot by dot, tag by tag — and the operator heard a robot stalling over something it plainly did
not understand. Nobody upstream can be asked to phrase it better: the string is a FACT about a file, and the
CHAT wants it exactly as it is. So the repair belongs where the figures already live — the TTS node, the one
place that sees everything SPOKEN and nothing WRITTEN. Precision on screen, a sentence a person would say out
loud in the ear.

UNLIKE the figure half, this is **language-agnostic on purpose**, and that is a real simplification rather
than an omission: which character groups thousands is a property of a language, while `.mkv`, `1080p` and
`x265` are the same token in every one of them.

WHAT IT REFUSES TO TOUCH is the half that makes it safe:

  · a DOMAIN standing on its own («coches.net», «zaelar.com») — a person really does say *coches punto net*,
    so rewriting it would be inventing a problem;
  · an IP, a version, a date, a time, a decimal — the same set the figure half already protects;
  · anything without a KNOWN extension. Suspicion is not evidence, and the two mistakes are not equal: a
    filename read badly is recoverable by asking again, a word eaten because it merely LOOKED technical is
    gone and the operator never learns it was said.

WHAT IT DELIBERATELY DOES NOT DO: spell numbers out. That belongs to the figure half, which documents why
(a Spanish/English number speller is a per-language component with its own gender and agreement rules).

Pure and dependency-free, like its sibling, so it can be measured without a provider or a session.
"""
from __future__ import annotations

import re

# A token ending in one of these is a FILE. Deliberately a LOCAL list rather than an import from
# `library/formats.py`: that table answers «what can the browser play», a product policy that moves with the
# product, and this one answers «would a TTS read this as a word» — the same extension can leave one list and
# have no business leaving the other.
_EXT = frozenset("""
mp4 m4v mkv avi mov webm ogv wmv flv m2ts mpg mpeg divx rmvb vob
mp3 m4a aac ogg oga opus wav flac wma aiff
pdf epub mobi djvu doc docx odt rtf txt md csv tsv xls xlsx ppt pptx pages
jpg jpeg png gif webp avif bmp svg heic heif tiff raw
zip rar 7z tar gz bz2 xz iso dmg pkg
json xml yaml yml html htm srt sub vtt ass nfo torrent log
""".split())

# The technical noise a release name carries. Every entry here is a fact about the ENCODING, never about the
# work — which is why «castellano», «latino», «vose» and every edition word are NOT in it: the operator asks
# for films «en castellano», so dropping that would answer a question he can no longer check.
_JUNK = re.compile(r"""^(?:
      \d{3,4}p | [48]k | 2160p | uhd | hdr\d* | sdr | hq
    | x\.?26[45] | h\.?26[45] | hevc | avc | av1 | xvid | vp9 | mpeg\d?
    | \d{1,2}bits?
    | web | webrip | webdl | bluray | bdrip | brrip | bdremux | remux | hdtv
    | dvdrip | dvdscr | hdrip | camrip | cam | telesync | ts | tc | scr
    | aac\d* | ac3 | eac3 | dts | dtshd | ddp\d* | dd | atmos | truehd | hd | ma
    | repack | proper | internal | rip | encode
)$""", re.I | re.X)

# Words that carry MEANING to the operator and survive even in the trailing position a release group sits in.
_KEEP = re.compile(r"^(?:castellano|espanol|español|latino|spanish|english|ingles|inglés|vose|vos|vo"
                   r"|subtitulado|subs?|dual|multi|extended|uncut|remastered|unrated|director|cut"
                   r"|temporada|season|s\d{1,2}e\d{1,2}|cap\d+|parte|part)$", re.I)

_SEPARATORS = re.compile(r"[._\-+]+")
_YEAR = re.compile(r"^(?:19|20)\d{2}$")
_SMALL_NUM = re.compile(r"^\d{1,2}$")

# A candidate run: no whitespace and no quoting, so «foo.mkv» hands over `foo.mkv` with the guillemets intact.
_CANDIDATE = re.compile(r"[^\s«»\"'()\[\]<>]+")
_TRAILING = ",;:!?…"

_URL = re.compile(r"\bhttps?://(?:www\.)?([^\s/«»\"'<>]+)(?:/[^\s«»\"'<>]*)?", re.I)
# `mi_variable` outside any filename: a lone underscore between word characters is never pronounced.
_INNER_UNDERSCORE = re.compile(r"(?<=\w)_(?=\w)")
# `-----`, `====`, `***` used as a rule or emphasis: a TTS either spells them or stalls.
_SYMBOL_RUN = re.compile(r"\s*(?<!\w)[-=*~^#|\\/_]{3,}(?!\w)\s*")


def _ext_of(token: str) -> str:
    _, dot, ext = token.rpartition(".")
    return ext.lower() if dot else ""


def is_filename(token: str) -> bool:
    """A token we are WILLING to rewrite: it ends in a known extension and is not a bare number."""
    if not token or _ext_of(token) not in _EXT:
        return False
    stem = token[: -(len(_ext_of(token)) + 1)]
    return bool(stem) and not stem.replace(".", "").replace(",", "").isdigit()


def spoken_name(token: str) -> str:
    """The filename as a person would say it: the title, its year, and nothing about the encoding."""
    stem = token[: -(len(_ext_of(token)) + 1)]
    parts = [p for p in _SEPARATORS.split(stem) if p]
    kept: list[str] = []
    prev_dropped = False
    for i, p in enumerate(parts):
        last = i == len(parts) - 1
        keep = bool(_KEEP.match(p))
        # The encoding tags, plus the two things that only ever TRAIL them: the stray digit left by an audio
        # layout («AAC5.1» splits into `AAC5` and `1») and the release group at the very end («…x265-Rapta»).
        drop = (not keep) and (
            bool(_JUNK.match(p))
            or (prev_dropped and _SMALL_NUM.match(p) and not _YEAR.match(p))
            or (prev_dropped and last)
        )
        if drop:
            prev_dropped = True
            continue
        prev_dropped = False
        kept.append(p)
    # Everything looked technical — say the stem rather than nothing, which is the failure that loses a fact.
    return " ".join(kept) if kept else " ".join(parts)


def _one_token(token: str) -> str:
    body, tail = token, ""
    while body and body[-1] in _TRAILING:
        body, tail = body[:-1], body[-1] + tail
    if not is_filename(body):
        return token
    return spoken_name(body) + tail


def speakable_names(text: str) -> str:
    """Filenames, addresses and symbol runs, said the way a person says them. Unrecognised text is UNTOUCHED."""
    if not text:
        return text
    try:
        out = _URL.sub(lambda m: m.group(1), text)
        out = _CANDIDATE.sub(lambda m: _one_token(m.group(0)), out)
        # The run eats its own surrounding whitespace and leaves ONE space. Never `.strip()` the text: this
        # also runs on a mid-stream CHUNK, and trimming its edges glues the words either side together.
        out = _SYMBOL_RUN.sub(" ", out)
        return _INNER_UNDERSCORE.sub(" ", out)
    except Exception:                      # never let a phrasing detail cost the operator the whole reply
        return text


# ── streaming ────────────────────────────────────────────────────────────────────────────────────────────
# The figure half holds back a few characters; a release name is sixty, so it needs its own budget — and,
# unlike a figure, its evidence arrives LAST. Holding only on a visible interior dot is too late: measured
# with 3-character chunks, «Mi» «nio» «ns.» were already spoken before the first dot proved anything, and the
# name came out half-transformed. So the rule is the simpler one — NEVER EMIT A PARTIAL WORD — and the hold
# is bounded by the current word, capped for a pathological run with no whitespace in it.
#
# ⚠️ With ONE exception, and it is not a nicety: a word run ending in sentence punctuation goes out at once.
# That period is what the TTS sentence tokenizer needs to close a segment, so holding it delays the last
# sentence's audio until the stream ends — the trap the figure half documents, and V2-538 left a guard on it
# that this rule turned red before the exception was added. A guard that predates you is evidence, not an
# obstacle: the rule got narrower, the guard stayed.
#
# The cost of the exception is a KNOWN, narrow limit: a chunk boundary landing exactly after a name's dot
# («Minions.» as a whole chunk) is indistinguishable from a sentence ending, so that prefix goes out
# untransformed and the rest is still cleaned. Rare — a tokenizer seldom ends a piece on a dot — and the
# failure degrades instead of breaking.
NAME_MAX_HOLD = 96
NAME_TAIL_RE = re.compile(r"\S+$")
_SENTENCE_END = re.compile(r"[.!?…:;]$")
_INTERIOR_DOT = re.compile(r"[A-Za-z0-9]\.[A-Za-z0-9]")
_HAS_LETTER = re.compile(r"[^\W\d_]", re.UNICODE)


def hold_start(buf: str) -> int | None:
    """Index from which `buf` must be WITHHELD because a word is still being spelled, or None."""
    m = NAME_TAIL_RE.search(buf)
    if not m or len(buf) - m.start() > NAME_MAX_HOLD:
        return None
    run = m.group(0)
    # A run with no letter in it is a FIGURE, and the figure half owns it — with its own, much tighter cap.
    # Claiming it here would quietly widen that cap from 24 to 96 and break the guard V2-538 left on it.
    if not _HAS_LETTER.search(run):
        return None
    if _SENTENCE_END.search(run) and not _INTERIOR_DOT.search(run):
        return None                        # a sentence closing, not a name being spelled
    return m.start()
