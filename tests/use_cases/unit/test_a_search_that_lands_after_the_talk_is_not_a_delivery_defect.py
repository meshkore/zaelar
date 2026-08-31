"""A search round that arrives with the conversation closed does not prove a delivery failure (V2-378).

Measured in `compare-insurance-quotes__es` (2026-08-27, 2/5). The report warned «⚠️ y NINGUNA se le empujó al
cerebro» and the judge turned it into a [media] and improvement no. 5: *«Es un fallo de ENTREGA del mecanismo que
deja al cerebro sin datos»*. Reading that session's timestamps:

    último turno del operador   298,0 s
    vueltas de búsqueda         472,9 s … 520,8 s   ← las OCHO

The conversation had been closed for almost three minutes. Notes are pushed into a mailbox that nobody was going
to empty, and the counter reads the DRAIN (the event the channel emits when delivering the note during a turn), not
the push — so it showed zero. There was no mechanism to fix: there was nobody to deliver to.

It also corrects a figure in the report itself: it said «2 consulta(s), 1 respuesta(s)», while the log contains
EIGHT searches and EIGHT results, all from the worker's NATIVE `WebSearch`.

It belongs to the same family as the line that report already prints for workers —«el motor SEGUÍA trabajando al
medir: lo que falte puede ser todavía no, no nunca»—: this channel did not receive that safeguard.
"""
import pytest

from tests.use_cases.e2e.agent import judge as J, report as R


def _texto(x) -> str:
    """`mechanism_facts` returns a STRING and `_mechanism_numbers` a list. Joining a string with «\n» inserts
    a separator between every character, so the first version of this file found nothing and failed
    for the wrong reason."""
    return x if isinstance(x, str) else "\n".join(x)


def _sr(returns, tarde, notas=0):
    return {"search_returns": {"queries": returns, "returns": returns,
                               "returns_after_last_turn": tarde, "notes_from_search": notas,
                               "sample": ["Web search results for query: precio medio seguro"]}}


# ── the judge ────────────────────────────────────────────────────────────────────────────────────────────────

def test_la_ronda_medida_ya_no_se_puntua_como_fallo_de_mecanismo():
    txt = _texto(J.mechanism_facts(_sr(8, 8)))
    assert "fallo de ENTREGA del mecanismo" not in txt
    assert "no se puntúa" in txt and "ya cerrada" in txt


def test_una_vuelta_A_TIEMPO_sin_nota_SIGUE_siendo_un_fallo():
    """The regression guard that supports the fix: V2-236 exists because the search responded correctly and died
    inside the worker. That must not go unnoticed."""
    txt = _texto(J.mechanism_facts(_sr(8, 0)))
    assert "fallo de ENTREGA del mecanismo" in txt
    assert "CON LA CONVERSACIÓN ABIERTA" in txt


def test_con_vueltas_MIXTAS_se_cuentan_solo_las_de_a_tiempo():
    txt = _texto(J.mechanism_facts(_sr(8, 6)))
    assert "CONTESTÓ 2 vez/veces CON LA CONVERSACIÓN ABIERTA" in txt


def test_si_HUBO_notas_no_se_dice_nada():
    txt = _texto(J.mechanism_facts(_sr(8, 0, notas=3)))
    assert "empujó al cerebro" not in txt


# ── the report ─────────────────────────────────────────────────────────────────────────────────────────────

def test_el_informe_explica_la_llegada_tardia_en_vez_de_avisar():
    txt = _texto(R._mechanism_numbers(_sr(8, 8)))
    assert "NINGUNA se le empujó" not in txt
    assert "DESPUÉS del último turno" in txt and "NO es un fallo de entrega" in txt


def test_el_informe_SIGUE_avisando_cuando_toca():
    txt = _texto(R._mechanism_numbers(_sr(8, 0)))
    assert "⚠️ y NINGUNA se le empujó al cerebro" in txt


# ── the counter ────────────────────────────────────────────────────────────────────────────────────────────

def _db(tmp_path, vueltas_ms):
    """A minimal event store with one search request and N search results at the given times."""
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
    """The measured round, in miniature: last turn at 298 s, the eight results between 473 and 521."""
    from tests.use_cases.e2e.agent import verify as V
    db = _db(tmp_path, [473_000, 480_000, 500_000, 521_000])
    out = V.search_returns(db, since=0, last_turn_ms=298_000)
    assert out["returns"] == 4 and out["returns_after_last_turn"] == 4


def test_el_contador_no_llama_tardia_a_una_de_a_tiempo(tmp_path):
    from tests.use_cases.e2e.agent import verify as V
    out = V.search_returns(_db(tmp_path, [100_000, 473_000]), since=0, last_turn_ms=298_000)
    assert out["returns"] == 2 and out["returns_after_last_turn"] == 1


def test_sin_saber_el_ultimo_turno_no_se_inventa_nada(tmp_path):
    """`last_turn_ms` may be missing (a round without a transcript). Counting those results as late would silence a
    real failure; counting them as on time preserves the usual warning, which is the safe direction."""
    from tests.use_cases.e2e.agent import verify as V
    out = V.search_returns(_db(tmp_path, [473_000, 521_000]), since=0)
    assert out["returns"] == 2 and out["returns_after_last_turn"] == 0


def test_el_arnes_PASA_el_instante_del_ultimo_turno():
    """The wiring: the counter can be perfect and still not receive the data."""
    from pathlib import Path
    src = Path("tests/use_cases/e2e/agent/run.py").read_text()
    assert 'last_turn_ms=(mech.get("sheet_timing") or {}).get("last_turn_ms")' in src
