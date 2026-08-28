"""«Tenía resultados y contestó que no había novedades» — ¿mintió, o le contamos que no había nada?

Es la pregunta que decide la ATRIBUCIÓN del bloqueador más repetido del tablero. Leído desde el transcript,
ese turno parece una mentira del producto. Si en su prompt ponía que la tarea seguía atascada, entonces
contestó **exactamente lo que le pusimos delante**, y el defecto es nuestro.

Medido en `find-direct-flight-budget__es` (2026-08-28, plató 24/7): `sheet_named_ms` cae entre el turno 5 y
el 6; en los turnos **6, 7 y 8** el bloque vivo traía la cara de «sin avanzar» y CERO filas, con cuatro vuelos
con nombre en la hoja del encargo. El juez lo puntuó 2/5 por «retener la entrega y negar lo que el sistema le
mostraba». El sistema le mostraba lo contrario.

Barrido sobre los 353 informes guardados: de las **48** rondas cuya hoja llegó a tener nombres, **45** tienen
al menos un turno al que no se le dijo — **257 turnos** en total.

Esto NO dice dónde está la avería (`_found_candidates` ya cae a `_sheet_has_rows`, así que la resolución de la
caja del encargo es la sospechosa) y no intenta adivinarlo. Dice cuántas veces pasa, que es lo que convierte
una inferencia sobre una ronda en un número sobre muchas.
"""
from __future__ import annotations

from tests.use_cases.e2e.agent import verify as V

_T = {"sheet_named_ms": 1000.0}
_VIVO = "TAREAS DE FONDO EN CURSO (los brain workers las están resolviendo): «Busca vuelos» · sin avanzar"


def test_el_caso_MEDIDO_marca_sus_turnos():
    pc = [{"turn": 5, "at_ms": 900.0, "live_line": _VIVO, "sheet_rows": []},
          {"turn": 6, "at_ms": 1100.0, "live_line": _VIVO, "sheet_rows": []},
          {"turn": 7, "at_ms": 1200.0, "live_line": _VIVO, "sheet_rows": []}]
    got = V.sheet_hidden_from_the_prompt(pc, _T)
    assert got["n"] == 2 and [t["turn"] for t in got["turns"]] == [6, 7]


def test_un_turno_ANTERIOR_a_que_hubiera_filas_no_cuenta():
    """No se le puede ocultar lo que todavía no existe."""
    pc = [{"turn": 0, "at_ms": 500.0, "live_line": _VIVO, "sheet_rows": []}]
    assert V.sheet_hidden_from_the_prompt(pc, _T)["n"] == 0


def test_si_el_prompt_SÍ_lo_dice_no_es_ceguera():
    """Aunque no le diéramos los nombres: decirle que hay algo ya cambia lo que puede contestar."""
    pc = [{"turn": 6, "at_ms": 1100.0, "sheet_rows": [],
           "live_line": "TAREAS DE FONDO EN CURSO · la tarea YA HA ENCONTRADO algo, pero sus nombres aún no"}]
    assert V.sheet_hidden_from_the_prompt(pc, _T)["n"] == 0


def test_si_le_dimos_las_FILAS_menos_todavía():
    pc = [{"turn": 6, "at_ms": 1100.0, "live_line": _VIVO, "sheet_rows": ["Iberia directo 21:50"]}]
    assert V.sheet_hidden_from_the_prompt(pc, _T)["n"] == 0


def test_sin_BLOQUE_VIVO_no_hay_ceguera():
    """La tarea ya no está en curso: sus resultados se entregaron o se cerraron, y no había nada que contarle
    en ese turno. Cinco de los 262 turnos del barrido eran esto — contarlos habría inflado el número con la
    clase de caso que el propio hallazgo dice que NO es."""
    pc = [{"turn": 6, "at_ms": 1100.0, "live_line": "", "sheet_rows": []}]
    assert V.sheet_hidden_from_the_prompt(pc, _T)["n"] == 0


def test_sin_filas_con_nombre_NUNCA_no_hay_pregunta_que_hacer():
    """Y se distingue de «cero turnos ciegos»: no es lo mismo no tener el dato que tenerlo y salir a cero."""
    got = V.sheet_hidden_from_the_prompt([{"turn": 0, "at_ms": 1.0, "live_line": _VIVO}], {})
    assert got["n"] == 0 and got["measurable"] is False
    assert V.sheet_hidden_from_the_prompt([], _T)["measurable"] is True


def test_al_JUEZ_se_le_dice_que_NO_lo_puntúe_como_negar():
    """Medir esto y no contárselo al juez deja el veredicto igual de equivocado: la nota la pone él."""
    from tests.use_cases.e2e.agent import judge as J
    hechos = J.mechanism_facts({"sheet_hidden_from_the_prompt":
                                {"n": 3, "measurable": True, "turns": [{"turn": 6}, {"turn": 7}, {"turn": 8}]}})
    txt = "\n".join(hechos) if isinstance(hechos, list) else str(hechos)
    assert "NO SE LO DIJIMOS" in txt and "6, 7, 8" in txt
    assert "NO lo puntúes como retener" in txt


def test_y_no_se_le_dice_nada_cuando_no_hubo_ceguera():
    """Un aviso que sale siempre deja de ser un aviso."""
    from tests.use_cases.e2e.agent import judge as J
    hechos = J.mechanism_facts({"sheet_hidden_from_the_prompt": {"n": 0, "measurable": True, "turns": []}})
    txt = "\n".join(hechos) if isinstance(hechos, list) else str(hechos)
    assert "NO SE LO DIJIMOS" not in txt


def test_la_CAUSA_se_lee_del_flujo_y_no_de_las_anomalias():
    """El aviso del motor es un evento `perf`, no un error, así que la lista de anomalías del auditor —que
    solo recoge `is_error`— no lo vería NUNCA. Emitir la señal y no traerla al informe habría sido la tercera
    media faena de la misma noche: el dato existe, y donde se mira no está."""
    import json
    ev = {"kind": "perf", "cat": "system",
          "payload": json.dumps({"kind": "perf", "cat": "system",
                                 "label": "🧾 hoja del encargo SIN RESOLVER", "nav_task": "6175ca-1"})}
    got = V.unresolved_errand_sheets([ev, ev])
    assert got["n"] == 2 and got["tabs"] == {"6175ca-1": 2}
    vacio = V.unresolved_errand_sheets([])
    assert vacio["n"] == 0 and vacio["tabs"] == {} and vacio["n_empty"] == 0


def test_la_causa_va_PEGADA_al_aviso_y_no_en_una_linea_suelta():
    """Dice lo mismo al juez —no culpes al modelo—, así que una segunda frase repitiéndolo sería ruido."""
    from tests.use_cases.e2e.agent import judge as J
    hechos = J.mechanism_facts({"sheet_hidden_from_the_prompt": {"n": 2, "measurable": True,
                                                                "turns": [{"turn": 6}, {"turn": 7}]},
                                "unresolved_errand_sheets": {"n": 3, "tabs": {"6175ca-1": 3}}})
    txt = "\n".join(hechos) if isinstance(hechos, list) else str(hechos)
    assert "NO SE LO DIJIMOS" in txt and "se sabe POR QUÉ" in txt and "6175ca-1" in txt
    assert txt.index("NO SE LO DIJIMOS") < txt.index("se sabe POR QUÉ")


def test_y_sin_causa_conocida_no_se_inventa_una():
    from tests.use_cases.e2e.agent import judge as J
    hechos = J.mechanism_facts({"sheet_hidden_from_the_prompt": {"n": 2, "measurable": True,
                                                                "turns": [{"turn": 6}, {"turn": 7}]},
                                "unresolved_errand_sheets": {"n": 0, "tabs": {}}})
    txt = "\n".join(hechos) if isinstance(hechos, list) else str(hechos)
    assert "NO SE LO DIJIMOS" in txt and "se sabe POR QUÉ" not in txt


def test_resolver_a_la_caja_EQUIVOCADA_se_cuenta_aparte():
    """Fallar al resolver ya se contaba; resolver a la caja equivocada se veía **igual que acertar**. Y era
    el caso de `search-buy-guitar__es`: `unresolved_errand_sheets.n` salió a 0 —o sea que resolvió— y aun así
    hubo seis turnos en los que al modelo no se le dijo que tuviera nada, con 15 candidatos en la hoja."""
    import json
    def _ev(label, **extra):
        return {"kind": "perf", "cat": "system",
                "payload": json.dumps({"kind": "perf", "cat": "system", "label": label, **extra})}
    got = V.unresolved_errand_sheets([
        _ev("🧾 hoja del encargo SIN RESOLVER", nav_task="a-1"),
        _ev("🧾 hoja del encargo RESUELTA PERO VACÍA", nav_task="b-1", hoja="results", n_items=0),
        _ev("🧾 hoja del encargo RESUELTA PERO VACÍA", nav_task="b-1", hoja="results", n_items=0)])
    assert got["n"] == 1 and got["tabs"] == {"a-1": 1}
    assert got["n_empty"] == 2 and got["empty_sheets"] == {"results": 2}


def test_al_juez_se_le_dice_CUÁL_de_las_dos_averías_fue():
    """Las dos llevan a mirar sitios distintos del motor, así que decir «avería» a secas no basta."""
    from tests.use_cases.e2e.agent import judge as J
    base = {"sheet_hidden_from_the_prompt": {"n": 2, "measurable": True, "turns": [{"turn": 6}, {"turn": 7}]}}
    vacia = J.mechanism_facts({**base, "unresolved_errand_sheets": {"n": 0, "tabs": {},
                                                                   "n_empty": 3, "empty_sheets": {"results": 3}}})
    txt = "\n".join(vacia) if isinstance(vacia, list) else str(vacia)
    assert "VACÍA" in txt and "results" in txt
    sin = J.mechanism_facts({**base, "unresolved_errand_sheets": {"n": 2, "tabs": {"a-1": 2},
                                                                 "n_empty": 0, "empty_sheets": {}}})
    txt2 = "\n".join(sin) if isinstance(sin, list) else str(sin)
    assert "no supo qué hoja" in txt2 and "VACÍA" not in txt2


def test_las_TRES_averías_se_cuentan_por_separado():
    """Las tres llevan a mirar sitios distintos del motor: no resolver, resolver a la caja equivocada, y que
    la lectura reviente. Meterlas en el mismo saco deja al que investiga donde estaba."""
    import json
    def _ev(label, **extra):
        return {"kind": "perf", "cat": "system",
                "payload": json.dumps({"kind": "perf", "cat": "system", "label": label, **extra})}
    got = V.unresolved_errand_sheets([
        _ev("🧾 hoja del encargo SIN RESOLVER", nav_task="a-1"),
        _ev("🧾 hoja del encargo RESUELTA PERO VACÍA", nav_task="b-1", hoja="results"),
        _ev("🧾 hoja del encargo ILEGIBLE", nav_task="c-1", error="KeyError: items")])
    assert got["n"] == 1 and got["n_empty"] == 1 and got["n_unreadable"] == 1
    assert got["errors"] == ["KeyError: items"]


def test_al_juez_la_ILEGIBLE_le_llega_con_su_error():
    from tests.use_cases.e2e.agent import judge as J
    hechos = J.mechanism_facts({
        "sheet_hidden_from_the_prompt": {"n": 4, "measurable": True, "turns": [{"turn": 9}]},
        "unresolved_errand_sheets": {"n": 0, "tabs": {}, "n_empty": 0, "empty_sheets": {},
                                     "n_unreadable": 2, "errors": ["KeyError: items"]}})
    txt = "\n".join(hechos) if isinstance(hechos, list) else str(hechos)
    assert "REVENTÓ" in txt and "KeyError: items" in txt


def test_el_TABLERO_dice_en_qué_filas_no_le_dijimos_nada(tmp_path, monkeypatch):
    """El juez ya lo dice en prosa, ronda por ronda. Sin el número en el tablero, leerlo obliga a abrir el
    informe de cada ronda una por una — y el tablero es donde se mira.

    Va con su número porque «hubo turnos ciegos» y «hubo catorce» piden lecturas distintas de la misma nota.
    """
    from tests.use_cases.e2e.agent import status as S
    monkeypatch.setattr(S, "LEDGER_PATH", tmp_path / "status.json")
    monkeypatch.setattr(S, "BOARD_PATH", tmp_path / "STATUS.md")
    S.record([{"scenario": "x__es", "tier": 2,
               "run": {"transcript": [], "mechanism_report": {"sheet_hidden_from_the_prompt": {"n": 6}}},
               "verdict": {"overall": 2, "scores": {"mecanismo": 3}, "veredicto": "flojo"}}], sandboxed=True)
    board = (tmp_path / "STATUS.md").read_text(encoding="utf-8")
    assert "NO le dijimos lo que ya tenía" in board
    assert "| `x__es` | 6 |" in board


def test_y_sin_turnos_ciegos_no_aparece_la_sección(tmp_path, monkeypatch):
    """Una sección que sale siempre deja de leerse, y el tablero ya tiene seis."""
    from tests.use_cases.e2e.agent import status as S
    monkeypatch.setattr(S, "LEDGER_PATH", tmp_path / "status.json")
    monkeypatch.setattr(S, "BOARD_PATH", tmp_path / "STATUS.md")
    S.record([{"scenario": "x__es", "tier": 2,
               "run": {"transcript": [], "mechanism_report": {"sheet_hidden_from_the_prompt": {"n": 0}}},
               "verdict": {"overall": 4, "scores": {"mecanismo": 4}, "veredicto": "bien"}}], sandboxed=True)
    assert "NO le dijimos" not in (tmp_path / "STATUS.md").read_text(encoding="utf-8")
