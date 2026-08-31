"""V2-314 — a round whose workers died due to a lack of QUOTA did not measure the product: it is INFRA.

Measured in `find-concert-tickets__es` (2026-08-25 10:53-10:56): three workers, with lifetimes of 1.8 s / 3.9 s / 1.9 s,
all three against «licencia-claude · sin relevo» (Claude's plan had exhausted its window and the chain had no
successor; direct DeepSeek returned 402 on its own account). The sheet came back empty, the judge read the empty
sheet, and the round produced `resultado 1 · mecanismo 2` against an engine that was never allowed to start.

It is the same kind of failure as the out-of-paper driver, seen from the other side: there the harness contaminated
the measurement; here the world—our bill—contaminates it. The rule is the same, INFRA, because a round declared
INFRA is rerun, while a false result remains on the board forever.
"""
import json
import sqlite3

import pytest

from tests.use_cases.e2e.agent import verify as V


@pytest.fixture
def db(tmp_path):
    """A unit test NEVER touches the live sandbox: it creates its own with the minimum schema that is read."""
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
    """The name matters: «sin cuota» without saying whose does not tell the operator what to replenish."""
    p, con, add = db
    for _ in range(3):
        add("proveedor sin cuota", {"text": "licencia-claude · sin relevo", "ok": False})
    con.commit()
    r = V.provider_exhausted(str(p), since=1.0)
    assert r["deaths"] == 3
    assert r["providers"] == ["licencia-claude"]


def test_la_negativa_a_LANZAR_tambien_cuenta_y_trae_la_hora(db):
    """The two halves of the same fact: the death, and us having learned from it (V2-314)."""
    p, con, add = db
    add("provider_asleep", {"until": 1787660400.0, "ok": False}, kind="provider_asleep")
    con.commit()
    r = V.provider_exhausted(str(p), since=1.0)
    assert r["asleep"] >= 1
    assert r["reset_at"] == pytest.approx(1787660400.0)


def test_lo_de_ANTES_de_la_ronda_no_se_cuenta(db):
    """`since` is what separates this round from the previous one; without it, a quota exhausted yesterday marks today's."""
    p, con, add = db
    add("proveedor sin cuota", {"text": "licencia-claude · sin relevo"}, ts=500)
    con.commit()
    assert V.provider_exhausted(str(p), since=1.0)["deaths"] == 0


def test_la_regla_pide_las_DOS_mitades():
    """Sensitivity: «hubo una muerte por cuota» alone would declare INFRA a round that was subsequently handed over and
    completed — handover exists precisely for that (V2-238) — and would hide real defects behind an exhausted step."""
    murio = {"deaths": 3, "asleep": 0, "providers": ["licencia-claude"], "reset_at": 0.0}
    assert V.no_quota_infra(murio, {"ok": 0, "spawned": 3}), "tres muertes por cuota y nadie terminó: es INFRA"
    assert V.no_quota_infra(murio, {"ok": 1, "spawned": 4}) == "", "hubo relevo y ALGUIEN terminó: sí midió"
    assert V.no_quota_infra({"deaths": 0, "asleep": 0}, {"ok": 0}) == "", "sin cuota agotada no se toca nada"
    assert V.no_quota_infra(None, None) == ""


def test_la_frase_NOMBRA_al_proveedor_y_la_hora():
    """The actionable information in quota-related INFRA is what to replenish and when it returns; without that it only says «no midió»."""
    import time
    vuelve = time.time() + 3600
    frase = V.no_quota_infra({"deaths": 3, "asleep": 1, "providers": ["licencia-claude"], "reset_at": vuelve},
                             {"ok": 0})
    assert "licencia-claude" in frase
    assert time.strftime("%H:%M", time.localtime(vuelve)) in frase


def test_negarse_a_LANZAR_basta_aunque_no_muera_nadie():
    """Since V2-314, the dispatcher does not launch when the chain is asleep: zero deaths and zero measured rounds."""
    assert V.no_quota_infra({"deaths": 0, "asleep": 2, "providers": []}, {"ok": 0})


def test_el_barrido_LO_USA_y_no_pisa_una_averia_ya_declarada():
    """The wiring half (V2-199) — and order matters: an out-of-paper driver takes precedence over quota,
    because that failure is OURS and can be fixed, while quota can only be waited out."""
    import inspect

    from tests.use_cases.e2e.agent import run as R
    src = "\n".join(ln for ln in inspect.getsource(R._run_scenario).splitlines()
                     if not ln.strip().startswith("#"))
    i = src.find("verifymod.no_quota_infra(")
    assert i > 0, "el barrido dejó de consultar la regla de cuota"
    assert "if not crashed:" in src[max(0, i - 200):i]


def test_y_el_informe_LO_LLEVA():
    """The reading can be correct and still fail to reach the report."""
    import inspect

    from tests.use_cases.e2e.agent import run as R
    src = inspect.getsource(R._run_scenario)
    assert 'mech["provider_exhausted"] = verifymod.provider_exhausted(' in src
