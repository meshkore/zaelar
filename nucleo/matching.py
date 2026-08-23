"""nucleo/matching.py — the ONE yardstick for «are these two texts the same errand?».

Born from a measured contradiction (2026-08-21): TWO similarity judges lived in this tree — `dispatch.find_duplicate`
(Jaccard >= 0.60 over content words) and `widgets/navegador/tasks._similar` (>= 2 shared stems OR Jaccard >= 0.40) —
and they disagreed about the SAME pair of texts. Jaccard between three live reformulations of one errand measured
0.333-0.375: below the dispatcher's bar («different errands» → three workers spawned) and above the browser's
(«same browsing session» → ONE tab handed to all three). Element refs are dealt out per look (V2-248), so the
second worker clicked `[29]` on a page the first had just changed. Each threshold was defensible alone; the
combination was not. F4 of the 2026-08-23 architecture audit: the PRIMITIVE lives here, once, and every judge
imports it with its own threshold.

WHY CONTAINMENT AND NOT JACCARD for «same errand». The brain REFORMULATES an errand each time it escalates — the
four requests of one live case measured 668, 437, 342 and 298 chars. Jaccard divides by the UNION, so a longer
rewording looks *different by being longer* even when the shorter one is fully inside it. Containment divides by
the SMALLER set, which is exactly the question being asked: «is the short version contained in the long one?».
Measured over the harness's full sweep (39 escalations, same process, both alive):

    same errand, reformulated:   containment 0.571 - 0.893     jaccard 0.319 - 0.450
    different errands:           containment 0.062 - 0.227

The two populations DO NOT OVERLAP under containment; under Jaccard they are inseparable from the threshold's
point of view. Containment >= any threshold in the (0.227, 0.571) gap separates them cleanly.

Pure stdlib on purpose: judges live in very different layers (the dispatcher, a widget's task registry) and the
yardstick must be importable from ANY of them without dragging the engine along or creating a cycle.
"""
from __future__ import annotations

import re
import unicodedata

_WORD_RE = re.compile(r"\w+", re.UNICODE)


def norm_text(text: str) -> str:
    """Accent-stripped lowercase. `\\w+` on top of THIS (not a latin-only class) so a goal in another alphabet
    still tokenizes — a latin-only class would silently turn matching off for that language."""
    n = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in n if not unicodedata.combining(c)).lower()


def content_words(text: str) -> set:
    """Words that carry the errand: length >= 4 after normalization. The tokenizer that both judges share —
    punctuation stripped by the regex, because `zurdo` and `zurdo,` counting as different words once cost two
    workers doing the same job on real money (V2-123)."""
    return {w for w in _WORD_RE.findall(norm_text(text)) if len(w) >= 4}


def jaccard(a: set, b: set) -> float:
    """|A∩B| / |A∪B| — kept for the judges whose measured thresholds are calibrated on it (the browser's
    clarification matcher). Penalizes length difference by construction; do NOT reach for it to answer «same
    errand?» across reformulations — that is what `containment` is for."""
    if not a or not b:
        return 0.0
    union = len(a | b)
    return len(a & b) / union if union else 0.0


def containment(a: set, b: set) -> float:
    """|A∩B| / min(|A|,|B|) — «is the smaller one inside the bigger one?». The primitive that separates
    reformulations of one errand from genuinely different errands (see module docstring for the measured,
    non-overlapping populations)."""
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))


#: The dispatcher's «same errand» bar. Sits in the measured gap — 0.22 above the worst different-errand pair
#: (0.227) and 0.12 below the weakest same-errand pair (0.571) — biased toward the different-errand side on
#: purpose: over-merging swallows a genuinely new task into an old session (the V2-123 flow-fusion class), and
#: that is worse than the duplicate worker this bar exists to prevent.
SAME_ERRAND = 0.45
