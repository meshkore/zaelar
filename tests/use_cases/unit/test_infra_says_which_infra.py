"""`INFRA` sin motivo es un agujero de operación, no de estilo.

Las cuatro puertas que llevan a INFRA piden acciones **opuestas**: el arnés se cayó (bug del instrumento),
los turnos volvieron vacíos (recargar un proveedor), el recall semántico estaba degradado (levantar el
prewarm) o el juez no dio nota (mirar su cadena). Desde el tablero se ven las cuatro exactamente igual.

Medido el 2026-08-28 con el plató 24/7 ya corriendo: dos filas pasaron de FAIL a INFRA en una hora, y
reconstruir cuál de las cuatro ramas las había movido fue **imposible** — el dict de la ronda ya no existe
cuando alguien lee el tablero. En un bucle que nadie mira durante ocho horas, ésa es la diferencia entre
«está midiendo» y «lleva toda la noche produciendo basura a toda velocidad», y la segunda es peor que estar
parado porque parado se nota.
"""
from __future__ import annotations

import json

from tests.use_cases.e2e.agent import status as S


def _ronda(**kw):
    base = {"scenario": "x__es", "tier": 2,
            "run": {"transcript": [{}] * 12, "mechanism_report": {}},
            "verdict": {"overall": 3, "scores": {"mecanismo": 3}, "veredicto": "bien"}}
    base.update(kw)
    return base


def test_turnos_vacios_lo_dicen_con_su_cuenta():
    r = _ronda(run={"transcript": [{}] * 12, "mechanism_report": {"mute_turns": {"n": 5}}})
    assert S._state(3, r) == "INFRA"
    assert "VACÍOS" in r["_infra_reason"] and "5 de 6" in r["_infra_reason"]


def test_el_recall_degradado_nombra_su_backend():
    r = _ronda(run={"transcript": [{}] * 12,
                    "mechanism_report": {"embeddings": {"degraded": True, "backend": "hash"}}})
    assert S._state(3, r) == "INFRA"
    assert "recall" in r["_infra_reason"] and "hash" in r["_infra_reason"]


def test_una_excepcion_de_verdad_y_el_juez_mudo_son_distintos():
    """Reescrito 2026-08-28, NO volteado: la propiedad —dos puertas, dos motivos distintos— es la misma. Lo
    que cambió es que `crashed` ya no se traduce a una frase inventada sino que se imprime la que trae dentro,
    así que el fixture pasa la frase real de una excepción en vez de un `True` pelado."""
    a = _ronda(run={"crashed": "ZeroDivisionError en el juez · autopsia: …",
                    "transcript": [], "mechanism_report": {}})
    S._state(3, a)
    b = _ronda()
    S._state(None, b)
    assert a["_infra_reason"] != b["_infra_reason"]
    assert "ZeroDivisionError" in a["_infra_reason"] and "juez no devolvió nota" in b["_infra_reason"]


def test_una_ronda_SANA_no_lleva_motivo():
    """La mitad de sensibilidad: un motivo que sale siempre deja de ser un motivo."""
    r = _ronda()
    assert S._state(3, r) == "FAIL"
    assert "_infra_reason" not in r


def test_el_motivo_llega_a_la_fila_y_al_tablero(tmp_path, monkeypatch):
    """La cadena entera: si se queda en el dict de la ronda no lo lee nadie."""
    monkeypatch.setattr(S, "LEDGER_PATH", tmp_path / "status.json")
    monkeypatch.setattr(S, "BOARD_PATH", tmp_path / "STATUS.md")
    S.record([_ronda(run={"transcript": [{}] * 12, "mechanism_report": {"mute_turns": {"n": 5}}})],
             sandboxed=True)
    fila = json.loads((tmp_path / "status.json").read_text(encoding="utf-8"))["scenarios"]["x__es"]
    assert fila["state"] == "INFRA" and "VACÍOS" in (fila["infra_reason"] or "")
    tablero = (tmp_path / "STATUS.md").read_text(encoding="utf-8")
    assert "INFRA —" in tablero and "VACÍOS" in tablero


def test_en_una_fila_INFRA_el_motivo_manda_sobre_el_veredicto(tmp_path, monkeypatch):
    """El veredicto habla de un producto que en esa ronda NO llegó a medirse. Leerlo como si sí invita justo
    al diagnóstico equivocado, que es el error que este nodo existe para no repetir."""
    monkeypatch.setattr(S, "LEDGER_PATH", tmp_path / "status.json")
    monkeypatch.setattr(S, "BOARD_PATH", tmp_path / "STATUS.md")
    r = _ronda(run={"transcript": [{}] * 12, "mechanism_report": {"mute_turns": {"n": 5}}})
    r["verdict"]["veredicto"] = "el producto no entregó nada"
    S.record([r], sandboxed=True)
    fila = [l for l in (tmp_path / "STATUS.md").read_text(encoding="utf-8").splitlines() if "x__es" in l][0]
    assert fila.index("INFRA —") < fila.index("el producto no entregó nada")
    assert "no medible" in fila


def test_el_motivo_que_YA_venia_escrito_no_se_sustituye_por_una_suposicion():
    """`crashed` no es «se cayó»: es un campo con TRES inquilinos —el conductor fuera de papel (V2-313), una
    fuente de verdad ilegible (V2-396), y una excepción real con su autopsia— y **cada uno trae ya escrita su
    frase**. La primera versión de este nodo puso un motivo genérico y era falso para los tres.

    Medido una hora después de escribirlo, sobre `best-plumber-same-day__us`: el tablero decía «el arnés se
    cayó», el log no tenía ni un traceback y el veredicto era un 2/5 de producto perfectamente normal. La
    frase real, que estaba en el campo, decía «el conductor se salió de su papel en 1 línea(s) del transcript
    (turno 13): la ronda no mide al producto» — otra cosa, y con otra acción detrás.

    Adivinar un motivo teniendo el bueno delante es el mismo error que este nodo existe para arreglar.
    """
    frase = "el conductor se salió de su papel en 1 línea(s) del transcript (turno(s) 13)"
    r = _ronda(run={"crashed": frase, "transcript": [{}] * 12, "mechanism_report": {}})
    assert S._state(2, r) == "INFRA"
    assert r["_infra_reason"] == frase, "se sustituyó el motivo real por uno inventado"


def test_y_el_juez_marcando_INFRA_es_OTRA_cosa():
    """La mitad de sensibilidad: las dos puertas iban juntas en una condición y decían lo mismo."""
    r = _ronda(verdict={"overall": 1, "scores": {}, "veredicto": "INFRA: no hubo respuesta"})
    assert S._state(1, r) == "INFRA"
    assert "juez" in r["_infra_reason"] and "conductor" not in r["_infra_reason"]
