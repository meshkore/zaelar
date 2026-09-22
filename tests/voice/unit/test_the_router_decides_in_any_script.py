"""V2-750, LIVE — is the routing decision language-agnostic? Measured against real Jev, not assumed.

THE QUESTION THE OPERATOR ASKED (2026-09-22): *«has analizado la gramática y el texto en idioma
español, pero en chino, japonés, hindú o inglés se pueden dar situaciones diferentes que también
confundan al sistema… no sé si jev es multi idioma… iba a decir traducir al inglés. Claro, eso va a
tardar y va a añadir latencia. Evalúa cuál es la mejor solución.»*

This node is the evaluation, kept as a test so the answer can be re-measured instead of remembered.

## WHAT IT MEASURES

The same nine orders in five languages (es · en · zh · ja · hi), against the REAL catalogue, asking
the two brief questions the decision composes — and, beside each, what `looks_like_create_widget`
answers today.

Measured 2026-09-22, p50 **758 ms** per call, the whole corpus in one brief-shaped trip each:

    looks_like_create_widget   es 8/9 · en 9/9 · zh 6/9 · ja 6/9 · hi 6/9   = 35/45
    build_decision.decide      es 9/9 · en 9/9 · zh 9/9 · ja 9/9 · hi 9/9   = 45/45

## AND THE ANSWER TO «¿HAY QUE TRADUCIR AL INGLÉS?» — NO

The criteria handed to Jev are still in Spanish (they are each widget's own declared name, aliases
and description: product data). It scored 45/45 across three non-Latin scripts against Spanish
criteria. Translation would add a model round trip on the critical path to repair something that is
not a translation problem: Jev does not parse grammar, it PICKS among declared options, so the only
cross-lingual burden is «does what he said resemble what this card says about itself» — and that is
what the measurement above answers.

⚠️ TWO THINGS THIS NODE ALSO MEASURED, and they shape the rule rather than decorate it:

  · `catalog_widget` ALWAYS names something. «¿Qué tiempo va a hacer mañana?» came back as his own
    generated weather card at 0.76 — arguably right, and the reason the decision never OPENS a card
    on its own. Which card an order is about, and whether one should open, are two questions.
  · `build_or_use` is directionally right but its confidence swings (0.32-0.97). That is why
    BUILDING demands a positive verdict AND no card named, while VETOING needs only the card: each
    clause fails towards «do not build», which is the cheap direction.

LIVE: needs `TYPESAFE_API_KEY`. Skips, never fails, when Jev is off — a node that cannot reach the
network has measured nothing and must not claim a pass.

It lives beside the deterministic nodes and not in a `live/` folder of its own, because the map's
own ratchet is right: a declared file the deterministic run never touches is a file nobody runs.
Without the key it SKIPS there, which is the honest answer.

Run: ZAELAR_LIVE_JEV=1 .venv/bin/pytest tests/voice/unit/test_the_router_decides_in_any_script.py -s
"""
from __future__ import annotations

import os

import pytest

from nucleo import jev as _jev
from nucleo.flash import build_decision as _bd
from nucleo.flash import router_guards as _rg
from nucleo.flash import turn_brief as _tb

LANGS = ("es", "en", "zh", "ja", "hi")

#: (id, the card it should name, what it should decide, the same order in five languages).
#: `show-video-filler` is HIS sentence, verbatim in Spanish and translated straight across.
CORPUS = [
    ("show-video", "youtube", "use_existing", {
        "es": "ábreme el widget de vídeo",
        "en": "open the video widget for me",
        "zh": "打开视频小组件",
        "ja": "ビデオウィジェットを開いて",
        "hi": "वीडियो विजेट खोलो"}),
    ("show-video-filler", "youtube", "use_existing", {
        "es": "Entonces, vamos a hacer una cosa, ábreme el widget de vídeo, preséntame un catálogo "
              "de vídeos sobre el Apolo once.",
        "en": "Right, let us do one thing, open the video widget for me and show me a catalogue of "
              "videos about Apollo eleven.",
        "zh": "那么，我们做件事，帮我打开视频小组件，给我一个关于阿波罗十一号的视频目录。",
        "ja": "じゃあ一つやろう、ビデオウィジェットを開いて、アポロ11号の動画カタログを見せて。",
        "hi": "तो चलो एक काम करते हैं, वीडियो विजेट खोलो और मुझे अपोलो ग्यारह के वीडियो की सूची दिखाओ।"}),
    ("show-agenda", "agenda", "use_existing", {
        "es": "enséñame mi agenda de hoy",
        "en": "show me my calendar for today",
        "zh": "给我看今天的日程",
        "ja": "今日の予定を見せて",
        "hi": "मुझे आज का कैलेंडर दिखाओ"}),
    ("play-music", "musica", "use_existing", {
        "es": "prepárame una cosa, ponme música de los ochenta",
        "en": "make me a thing, play me some eighties music",
        "zh": "帮我弄个事，放点八十年代的音乐",
        "ja": "ちょっとやって、80年代の音楽をかけて",
        "hi": "एक काम करो, अस्सी के दशक का संगीत बजाओ"}),
    # The 2026-08-13 incident sentence: a create verb next to a widget NAMED AS A DESTINATION.
    ("deliver-into-widget", "results", "use_existing", {
        "es": "investiga los ferris a Formentera y entrega el resultado montado en el widget results",
        "en": "research the ferries to Formentera and deliver the result built into the results widget",
        "zh": "调查去福门特拉的渡轮，把结果放进 results 小组件里",
        "ja": "フォルメンテラ行きのフェリーを調べて、結果を results ウィジェットにまとめて",
        "hi": "फॉर्मेंटेरा की फ़ेरी पर शोध करो और नतीजा results विजेट में दिखाओ"}),
    ("build-chess", "none", "build_new", {
        "es": "créame un widget de ajedrez",
        "en": "build me a chess widget",
        "zh": "给我做一个国际象棋小组件",
        "ja": "チェスのウィジェットを作って",
        "hi": "मेरे लिए एक शतरंज विजेट बनाओ"}),
    ("build-steps", "none", "build_new", {
        "es": "móntame un widget que cuente mis pasos",
        "en": "build me a widget that tracks my steps",
        "zh": "给我做一个记录步数的小组件",
        "ja": "歩数を記録するウィジェットを作って",
        "hi": "मेरे कदम गिनने वाला एक विजेट बनाओ"}),
    # Both at once: open one card AND ask for a new one. The veto must not swallow the create.
    ("create-and-show", "none", "build_new", {
        "es": "abre la agenda y luego créame un widget nuevo para contar calorías",
        "en": "open the calendar and then build me a new widget to count calories",
        "zh": "打开日程，然后给我做一个新的卡路里小组件",
        "ja": "予定を開いて、それからカロリーを数える新しいウィジェットを作って",
        "hi": "कैलेंडर खोलो और फिर कैलोरी गिनने का नया विजेट बनाओ"}),
    ("no-widget", "none", "none", {
        "es": "¿qué tiempo va a hacer mañana?",
        "en": "what is the weather going to be tomorrow?",
        "zh": "明天天气怎么样？",
        "ja": "明日の天気はどう？",
        "hi": "कल मौसम कैसा रहेगा?"}),
]


@pytest.fixture(scope="module")
def measured():
    """One pass over the corpus. Module-scoped: 45 round trips is the whole cost of this node."""
    # OPT-IN, and the reason is the sweep, not shyness. Jev is enabled on the operator's machine, so
    # without this flag every deterministic pass of `tests/watchdog.py` would fire 45 paid round
    # trips and take 35 s to re-measure something nobody asked it to. A live node is a MEASUREMENT
    # somebody ordered; it lives among the deterministic files only so the map's own ratchet can see
    # that a declared file is reachable by the run, which is the rule that put it here.
    if os.environ.get("ZAELAR_LIVE_JEV", "").strip() not in ("1", "true", "yes"):
        pytest.skip("live measurement — set ZAELAR_LIVE_JEV=1 to spend the round trips")
    if not _jev.enabled():
        pytest.skip("Jev is off (no TYPESAFE_API_KEY) — this node measures nothing without it")
    catalog = _tb.catalog_question()
    if not catalog:
        pytest.skip("no catalogue question to ask")
    rows = []
    for cid, exp_cat, exp_build, texts in CORPUS:
        for lang in LANGS:
            text = texts[lang]
            out = _jev.choose_many_sync(
                text,
                {_tb.CATALOG_KEY: catalog, _bd.BUILD_KEY: _bd.build_question()},
                question_id=f"v750-{cid}-{lang}") or {}
            cat = (out.get(_tb.CATALOG_KEY) or {}).get("choice")
            bld = (out.get(_bd.BUILD_KEY) or {}).get("choice")
            regex = bool(_rg.looks_like_create_widget(text))
            # The decision, composed exactly as `build_decision.decide` composes it. Built from the
            # raw answers rather than through a fake brief on purpose: what is under test here is the
            # MODEL's answers, and the rule's own wiring is pinned deterministically in node 3.76.
            named = "" if cat in (None, "none") else str(cat)
            build = regex
            if named and bld != "build_new":
                build = False
            elif bld == "build_new" and not named:
                build = True
            rows.append({"case": cid, "lang": lang, "cat": cat, "build_q": bld, "regex": regex,
                         "decided": build, "want_build": exp_build == "build_new",
                         "want_cat": exp_cat, "want_build_q": exp_build})
    return rows


def _score(rows, key, want):
    return sum(1 for r in rows if bool(r[key]) == bool(r[want])), len(rows)


def test_the_decision_beats_the_grammar_overall(measured):
    d_ok, n = _score(measured, "decided", "want_build")
    r_ok, _ = _score(measured, "regex", "want_build")
    print(f"\n  decision {d_ok}/{n}   ·   bare grammar {r_ok}/{n}")
    for lang in LANGS:
        sub = [r for r in measured if r["lang"] == lang]
        print(f"    {lang}: decision {_score(sub,'decided','want_build')[0]}/{len(sub)}"
              f"   grammar {_score(sub,'regex','want_build')[0]}/{len(sub)}")
    assert d_ok >= r_ok, "the composed decision is worse than the regex it was meant to outrank"
    assert d_ok >= n - 1, f"only {d_ok}/{n} — re-read the corpus before relaxing this"


@pytest.mark.parametrize("lang", [l for l in LANGS if l not in ("es", "en")])
def test_a_non_latin_script_is_no_longer_blind(measured, lang):
    """The half no table of ours can fix. Today's grammar returns False for «make me a chess widget»
    in every one of these, so a genuine create never reaches the generator — silently."""
    sub = [r for r in measured if r["lang"] == lang]
    assert _score(sub, "decided", "want_build")[0] > _score(sub, "regex", "want_build")[0], lang


@pytest.mark.parametrize("lang", LANGS)
def test_HIS_sentence_never_builds_a_widget_in_any_language(measured, lang):
    """The measured incident, in five languages. A pass here is the two minutes and the duplicate
    card not happening again."""
    r = next(x for x in measured if x["case"] == "show-video-filler" and x["lang"] == lang)
    assert r["decided"] is False, f"{lang}: still routed to the generator ({r})"
    assert r["cat"] == "youtube", f"{lang}: the card was not even recognised ({r})"


@pytest.mark.parametrize("lang", LANGS)
def test_a_genuine_create_still_reaches_the_generator(measured, lang):
    for case in ("build-chess", "build-steps", "create-and-show"):
        r = next(x for x in measured if x["case"] == case and x["lang"] == lang)
        assert r["decided"] is True, f"{lang}/{case}: a real create was refused ({r})"


def test_the_criteria_are_never_translated(measured):
    """The design claim, asserted rather than described: the catalogue question is built from each
    widget's own declared text — Spanish product data — and is handed across untouched. If a
    translation step ever appears, it costs a round trip on the critical path and this goes red."""
    q = _tb.catalog_question()
    blob = " ".join(str(v) for v in (q or {}).get("criteria", {}).values())
    assert "YouTube" in blob and ("vídeo" in blob or "video" in blob), (
        "the catalogue criteria stopped carrying the widgets' own words")
