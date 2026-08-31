"""A scenario that has never run can never run (V2-367).

The supervisor rotation came from the MARKER (`status.json`), and the marker only lists what has already run
at least once. The loop is closed and has no exit: nobody runs it → it never enters the marker → nobody
runs it. A new scenario NEVER enters the improvement loop, and not because of a bug: because of the shape of
the data.

Measured on 2026-08-27, with the operator asking that the system “contribute to testing all the use cases we
have scheduled”: **135 scenarios with a runner, 32 in the marker — 103 outside the loop.** Among them were
the TWO multimedia scenarios, meaning two entire product surfaces (play music, watch a video) without a
single measurement, with their scenarios written and ready since 2026-08-26.

What makes it hard to see is that **from the outside it does not look like a gap**: the scenario EXISTS, the
catalog lists it, `scenarios.py` defines it, and the marker —which is where one looks to see how everything is
going— does not say it is missing. It is the family of “a test outside the map CLAIMS to have run”: absence is
presented as coverage.

The order is a decision, not a detail: broken first (where we already know what to look at), NEVER MEASURED
next (they bring new information, but each one costs an entire studio round), and passing ones last so that a
regression is visible without taking the broken ones' turn.
"""
import json

import pytest

from tests.use_cases.e2e.agent import supervisor as S


@pytest.fixture
def marcador(tmp_path, monkeypatch):
    """A fake `status.json`, so we do not read the operator's or depend on what ran today."""
    def _poner(scenarios: dict):
        raiz = tmp_path
        (raiz / "tests" / "use_cases").mkdir(parents=True, exist_ok=True)
        (raiz / "tests" / "use_cases" / "status.json").write_text(
            json.dumps({"scenarios": scenarios}), encoding="utf-8")
        monkeypatch.setattr(S, "_RAIZ", raiz)
        monkeypatch.delenv("UC_ROTACION", raising=False)
    return _poner


def _con_runner(monkeypatch, ids):
    monkeypatch.setattr(S, "_con_runner", lambda: [type("E", (), {"id": i})() for i in ids])


def test_el_caso_medido_multimedia_entra_en_la_rotacion(marcador, monkeypatch):
    """The exact state on 2026-08-27: two product surfaces with a runner and without a single measurement."""
    marcador({"search-buy-used-car": {"state": "FAIL"}})
    _con_runner(monkeypatch, ["search-buy-used-car",
                              "play-music-and-build-playlist",
                              "watch-a-video-not-listen-to-it"])
    r = S.rotacion()
    assert "play-music-and-build-playlist" in r
    assert "watch-a-video-not-listen-to-it" in r


def test_el_orden_es_rotos_nunca_buenos(marcador, monkeypatch):
    marcador({"roto": {"state": "FAIL"}, "bueno": {"state": "PASS"}})
    _con_runner(monkeypatch, ["roto", "bueno", "nuevo"])
    assert S.rotacion() == ["roto", "nuevo", "bueno"]


def test_un_capped_sigue_FUERA_aunque_tenga_runner(marcador, monkeypatch):
    """The operator excluded them from the loop on 2026-08-20: one of their credentials is missing and there
is no way to reach them, so they would create work that nobody can close. A `capped` is ALREADY in the marker,
so the never-measured branch must not rescue it through the back door."""
    marcador({"capado": {"state": "capped"}})
    _con_runner(monkeypatch, ["capado", "nuevo"])
    assert S.rotacion() == ["nuevo"]


def test_UC_ROTACION_sigue_mandando(marcador, monkeypatch):
    """This does not affect the control that pins the focus on one case while iterating on it."""
    marcador({"roto": {"state": "FAIL"}})
    _con_runner(monkeypatch, ["roto", "nuevo"])
    monkeypatch.setenv("UC_ROTACION", "solo-este")
    assert S.rotacion() == ["solo-este"]


def test_sin_catalogo_legible_la_rotacion_de_siempre_SIGUE(marcador, monkeypatch):
    """The safe direction: running out of never-measured cases is a gap; running out of rotation for the
supervisor, which exists to never stop, is not."""
    marcador({"roto": {"state": "FAIL"}, "bueno": {"state": "PASS"}})
    monkeypatch.setattr(S, "_con_runner", lambda: (_ for _ in ()).throw(RuntimeError("catálogo roto")))
    assert S.rotacion() == ["roto", "bueno"]


def test_un_catalogo_que_revienta_no_tumba_a__con_runner(monkeypatch):
    import tests.use_cases.e2e.agent.scenarios as _sc
    monkeypatch.setattr(_sc, "all_scenarios", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    assert S._con_runner() == []


def test_con_marcador_VACIO_los_nunca_medidos_bastan(marcador, monkeypatch):
    """A newly opened studio: nothing has run yet. Without this branch it would fall back to the reserve
scenario and the loop would measure only ONE forever."""
    marcador({})
    _con_runner(monkeypatch, ["uno", "dos"])
    assert S.rotacion() == ["uno", "dos"]


def test_el_catalogo_REAL_trae_los_dos_de_multimedia():
    """Premise guard: if someone renames those scenarios tomorrow, this file stops measuring what it claims to
measure, and we need to find out here, not in a batch."""
    ids = {x.id for x in S._con_runner()}
    assert "play-music-and-build-playlist" in ids
    assert "watch-a-video-not-listen-to-it" in ids
