"""Two harness faults fixed on 2026-08-23, each with its measured cost, each ratcheted here.

1. THE US DRIVER COULD NEVER SAY GOODBYE. The driver's closing regex and its whole system prompt were
   Spanish-only while 60 of the 133 scenarios are the US locale: an English persona signing off with
   "perfect, thanks!" never matched, so every US round burned its full turn budget by construction and ate
   an efficiency penalty its ES twin never faced. The market-twins guard (same signals, same turns) could
   not see it — the bias lived in the driver, not in the scenarios.

2. AN INFRA VERDICT HELD THE ANSWER AND DID NOT PRINT IT. `cheapest-monitor` died as «INFRA: timed out»
   while the engine's own log ended in `Fetching 5 files… jina-reranker` — the whole diagnosis (a 1.1 GB
   model download blocking the event loop) sat one `tail` away, and rediscovering it took half an hour of
   manual process sampling. Worse, the crash handler recorded `transcript: []`, throwing away the five real
   turns that had already been driven and paid for.
"""
from __future__ import annotations

import socket
import threading

import pytest

from tests.use_cases.e2e.agent import driver as drivermod
from tests.use_cases.e2e.agent import run as runmod
from tests.use_cases.e2e.agent import config as ucconfig


class _Scn:
    """The four attributes Driver actually reads — a scenario stand-in, never the live catalog."""

    def __init__(self, locale: str) -> None:
        self.id = f"dummy__{locale}"
        self.locale = locale
        self.persona_brief = "You want a thing." if locale == "us" else "Quieres una cosa."
        self.opening_line = "hola"


# ── 1 · the goodbye, in both languages ─────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("line", [
    "Perfecto, muchas gracias",
    "Vale, eso es todo. Hasta luego",
    "Genial, gracias.",
    # …and the English half that never matched before 2026-08-23:
    "Perfect, thanks!",
    "Great, thanks.",
    "That's all, thank you.",
    "Nothing else, goodbye",
    "Ok thanks, bye for now",
])
def test_a_closing_line_closes_in_both_languages(line):
    assert drivermod.is_closing(line), line


@pytest.mark.parametrize("line", [
    # Mid-conversation acknowledgments and errands must NOT read as goodbyes, in either language.
    "Gracias por avisar, ¿y el precio?",         # gracias mid-sentence, still asking
    "Please take care of the booking and let me know.",   # an ERRAND, not a farewell
    "Thanks to that filter it should be cheaper, can you rerun it",  # thanks mid-sentence
    # THE line that ended `cheapest-monitor` on turn 2 of 10, measured 2026-08-23. It answers the agent's
    # clarifying question — three new constraints — and signs off politely. Courtesy is a SUFFIX in Spanish,
    # not a message, and reading it as a farewell killed the round before a single search ran.
    "Sí, eso me vale: 27 pulgadas 4K y por debajo de 300 si se puede. Gracias.",
    "Vale, pues busca por debajo de 300 euros. Gracias.",
    "Sure, that works for me, under 300 and 27 inches. Thanks.",
])
def test_an_errand_or_acknowledgment_is_not_a_goodbye(line):
    assert not drivermod.is_closing(line), line


def test_the_us_driver_speaks_english_to_its_own_persona():
    """The system prompt is the steering wheel: a US persona instructed in Spanish to close with «gracias»
    is being pushed out of character on every turn — and its sign-off then cannot match either."""
    sys_us = drivermod.Driver(_Scn("us")).history[0]["content"]
    assert "FIXED IDENTITY" in sys_us
    assert "What day is TODAY" in sys_us
    assert "thanks" in sys_us
    assert "IDENTIDAD FIJA" not in sys_us
    assert "gracias" not in sys_us


def test_the_es_driver_is_untouched():
    """The fix adds a language, it must not move the one already measured against 32 rounds."""
    sys_es = drivermod.Driver(_Scn("es")).history[0]["content"]
    assert "IDENTIDAD FIJA" in sys_es
    assert "Qué día es HOY" in sys_es
    assert "gracias" in sys_es


# ── 2 · the autopsy: alive / wedged / dead, and the log tail ───────────────────────────────────────────────

def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def test_a_dead_engine_is_called_dead(monkeypatch):
    monkeypatch.setattr(ucconfig, "ZAELAR_URL", f"http://127.0.0.1:{_free_port()}")
    monkeypatch.setattr(ucconfig, "SANDBOX_DB", "")
    out = runmod.engine_autopsy("turno 3: timed out")
    assert "MUERTO" in out["engine"], out


def test_a_wedged_engine_is_called_wedged(monkeypatch):
    """A socket that ACCEPTS and never answers — the exact shape of 2026-08-23's blocked event loop. This
    test deliberately spends the probe's 5 s: the distinction alive-vs-wedged is the whole point."""
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]
    conns: list = []
    t = threading.Thread(target=lambda: conns.append(srv.accept()), daemon=True)
    t.start()
    try:
        monkeypatch.setattr(ucconfig, "ZAELAR_URL", f"http://127.0.0.1:{port}")
        monkeypatch.setattr(ucconfig, "SANDBOX_DB", "")
        out = runmod.engine_autopsy("turno 3: timed out")
        assert "CLAVADO" in out["engine"], out
    finally:
        srv.close()
        for c, _ in conns:
            c.close()


def test_the_log_tail_travels_with_the_verdict(tmp_path, monkeypatch):
    """The last log lines ARE the diagnosis (`Fetching 5 files… jina-reranker` was the whole answer). Read
    from the same place `verify.py` derives (`SANDBOX_DB` → workspace/logs/), tail-read so a multi-MB log
    costs nothing, and capped at the last 5 non-empty lines."""
    ws = tmp_path / "ws"
    (ws / "memory" / "_data").mkdir(parents=True)
    db = ws / "memory" / "_data" / "sandbox.db"
    db.write_text("")
    (ws / "logs").mkdir()
    filler = "x" * 200
    lines = [filler] * 600 + ["", "  ", "Fetching 5 files:   0%  jina-reranker"]   # >64 KB before the tail
    (ws / "logs" / "engine.log").write_text("\n".join(lines), encoding="utf-8")
    monkeypatch.setattr(ucconfig, "ZAELAR_URL", f"http://127.0.0.1:{_free_port()}")
    monkeypatch.setattr(ucconfig, "SANDBOX_DB", str(db))
    out = runmod.engine_autopsy("timed out")
    assert out["log_tail"], out
    assert "jina-reranker" in out["log_tail"][-1]
    assert len(out["log_tail"]) <= 5
    assert all(ln.strip() for ln in out["log_tail"])       # blank lines never count as evidence


def test_the_autopsy_never_masks_the_crash(monkeypatch):
    """Fail-soft is load-bearing: an autopsy that raises replaces the real error with its own."""
    monkeypatch.setattr(ucconfig, "ZAELAR_URL", "not-even-a-url")
    monkeypatch.setattr(ucconfig, "SANDBOX_DB", "/nonexistent/x/y/z.db")
    out = runmod.engine_autopsy("boom")
    assert out["error"] == "boom"
    assert out.get("engine")                                # it still classified, however vaguely


# ── 3 · the turns already driven survive the crash ─────────────────────────────────────────────────────────

def test_a_scenario_crash_carries_what_was_already_measured():
    turns = [{"who": "tester", "text": "hola"}, {"who": "zaelar", "text": "dime"}]
    e = runmod.ScenarioCrash("turno 3: timed out", transcript=turns, autopsy={"engine": "CLAVADO"})
    assert e.transcript == turns
    assert e.autopsy == {"engine": "CLAVADO"}
    assert "timed out" in str(e)


def test_the_batch_handler_reads_the_crash_not_an_empty_record():
    """Wiring guard, same pattern as `test_the_wiring_is_in_the_event_handler`: the fix is one except-block
    in `_run_batch`, and an innocent refactor that rebuilds the INFRA row from scratch would silently bring
    back `transcript: []`. Anchored on the handler's own print, which is part of the contract («si tienes
    la respuesta, imprímela»)."""
    import inspect
    src = inspect.getsource(runmod._run_batch)
    i = src.find("scenario crashed")
    assert i != -1
    window = src[i:i + 1600]
    assert 'getattr(e, "transcript"' in window, "el handler ya no rescata los turnos ya conducidos"
    assert 'getattr(e, "autopsy"' in window, "el handler ya no adjunta la autopsia del motor"
    assert "engine_autopsy" in window, "un crash sin autopsia propia ya no recibe una"
    assert "⚕" in window, "la autopsia ya no se imprime en el momento"


# ── a lab round says whether it is measuring on top of an old one ─────────────────────────────────────────

def test_a_lab_round_can_start_from_clean_memory():
    """`--fresh` exists because a lab agent is PERSISTENT: it holds the memory of every round ever driven
    against it. Measured 2026-08-23 — the third attempt at `cheapest-monitor` opened with zaelar saying «tú
    antes hablabas de un 27" 4K por unos 300 euros», a preference from the attempt that died two hours
    earlier. Without the flag the only way to measure clean was to remember to reset by hand first."""
    from tests.use_cases.e2e.agent import run as runmod
    ap = runmod._parser() if hasattr(runmod, "_parser") else None
    if ap is None:                       # the parser is built inline in main(); fall back to the source
        import inspect
        src = inspect.getsource(runmod)
        assert '"--fresh"' in src
        return
    assert ap.parse_args(["--scenario", "x", "--lab", "es", "--fresh"]).fresh is True
    assert ap.parse_args(["--scenario", "x", "--lab", "es"]).fresh is False


def test_a_lab_round_that_did_not_reset_says_so():
    """The failure mode this guards is not a red round — it is a GREEN one nobody questions. The harness
    stamps `memory_carryover` from the cases THIS invocation ran, so a single-case round against a
    long-lived lab reported an empty carryover while the agent demonstrably remembered. Evidence that was
    not wrong, just blind. So the round says it out loud instead."""
    import inspect
    from tests.use_cases.e2e.agent import run as runmod
    src = inspect.getsource(runmod._lab_batch)
    assert "memoria del plató NO borrada" in src
    assert "--fresh" in src


def test_the_reset_is_never_silent():
    """The operator's own rule, and it survives the new flag: a lab agent is what they have open in a
    bookmark, so wiping it is theirs to ask for. `--fresh` is opt-in and announces itself; the default path
    still touches nothing."""
    import inspect
    from tests.use_cases.e2e.agent import run as runmod
    src = inspect.getsource(runmod._lab_batch)
    i_reset = src.index("labs.reset(prof)")
    assert "getattr(args, \"fresh\", False)" in src[:i_reset], "el reset no está detrás del opt-in"
    assert "reseteando el plató" in src[:i_reset], "el reset no se anuncia antes de borrar"
