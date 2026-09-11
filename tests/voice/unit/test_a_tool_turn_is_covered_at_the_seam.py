"""A turn that calls a TOOL is covered at the seam, not only before the model (V2-669, 2026-09-11).

The operator, after the model moved to a slower/better one: «si una pregunta como a qué hora tengo esta
actividad en la agenda tarda 8 segundos en resolverse, necesitamos alguna frase o palabra de relleno… o
incluso más rápido que dijera "dame unos segundos", porque si tenemos una locución demasiado larga
alargaremos innecesariamente el tiempo de respuesta».

MEASURED before building anything, from his own observability (`memory/_data/zaelar.db`, `deepseek-v4-pro`):

  · the `read_widget` turn that answers «¿a qué hora tengo la cita con Hacienda?» took **6 029 ms**, with
    `ttft_ms: 0` — the first pass returned a TOOL CALL and no text at all, so the reply stream stayed empty
    across the whole turn.
  · across 7 real voice turns that took a light route, the turn ENDED 3.4-5.9 s AFTER the tool event, while
    the lead-in filler had sounded 1.0-3.3 s BEFORE it. The lead-in's ~1 s of audio was long over.

So there is a hole of several seconds on the FAR side of the tool seam that nothing covered: the lead-in is
chosen ~1.1 s in, before any model has spoken, and by construction it cannot know what is coming. The work
cover is chosen once the router has already decided, which is why it can NAME the source — and that is what
keeps two covers from reading as the same wait twice, the failure this codebase already met once (V2-189,
session 2bdc67ee: «Déjame que mire…» then «Vale, dame un momento que lo miro.» back to back).

These tests drive the REAL node wrapper with fake inner generators, exactly like its sibling
`test_filler_audio.py`: the contract is about ORDER, CONDITIONS and what reaches the transcript.
"""
from __future__ import annotations

import asyncio
import inspect

import pytest
from livekit.agents.types import FlushSentinel

from voice.engine.core import langs
from voice.engine.speech import filler_audio as fa


class _Brain:
    def __init__(self):
        self._last_filler = ""
        self._last_spoken = ""
        self._last_spoke_at = 0.0


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    fa._reset_for_tests()
    monkeypatch.setenv("ZAELAR_FILLER_MS", "50")
    monkeypatch.setattr(fa, "_WORK_GRACE_S", 0.02)
    monkeypatch.setattr(fa, "_ARM_GRACE_S", 0.05)   # the real 0.8 s only delays the UNARMED case, and in a
                                                    # live turn the tool note lands ~3 s in, long past it
    monkeypatch.setattr(fa, "_COVER_MIN_GAP_S", 0.05)
    yield
    fa._reset_for_tests()


def _shape(out):
    return ["FLUSH" if isinstance(c, FlushSentinel) else c for c in out]


def _inner(*, note_at: float | None, first_after: float, kind: str = "widget", target: str = "Agenda",
           brain=None, chunks=("Tienes la cita a las 11:30.",)):
    """A fake provider: it publishes its work note mid-flight (which is exactly what the real voice provider
    does at the light-route seam) and only then produces the second pass's first chunk."""
    async def impl(agent, chat_ctx, tools, model_settings):
        if note_at is None:
            await asyncio.sleep(first_after)
        else:
            await asyncio.sleep(note_at)
            fa.note_work(brain or _Brain(), kind, target)
            await asyncio.sleep(max(first_after - note_at, 0.0))
        for c in chunks:
            yield c
    return impl


def _run(impl):
    async def go():
        out = []
        async for c in fa.llm_node_with_filler(None, impl, None, None, None):
            out.append(c)
        return out
    return asyncio.run(go())


# ── the hole the operator measured ────────────────────────────────────────────────────────────────────────

def test_the_far_side_of_the_tool_seam_is_covered(monkeypatch):
    """The measured shape: lead-in at ~1 s, tool at ~3 s, answer at ~6 s. Before this, the stretch between
    the tool and the answer was silence."""
    monkeypatch.setattr(fa, "_pick_phrase", lambda brain, kind="neutral", phrase="": "Voy a mirarlo…")
    fa.arm(_Brain())
    out = _shape(_run(_inner(note_at=0.20, first_after=0.60)))
    assert out[:2] == ["Voy a mirarlo… ", "FLUSH"], f"the lead-in still comes first — got {out}"
    assert out[-1] == "Tienes la cita a las 11:30.", f"the reply must arrive untouched — got {out}"
    assert len(out) == 5, f"expected lead-in + FLUSH + cover + FLUSH + reply — got {out}"
    assert out[3] == "FLUSH", "the cover needs its own FlushSentinel or it is retained and arrives glued"


def test_the_cover_NAMES_where_we_are_looking(monkeypatch):
    """This is the whole reason a second cover is not a second stall: it carries information the blind
    lead-in could not — WHERE the answer is being looked for."""
    monkeypatch.setattr(fa, "_pick_phrase", lambda brain, kind="neutral", phrase="": "Voy a mirarlo…")
    fa.arm(_Brain())
    out = _shape(_run(_inner(note_at=0.20, first_after=0.60, target="Agenda")))
    assert "Agenda" in out[2], f"the cover must name the card it is reading — got {out[2]!r}"


def test_a_turn_whose_lead_in_never_sounded_is_still_covered(monkeypatch):
    """Nothing armed (an action turn under the "smart" policy, or an arm that lost its race). The tool wait
    is exactly as long, so the cover is MORE needed here, not less."""
    out = _shape(_run(_inner(note_at=0.20, first_after=0.60, kind="search")))
    assert len(out) == 3 and out[1] == "FLUSH", f"expected cover + FLUSH + reply — got {out}"
    # the ACTIVE language's pool, never a hardcoded one — this suite runs under the default (English) and
    # asserting Spanish here would only measure which pool the harness happens to sit in
    assert out[0].strip() in langs.spec(None).covers_search, f"unexpected search cover {out[0]!r}"


# ── the counterweights: when it must stay quiet ───────────────────────────────────────────────────────────

def test_a_fast_second_pass_BEATS_the_cover(monkeypatch):
    """The same rule the lead-in has: if the answer is already there, saying we are going to look for it is
    pure added latency — a cover cannot be cut mid-sentence, so its own length is delay."""
    monkeypatch.setattr(fa, "_pick_phrase", lambda brain, kind="neutral", phrase="": "Voy a mirarlo…")
    fa.arm(_Brain())
    out = _shape(_run(_inner(note_at=0.20, first_after=0.205)))
    assert out == ["Voy a mirarlo… ", "FLUSH", "Tienes la cita a las 11:30."], \
        f"a reply inside the grace must arrive with no work cover — got {out}"


def test_two_of_OUR_OWN_waits_never_sound_back_to_back(monkeypatch):
    """V2-189, session 2bdc67ee: «Déjame que mire…» followed by «Vale, dame un momento que lo miro.» The
    guard is measured from the lead-in's FIRE, because this node cannot know how long its TTS took."""
    monkeypatch.setattr(fa, "_pick_phrase", lambda brain, kind="neutral", phrase="": "Voy a mirarlo…")
    monkeypatch.setattr(fa, "_COVER_MIN_GAP_S", 5.0)
    fa.arm(_Brain())
    out = _shape(_run(_inner(note_at=0.10, first_after=0.50)))
    assert out == ["Voy a mirarlo… ", "FLUSH", "Tienes la cita a las 11:30."], \
        f"a cover on the lead-in's heels must be held — got {out}"


def test_only_ONE_cover_per_turn(monkeypatch):
    """A route that re-publishes its note (a retry, a second light route in one turn) must not turn the turn
    into a monologue of waits."""
    brain = _Brain()

    async def impl(agent, chat_ctx, tools, model_settings):
        await asyncio.sleep(0.15)
        fa.note_work(brain, "widget", "Agenda")
        await asyncio.sleep(0.15)
        fa.note_work(brain, "search")
        await asyncio.sleep(0.20)
        yield "Ya está."

    out = _shape(_run(impl))
    assert out.count("FLUSH") == 1, f"exactly one cover may sound — got {out}"


def test_the_operators_no_fillers_rule_silences_the_cover_too(monkeypatch):
    """`fillers: off` is a rule he gave by voice. A mouth that keeps talking through it is the V2-633 bug."""
    import nucleo.style_policy as sp
    monkeypatch.setattr(sp, "filler_allowed", lambda kind="neutral": False)
    out = _shape(_run(_inner(note_at=0.20, first_after=0.60)))
    assert out == ["Tienes la cita a las 11:30."], f"no cover may sound with fillers off — got {out}"


# ── what the cover must never pollute ─────────────────────────────────────────────────────────────────────

def test_the_cover_is_taken_OUT_of_the_transcript(monkeypatch):
    """Same contract as the lead-in: it is real speech and it is shown as its own marked chat-wall event,
    never inside the reply's bubble nor in the model's own history."""
    out = _shape(_run(_inner(note_at=0.20, first_after=0.60, kind="search")))
    cover = out[0].strip()
    assert fa.strip_if_filler(cover), "the cover must be pending removal from the forwarded transcript"


def test_the_cover_never_becomes_the_REPLY_CONTEXT(monkeypatch):
    """The 2026-08-17 bug, one mechanism over: a cover carries no topic, so feeding it to the
    directed-content judge gets the operator's NEXT turn classified as room noise."""
    brain = _Brain()
    brain._last_reply = "sentinel"
    _run(_inner(note_at=0.20, first_after=0.60, brain=brain, kind="recall"))
    assert brain._last_reply == "sentinel", "a cover may update anti-echo, never the reply context"
    assert brain._last_spoken and brain._last_spoken != "sentinel", "anti-echo MUST see what we said"


# ── the catalog ───────────────────────────────────────────────────────────────────────────────────────────

def test_every_shipped_language_covers_all_three_light_routes():
    for code in ("es", "en"):
        s = langs.spec(code)
        for field in ("covers_widget", "covers_search", "covers_recall"):
            pool = getattr(s, field, ()) or ()
            assert pool, f"[{code}] ships no {field}"
            for phrase in pool:
                assert len(phrase) <= 45, f"[{code}] cover too long ({len(phrase)}c): {phrase!r} — a cover " \
                                          "cannot be cut mid-sentence, so its length IS latency"


def test_a_widget_cover_with_nothing_to_NAME_says_nothing():
    """Silence beats «Lo miro en …». The template is what makes this detectable."""
    for _ in range(20):
        assert langs.pick_cover("widget", target="") == ""


def test_an_unknown_route_gets_no_cover():
    assert langs.pick_cover("", target="x") == ""
    assert langs.pick_cover("escalate", target="x") == ""


def test_the_cover_never_repeats_the_lead_in_that_just_sounded():
    lead = langs.spec(None).covers_search[0]
    for _ in range(30):
        assert langs.pick_cover("search", last=lead) != lead


# ── wiring: both light routes of the VOICE channel, and deliberately NOT the text channel ─────────────────

def test_all_three_light_routes_of_the_voice_channel_cover_their_seam():
    src = inspect.getsource(__import__("voice.engine.llm.providers.nucleo", fromlist=["x"]))
    assert "_fa_w.note_work(brain, kind, target)" in src, "the voice channel must publish its work note"
    for call in ('_cover_work("widget"', '_cover_work("recall")', '_cover_work("search")'):
        assert call in src, f"the light route is not covered at its seam: {call}"


def test_the_TEXT_channel_covers_nothing_on_purpose():
    """The probe has no dead air to fill — its answer appears when it appears — so the parallel-implementation
    rule (V2-252) deliberately does not reach this one, and that is written down instead of left as drift."""
    src = inspect.getsource(__import__("nucleo.flash.probe", fromlist=["x"]))
    assert "note_work" not in src, "a work cover in the text channel would be a mouth nobody asked for"
