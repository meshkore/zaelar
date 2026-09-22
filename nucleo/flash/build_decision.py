"""nucleo/flash/build_decision.py — does this turn reach the WIDGET GENERATOR, or a card that exists?

THE DEFECT THIS EXISTS FOR (live session b41925f6, 2026-09-22). The operator said, with the YouTube
card already on his screen:

    «Entonces, vamos a hacer una cosa, ábreme el widget de vídeo, preséntame un catálogo de vídeos
     sobre el Apolo once.»

`router_guards.looks_like_create_widget` answered True, so the `show_widget` tool was redirected to
the generator, a Brain Worker opened, and two minutes later there was a brand-new duplicate video
player in his catalogue called **`entonces-vamos-cosa`** — named after «Entonces, vamos a hacer una
cosa». The match was literally `hacer una cosa, abreme el widget`: `_CREATE_WIDGET_RE` allows 45
characters of anything between a create verb and the word «widget» and never asks whether the verb
GOVERNS it. «Vamos a hacer una cosa» is a discourse opener, not an order to make something.

And the turn's own verdict had already answered correctly — `catalog_widget = youtube` at **1.00**,
read by nobody, and `screen_action = youtube:search` at 0.91, read and overruled.

## WHY A GRAMMAR TABLE CANNOT BE THE ONE THAT DECIDES

Measured across five languages (the five-language corpus of node 2.68), `looks_like_create_widget` is not
Spanish-biased — it is **Latin-script only**, and it is wrong in both directions:

| | today's regex | this module |
|---|---|---|
| es | 8/9 | 9/9 |
| en | 9/9 | 9/9 |
| zh | **6/9** | 9/9 |
| ja | **6/9** | 9/9 |
| hi | **6/9** | 9/9 |

Its misses in zh/ja/hi are all the same shape: «チェスのウィジェットを作って» (make me a chess widget)
returns False, so in those languages **the generator is unreachable by voice** — a silent absence,
which is the failure mode nobody reports. Adding CJK and Devanagari verb tables would be the same
mistake in three more scripts: a list of the forms somebody remembered. See CLAUDE.md, «UNA TABLA DE
VERBOS NO ES UN ENRUTADOR».

## THE RULE, AND WHY IT IS A COMPOSITION AND NOT A REPLACEMENT

Two verdicts that the turn brief already pays for in the same round trip (N questions cost one trip;
measured p50 758 ms over the corpus, and read 2-4 s later — nobody waits):

  · `catalog_widget` — which card of the catalogue the order NAMES, enumerated from each widget's own
    declared name, aliases and description. 25/25 across the five languages on the show cases.
  · `build_or_use` — build something new, use something that exists, or neither.

```
VETO   catalog_widget names a card, at or above the gate, and build_or_use is not «build_new»
       → the generator is refused, whatever the grammar says
ADD    build_or_use says «build_new», at or above the gate, and catalog_widget is «none»
       → the generator is reached, even where the grammar is blind
else   today's path, bit for bit: the grammar proposes
```

The two clauses are deliberately asymmetric. The VETO is what repairs the measured incident and it
can only ever *refuse* work — the cheap direction, since refusing wrongly costs a card that opens
instead of a card that gets written. The ADD is what makes a genuine create reachable in a script no
table of ours can read, and it demands a POSITIVE verdict: building a widget is two minutes and a new
folder in his catalogue, so it should require a yes, not merely the absence of a no.

⚠️ `catalog_widget` ALWAYS names something. «¿Qué tiempo va a hacer mañana?» came back as his own
generated weather card at 0.76 — arguably right, and exactly why this module never OPENS anything on
its own. Which card an order is about, and whether a card should open at all, are two questions; the
second one is `canvas`, and it has its own reader.
"""
from __future__ import annotations

#: The brief key. Its twin `catalog_widget` lives in `turn_brief` because it is a screen question;
#: this one is about the catalogue as a whole, so its wording lives with the decision it serves.
BUILD_KEY = "build_or_use"

BUILD_INSTRUCTIONS = (
    "The operator gave an order. Does it ask us to BUILD A NEW card that does not exist yet, or to "
    "use a card that already exists in the catalogue? Answer 'build_new' only when he is asking for "
    "something to be made. Answer 'use_existing' when a card in the catalogue already does it. "
    "Answer 'none' when the order is not about a card at all.")

BUILD_CHOICE = {
    "build_new": "he asks us to create/generate/program a NEW card that does not exist yet",
    "use_existing": "a card that already exists in the catalogue can serve this order",
    "none": "the order is not about opening or building a card",
}


def build_question() -> dict:
    """The question, for the turn brief. Always worth asking: it costs no round trip of its own."""
    return {"instructions": BUILD_INSTRUCTIONS, "criteria": dict(BUILD_CHOICE)}


def named_card(brief) -> str:
    """Which card of ours the order names — "" when none does, or when the verdict is unsure.

    Read from WHICHEVER TWIN the brief asked. `turn_brief.build` asks `screen_action` when something
    is open and `catalog_widget` when nothing is, on purpose (with cards open the ACTION is what
    disambiguates: 0.94 vs 0.26 measured), and this module must not make it ask both — two answers
    about one order in one brief is the thing that design avoids. `screen_action` names its owner in
    the key itself (`youtube:search`), so both shapes answer the same question here.
    """
    if not brief:
        return ""
    try:
        from nucleo.flash import direct_action as _da, turn_brief as _tb
        owner, _action = _da.from_brief(brief)      # screen_action, re-validated against what is open
        if owner:
            return str(owner)
        cat, _c = _tb.read(brief, _tb.CATALOG_KEY, "")
        cat = str(cat or "").strip()
        return "" if cat == "none" else cat
    except Exception:  # noqa: BLE001
        return ""


def verdicts(brief) -> tuple[str, str]:
    """`(named card, build_or_use)` as the gate already filtered them — "" when absent or unsure.

    `build_or_use` goes through `turn_brief.read`, so an unsure verdict reads as absence and this
    module answers «no opinion», which is today's path. Never raises: a classifier may not break a
    turn.
    """
    if not brief:
        return ("", "")
    try:
        from nucleo.flash import turn_brief as _tb
        bld, _b = _tb.read(brief, BUILD_KEY, "")
        return (named_card(brief), str(bld or "").strip())
    except Exception:  # noqa: BLE001
        return ("", "")


def decide(text: str, *, brief=None, proposed: bool | None = None) -> tuple[bool, str]:
    """`(build_a_new_widget, why)`. `why` is "" when nothing but the grammar had an opinion.

    `proposed` is the grammar's answer; left out, it is asked for. The caller passes it when it has
    already computed it, so the two never disagree about the same sentence.
    """
    if proposed is None:
        try:
            from nucleo.flash import router_guards as _rg
            proposed = bool(_rg.looks_like_create_widget(text))
        except Exception:  # noqa: BLE001
            proposed = False
    cat, bld = verdicts(brief)
    # VETO — an order that names a card we already have is not an order to write one.
    if cat and bld != "build_new":
        return (False, f"named={cat}")
    # ADD — a create the grammar cannot see, in a script it cannot read. It demands a POSITIVE
    # verdict AND no card named: two independent signals agreeing, each failing towards «do not
    # build», which is the cheap direction.
    if bld == "build_new" and not cat:
        return (True, f"{BUILD_KEY}=build_new")
    return (bool(proposed), "")
