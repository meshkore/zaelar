"""V2-749 — the three seams that turn a correct spotter into a cheaper microphone.

`test_the_cheap_ear_spots_the_name.mjs` proves the RULES (what counts as the name, what travels with it,
when parking is licensed). This file proves the WIRING, which is the half that fails silently: every one of
these modules would keep working perfectly with the new code present and unreached, and the only symptom
would be a bill that did not go down.

The disarm that governs the file: delete any one of the calls asserted below and this goes red. If it does
not, the assertion is describing the code instead of holding it.
"""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
SSE = ROOT / "frontend" / "app" / "services" / "sse.js"
SESSION = ROOT / "frontend" / "app" / "services" / "session-lk.js"
AGENT = ROOT / "voice" / "engine" / "pipeline" / "agent.py"
EAR = ROOT / "frontend" / "app" / "services" / "wakeword.js"


def _src(p: Path) -> str:
    assert p.exists(), f"{p} is gone — the seam moved and this test has to move with it"
    return p.read_text(encoding="utf-8")


# ── 1 · the wall asks before it paints ─────────────────────────────────────────────────────────────────
def test_the_provisional_line_goes_through_the_predicate_and_not_around_it():
    s = _src(SSE)
    assert "paintsProvisional(store.attentionMode(), store.attentionHit())" in s, \
        "the interim branch must ASK — a second unguarded call is how the erased text came back"
    # The old unconditional call is the exact shape of the bug he reported. One guarded call, no other.
    assert s.count("captionPartial(d.text)") == 1
    assert "captionPartial(d.text);\n" not in s.replace(
        "if (paintsProvisional(store.attentionMode(), store.attentionHit())) captionPartial(d.text);\n", "")


def test_the_predicate_is_imported_from_the_module_that_owns_the_rules():
    # Not re-implemented in `sse.js`: two copies of one rule is how the caption and the tap would come to
    # disagree about whether the agent is listening.
    assert 'import { paintsProvisional } from "./wakeword.js' in _src(SSE)


# ── 2 · ⚠️ the tap never closes over an ear that is not running ────────────────────────────────────────
def test_parking_is_gated_on_the_recogniser_having_actually_started():
    s = _src(SESSION)
    assert "function _applyPark()" in s, "one place decides it, or the effect and the callback will drift"
    park = s.split("function _applyPark()", 1)[1].split("\n}", 1)[0]
    for needed in ("wake.armed()", "store.agentLive()", "store.attentionHit()", "store.micMuted()"):
        assert needed in park, f"the park decision must read {needed} — see the deafness note in wakeword.js"
    assert "_wakeMode()" in park


def test_the_arming_pushes_the_decision_because_it_is_not_a_signal():
    s = _src(SESSION)
    assert "onArmed: () => _applyPark()" in s, \
        "`armed()` flips inside the recogniser's own callbacks; an effect alone is subscribed to nothing"


def test_a_stopped_session_leaves_the_tap_open():
    # A parked tap that outlives its session is an agent that comes back deaf, and the operator would have
    # no way to tell that from a broken microphone.
    s = _src(SESSION)
    head = s.split("export async function stop() {", 1)[1][:400]
    assert "wake.stop()" in head and "setTapParked(false)" in head


def test_the_tap_never_writes_the_microphone_switch():
    # `voice/mic_input.py` carries a standing rule (operator, 2026-09-10): the mic switch and the attention
    # mode «may never be written in terms of each other». The tap is a third axis and it meets the switch at
    # exactly one line — the transport. If parking ever reached `mic.setMuted` it would be persisted to
    # localStorage and POSTed to the engine, and the icon would start lying about what he chose.
    s = _src(SESSION)
    park_block = s.split("export function setTapParked(", 1)[1].split("\nexport function tapParked", 1)[0]
    for forbidden in ("mic.setMuted", "setMicMuted", "hb_mic_muted", "api.micState"):
        assert forbidden not in park_block, f"parking must not touch {forbidden}"


# ── 3 · the engine understands what the browser sends ──────────────────────────────────────────────────
def test_the_engine_answers_the_wake_topic():
    s = _src(AGENT)
    assert 'topic == "zaelar-wake"' in s, "a topic nobody handles fails SILENTLY: the sentence just vanishes"
    after = s.split('if topic == "zaelar-wake":', 1)[1]
    block = after.split("if topic ==", 1)[0]          # up to the next topic branch, not the first `return`
    assert "note_preroll(" in block, "the words before the name are the point of the whole design"
    assert "generate_reply(" in block, "…and the turn still has to be answered"


def test_the_browser_publishes_on_the_topic_the_engine_listens_on():
    # One misspelling on either side and this feature is inert with nothing in the log to say so.
    s = _src(SESSION)
    assert 'topic: "zaelar-wake"' in s and '"t": "zaelar-wake"' in s.replace("t: \"zaelar-wake\"", '"t": "zaelar-wake"')


@pytest.mark.parametrize("name", ["normalize", "spotIn", "wakeNames", "paintsProvisional", "armed", "takeTail"])
def test_the_rules_stay_exported_for_the_test_to_drive(name):
    # The V2-647 lesson: the moment one of these stops being reachable, its `.mjs` starts testing a copy.
    assert f"export function {name}(" in _src(EAR)
