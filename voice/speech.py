#
# SPEECH OUTPUT GATE — the ONE choke-point for everything that reaches the operator's speaker.
#
# ARCHITECTURE (operator decision, 2026-07): the voice/UI layer is a pure I/O boundary. It captures mic/text on
# the way IN and emits audio on the way OUT — and the ONLY audio it emits is prose that OUR core deliberately
# produced FOR the operator. Anything else — cluster chatter with other agents, cron/watchdog metadata, raw
# provider errors, markdown formatting, silent control tags — must NEVER hit TTS. The cluster channel in
# particular reaches the operator ONLY when the brain preprocesses it into an operator-facing message; the
# transport itself has no path to the speaker.
#
# So instead of trusting each caller to hand TTS clean text, we funnel EVERY spoken string through here first:
#
#   sanitize(text)  → speakable prose, or "" if there's nothing worth saying out loud.
#   inline(text)    → the streaming-safe subset (boundary-safe, no look-ahead) for token-by-token voice replies.
#
# Both are pure, stateless and brain-agnostic. The rule of thumb for a maintainer: if you're about to push a
# TTSSpeakFrame / LLMTextFrame, the text MUST have come through here. There is no other sanctioned way to speak.
#
import re

# ── patterns (compiled once) ────────────────────────────────────────────────────────────────────────────────
_CODE_FENCE   = re.compile(r"```.*?```", re.S)               # whole fenced code block → dropped (never spoken)
_CODE_FENCE_L = re.compile(r"^\s*```.*$", re.M)              # a lone/again-unclosed fence line
_INLINE_CODE  = re.compile(r"`([^`]*)`")                     # `code` → code (keep the words, drop the ticks)
_IMAGE        = re.compile(r"!\[[^\]]*\]\([^)]*\)")          # ![alt](url) → dropped
_LINK         = re.compile(r"\[([^\]]*)\]\((?:[^)]*)\)")     # [text](url) → text
_BRAIN_TAG    = re.compile(r"\[\[[^\]]*\]\]")                # stray [[cluster.send]] / [[cron.create]] leftovers
_FENCE_BLOCK  = re.compile(r"⟦[^⟧]*⟧")                       # ⟦UNTRUSTED PEER MESSAGE⟧ delimiters
_HR           = re.compile(r"^\s*(?:[-*_]\s*){3,}$", re.M)   # --- / *** horizontal rule line
_TABLE_SEP    = re.compile(r"^\s*\|?[\s:\-|]+\|[\s:\-|]+$", re.M)   # |---|:--:| table separator row
_HEADING      = re.compile(r"^\s{0,3}#{1,6}\s*", re.M)       # ## Heading → Heading
_BLOCKQUOTE   = re.compile(r"^\s{0,3}>\s?", re.M)            # > quote → quote
_BULLET       = re.compile(r"^\s{0,3}[-*+]\s+", re.M)        # - item / * item → item
_EMPHASIS     = re.compile(r"(\*\*|__|\*|_)")                # bold/italic markers → removed
_WS_RUN       = re.compile(r"[ \t]{2,}")
_NL_RUN       = re.compile(r"\n{3,}")

# A line that is ONLY key/value metadata (native cron docs, status trailers) is not something to say out loud.
_META_LINE    = re.compile(r"^\s*(?:\*\*[^*]+\*\*|[A-Z][\w /-]{0,30})\s*[:：]\s*\S.*$")


def _strip_markup(text: str, *, drop_code: bool) -> str:
    """Turn markdown/tag noise into plain speakable characters. Shared by sanitize() and inline()."""
    if drop_code:
        text = _CODE_FENCE.sub(" ", text)
        text = _CODE_FENCE_L.sub(" ", text)
    text = _IMAGE.sub("", text)
    text = _LINK.sub(r"\1", text)
    text = _INLINE_CODE.sub(r"\1", text)
    text = _BRAIN_TAG.sub("", text)
    text = _FENCE_BLOCK.sub("", text)
    text = _HR.sub("", text)
    text = _TABLE_SEP.sub("", text)
    text = _HEADING.sub("", text)
    text = _BLOCKQUOTE.sub("", text)
    text = _BULLET.sub("", text)
    text = _EMPHASIS.sub("", text)
    return text


def sanitize(text: str, *, drop_metadata: bool = True) -> str:
    """Full clean for a COMPLETE message (proactive/cron/error line). Returns speakable prose or "" if nothing
    worth saying survives. drop_metadata removes pure key:value lines (cron doc headers, status trailers)."""
    if not text:
        return ""
    out = _strip_markup(text, drop_code=True)
    if drop_metadata:
        kept = [ln for ln in out.splitlines() if ln.strip() and not _META_LINE.match(ln)]
        out = "\n".join(kept)
    out = _NL_RUN.sub("\n\n", out)
    out = _WS_RUN.sub(" ", out)
    out = "\n".join(ln.strip() for ln in out.splitlines())
    out = out.strip()
    # Nothing but punctuation/symbols left → nothing to say.
    if not re.search(r"[A-Za-zÀ-ÿ0-9]", out):
        return ""
    return out


def inline(text: str) -> str:
    """Streaming-safe subset for token-by-token voice replies. Every transform here is boundary-safe (no
    look-ahead across chunks): removing a stray '*', '`', '#', bullet or link markup never corrupts a word even
    if the reply is split mid-token. Code fences are NOT reliably detectable mid-stream, so they're left to the
    hold-back logic in the caller; here we only drop the fence markers we can see."""
    if not text:
        return ""
    out = _strip_markup(text, drop_code=False)
    out = _WS_RUN.sub(" ", out)
    return out
