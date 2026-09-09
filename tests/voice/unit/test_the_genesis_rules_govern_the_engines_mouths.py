"""V2-633 — the genesis style rules govern the engine's OWN mouths, and a spoken rule overrides them on
the very next turn.

Measured live (session 6c715232, 2026-09-09): the operator's rule «al recibir órdenes no responder nada»
was set AND persisted by set_style_directive — and «Reproduce el vídeo» still produced «Déjame ver…» (the
lead-in filler) plus «Hecho.» (the never-mute backstop / the fast lane's V2-572 ack). The model obeyed;
the ENGINE spoke. Three mouths talk without the model and none of them consulted any rule.

The fix is a policy with the operator's requested layering: shipped defaults in `nucleo/genesis.json`
(short orders run in silence; fillers "smart" — never covering a turn that is itself a short order), and
per-install overrides written by the directive handler in the SAME turn, read per use — so «confírmame las
órdenes» governs the next utterance without any restart. Voice mouths only: chat keeps its text acks
(an empty chat bubble looks broken; a written «Hecho.» interrupts nobody), so the probe is untouched.
"""
from __future__ import annotations

import asyncio
import json
import pathlib

import pytest
from livekit.agents.types import FlushSentinel

from nucleo import style_policy as sp
from voice.engine.speech import filler_audio as fa

ENGINE = pathlib.Path(__file__).resolve().parents[3]


class _Brain:
    _last_filler = ""
    _last_spoken = ""
    _last_spoke_at = 0.0
    _last_ack = ""


@pytest.fixture(autouse=True)
def _isolated(monkeypatch, tmp_path):
    """Every case runs against a THROWAWAY workspace: the policy's override file must never be the
    operator's real one (a unit test never touches live artifacts)."""
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    monkeypatch.setenv("ZAELAR_FILLER_MS", "50")
    sp._reset_for_tests()
    fa._reset_for_tests()
    yield
    sp._reset_for_tests()
    fa._reset_for_tests()


# ── 1 · the genesis defaults are the operator's order ────────────────────────────────────────────────────

def test_genesis_ships_silent_short_orders_and_smart_fillers():
    assert sp.confirm_short_actions() is False, "genesis: a pause that pauses needs no «Hecho.»"
    assert sp.filler_mode() == "smart"
    assert sp.filler_allowed("action") is False, "«reproduce el vídeo» must not get «un segundo…»"
    assert sp.filler_allowed("neutral") is True, "a question that takes real work keeps its cover"


def test_the_genesis_file_is_real_and_valid():
    data = json.loads((ENGINE / "nucleo/genesis.json").read_text(encoding="utf-8"))
    assert isinstance(data.get("style"), dict) and "confirm_short_actions" in data["style"]


def test_the_missing_media_verbs_now_classify_as_action():
    """«Reproduce el vídeo.» read as "neutral" and got a thinking cover — the literal annoyance."""
    for t in ("Reproduce el vídeo.", "Reanuda la música", "Salta esta canción", "Siguiente canción",
              "Resume the video", "Skip this song"):
        assert fa.filler_kind(t) == "action", t
    assert fa.filler_kind("¿Puedes reproducir el vídeo?") == "neutral", "a question still thinks"


# ── 2 · a spoken rule flips the flags instantly, and retiring it restores genesis ────────────────────────

def test_a_directive_overrides_and_a_retraction_restores():
    assert sp.apply_directive("quiero que me confirmes las órdenes") == {"confirm_short_actions": True}
    assert sp.confirm_short_actions() is True, "the override governs the very next read"
    released = sp.retract_directive("olvida lo de confirmarme las órdenes")
    assert "confirm_short_actions" in released
    assert sp.confirm_short_actions() is False, "back to genesis"


def test_the_operators_literal_sentence_parses():
    flags = sp._flags_for("Al recibir órdenes no responder nada; ejecutar directamente, "
                          "sin confirmar ni repetir lo hecho.")
    assert flags == {"confirm_short_actions": False}


def test_prose_the_mouths_cannot_act_on_changes_nothing(tmp_path):
    assert sp.apply_directive("llámame siempre capitán") == {}
    assert not (tmp_path / "config" / "style.json").exists(), "no override file for a no-op"


def test_overrides_persist_in_the_workspace_not_the_repo(tmp_path):
    sp.apply_directive("no me confirmes las órdenes")
    p = tmp_path / "config" / "style.json"
    assert p.exists(), "the override must live under the workspace (cloud Machine = its Volume)"
    assert json.loads(p.read_text())["confirm_short_actions"] is False


# ── 3 · the filler consults the policy at FIRE time ──────────────────────────────────────────────────────

def _inner_llm(*, first_after: float):
    async def impl(agent, chat_ctx, tools, model_settings):
        await asyncio.sleep(first_after)
        yield "Ya está el vídeo."
    return impl


async def _collect(impl):
    out = []
    async for c in fa.llm_node_with_filler(None, impl, None, None, None):
        out.append(c)
    return out


def test_a_slow_ACTION_turn_gets_no_filler_under_genesis():
    fa.arm(_Brain(), "Reproduce el vídeo.")
    out = asyncio.run(_collect(_inner_llm(first_after=0.3)))
    assert not any(isinstance(c, FlushSentinel) for c in out), f"a filler covered an order: {out}"
    assert out == ["Ya está el vídeo."]


def test_the_same_turn_gets_its_filler_back_when_the_operator_asks():
    sp.apply_directive("vuelve a las muletillas")           # fillers: "on"
    fa.arm(_Brain(), "Reproduce el vídeo.")
    out = asyncio.run(_collect(_inner_llm(first_after=0.3)))
    assert any(isinstance(c, FlushSentinel) for c in out), "fillers:on must cover even an action turn"


def test_a_slow_QUESTION_still_gets_its_cover_by_default():
    fa.arm(_Brain(), "¿Qué tiempo hará mañana en Soria?")
    out = asyncio.run(_collect(_inner_llm(first_after=0.3)))
    assert any(isinstance(c, FlushSentinel) for c in out), "smart keeps the thinking cover"


def test_fillers_off_silences_even_the_thinking_cover():
    sp.apply_directive("nada de muletillas")
    fa.arm(_Brain(), "¿Qué tiempo hará mañana en Soria?")
    out = asyncio.run(_collect(_inner_llm(first_after=0.3)))
    assert not any(isinstance(c, FlushSentinel) for c in out)


# ── 4 · the fast lane's ack rides the policy ─────────────────────────────────────────────────────────────

def _run_fast_lane(monkeypatch):
    from nucleo import actionmap as amap
    from voice.engine.llm.providers import fast_lane

    monkeypatch.setattr(amap, "enabled", lambda: True)
    monkeypatch.setattr(amap, "match", lambda t: {"id": 1, "source": "seed"})
    monkeypatch.setattr(amap, "execute", lambda hit, emit, phrase="": True)
    monkeypatch.setattr(amap, "describe", lambda hit: "widget_data:youtube:pause")
    from memory import api as mem
    monkeypatch.setattr(mem, "write", lambda *a, **k: None)      # live DB stays untouched
    spoken = []

    async def _fake_ack(brain):
        spoken.append("ack")
    monkeypatch.setattr(fast_lane, "_speak_ack", _fake_ack)

    class _B:
        _acc = None
        _window: list = []
    handled = asyncio.run(fast_lane.handled(_B(), "pausa el vídeo", lambda *a, **k: None,
                                            first_turn=False, t_entry=0.0, window_max=40))
    assert handled is True, "the lane itself must still resolve the turn"
    return spoken


def test_the_fast_lane_runs_in_silence_under_genesis(monkeypatch):
    assert _run_fast_lane(monkeypatch) == [], "V2-572's ack is now opt-in: pause and say nothing"


def test_the_fast_lane_confirms_again_when_the_operator_asks(monkeypatch):
    sp.apply_directive("confírmame las órdenes")
    assert _run_fast_lane(monkeypatch) == ["ack"]


# ── 5 · the provider's never-mute backstops and the prompt line are wired (source contracts) ─────────────

def test_the_voice_backstops_consult_the_policy():
    src = (ENGINE / "voice/engine/llm/providers/nucleo.py").read_text(encoding="utf-8")
    assert 'if data_done["v"] and not spoken_text and _ack_allowed' in src, \
        "the data-op «Hecho.» backstop must be gated by the style policy"
    assert 'if acted["widget"] and not spoken_text and _ack_allowed' in src, \
        "the show/close «Aquí lo tienes» backstop must be gated too"
    assert "_style_ack.confirm_short_actions()" in src
    # The directive handler was extracted (ratchet): both channels delegate to style_directive.py, which
    # is where the flags must move in the SAME turn.
    shared = (ENGINE / "nucleo/flash/style_directive.py").read_text(encoding="utf-8")
    assert "apply_directive(" in shared and "retract_directive(" in shared, \
        "set_style_directive must move the flags in the SAME turn"
    assert "style_directive" in src, "the voice channel must delegate to the shared handler"


def test_the_model_prompt_carries_the_silence_rule_only_while_silent():
    line = sp.prompt_line()
    assert line and "no digas nada" in line.lower()
    sp.apply_directive("confírmame las órdenes")
    assert sp.prompt_line() == "", "with confirmations on, the model keeps its old manners"
    src = (ENGINE / "nucleo/flash/prompt.py").read_text(encoding="utf-8")
    assert "prompt_lines(" in src, "prompt.py must append the runtime-mode lines (wake-word + silence)"
    shared = (ENGINE / "nucleo/flash/style_directive.py").read_text(encoding="utf-8")
    assert "prompt_line()" in shared, "style_directive.prompt_lines must carry the policy line"


# ── 6 · the stuck apology is for turns that produced NOTHING (V2-634) ────────────────────────────────────

def test_an_acted_but_silent_turn_never_gets_the_stuck_apology():
    """Measured live (session b828c901): with silent orders on, a turn that executed play_video ended with
    empty spoken_text and fell into the mute backstop — four «se me ha ido» apologies over turns that had
    worked, reading as not-understanding. The backstop must be gated on the turn having done NOTHING, and a
    context-bleed dedupe counts as handled (a deliberately ignored duplicate is not a void to apologize for)."""
    src = (ENGINE / "voice/engine/llm/providers/nucleo.py").read_text(encoding="utf-8")
    assert "if not spoken_text and not _tool_handled:" in src, \
        "the mute backstop must skip turns that acted (V2-633 silence is design, not a void)"
    # V2-646 narrowed this by ONE state, and the narrowing is the point: a deduped duplicate still counts as
    # handled on a SPOKEN turn (that is V2-634's lesson, dragged-in room noise deserves silence), but never on
    # a TYPED one — nobody types by accident, and a written question that got a vetoed action and no words is
    # the void this backstop exists for (measured live 22:30:39, completion_chars=0).
    assert 'or (deduped["v"] and not _typed_turn)' in src, \
        "a deduped duplicate order was HANDLED — it must still count into _tool_handled for spoken turns"
    assert "_typed_turn = attention.was_typed()" in src, \
        "and the typed exception must read the real fact, not assume it"
    assert 'deduped["v"] = True' in src, "the context-bleed guard must mark the turn as handled"
