"""V2-327 — the report says which BRIDGES the worker used, read from its session logs.

OBSERVABILITY DOES NOT WORK FOR THIS, and the dangerous part is that it looks as though it does. A control measured
on 2026-08-25 over the same window: `nav_cli` appears **9** times in the events while the worker drives the browser
dozens of times. A count over the bus gives a small, credible number — and with it I almost reported
«`widget_cli`: 0 uses in 1350 events» as proof that this bridge is never used.

The authoritative source said the opposite, and something much more useful:

    332 sessions · 81 mention nav_cli · 5 mention widget_cli · and ALL FIVE have an Exit code 2

In other words, the workers WERE trying it and the bridge was rejecting them: `--help` replied «unknown command» with
code 2 (V2-325).

WHY IT BELONGS IN THE REPORT. `widget_cli` is the only way a worker can put into the sheet what it learns by
OPENING records; without it, the sheet only collects what the automatic extractor pulls from a listing. That
difference decided three consecutive rounds (mechanism 4-5, result 1-2) and **nothing in the report showed it**.

And it is the missing half of V2-325: there, a measured friction was removed by writing down that this does NOT
prove that the workers will use the sheet. This is what measures it.
"""
import json

import pytest

from tests.use_cases.e2e.agent import verify as V


@pytest.fixture
def sesiones(tmp_path):
    """Fake session logs — a unit test never reads those from the live set."""
    d = tmp_path / "sessions"
    d.mkdir()

    def _add(nombre, *lineas):
        (d / f"{nombre}.jsonl").write_text("\n".join(json.dumps(x) for x in lineas), encoding="utf-8")
    return d, _add


def test_sin_logs_no_INVENTA_nada(tmp_path):
    r = V.worker_bridges(logs_dir=str(tmp_path / "no-existe"))
    assert r["read"] is False and r["sessions"] == 0 and r["by_bridge"] == {}


def test_cuenta_las_SESIONES_que_tocan_cada_puente(sesiones):
    d, add = sesiones
    add("a", {"text": "python -m nucleo.nav_cli snapshot"})
    add("b", {"text": "python -m nucleo.nav_cli click 3"})
    add("c", {"text": "python -m nucleo.widget_cli read results"})
    r = V.worker_bridges(logs_dir=str(d))
    assert r["read"] is True and r["sessions"] == 3
    assert r["by_bridge"]["nav_cli"] == 2
    assert r["by_bridge"]["widget_cli"] == 1


def test_marca_las_que_ADEMÁS_llevan_un_fallo(sesiones):
    """The signal V2-325 found: the bridge is touched and the session dies with `Exit code 2`."""
    d, add = sesiones
    add("a", {"text": "python -m nucleo.widget_cli --help"}, {"text": "Exit code 2 comando desconocido: --help"})
    add("b", {"text": "python -m nucleo.widget_cli read results"}, {"text": "ok"})
    r = V.worker_bridges(logs_dir=str(d))
    assert r["by_bridge"]["widget_cli"] == 2
    assert r["errors"]["widget_cli"] == 1


def test_el_error_se_cuenta_como_COINCIDENCIA_no_como_culpa(sesiones):
    """Instrument honesty: an `Exit code 2` in the same session does NOT prove that it belongs to that bridge. It is
    counted separately and the docstring says so; if it is ever used to assign blame, the signal must first be narrowed."""
    d, add = sesiones
    add("a", {"text": "nav_cli snapshot"}, {"text": "widget_cli read results"},
        {"text": "Exit code 2 en algún sitio"})
    r = V.worker_bridges(logs_dir=str(d))
    assert r["errors"]["nav_cli"] == 1 and r["errors"]["widget_cli"] == 1


def test_las_sesiones_ANTERIORES_a_la_ronda_no_cuentan(sesiones):
    """`since` is what separates this round from the earlier ones; without it, the set accumulates 338 sessions and
    the number ceases to mean anything about the case being measured."""
    import os
    import time
    d, add = sesiones
    add("vieja", {"text": "widget_cli read results"})
    os.utime(d / "vieja.jsonl", (time.time() - 3600, time.time() - 3600))
    add("nueva", {"text": "nav_cli snapshot"})
    r = V.worker_bridges(logs_dir=str(d), since=time.time() - 60)
    assert r["sessions"] == 1
    assert "widget_cli" not in r["by_bridge"]


def test_el_informe_LO_LLEVA():
    """The wiring half (V2-199): the reading can be correct and fail to reach whoever needs it."""
    import inspect

    from tests.use_cases.e2e.agent import run as R
    assert 'mech["worker_bridges"] = verifymod.worker_bridges(' in inspect.getsource(R._run_scenario)
