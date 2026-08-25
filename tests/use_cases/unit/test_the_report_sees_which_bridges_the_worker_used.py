"""V2-327 — el informe dice con qué PUENTES trabajó el worker, leído de sus logs de sesión.

LA OBSERVABILIDAD NO SIRVE PARA ESTO, y lo peligroso es que parece que sí. Control medido el 2026-08-25 sobre
la misma ventana: `nav_cli` aparece **9** veces en los eventos mientras el worker conduce el navegador decenas
de veces. Un recuento sobre el bus da un número pequeño y creíble — y con él estuve a punto de reportar
«`widget_cli`: 0 usos en 1350 eventos» como prueba de que ese puente no se usa nunca.

La fuente autoritativa dijo lo contrario, y algo mucho más útil:

    332 sesiones · 81 mencionan nav_cli · 5 mencionan widget_cli · y las CINCO llevan un Exit code 2

O sea que los workers SÍ lo intentaban y el puente los echaba: `--help` contestaba «comando desconocido» con
código 2 (V2-325).

POR QUÉ VA EN EL INFORME. `widget_cli` es la única forma que tiene un worker de poner en la hoja lo que aprende
ABRIENDO fichas; sin él la hoja solo recoge lo que el extractor automático saca de un listado. Esa diferencia
decidió tres rondas seguidas (mecanismo 4-5, resultado 1-2) y **nada en el informe la mostraba**.

Y es la mitad que faltaba de V2-325: allí se quitó una fricción medida dejando escrito que eso NO prueba que
los workers vayan a usar la hoja. Esto es lo que lo mide.
"""
import json

import pytest

from tests.use_cases.e2e.agent import verify as V


@pytest.fixture
def sesiones(tmp_path):
    """Logs de sesión de mentira — un test unitario nunca lee los del plató vivo."""
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
    """La señal que encontró V2-325: el puente se toca y la sesión muere con `Exit code 2`."""
    d, add = sesiones
    add("a", {"text": "python -m nucleo.widget_cli --help"}, {"text": "Exit code 2 comando desconocido: --help"})
    add("b", {"text": "python -m nucleo.widget_cli read results"}, {"text": "ok"})
    r = V.worker_bridges(logs_dir=str(d))
    assert r["by_bridge"]["widget_cli"] == 2
    assert r["errors"]["widget_cli"] == 1


def test_el_error_se_cuenta_como_COINCIDENCIA_no_como_culpa(sesiones):
    """Honestidad del instrumento: un `Exit code 2` en la misma sesión NO prueba que sea de ese puente. Se
    cuenta aparte y el docstring lo dice; si algún día se usa para acusar, hay que estrechar la señal primero."""
    d, add = sesiones
    add("a", {"text": "nav_cli snapshot"}, {"text": "widget_cli read results"},
        {"text": "Exit code 2 en algún sitio"})
    r = V.worker_bridges(logs_dir=str(d))
    assert r["errors"]["nav_cli"] == 1 and r["errors"]["widget_cli"] == 1


def test_las_sesiones_ANTERIORES_a_la_ronda_no_cuentan(sesiones):
    """`since` es lo que separa esta ronda de las de antes; sin él, el plató acumula 338 sesiones y el número
    deja de significar nada sobre el caso que se está midiendo."""
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
    """La mitad de cableado (V2-199): la lectura puede acertar y no llegar a quien la necesita."""
    import inspect

    from tests.use_cases.e2e.agent import run as R
    assert 'mech["worker_bridges"] = verifymod.worker_bridges(' in inspect.getsource(R._run_scenario)
