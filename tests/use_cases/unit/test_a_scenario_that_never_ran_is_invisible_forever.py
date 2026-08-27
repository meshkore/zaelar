"""Un escenario que nunca ha corrido no puede correr nunca (V2-367).

La rotación del supervisor salía del MARCADOR (`status.json`), y el marcador solo lista lo que ya corrió
alguna vez. El bucle es cerrado y no tiene salida: nadie lo corre → nunca entra en el marcador → nadie lo
corre. Un escenario nuevo no entra al bucle de mejora JAMÁS, y no por un fallo: por la forma del dato.

Medido el 2026-08-27, con el operador pidiendo que el sistema «contribuya a la prueba de todos los casos de
uso que tenemos programados»: **135 escenarios con runner, 32 en el marcador — 103 fuera del bucle.** Entre
ellos los DOS de multimedia, o sea dos superficies enteras del producto (poner música, ver un vídeo) sin una
sola medida, con sus escenarios escritos y listos desde el 2026-08-26.

Lo que lo hace difícil de ver es que **desde fuera no parece un hueco**: el escenario EXISTE, el catálogo lo
lista, `scenarios.py` lo define, y el marcador —que es donde se mira para saber cómo va todo— no dice que
falte. Es la familia de «un test fuera del mapa AFIRMA que corrió»: la ausencia se presenta como cobertura.

El orden es una decisión, no un detalle: rotos primero (donde ya sabemos qué mirar), NUNCA MEDIDOS después
(traen información nueva, pero cada uno cuesta una ronda entera de plató), y los que pasan al final para que
una regresión se vea sin comerse el turno de los rotos.
"""
import json

import pytest

from tests.use_cases.e2e.agent import supervisor as S


@pytest.fixture
def marcador(tmp_path, monkeypatch):
    """Un `status.json` de mentira, para no leer el del operador ni depender de qué corrió hoy."""
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
    """La forma exacta del 2026-08-27: dos superficies del producto con runner y sin una sola medida."""
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
    """El operador los excluyó del bucle en 2026-08-20: les falta una credencial suya y no hay forma de
    llegar, así que darían trabajo que nadie puede cerrar. Un `capped` YA ESTÁ en el marcador, así que la
    rama de nunca-medidos no debe rescatarlo por la puerta de atrás."""
    marcador({"capado": {"state": "capped"}})
    _con_runner(monkeypatch, ["capado", "nuevo"])
    assert S.rotacion() == ["nuevo"]


def test_UC_ROTACION_sigue_mandando(marcador, monkeypatch):
    """El mando para clavar el foco en un caso mientras se itera sobre él no lo toca esto."""
    marcador({"roto": {"state": "FAIL"}})
    _con_runner(monkeypatch, ["roto", "nuevo"])
    monkeypatch.setenv("UC_ROTACION", "solo-este")
    assert S.rotacion() == ["solo-este"]


def test_sin_catalogo_legible_la_rotacion_de_siempre_SIGUE(marcador, monkeypatch):
    """La dirección segura: quedarse sin los nunca-medidos es un hueco; quedarse sin rotación para el
    supervisor, que existe para no parar nunca."""
    marcador({"roto": {"state": "FAIL"}, "bueno": {"state": "PASS"}})
    monkeypatch.setattr(S, "_con_runner", lambda: (_ for _ in ()).throw(RuntimeError("catálogo roto")))
    assert S.rotacion() == ["roto", "bueno"]


def test_un_catalogo_que_revienta_no_tumba_a__con_runner(monkeypatch):
    import tests.use_cases.e2e.agent.scenarios as _sc
    monkeypatch.setattr(_sc, "all_scenarios", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    assert S._con_runner() == []


def test_con_marcador_VACIO_los_nunca_medidos_bastan(marcador, monkeypatch):
    """Un plató recién estrenado: nada ha corrido todavía. Sin esta rama caería al escenario de reserva y el
    bucle mediría UNO solo para siempre."""
    marcador({})
    _con_runner(monkeypatch, ["uno", "dos"])
    assert S.rotacion() == ["uno", "dos"]


def test_el_catalogo_REAL_trae_los_dos_de_multimedia():
    """Guarda de premisa: si mañana alguien renombra esos escenarios, este fichero deja de medir lo que dice
    medir y hay que enterarse aquí, no en una tanda."""
    ids = {x.id for x in S._con_runner()}
    assert "play-music-and-build-playlist" in ids
    assert "watch-a-video-not-listen-to-it" in ids
