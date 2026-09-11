"""nucleo/flash/verb_forms.py — English verb inflections for the deterministic guards (V2-677).

WHY THIS EXISTS. Every grammar guard in this codebase is bilingual by declaration and monolingual in
practice. The Spanish side is written with open suffixes — `cierr\\w*`, `pon(?:er|iendo|dr[aáeé])\\w*`,
`muestr\\w*` — so it catches the whole conjugation. The English side is a list of BARE STEMS:
`close|hide|play|put|load|show`. English inflects too, and the forms an operator actually speaks are
exactly the ones a bare stem misses: the gerund after a preposition or an auxiliary («go on WITH PLAYING
the video», «start PLAYING it», «keep SHOWING me») and the third person.

Measured live 2026-09-11, session 366787ed, English session: «With playing the Neil Armstrong video.» was
read as licensing nothing and the load was eaten as context-bleed — four times in two minutes, while the
same order in Spanish («ponme el vídeo») has worked since V2-664. The operator's own reading of it was
«va mejor en castellano», and he was right: it did, and this file is why.

A guard written verb by verb goes stale the same way twice. What keeps it honest is that the FORMS are
derived, not typed: add a stem to a license and its inflections come with it, and the node's test asserts
that every English stem in every license matches its own four forms.

Nothing here decides anything — it builds regex fragments. No I/O, no state, stdlib only.
"""
from __future__ import annotations

# Verbs whose final consonant doubles before a vowel suffix (CVC + stress on the last syllable).
_DOUBLE = frozenset({"put", "stop", "drop", "set", "cut", "run", "get", "skip", "flip", "swap", "plan",
                     "trim", "pin", "quit", "fit", "bit"})

# Where the regular rules lie. Values are the COMPLETE form list; the stem is added by `forms()`.
_IRREGULAR: dict[str, tuple[str, ...]] = {
    "show":   ("shows", "showing", "showed", "shown"),
    "find":   ("finds", "finding", "found"),
    "put":    ("puts", "putting"),                      # past = the stem
    "get":    ("gets", "getting", "got", "gotten"),
    "bring":  ("brings", "bringing", "brought"),
    "go":     ("goes", "going", "went", "gone"),
    "leave":  ("leaves", "leaving", "left"),
    "make":   ("makes", "making", "made"),
    "keep":   ("keeps", "keeping", "kept"),
    "hide":   ("hides", "hiding", "hid", "hidden"),
    "quit":   ("quits", "quitting"),
    "shrink": ("shrinks", "shrinking", "shrank", "shrunk"),
    "take":   ("takes", "taking", "took", "taken"),
    "come":   ("comes", "coming", "came"),
    "give":   ("gives", "giving", "gave", "given"),
    "blow":   ("blows", "blowing", "blew", "blown"),
}

_SIBILANT = ("s", "x", "z", "ch", "sh", "o")


def forms(stem: str) -> tuple[str, ...]:
    """Every inflected form of one English verb: the stem, third person, gerund and past.

    Irregulars come from the table above; everything else follows the three regular rules (sibilant `-es`,
    silent-e dropped before `-ing`/`-ed`, final consonant doubled for the CVC verbs).
    """
    s = (stem or "").strip().lower()
    if not s:
        return ()
    if s in _IRREGULAR:
        return (s,) + _IRREGULAR[s]
    third = s + ("es" if s.endswith(_SIBILANT) else "s")
    if s in _DOUBLE:
        root = s + s[-1]
        return (s, third, root + "ing", root + "ed")
    if s.endswith("e") and not s.endswith("ee"):
        return (s, third, s[:-1] + "ing", s + "d")
    if s.endswith("y") and len(s) > 2 and s[-2] not in "aeiou":
        # «apply» → applies/applying/applied
        return (s, s[:-1] + "ies", s + "ing", s[:-1] + "ied")
    return (s, third, s + "ing", s + "ed")


def alternation(*stems: str) -> str:
    """A regex fragment (no anchors, no group) matching any inflected form of any stem given.

    Longest first, so an alternation never settles for a prefix of a longer form it also contains.
    """
    out: set[str] = set()
    for st in stems:
        out.update(forms(st))
    return "|".join(sorted(out, key=lambda w: (-len(w), w)))
