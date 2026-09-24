"""V2-765 — no language, no agent: until the picker is used, the agent is STOPPED.

Measured 2026-09-24 on the operator's own factory reset: the language picker was on screen, the voice session
was already live behind it, and «Vale, quiero que mejores ahora un poquito» — said to somebody else — was
classified as Spanish, LOCKED the language (`agent.py`'s first-run detection), closed the picker and spoke «Vale
— ya está todo listo en tu idioma». His words: *«no quiero que esté escuchando… es una pantalla sine qua non…
hasta que no se ha inicializado el idioma, no se puede trabajar con él»*.

The gate is the ⏻ switch itself (`nucleo/runstate.py`), derived from the same `stt_language` the picker writes
and a reset wipes — so everything ⏻ already stops (the LiveKit token, workers, background ticks, crons) stops
here too, and there is no second copy of the fact to fall out of step.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from memory import db as memdb
from nucleo import runstate

ENGINE = Path(__file__).resolve().parents[3]


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    """A workspace with NO language: a temp settings file, a temp database, the gate switched back on."""
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    monkeypatch.setenv("ZAELAR_LANGUAGE_GATE", "1")
    monkeypatch.setenv("ZAELAR_LOOP", "0")
    memdb.reset_db()
    memdb.get_db()
    settings_file = tmp_path / "settings.json"
    settings_file.write_text("{}", encoding="utf-8")
    from config import settings as _s
    from i18n.init import detect
    monkeypatch.setattr(_s, "SETTINGS_FILE", settings_file)

    def _update(patch):
        cur = json.loads(settings_file.read_text(encoding="utf-8"))
        cur.update(patch)
        settings_file.write_text(json.dumps(cur), encoding="utf-8")
    monkeypatch.setattr(_s, "update", _update)
    monkeypatch.setattr(detect, "_should_cache", None)
    # lock()'s other halves are not what is under test: the bundle, the memory's language, the progress.
    from i18n import init as _init

    async def _prepare(code):
        return {}
    monkeypatch.setattr(_init, "prepare", _prepare)
    monkeypatch.setattr(detect, "_pending_steps", lambda code: [])

    async def _prio(code):
        return {}
    monkeypatch.setattr(detect, "_priority_translate", _prio)
    from nucleo import dispatch
    monkeypatch.setattr(dispatch, "resume_all", lambda: 0)
    monkeypatch.setattr(dispatch, "pause_all", lambda: 0)
    runs: list[dict] = []
    import voice.observer as obs
    real_emit = obs.emit

    def _emit(kind, label="", **kw):
        if kind == "run":
            runs.append({"label": label, **(kw.get("extra") or {})})
        return real_emit(kind, label, **kw)
    monkeypatch.setattr(obs, "emit", _emit)
    runstate._reset_for_tests()
    runstate._state.update({"value": None})
    yield {"runs": runs, "settings": settings_file}
    runstate._reset_for_tests()
    memdb.reset_db()


def test_a_fresh_install_is_a_stopped_agent_and_says_why(workspace):
    assert runstate.stopped() is True, "no language chosen and the agent reads as running"
    snap = runstate.snapshot()
    assert snap["running"] is False and snap["reason"] == "language" and snap["src"] == "language"
    assert runstate.blocks_new_work(who="test") is True, "a worker could start before the language exists"


def test_the_power_button_cannot_start_it(workspace):
    res = asyncio.run(runstate.start("operator"))
    assert res["ok"] is False and res["reason"] == "language"
    assert runstate.stopped() is True, "⏻ walked past the language picker"


def test_the_picker_is_the_door_out_and_the_agent_starts_with_it(workspace):
    from i18n.init import detect
    res = asyncio.run(detect.lock("es", onboarding=True))
    assert res["ok"]
    assert runstate.stopped() is False, "the language was chosen and the agent stayed stopped"
    starts = [r for r in workspace["runs"] if r["label"] == "start"]
    assert starts and starts[-1]["src"] == "language", (
        "the frontend learns the agent started from the `run` event — without it the tab stays off")


def test_a_later_language_switch_does_not_start_anything(workspace):
    from i18n.init import detect
    asyncio.run(detect.lock("es", onboarding=True))
    asyncio.run(runstate.stop("operator"))
    workspace["runs"].clear()
    asyncio.run(detect.lock("en"))                  # the ⚙ switch
    assert runstate.stopped() is True, "a ⚙ language switch started an agent the operator had stopped"
    assert not [r for r in workspace["runs"] if r["label"] == "start"]


def test_a_fresh_start_forgets_any_earlier_power_off(workspace):
    """«Hay que olvidarse de cuál era el estado anterior… tienen que empezar con todo arrancado» (2026-09-24).
    Measured that evening: ⏻ presses on the boot veil persisted «stopped by the operator», and the agent stayed
    off after he chose his language."""
    runstate._persist(runstate.STOPPED, "operator")
    from i18n.init import detect
    asyncio.run(detect.lock("es", onboarding=True))
    assert runstate.stopped() is False, "a brand-new agent inherited a ⏻ off from before its language existed"


def test_the_voice_can_never_choose_the_language():
    """The path that chose Spanish from a sentence he said to somebody else is gone, not guarded."""
    src = (ENGINE / "voice/engine/pipeline/agent.py").read_text(encoding="utf-8")
    assert "_maybe_detect_language" not in src and ".lock(" not in src, (
        "the voice pipeline locks a language again — the picker must be the only door")


def test_a_turn_heard_without_a_language_never_reaches_the_brain():
    """The backstop for a session that outlived the gate: after the mic switch, before the attention judge."""
    src = (ENGINE / "voice/engine/llm/providers/nucleo.py").read_text(encoding="utf-8")
    mic = src.index("mic_input.blocks_turn(text)")
    gate = src.index("_rs_lang.language_pending()")
    judge = src.index("_attention_turn.judge(")
    assert mic < gate < judge


def test_the_voice_session_is_refused_while_stopped():
    src = (ENGINE / "server/livekit_api.py").read_text(encoding="utf-8")
    assert "if runstate.stopped():" in src and '"engine_stopped"' in src


def test_a_factory_reset_also_forgets_the_power_button():
    """With memory KEPT, a ⏻ off from before the reset survives in `sys_kv`; the picker would then lift its gate
    onto «stopped by the operator» and the brand-new agent would stay off with nothing saying why."""
    src = (ENGINE / "scripts/reset-memory.sh").read_text(encoding="utf-8")
    factory = src[src.index('if [[ "$FACTORY" == "1" ]]; then'):src.index("# 6) THE AGENT'S FILES")]
    assert "kv_del('run:state')" in factory
