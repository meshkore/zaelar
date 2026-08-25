"""V2-314 — una ronda cuyos workers murieron por falta de CUOTA no ha medido al producto: es INFRA.

Medido en `find-concert-tickets__es` (2026-08-25 10:53-10:56): tres workers, 1,8 s / 3,9 s / 1,9 s de vida, los
tres contra «licencia-claude · sin relevo» (el plan de Claude había agotado su ventana y la cadena no tenía
sucesor; DeepSeek directo respondía 402 en su propia cuenta). La hoja volvió vacía, el juez leyó la hoja vacía, y
la ronda salió `resultado 1 · mecanismo 2` contra un motor al que no se le dejó arrancar.

Es la misma clase de avería que el conductor fuera de papel, vista desde el otro lado: allí el arnés contaminaba
la medida, aquí la contamina el mundo — nuestra factura. La regla es la misma, INFRA, porque una ronda declarada
INFRA se vuelve a correr y una nota falsa se queda en el tablero para siempre.
"""
import json
import sqlite3

import pytest

from tests.use_cases.e2e.agent import verify as V


@pytest.fixture
def db(tmp_path):
    """Un test unitario NUNCA toca el sandbox vivo: se fabrica el suyo con el esquema mínimo que se lee."""
    p = tmp_path / "obs.db"
    con = sqlite3.connect(p)
    con.execute("CREATE TABLE events (id INTEGER PRIMARY KEY, ts_ms INTEGER, topic TEXT, payload TEXT, "
                "cat TEXT, kind TEXT, label TEXT)")

    def add(label, payload, *, cat="worker", kind="task", ts=2000):
        con.execute("INSERT INTO events (ts_ms, topic, payload, cat, kind, label) VALUES (?,?,?,?,?,?)",
                    (ts, "obs", json.dumps(payload), cat, kind, label))
    con.commit()
    return p, con, add


def test_sin_muertes_por_cuota_no_dice_nada(db):
    p, con, add = db
    add("phase", {"text": "buscando"})
    con.commit()
    r = V.provider_exhausted(str(p), since=1.0)
    assert r["deaths"] == 0 and r["asleep"] == 0


def test_cuenta_las_muertes_y_NOMBRA_al_proveedor(db):
    """El nombre importa: «sin cuota» sin decir de quién no le dice al operador qué recargar."""
    p, con, add = db
    for _ in range(3):
        add("proveedor sin cuota", {"text": "licencia-claude · sin relevo", "ok": False})
    con.commit()
    r = V.provider_exhausted(str(p), since=1.0)
    assert r["deaths"] == 3
    assert r["providers"] == ["licencia-claude"]


def test_la_negativa_a_LANZAR_tambien_cuenta_y_trae_la_hora(db):
    """Las dos mitades del mismo hecho: la muerte, y nosotros habiendo aprendido de ella (V2-314)."""
    p, con, add = db
    add("provider_asleep", {"until": 1787660400.0, "ok": False}, kind="provider_asleep")
    con.commit()
    r = V.provider_exhausted(str(p), since=1.0)
    assert r["asleep"] >= 1
    assert r["reset_at"] == pytest.approx(1787660400.0)


def test_lo_de_ANTES_de_la_ronda_no_se_cuenta(db):
    """`since` es lo que separa esta ronda de la anterior; sin él, una cuota agotada ayer marca la de hoy."""
    p, con, add = db
    add("proveedor sin cuota", {"text": "licencia-claude · sin relevo"}, ts=500)
    con.commit()
    assert V.provider_exhausted(str(p), since=1.0)["deaths"] == 0


def test_la_regla_pide_las_DOS_mitades():
    """Sensibilidad: «hubo una muerte por cuota» a secas declararía INFRA una ronda que luego se relevó y
    entregó — el relevo existe justo para eso (V2-238) — y taparía defectos reales tras un escalón agotado."""
    murio = {"deaths": 3, "asleep": 0, "providers": ["licencia-claude"], "reset_at": 0.0}
    assert V.no_quota_infra(murio, {"ok": 0, "spawned": 3}), "tres muertes por cuota y nadie terminó: es INFRA"
    assert V.no_quota_infra(murio, {"ok": 1, "spawned": 4}) == "", "hubo relevo y ALGUIEN terminó: sí midió"
    assert V.no_quota_infra({"deaths": 0, "asleep": 0}, {"ok": 0}) == "", "sin cuota agotada no se toca nada"
    assert V.no_quota_infra(None, None) == ""


def test_la_frase_NOMBRA_al_proveedor_y_la_hora():
    """Lo accionable de un INFRA por cuota es qué recargar y cuándo vuelve; sin eso solo dice «no midió»."""
    import time
    vuelve = time.time() + 3600
    frase = V.no_quota_infra({"deaths": 3, "asleep": 1, "providers": ["licencia-claude"], "reset_at": vuelve},
                             {"ok": 0})
    assert "licencia-claude" in frase
    assert time.strftime("%H:%M", time.localtime(vuelve)) in frase


def test_negarse_a_LANZAR_basta_aunque_no_muera_nadie():
    """Desde V2-314 el dispatcher no lanza cuando la cadena duerme: cero muertes y cero rondas medidas."""
    assert V.no_quota_infra({"deaths": 0, "asleep": 2, "providers": []}, {"ok": 0})


def test_el_barrido_LO_USA_y_no_pisa_una_averia_ya_declarada():
    """La mitad de cableado (V2-199) — y el orden importa: un conductor fuera de papel manda sobre la cuota,
    porque esa avería es NUESTRA y se arregla, y la cuota solo se espera."""
    import inspect

    from tests.use_cases.e2e.agent import run as R
    src = "\n".join(ln for ln in inspect.getsource(R._run_scenario).splitlines()
                     if not ln.strip().startswith("#"))
    i = src.find("verifymod.no_quota_infra(")
    assert i > 0, "el barrido dejó de consultar la regla de cuota"
    assert "if not crashed:" in src[max(0, i - 200):i]


def test_y_el_informe_LO_LLEVA():
    """La lectura puede acertar y no llegar al informe."""
    import inspect

    from tests.use_cases.e2e.agent import run as R
    src = inspect.getsource(R._run_scenario)
    assert 'mech["provider_exhausted"] = verifymod.provider_exhausted(' in src
