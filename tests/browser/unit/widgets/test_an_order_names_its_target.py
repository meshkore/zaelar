"""V2-666 · an order NAMES its target — a show never lands on the card that merely happens to be open, and a
sentence that names its widget is never treated as «muéstramelo».

Measured live, session 53de97d4 (2026-09-11):
  · 10:33:27 — «ponme un gráfico de la evolución del Bitcoin de este último año» with the YouTube card open:
    `runtime.identify` returned `youtube` with score 0.0 and zero candidates (`by_context: True`), the show
    guard consumed it as a NAME, stole the model's escalation, opened the video card and said «Aquí lo tienes».
  · 10:59:10 — «Mírame, ábreme la agenda inmediatamente» opened the SEARCH card: the article «la» is a bare
    deictic token, so the whole sentence was «muéstramelo»-shaped, the noun he said was discarded, and the
    fallback «the previous route was a web search» chose for him.

Both channels are driven — the voice provider's guard and the probe's mirror — because the decision exists twice
(V2-252). The deictic continuity these guards were built for («Vale, pues muéstramelo» after a weather question)
is asserted alongside, so the fix cannot be a regression dressed as a rule.
"""
from __future__ import annotations

import pytest

from widgets import runtime

_BITCOIN = "Ponme ahí... Johnny, ponme un gráfico de la evolución del Bitcoin de este último año."
_AGENDA = "Pero ¿cómo que no? Mírame, ábreme la agenda inmediatamente."
_PRIOR = [{"role": "user", "content": "Olvídate de eso, respóndeme a la pregunta que te he hecho lo primero."}]


@pytest.fixture
def _youtube_open(monkeypatch):
    """The canvas state the incident had: exactly ONE card open, the video player."""
    from memory import api as _memapi
    monkeypatch.setattr(_memapi, "state", lambda: {"open_widgets": ["youtube"], "recent_widgets": ["youtube"]})


# ── the resolver itself ──────────────────────────────────────────────────────────────────────────────────
def test_identify_still_hands_back_the_only_open_card_by_context():
    """The data-op nuance is intact — «súbele el volumen» with one card open must keep operating it."""
    r = runtime.identify(_BITCOIN, open_ids=["youtube"])
    assert r["match"] == "youtube" and r["by_context"] is True and r["candidates"] == []


def test_identify_named_refuses_the_by_context_fallback():
    assert runtime.identify_named(_BITCOIN, open_ids=["youtube"]) is None
    assert runtime.identify_named(_BITCOIN) is None


def test_identify_named_keeps_a_real_name_with_or_without_context():
    assert runtime.identify_named(_AGENDA) == "agenda"
    assert runtime.identify_named(_AGENDA, open_ids=["youtube"], recent_ids=["search"]) == "agenda"


# ── the voice provider's show guard ───────────────────────────────────────────────────────────────────────
def test_the_voice_guard_never_opens_the_only_open_card_for_a_sentence_that_names_nothing(_youtube_open):
    from voice.engine.llm.providers import widget_intent
    assert widget_intent._show_guard_target(_BITCOIN, [], "") is None
    # …so the model's escalation stands instead of a blind «Aquí lo tienes» over the video player.


def test_the_voice_guard_resolves_the_named_widget_even_after_a_web_search(_youtube_open):
    from voice.engine.llm.providers import widget_intent
    assert widget_intent._show_guard_target(_AGENDA, _PRIOR, "search") == "agenda"


def test_the_voice_guard_keeps_the_deictic_continuity(monkeypatch):
    """The rule the guard was built for (V2-300) still holds: a bare «muéstramelo» takes its noun from the
    previous topic. The stub goes where the function LOOKS (V2-555)."""
    from voice.engine.llm.providers import widget_intent
    monkeypatch.setattr(widget_intent, "_identify",
                        lambda text: "meteo-soria" if "tiempo" in text.lower() else None)
    ctx = [{"role": "user", "content": "¿Qué tiempo hará mañana aquí?"}]
    assert widget_intent._show_guard_target("Vale, pues muéstramelo.", ctx, "") == "meteo-soria"


def test_the_voice_guard_keeps_the_search_continuity_for_a_bare_pronoun():
    """«muéstramelo» right after a WEB SEARCH still means the search surface — that continuity was never the
    defect; applying it to a sentence that NAMED the agenda was."""
    from voice.engine.llm.providers import widget_intent
    if runtime.get("search") is None:
        pytest.skip("no search surface in this catalog")
    ctx = [{"role": "user", "content": "¿A cuánto está el bitcoin?"}]
    assert widget_intent._show_guard_target("Vale, pues muéstramelo.", ctx, "search") == "search"


# ── the probe's mirror ────────────────────────────────────────────────────────────────────────────────────
def test_the_probe_mirror_agrees_on_both_measured_sentences(_youtube_open):
    from nucleo.flash import show_target
    assert show_target._show_target(_BITCOIN, [], "") is None
    assert show_target._show_target(_AGENDA, _PRIOR, "search") == "agenda"


def test_the_probe_mirror_keeps_the_deictic_continuity(monkeypatch):
    from nucleo.flash import show_target
    monkeypatch.setattr(show_target, "_identify_ctx",
                        lambda _rt, text: "meteo-soria" if "tiempo" in text.lower() else None)
    ctx = [{"role": "user", "content": "¿Qué tiempo hará mañana aquí?"}]
    assert show_target._show_target("Vale, pues muéstramelo.", ctx, "") == "meteo-soria"


def test_both_channels_ask_the_named_resolver_first():
    """A wiring guard on the CHANNELS (V2-555): the name must be consulted before any deictic hunt, in both."""
    import re
    from pathlib import Path
    for rel, fn in (("voice/engine/llm/providers/widget_intent.py", "_identify_named("),
                    ("nucleo/flash/show_target.py", "_identify_named_ctx(")):
        src = Path(rel).read_text(encoding="utf-8")
        code = re.sub(r"(?m)^\s*#.*$", "", src)
        named = code.index(fn)
        deictic = code.index("deictic = (")
        assert named < deictic, f"{rel}: the name must win before the deictic hunt runs"
        assert "return _identify(text)\n" not in code and "return _identify_ctx(runtime, text)\n" not in code, \
            f"{rel}: the by-context fallback must not be the guard's last word"
