"""nucleo/actionmap/normalize.py — MECHANICAL utterance normalization for the action map (V2-539).

Only mechanics live here, on purpose: lowercase, accent strip, punctuation strip, whitespace collapse.
No stemming, no stopword removal, no courtesy-prefix stripping — "por favor limpia la pantalla" is another
ENTRY in the seed pack, not something this function is allowed to understand. Intelligence in the matcher
is exactly what the no-hardcoded-intent doctrine forbids (V2-095): the map does an exact lookup of the
whole normalized utterance, and anything it does not know verbatim goes to the model.
"""
import re
import unicodedata

# Punctuation that STT/typing sprinkles onto an otherwise identical command. Removed anywhere in the
# phrase (not just at the edges): "abre, el whatsapp" and "abre el whatsapp." must collide.
_PUNCT_RE = re.compile(r"[.,;:!?¡¿…\"'«»()\[\]]+")
_WS_RE = re.compile(r"\s+")


def normalize(text: str) -> str:
    """Canonical form used both to store a phrase and to look one up. Deterministic, µs, never raises."""
    t = (text or "").strip().lower()
    if not t:
        return ""
    t = unicodedata.normalize("NFD", t)
    t = "".join(ch for ch in t if unicodedata.category(ch) != "Mn")  # drop combining accents
    t = _PUNCT_RE.sub(" ", t)
    return _WS_RE.sub(" ", t).strip()
