"""V2-460 — a stage agent starts with a BLANK session, not with last week's screen.

Operator rule (2026-08-28), stated while looking at a freshly started ES agent that opened showing the results
sheet from a car-rental assignment from days earlier: «the first thing to do when launching a use case test is
to reset and leave the session clean for all processes. You can keep the memory or basic state, but everything
else must be ready to start a blank session and focus observability on the task and test in progress.»

The runner had already been doing this BEFORE EVERY CASE since 2026-08-21 (same complaint, another path). What
was missing was manual startup: a stage agent is intentionally persistent —that is the reason for the fixed
port— so its canvas, background work, and observability window survive the PROCESS, because what persists is the
workspace on disk. And what survives is exactly what makes a run unreadable: the ◷ viewer cannot distinguish
«this test» from «what was there before».
"""
from __future__ import annotations

import json

import pytest

from tests.use_cases.lab import profiles as LP, stage


@pytest.fixture()
def lab(monkeypatch, tmp_path):
    """Fake stage: it neither starts an engine nor writes to the operator's real workspace."""
    monkeypatch.setattr(stage, "LAB_ROOT", tmp_path)
    monkeypatch.setattr(stage, "seed_profile", lambda p: {"state": 4, "pills": 2})
    monkeypatch.setattr(stage, "seed_provider_chain", lambda ws: "aimlapi → deepseek")
    monkeypatch.setattr(stage, "_restore_kv", lambda ws, carried: None)

    class _Proc:
        pid = 4242

    def _spawn(**kw):
        return type("E", (), {"process": _Proc(), "base_url": f"http://127.0.0.1:{kw['port']}"})()

    monkeypatch.setattr(stage, "spawn_engine", _spawn)
    # `_alive` checks the pid for REAL (if it always returned True, `up()` would believe one was already running
    # and exit without starting anything), and nothing responds on the port before startup (if something did,
    # `up()` would read it as a FOREIGN engine on our port and refuse — which is correct in production).
    monkeypatch.setattr(stage, "_alive", lambda pid: bool(pid))
    monkeypatch.setattr(stage, "_get", lambda url, timeout=2.0: None)
    return tmp_path


def _meta(profile) -> dict:
    return json.loads((stage.workspace_of(profile) / "lab.json").read_text(encoding="utf-8"))


# ── startup ──────────────────────────────────────────────────────────────────────────────────────────────
def test_arrancar_deja_la_sesion_en_blanco(monkeypatch, lab):
    posted: list[tuple[str, dict]] = []
    monkeypatch.setattr(stage, "_post", lambda url, payload, timeout=60.0: posted.append((url, payload))
                        or {"session": "abc12345", "reset": {}})
    _, st = stage.up(LP.ES, voice=False)
    assert posted, "arrancó sin limpiar: el operador abre el puerto y ve la ronda anterior"
    assert st.cleaned is True
    assert _meta(LP.ES)["cleaned"] is True


def test_se_limpia_por_RESET_HARD_y_jamas_por_el_que_REINICIA(monkeypatch, lab):
    """The two halves of the rule, and the second is the dangerous one.

    `/reset/hard` stops the processes and clears the LIVE canvas, keeping memory and profile — what makes this
    agent Marc from Madrid, in other words the only thing that cannot be thrown away. `/api/reset/full` with
    `wipe_memory` would also do something else: relaunch the engine with `make run` in the REAL engine
    directory, and `scripts/run-livekit.sh` kills every `python -m server` by NAME — it would take down both
    the stage AND the operator's engine.
    """
    urls: list[str] = []
    monkeypatch.setattr(stage, "_post", lambda url, payload, timeout=60.0: urls.append(url) or {})
    stage.clean_session(LP.ES)
    assert urls == [f"http://127.0.0.1:{LP.ES.port}/reset/hard"]
    assert not any("reset/full" in u for u in urls)


def test_cada_agente_se_limpia_en_SU_puerto(monkeypatch, lab):
    """One stage cleaning the other would be worse than not cleaning: it kills a run's work when it was going well."""
    urls: list[str] = []
    monkeypatch.setattr(stage, "_post", lambda url, payload, timeout=60.0: urls.append(url) or {})
    stage.clean_session(LP.US)
    assert str(LP.US.port) in urls[0] and str(LP.ES.port) not in urls[0]


# ── when it CANNOT be achieved ───────────────────────────────────────────────────────────────────────────
def test_una_limpieza_que_falla_no_tumba_el_arranque_pero_SE_DICE(monkeypatch, lab):
    """Requesting the cleanup is not the same as achieving it — a lesson that already cost an entire batch in the runner,
    where a fixed two-second wait printed «engine reset» no matter what happened.

    A running agent with a dirty screen still measures; one that refuses to start measures nothing. So it is
    not fatal, but the state says so and the CLI prints it both ways.
    """
    monkeypatch.setattr(stage, "_post", lambda url, payload, timeout=60.0: None)
    _, st = stage.up(LP.ES, voice=False)
    assert st.cleaned is False
    assert _meta(LP.ES)["cleaned"] is False


def test_el_estado_ARRASTRA_la_limpieza_o_la_CLI_no_puede_decirla(lab):
    ws = stage.workspace_of(LP.ES)
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "lab.json").write_text(json.dumps({"pid": 1, "port": LP.ES.port, "cleaned": True}), encoding="utf-8")
    assert stage.status(LP.ES).cleaned is True
    (ws / "lab.json").write_text(json.dumps({"pid": 1, "port": LP.ES.port}), encoding="utf-8")
    assert stage.status(LP.ES).cleaned is False, "sin el campo se asume SUCIO, que es lo que no engaña"


# ── what must NOT be taken down ──────────────────────────────────────────────────────────────────────────
def test_la_memoria_y_el_perfil_NO_se_tocan_al_limpiar(monkeypatch, lab):
    """The other half of the rule («you can keep the memory or basic state»), and it is not a detail: the
    seeded profile is what makes «find me a plumber» resolve to Madrid without anyone naming the city.
    Deleting it would turn every cleanup into a case measuring someone else."""
    llamado = {"wipe": 0, "seed": 0}
    monkeypatch.setattr(stage, "wipe", lambda p: llamado.__setitem__("wipe", llamado["wipe"] + 1) or {})
    monkeypatch.setattr(stage, "seed_profile", lambda p: llamado.__setitem__("seed", llamado["seed"] + 1))
    monkeypatch.setattr(stage, "_post", lambda url, payload, timeout=60.0: {"session": "x"})
    stage.clean_session(LP.ES)
    assert llamado == {"wipe": 0, "seed": 0}, "limpiar la sesión no puede tocar la memoria ni resembrar"
