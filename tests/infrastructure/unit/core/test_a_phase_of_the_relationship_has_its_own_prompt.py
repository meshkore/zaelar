"""Context packs: prompt that exists only during a phase, and archives itself (V2-675).

The operator's direction (2026-09-11): *«un sistema de prompts que podamos inyectar en ciertas fases… de
momento solo tendrá esta parte inicial»* and *«cuando ya hemos terminado con eso, esos prompts iniciales
desaparecen»*.

The invariants worth guarding are the ones that make a phase a PHASE and not a new permanent tax: it costs
nothing when inactive, it can be turned off, and once it is off it never comes back. The phase's own PROSE is
not asserted here on purpose — a test that pins the wording of a prompt makes it unimprovable, and the block
is judged by what the model does with it, not by a substring.
"""
from __future__ import annotations

import asyncio
import re
from pathlib import Path

import pytest

from nucleo import context_packs
from nucleo.context_packs import introduction

ENGINE = Path(__file__).resolve().parents[4]


@pytest.fixture(autouse=True)
def _fresh():
    """Every case starts with a REGISTERED introduction pack and a turn counter at zero — the module is
    process-lived, so without this a case inherits whatever the previous one left."""
    introduction.install()
    introduction._turns = 0
    introduction._judging = False
    yield


@pytest.fixture()
def running(monkeypatch):
    """A live introduction: no flag, a language chosen, nothing known about the operator yet."""
    store = {"stt_language": "es"}
    monkeypatch.setattr("config.settings.get", lambda k, d=None: store.get(k, d))
    monkeypatch.setattr("config.settings.update", lambda patch: store.update(patch))
    monkeypatch.setattr(introduction, "_known", lambda: {})
    return store


# ── the phase runs, and then it does not ────────────────────────────────────────────────────────────────
def test_the_pack_is_composed_while_the_phase_runs(running):
    assert introduction.is_active()
    assert "introduction" in context_packs.active_ids()
    assert context_packs.compose().strip()


def test_a_closed_phase_costs_NOTHING(running):
    introduction.close("test")
    assert running["intro_done"] is True
    assert not introduction.is_active()
    assert context_packs.active_ids() == []
    assert context_packs.compose() == "", "an archived phase is still being paid for on every turn"


def test_the_phase_waits_for_a_language(monkeypatch):
    """While the language ceremony is open nobody has spoken yet (V2-672), and a phase block riding a prompt
    in a language the operator has not chosen is the exact failure that batch closed."""
    monkeypatch.setattr("config.settings.get", lambda k, d=None: {"stt_language": ""}.get(k, d))
    assert not introduction.is_active()


def test_unreadable_settings_mean_NO_phase(monkeypatch):
    """The safe direction is asymmetric: a missing block costs a plainer first conversation, a block that
    cannot be turned off costs every turn forever."""
    def _boom(*a, **k):
        raise OSError("disk")
    monkeypatch.setattr("config.settings.get", _boom)
    assert not introduction.is_active()


def test_closing_twice_writes_once(running):
    introduction.close("first")
    running["intro_done"] = "sentinel"
    introduction.close("second")
    assert running["intro_done"] == "sentinel", "close() is not idempotent — it rewrote a settled flag"


# ── the three exits ─────────────────────────────────────────────────────────────────────────────────────
def test_knowing_his_name_ends_the_phase_with_no_model_call(running, monkeypatch):
    """The cheap exit. Knowing his name is the one fact the introduction exists to learn, and the memory
    writes it on its own — so in the common case this phase ends without a single extra call."""
    def _never(*a, **k):
        raise AssertionError("the judge was called when the deterministic exit was available")
    monkeypatch.setattr(introduction, "_judge_sync", _never)
    monkeypatch.setattr(introduction, "_known", lambda: {"operator_name": "Ricart"})
    introduction._turns = 9
    asyncio.run(introduction._maybe_close())
    assert running.get("intro_done") is True


def test_the_judge_can_end_it_when_the_name_never_arrives(running, monkeypatch):
    monkeypatch.setattr(introduction, "_recent", lambda limit=14: "PERSON: hi\nASSISTANT: hello")
    monkeypatch.setattr(introduction, "_judge_sync", lambda t: True)
    introduction._turns = introduction._JUDGE_AFTER
    asyncio.run(introduction._maybe_close())
    assert running.get("intro_done") is True


def test_an_unreachable_judge_leaves_the_phase_OPEN(running, monkeypatch):
    """Fail-open in the direction that keeps the phase running: a network blip must not silently skip the
    introduction. The cap ends it eventually."""
    monkeypatch.setattr(introduction, "_recent", lambda limit=14: "PERSON: hi")
    def _boom(t):
        raise RuntimeError("no provider")
    monkeypatch.setattr(introduction, "_judge_sync", _boom)
    introduction._turns = introduction._JUDGE_AFTER
    asyncio.run(introduction._maybe_close())
    assert not running.get("intro_done")
    assert introduction.is_active()


def test_the_cap_ends_an_introduction_that_never_ends(running, monkeypatch):
    monkeypatch.setattr(introduction, "_judge_sync", lambda t: False)
    monkeypatch.setattr(introduction, "_recent", lambda limit=14: "PERSON: no")
    introduction._turns = introduction._MAX_TURNS
    asyncio.run(introduction._maybe_close())
    assert running.get("intro_done") is True


def test_the_judge_is_not_asked_on_every_turn(running, monkeypatch):
    """It is off the hot path, not free. Before `_JUDGE_AFTER` nothing is settled, and after it the call is
    rationed — an introduction is a handful of turns and this would otherwise be a model call per turn."""
    calls = []
    monkeypatch.setattr(introduction, "_recent", lambda limit=14: "PERSON: hi")
    monkeypatch.setattr(introduction, "_judge_sync", lambda t: calls.append(1) or False)
    for n in range(0, introduction._MAX_TURNS):
        introduction._turns = n
        asyncio.run(introduction._maybe_close())
    assert 0 < len(calls) < introduction._MAX_TURNS // 2, f"the judge ran {len(calls)} times in 30 turns"


def test_the_judge_never_runs_before_anything_could_have_happened(running, monkeypatch):
    monkeypatch.setattr(introduction, "_recent", lambda limit=14: "PERSON: hi")
    def _never(t):
        raise AssertionError("the judge ran on the very first turns")
    monkeypatch.setattr(introduction, "_judge_sync", _never)
    for n in range(introduction._JUDGE_AFTER):
        introduction._turns = n
        asyncio.run(introduction._maybe_close())


def test_the_judge_reads_a_one_word_answer():
    """Its prompt asks for one word; anything else must not be read as «yes» — a chatty model saying
    «No, they have only exchanged greetings» begins with an N and must stay a no."""
    import nucleo.memllm as memllm
    for raw, expected in (("yes", True), ("Yes.", True), ("sí", True),
                          ("no", False), ("No, they have only exchanged greetings", False), ("", False)):
        orig = memllm.chat_sync
        memllm.chat_sync = lambda *a, **k: raw
        try:
            assert introduction._judge_sync("PERSON: hi") is expected, f"{raw!r}"
        finally:
            memllm.chat_sync = orig


# ── the registry's own rules ────────────────────────────────────────────────────────────────────────────
def test_a_broken_pack_does_not_take_its_NEIGHBOURS_down(monkeypatch):
    """The catch is PER PACK, not one net around the whole section — which is the difference this case
    exists to measure: with a single outer try, one broken pack silently deletes every other phase's
    contribution and the turn goes out with no context at all, looking exactly like the steady state."""
    def _boom():
        raise RuntimeError("pack is broken")
    context_packs.register(context_packs.Pack(id="broken", title="Broken", order=1,
                                              active=lambda: True, block=_boom))
    context_packs.register(context_packs.Pack(id="fine", title="Fine", order=2,
                                              active=lambda: True, block=lambda: "SURVIVOR"))
    try:
        assert "SURVIVOR" in context_packs.compose()
        assert "broken" in context_packs.active_ids()
    finally:
        context_packs._REGISTRY = [p for p in context_packs._REGISTRY
                                   if p.id not in ("broken", "fine")]


def test_a_pack_whose_active_check_raises_is_treated_as_inactive():
    def _boom():
        raise RuntimeError("nope")
    context_packs.register(context_packs.Pack(id="bad", title="Bad", order=1,
                                              active=_boom, block=lambda: "x"))
    try:
        assert "bad" not in context_packs.active_ids()
        assert "x" not in context_packs.compose()
    finally:
        context_packs._REGISTRY = [p for p in context_packs._REGISTRY if p.id != "bad"]


def test_registering_twice_does_not_double_the_block():
    introduction.install()
    introduction.install()
    assert [p.id for p in context_packs.registered()].count("introduction") == 1


def test_packs_are_ordered_by_their_declared_order():
    context_packs.register(context_packs.Pack(id="zzz", title="Z", order=1,
                                              active=lambda: False, block=lambda: ""))
    try:
        assert [p.id for p in context_packs.registered()][0] == "zzz"
    finally:
        context_packs._REGISTRY = [p for p in context_packs._REGISTRY if p.id != "zzz"]


def test_the_section_declares_itself_TEMPORARY(running):
    """Without a header saying so, the model reads a phase instruction as a permanent fact about who it is —
    the one thing a pack must never become."""
    header = context_packs.compose().strip().split("\n")[0]
    assert "temporal" in header.lower()


# ── wiring ──────────────────────────────────────────────────────────────────────────────────────────────
def _code(path: Path) -> str:
    import tokenize
    out, prev_type = [], None
    with open(path, "rb") as fh:
        for tok in tokenize.tokenize(fh.readline):
            if tok.type == tokenize.COMMENT:
                continue
            if tok.type == tokenize.STRING and prev_type in (None, tokenize.INDENT, tokenize.NEWLINE,
                                                             tokenize.NL):
                continue
            out.append(tok.string)
            prev_type = tok.type
    return " ".join(out)


def test_the_prompt_carries_the_packs_after_the_operators_own_directive():
    """A directive is HIS instruction and a pack is OURS, so his is read last of the two."""
    src = _code(ENGINE / "nucleo/flash/prompt.py")
    assert "_packs . compose ( )" in src, "build_flash_system does not compose the context packs"
    i_dir, i_pack = src.index("_directive_block ( directive )"), src.index("_packs . compose ( )")
    assert i_dir < i_pack, "a pack is read before the operator's own directive"


def test_the_phase_is_watched_from_the_bus_and_not_from_the_voice_provider():
    """The Susurro/actionmap pattern: zero coupling with the provider, and it covers BOTH channels for free
    because `observer.turn_detail` is where a voice turn and a probe turn both close."""
    src = _code(ENGINE / "nucleo/context_packs/introduction.py")
    assert re.search(r'bus\s*\.\s*subscribe\s*\(\s*"turn\.completed"\s*\)', src)
    boot = _code(ENGINE / "server/__init__.py")
    assert "_intro_pack . start ( )" in boot, "nothing starts the phase watcher at boot"


def test_the_phrasebook_stands_aside_while_a_phase_is_guiding():
    """The operator's own «excepción al inicio»: during the introduction «hola» is not small talk, it is the
    first move of a conversation that has somewhere to go. Both channels."""
    lane = _code(ENGINE / "voice/engine/llm/providers/fast_lane.py")
    m = re.search(r"async def small_talk\b.*?(?=\ndef |\nasync def |\Z)", lane, re.S)
    assert m and "context_packs . active_ids ( )" in m.group(0), "the voice lane answers during a phase"
    mirror = _code(ENGINE / "nucleo/flash/smalltalk.py")
    assert "context_packs . active_ids ( )" in mirror, "the probe mirror answers during a phase"


def test_the_flag_starts_the_relationship_over_on_a_factory_reset():
    from config import settings
    assert introduction.FLAG in settings.AGENT_KEYS, (
        "the introduction flag records something about the RELATIONSHIP, so «empezar de cero» must clear it")
    assert introduction.FLAG not in settings.INSTALL_KEYS
