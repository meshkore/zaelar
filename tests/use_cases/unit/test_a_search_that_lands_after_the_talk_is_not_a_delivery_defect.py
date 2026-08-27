"""Una vuelta de búsqueda que llega con la conversación cerrada no prueba un fallo de entrega (V2-378).

Medido en `compare-insurance-quotes__es` (2026-08-27, 2/5). El informe avisó «⚠️ y NINGUNA se le empujó al
cerebro» y el juez lo convirtió en un [media] y en la mejora nº5: *«Es un fallo de ENTREGA del mecanismo que
deja al cerebro sin datos»*. Leídos los relojes de esa sesión:

    último turno del operador   298,0 s
    vueltas de búsqueda         472,9 s … 520,8 s   ← las OCHO

La conversación llevaba casi tres minutos cerrada. Las notas se empujan a un buzón que nadie iba a vaciar, y
el contador lee el DRENAJE (el evento que emite el canal al entregar la nota en un turno), no el empujón —
así que marcaba cero. No había mecanismo que arreglar: no había a quién entregar.

De paso corrige una cifra del propio informe: decía «2 consulta(s), 1 respuesta(s)» y en el registro hay
OCHO idas y OCHO vueltas, todas del `WebSearch` NATIVO del worker.

Es la misma familia que la línea que ese informe ya imprime para los workers —«el motor SEGUÍA trabajando al
medir: lo que falte puede ser todavía no, no nunca»—: este canal no participaba de ese cuidado.
"""
import pytest

from tests.use_cases.e2e.agent import judge as J, report as R


def _texto(x) -> str:
    """`mechanism_facts` devuelve una CADENA y `_mechanism_numbers` una lista. Unir una cadena con «\n» mete
    un salto entre cada carácter, así que la primera versión de este fichero no encontraba nada y daba rojo
    por el motivo equivocado."""
    return x if isinstance(x, str) else "\n".join(x)


def _sr(returns, tarde, notas=0):
    return {"search_returns": {"queries": returns, "returns": returns,
                               "returns_after_last_turn": tarde, "notes_from_search": notas,
                               "sample": ["Web search results for query: precio medio seguro"]}}


# ── el juez ────────────────────────────────────────────────────────────────────────────────────────────────

def test_la_ronda_medida_ya_no_se_puntua_como_fallo_de_mecanismo():
    txt = _texto(J.mechanism_facts(_sr(8, 8)))
    assert "fallo de ENTREGA del mecanismo" not in txt
    assert "no se puntúa" in txt and "ya cerrada" in txt


def test_una_vuelta_A_TIEMPO_sin_nota_SIGUE_siendo_un_fallo():
    """La sensibilidad que sostiene el arreglo: V2-236 existe porque la búsqueda contestaba bien y moría
    dentro del worker. Eso no se puede dejar de ver."""
    txt = _texto(J.mechanism_facts(_sr(8, 0)))
    assert "fallo de ENTREGA del mecanismo" in txt
    assert "CON LA CONVERSACIÓN ABIERTA" in txt


def test_con_vueltas_MIXTAS_se_cuentan_solo_las_de_a_tiempo():
    txt = _texto(J.mechanism_facts(_sr(8, 6)))
    assert "CONTESTÓ 2 vez/veces CON LA CONVERSACIÓN ABIERTA" in txt


def test_si_HUBO_notas_no_se_dice_nada():
    txt = _texto(J.mechanism_facts(_sr(8, 0, notas=3)))
    assert "empujó al cerebro" not in txt


# ── el informe ─────────────────────────────────────────────────────────────────────────────────────────────

def test_el_informe_explica_la_llegada_tardia_en_vez_de_avisar():
    txt = _texto(R._mechanism_numbers(_sr(8, 8)))
    assert "NINGUNA se le empujó" not in txt
    assert "DESPUÉS del último turno" in txt and "NO es un fallo de entrega" in txt


def test_el_informe_SIGUE_avisando_cuando_toca():
    txt = _texto(R._mechanism_numbers(_sr(8, 0)))
    assert "⚠️ y NINGUNA se le empujó al cerebro" in txt


# ── el contador ────────────────────────────────────────────────────────────────────────────────────────────

def _db(tmp_path, vueltas_ms):
    """Un almacén de eventos mínimo con una ida y N vueltas de búsqueda en los instantes dados."""
    import json as _j
    import sqlite3
    p = tmp_path / "e.db"
    con = sqlite3.connect(p)
    con.execute("CREATE TABLE events (ts_ms INTEGER, kind TEXT, label TEXT, payload TEXT, topic TEXT)")
    con.execute("INSERT INTO events VALUES (?,?,?,?,?)",
                (100, "search", "🌐 web", _j.dumps({"text": "web_search seguro coche"}), ""))
    for ms in vueltas_ms:
        con.execute("INSERT INTO events VALUES (?,?,?,?,?)",
                    (ms, "search", "🌐 web ↩", _j.dumps({"text": "Web search results for query: seguro"}), ""))
    con.commit()
    con.close()
    return str(p)


def test_el_contador_separa_las_tardias_de_las_de_a_tiempo(tmp_path):
    """La ronda medida, en miniatura: último turno a los 298 s, las ocho vueltas entre 473 y 521."""
    from tests.use_cases.e2e.agent import verify as V
    db = _db(tmp_path, [473_000, 480_000, 500_000, 521_000])
    out = V.search_returns(db, since=0, last_turn_ms=298_000)
    assert out["returns"] == 4 and out["returns_after_last_turn"] == 4


def test_el_contador_no_llama_tardia_a_una_de_a_tiempo(tmp_path):
    from tests.use_cases.e2e.agent import verify as V
    out = V.search_returns(_db(tmp_path, [100_000, 473_000]), since=0, last_turn_ms=298_000)
    assert out["returns"] == 2 and out["returns_after_last_turn"] == 1


def test_sin_saber_el_ultimo_turno_no_se_inventa_nada(tmp_path):
    """`last_turn_ms` puede faltar (una ronda sin transcript). Contar esas vueltas como tardías silenciaría un
    fallo real; contarlas como a tiempo conserva el aviso de siempre, que es la dirección segura."""
    from tests.use_cases.e2e.agent import verify as V
    out = V.search_returns(_db(tmp_path, [473_000, 521_000]), since=0)
    assert out["returns"] == 2 and out["returns_after_last_turn"] == 0


def test_el_arnes_PASA_el_instante_del_ultimo_turno():
    """El cableado: el contador puede estar perfecto y no recibir el dato."""
    from pathlib import Path
    src = Path("tests/use_cases/e2e/agent/run.py").read_text()
    assert 'last_turn_ms=(mech.get("sheet_timing") or {}).get("last_turn_ms")' in src
