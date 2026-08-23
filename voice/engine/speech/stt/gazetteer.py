"""Static term boosting for the remote STT: the place names nova-3 destroys.

WHY THIS EXISTS. A real session (2026-08-21): Deepgram split «Calatayud» into «cal»+«a», the segmenter's
«ends in "a", so it governs something not said yet» rule fired on the fragment, and it kept gluing pieces
together for 23 turns until the brain received one monstrous sentence. The distiller then wrote
`operator.location = "Vive en Calatayud."` over a legitimate «Soria» — a wrong memory written with perfect
fidelity, out of two characters the STT invented. Boosting the name is the only fix that acts BEFORE the
damage; everything downstream is repairing a sentence that was already wrong.

THE CRITERION IS RISK, NOT POPULATION — measured, not preferred. Deepgram caps keyterm at **500 sub-word
tokens across all terms**, which for real place names is about a hundred entries. Calatayud ranks #429 in
Spain by population and Valls #321, so a list ranked by size never reaches either of the two names that
motivated this: the budget would go to Madrid, Barcelona and Valencia, which nova-3 already gets right.
So every slot goes to a name measured to FAIL. The sweep behind the list — 941 municipalities spoken to
nova-3, 342 of them mis-transcribed — is described in the header of `_data/es_places.txt`, next to the
data it produced.

WHAT IT DOES NOT DO. Boosting is a bias, not a guarantee: verified live with the shipped list, 9 of 10
sampled names were recovered and «Manresa» still came back as «Mandesa». And the list is single-word only,
so «Cornellá de Llobregat» is still mis-heard — that gap is named at the bottom of the data file.

FAIL-SOFT IS NOT OPTIONAL. Going over the cap is an HTTP 400 on the listen request, which means no STT at
all: the agent goes deaf rather than mishearing a town. That is a much worse failure than the one being
fixed, so the shipped list is held inside a measured envelope by `tests/voice/unit/test_stt_gazetteer.py`
and clamped again here at call time. A gazetteer that cannot be loaded returns no terms and the STT is
built exactly as it was before.
"""
from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path

_DATA = Path(__file__).parent / "_data"

# The envelope, bisected against the live API on 2026-08-23 (nova-3, language=es) with THIS list's own
# contents — not with a generic sample, because the cap counts sub-word tokens and rare names cost more of
# them. 121 single-word entries was the largest accepted prefix; 122 was a 400. 100 ship, so there is room for
# the memory hook to add its own on top without anyone re-measuring. Raising either number without re-running
# the bisect is how the agent goes deaf.
MAX_TERMS = 118
MAX_CHARS = 1000


@lru_cache(maxsize=None)
def _load(code: str) -> tuple[str, ...]:
    """One term per line, `#` comments ignored. Missing file → no boosting, never an exception."""
    try:
        raw = (_DATA / f"{code}_places.txt").read_text(encoding="utf8")
    except Exception:  # noqa: BLE001
        return ()
    out = []
    for line in raw.splitlines():
        term = line.split("#", 1)[0].strip()
        if term:
            out.append(term)
    return tuple(out)


def _clamp(terms) -> list[str]:
    """The last line of defence before the wire, in the SAME units the server counts against.

    `_load` is cached and the test guards the shipped file, so in practice nothing is dropped here. It exists
    because the cost of being wrong is asymmetric: one term too many is not one town mistranscribed, it is the
    whole session with no transcription."""
    out, chars = [], 0
    for t in terms:
        if len(out) >= MAX_TERMS or chars + len(t) > MAX_CHARS:
            break
        out.append(t)
        chars += len(t)
    return out


def terms(code: str) -> list[str]:
    """Boost terms for a session in `code`, already clamped. Unknown language → empty.

    NOT sent while the language is still being auto-detected. First-run STT runs with `language="multi"` so
    that `i18n.init.detect` can classify the operator's first sentence; seeding Spanish toponyms there would
    bias the very decision that picks the language. The caller enforces this — see `deepgram.py`.
    """
    return _clamp(_load((code or "").strip().lower()))


# ── the memory hook: BUILT, DELIBERATELY OFF ────────────────────────────────────────────────────────────────
#
# Boosting the places and contacts the operator has actually mentioned would beat any static list — his own
# towns are exactly the ones that break. It stays off because turning it on ships personal data (names of
# people he knows, places he has been) to a third party on every session, and that is his decision to make
# with the privacy cost stated, not a default to slip in. The switch is here so that decision costs one env
# var, not a rewrite.
MEMORY_ENV = "ZAELAR_STT_BOOST_FROM_MEMORY"

# The slots it would read, named one by one on purpose. Anything wider ("everything the operator ever said")
# would be impossible to describe to him honestly when he is asked to approve it — and this is a list that
# leaves the machine.
_PERSONAL_SLOTS = ("operator_name", "location", "familia")

_PROPER = re.compile(r"\b[A-ZÁÉÍÓÚÜÑÀÈÌÒÙÇ][\wÁÉÍÓÚÜÑàèìòùáéíóúüñç'’-]{2,}")

# Capitalisation alone does not make a proper noun: memory sentences are DISTILLED prose, so they start with a
# capital verb — «Vive en Calatayud» offered up «Vive» as a term to boost. Dropping the first word instead would
# have been worse, because `operator_name` is exactly one word and it would always be the first. So: an explicit
# list of the openers that show up in distilled state, and nothing cleverer. A word that slips through costs a
# slot; the list itself is the honest description of how dumb this extraction is.
_NOT_A_NAME = frozenset("""
vive reside es esta está era son tiene trabaja nacio nació va viaja conoce quiere usa prefiere
su sus el la los las un una del de en con por para y o no si sí se le les lo hace hay
""".split())


def memory_terms(limit: int = 30) -> list[str]:
    """Proper nouns from the operator's own memory. `[]` unless `ZAELAR_STT_BOOST_FROM_MEMORY` is set.

    Deliberately dumb: capitalised words out of three named state fields. The point of the hook is that the
    decision is one env var away, not that the extraction is clever — a smarter version can replace this
    without touching the privacy boundary, which is the part that needs the operator's answer.
    """
    if (os.getenv(MEMORY_ENV) or "").strip().lower() not in ("1", "true", "yes", "on"):
        return []
    try:
        from memory import api as _mem
        state = _mem.state() or {}
    except Exception:  # noqa: BLE001
        return []
    seen, out = set(), []
    for field in _PERSONAL_SLOTS:
        for word in _PROPER.findall(str(state.get(field) or "")):
            key = word.lower()
            if key in _NOT_A_NAME:
                continue
            if key not in seen:
                seen.add(key)
                out.append(word)
            if len(out) >= limit:
                break
    return out[:limit]


def boost_terms(code: str) -> list[str]:
    """Everything the STT should boost for this session, clamped ONCE — the only function `deepgram.py` calls.

    It exists because of a bug in the first version of this module: the static list and the memory terms were
    each clamped on their own and then added together, so the pair could go over the cap even though neither
    half did. What the server counts is the REQUEST, so the request is what has to be measured.

    The operator's own places go FIRST. If anything has to be dropped it should be a town he has never named,
    not the one he lives in — which is the entire point of the hook.
    """
    return _clamp([*memory_terms(), *terms(code)])
