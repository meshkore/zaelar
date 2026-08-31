"""V2-389 — the guard refuses to measure, and afterward NOBODY restarts anything.

`run.stale_engine_refusal` does the right thing: if the stage runs code older than the tree, it REFUSES. What
was missing was what happens afterward. The round enters the journal as INFRA in ~45 s, the supervisor moves to
the next scenario… and that one refuses too, and the next one, and the next one. The loop looks alive —the journal
fills up, the scenarios rotate, no round hangs— and it measures NOTHING.

Measured on 2026-08-27: `search-buy-camera__es` INFRA in 45 s, and it continued only because I was watching and
manually restarted it within a minute. With two agents pushing engine changes every ~20 minutes, that is not an
oddity: it is the default state of an unattended batch. And it is exactly the opposite of the operator's request
("that the system not stop"), made worse by the fact that a stopped loop that keeps writing to the journal does not
look stopped.
"""
from __future__ import annotations

import pytest

from tests.use_cases.e2e.agent import supervisor as S


@pytest.fixture
def bucle(monkeypatch):
    """Drives ONE iteration of the real loop, with the round and restart replaced by witnesses."""
    visto = {"rondas": [], "reinicios": 0, "apuntes": []}

    def _reinicia(lab="es"):
        visto["reinicios"] += 1
        return visto.get("_reinicio_ok", True)

    def _una_ronda(esc, lab="es"):
        visto["rondas"].append(esc)
        # the first attempt is stale; the one after restarting is not
        rancio = visto.get("_rancio_siempre", False) or len(visto["rondas"]) == 1
        return {"escenario": esc, "resultado": "INFRA" if rancio else "FAIL",
                "segundos": 45, "sha": "abc", "motivo": "", "log": "", "_rancio": rancio}

    monkeypatch.setattr(S, "_reinicia_plato", _reinicia)
    monkeypatch.setattr(S, "una_ronda", _una_ronda)
    monkeypatch.setattr(S, "_apunta", lambda **kw: visto["apuntes"].append(kw))
    monkeypatch.setattr(S, "rotacion", lambda: ["un-caso"])
    monkeypatch.setattr(S, "_recargar_si_cambie", lambda *_a, **_k: None)
    monkeypatch.setattr(S, "_huella", lambda: "")
    monkeypatch.setattr(S.time, "sleep", lambda *_a: (_ for _ in ()).throw(_Basta()))
    return visto


class _Basta(Exception):
    """Stops the `while True` at the end of the first iteration."""


def _una_vuelta():
    with pytest.raises(_Basta):
        S.main()


def test_una_ronda_perdida_por_plato_rancio_se_REPITE(bucle):
    """The heart of it: without this, the round is treated as spent and the scenario is not measured until the next iteration."""
    _una_vuelta()
    assert bucle["reinicios"] == 1, "the stage must be restarted, rather than continuing to measure against old code"
    assert bucle["rondas"] == ["un-caso", "un-caso"], "the round that encountered stale code is repeated"


def test_el_reinicio_queda_APUNTADO(bucle):
    """A silent restart leaves the journal saying that the round simply failed twice."""
    _una_vuelta()
    assert any(a.get("resultado") == "RECARGA-PLATO" for a in bucle["apuntes"])


def test_si_el_plato_NO_levanta_no_se_repite_la_ronda(bucle):
    """Repeating against a stage that did not start measures the same thing: nothing."""
    bucle["_reinicio_ok"] = False
    _una_vuelta()
    assert bucle["rondas"] == ["un-caso"]


def test_un_plato_que_sigue_rancio_NO_entra_en_bucle(bucle):
    """The branch on the other side: retrying until it works turns a stage that does not start into an infinite
    loop that measures nothing — the same failure in another guise."""
    bucle["_rancio_siempre"] = True
    _una_vuelta()
    assert bucle["rondas"] == ["un-caso", "un-caso"], "ONE repetition, not N"
    assert bucle["reinicios"] == 1


def test_una_ronda_SANA_no_reinicia_nada(bucle):
    """And the other direction: a normal FAIL must not cost a stage restart, which throws the session the operator
    is watching out from under them."""
    bucle["rondas"].append("—ya-hubo-una—")     # so the first real round is not stale
    _una_vuelta()
    assert bucle["reinicios"] == 0


class _ProcesoQueImprime:
    """Fake Popen: writes to the round log what the runner would print and then exits."""

    def __init__(self, texto):
        self._texto, self.pid = texto, 424242

    def __call__(self, _argv, cwd=None, stdout=None, stderr=None, start_new_session=None):
        stdout.write(self._texto); stdout.flush()
        return self

    def poll(self):
        return 0

    def wait(self, timeout=None):
        return 0


_REHUSA = ("✗ el motor que va a contestar corre d5771e5 y el arbol esta en 1882d30: "
           "no es el mismo codigo.\n")


@pytest.mark.parametrize("salida, rancio", [
    (_REHUSA, True),
    ("  tester  · hola\n  zaelar  · qué tal\nPASSED 0/1 (overall>=4)\n", False),
])
def test_una_ronda_REAL_dice_si_el_plato_salio_rancio(monkeypatch, tmp_path, salida, rancio):
    """The real `una_ronda`, not the loop's witness.

    When writing this the first time, disabling `una_ronda`'s `_rancio` did NOT work: the fixtures above replace
    all of `una_ronda` with a double, so they measured my double rather than the function. Without this, the loop
    can be perfect and never learn that stale code was encountered.
    """
    monkeypatch.setattr(S, "_SALIDA", tmp_path)
    monkeypatch.setattr(S, "_apunta", lambda **kw: None)
    monkeypatch.setattr(S, "_sha", lambda: "abc1234")
    monkeypatch.setattr(S.subprocess, "Popen", _ProcesoQueImprime(salida))
    parte = S.una_ronda("un-caso")
    assert parte["_rancio"] is rancio


def test_una_ronda_rancia_se_reconoce_por_lo_que_IMPRIME_el_runner():
    """The marker must be the guard's actual text, not a paraphrase: if the runner changes the phrase and this does
    not, the supervisor stops seeing stale code and the entire defect silently returns."""
    from pathlib import Path
    assert S._PLATO_RANCIO in Path("tests/use_cases/e2e/agent/run.py").read_text(encoding="utf-8")
