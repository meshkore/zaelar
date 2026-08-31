"""V2-328 — “clean engine” checked two of three signals and claimed the opposite of what was happening.

`probe_client.settle_after_reset()` checks worker sessions (`/api/tasks`) and canvas cards.
It was missing the third: **a BROWSER tab is a separate record**, and it can continue driving without
a live worker session and without an open card.

MEASURED ON 2026-08-25, and I caused it. I killed a batch with `hotel-under-15-days` halfway through; the next one started at
`search-buy-motorcycle__es` and its log says, literally:

    ▸ motor limpio en 0.0s: sin trabajo vivo ni tarjetas (memoria y estado intactos)

Meanwhile, between 21:06 and 21:09, the browser was opening `booking.com/hotel/es/eurostars-regina`,
`booking.com/searchresults?ss=Sevilla` y `google.com/travel/search`, y el prompt de esa ronda llevaba
«ibis Budget Sevilla Aeropuerto — 48 €»; «Eurostars Al-Andalus Palace — 55 €».

The verdicts blamed the PRODUCT:
  · motorcycle (mechanism 2): “inability to filter structural noise (hotels/spare parts)”
  · bicycle (adaptation 2): “distraction by results from other contexts (hotels)”

It was not the product losing focus. It was our work from the previous batch, with the harness claiming the
opposite precisely on the line the operator reads to trust that the next case is measured on its own.

IT IS MEASURED BY ACTIVITY, NOT STATE, and that is deliberate: state already failed once in this exact way
(`active_sessions()` without filtering before V2-115). A record with a gap says “nothing alive” with the same face
as a correct record; a milestone emitted three seconds ago admits no interpretation.
"""
import json
import sqlite3
import time

import pytest

from tests.use_cases.e2e.agent import verify as V


@pytest.fixture
def db(tmp_path):
    """A unit test never looks at the live set."""
    p = tmp_path / "obs.db"
    con = sqlite3.connect(p)
    con.execute("CREATE TABLE events (id INTEGER PRIMARY KEY, ts_ms INTEGER, topic TEXT, payload TEXT, "
                "cat TEXT, kind TEXT, label TEXT)")

    def add(*, hace_s, label="🏁 hito", text="🌐 abrió https://www.booking.com/searchresults"):
        con.execute("INSERT INTO events (ts_ms, topic, payload, cat, kind, label) VALUES (?,?,?,?,?,?)",
                    (int((time.time() - hace_s) * 1000), "obs", json.dumps({"text": text}),
                     "worker", "navegador", label))
        con.commit()
    return p, add


def test_sin_actividad_de_navegador_no_acusa_a_nadie(db):
    p, add = db
    assert V.browser_still_driving(str(p)) == {"driving": False, "last_s": None, "url": ""}


def test_un_hito_RECIENTE_dice_que_sigue_conduciendo(db):
    p, add = db
    add(hace_s=2)
    r = V.browser_still_driving(str(p))
    assert r["driving"] is True
    assert r["last_s"] < 6
    assert "booking.com" in r["url"], "hay que decir DÓNDE está, o el aviso no sirve para nada"


def test_un_hito_VIEJO_no_lo_dice(db):
    """Sensitivity: if any old trace counted, no batch would ever start."""
    p, add = db
    add(hace_s=60)
    r = V.browser_still_driving(str(p))
    assert r["driving"] is False
    assert r["last_s"] >= 59


def test_el_umbral_de_silencio_se_puede_ajustar_y_MUERDE(db):
    p, add = db
    add(hace_s=10)
    assert V.browser_still_driving(str(p), quiet_s=6)["driving"] is False
    assert V.browser_still_driving(str(p), quiet_s=20)["driving"] is True


def test_una_db_ilegible_no_tumba_la_tanda(tmp_path):
    """Fail-soft: being unable to look is not “it is dirty.” Blocking a batch because of a failed read would cost more
    than measuring a case with a warning."""
    assert V.browser_still_driving(str(tmp_path / "no-existe.db"))["driving"] is False


def test_el_arranque_del_caso_LO_CONSULTA_y_PISA_el_veredicto_limpio():
    """Half the wiring, and this is the part that matters: the signal can be perfect and the line can still lie.
    It checks that, in addition to being queried, it MARKS `clean = False` — which is what the operator reads."""
    import inspect

    from tests.use_cases.e2e.agent import run as R
    # `_run_batch`, not `_run_scenario`: the reset lives in the BATCH loop, before each case. This test’s first
    # attempt pointed at the wrong place and went red — exactly what a wiring guard must do when the wiring is
    # not where one thinks it is.
    src = "\n".join(ln for ln in inspect.getsource(R._run_batch).splitlines()
                    if not ln.strip().startswith("#"))
    i = src.find("verifymod.browser_still_driving(")
    assert i > 0, "el arranque del caso dejó de mirar el navegador"
    cola = src[i:i + 400]
    assert 'st["clean"] = False' in cola, "lo consulta y no cambia el veredicto que se imprime"
    j = src.find('if st["clean"]:')
    assert 0 < i < j, "se mira DESPUÉS de imprimir: llegaría tarde"


def test_y_el_aviso_NOMBRA_lo_que_quedó_vivo():
    """A “not clean” message without saying what remained alive forces an investigation from scratch every time."""
    import inspect

    from tests.use_cases.e2e.agent import run as R
    assert 'navegador ACTIVO hace' in inspect.getsource(R._run_batch)
