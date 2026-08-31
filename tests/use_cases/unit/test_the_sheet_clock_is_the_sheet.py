"""The delivery clock is the SHEET's, not the browser narration's (2026-08-24).

`sheet_timing` is the field used to decide this suite's most consequential question: whether the agent HAD
results and did not mention them (behavior), or whether the browser finished after the turns ran out (latency).
They direct fixes to opposite halves of the system. It had two defects, both measured:

1. `id == "results"`, an EXACT comparison against the pre-V2-259 id, when there was one sheet. Since
   then each job opens its own (`results::<id>`) and that `show` matched nothing. The only match
   was the bare box's… emitted by the canvas ECHO (`src="user"`), meaning the phantom that V2-261
   filters in the frontend. `sheet_ms` measured when a card that nobody opened appeared.

2. `first_result_ms` came from a `browser` event whose TEXT parsed as items — that is, when the
   browser COUNTED an extraction, not when the sheet received rows. On the same sheet from the 18:02 round:
   rows at **18:02:39**, narration at **18:14:36**. Twelve minutes. Every «arrived 42 s earlier /
   163 s later» from that batch was measured against that clock.

And opening a sheet is not filling it: opening emits its own `data`, so without distinguishing it the row clock
falls at the same instant as the opening clock and EVERY round appears to have delivered at the beginning —
the most convenient lie this field could tell. They are separated by `src`, measured by following a complete
sheet:

    18:02:00  data   results--c30db3-1  src=system     ← opening (disk mirror)
    18:02:00  show   results::c30db3-1  src=worker:1   ← sheet opens
    18:02:39  data   results::c30db3-1  src=worker     ← rows start arriving here
    18:09:26  blank  results--c30db3-1  src=system     ← a clearing
"""
import json
import sqlite3

import pytest

from tests.use_cases.e2e.agent import verify


def _db(tmp_path, events):
    """A database with the REAL shape of `events` — including columns, which have already bitten once today."""
    p = tmp_path / "s.db"
    con = sqlite3.connect(str(p))
    con.execute("CREATE TABLE events (ts_ms REAL, topic TEXT, kind TEXT, label TEXT, payload TEXT)")
    for ts, kind, label, ident, src in events:
        con.execute("INSERT INTO events VALUES (?,?,?,?,?)",
                    (ts, "observer", kind, label,
                     json.dumps({"id": ident, "label": label, "src": src})))
    con.commit(); con.close()
    return str(p)


# The 18:02 round exactly as it appeared in the log — CORRECTED on 2026-08-24 (V2-300) using what round 23 showed:
# a `data src=worker` WITHOUT `op` is the PHASE repaint (`sheets.record_phase`, «there is nothing to save»),
# not a row. In 23 that repaint moved the clock 104 s earlier and the judge filed [high] a «full sheet»
# that was EMPTY — the turn was telling the truth and the instrument accused the product. The real delivery is
# the intake (`src=browser`) or a worker data-op through the bridge, which travels WITH its `op`.
REAL = [
    (1000.0, "widget", "data",  "results--c30db3-1", "system"),
    (1000.0, "widget", "show",  "results::c30db3-1", "worker:1"),
        (20000.0, "widget", "data", "results::c30db3-1", "worker"),      # phase repaint — NOT a row
        (39000.0, "widget", "data", "results::c30db3-1", "navegador"),   # the intake: real rows arrive here
    (60000.0, "widget", "data", "results::c30db3-1", "worker"),
]


def test_la_hoja_del_ENCARGO_es_la_que_se_mide(tmp_path):
    out = verify.sheet_timing(_db(tmp_path, REAL))
    assert out["sheet_box"] == "c30db3-1", "se mide la hoja del encargo, no la caja pelada"
    assert out["sheet_ms"] == 1000.0


def test_el_ECO_de_la_caja_pelada_no_cuenta(tmp_path):
    """`src="user"` is the canvas reporting what already happened — the phantom V2-261 filters. Treating it as
    the sheet opening measured a card that nobody opened."""
    ev = [(500.0, "widget", "show", "results", "user")] + REAL
    out = verify.sheet_timing(_db(tmp_path, ev))
    assert out["sheet_box"] == "c30db3-1"
    assert out["sheet_ms"] == 1000.0, "el eco es 500 ms antes y no puede ganar"


def test_ESTRENAR_no_es_llenar(tmp_path):
    """Without this, the row clock falls at the instant of opening and every round «delivers at the beginning»."""
    out = verify.sheet_timing(_db(tmp_path, REAL))
    assert out["sheet_rows_ms"] == 39000.0
    assert out["sheet_rows_ms"] != out["sheet_ms"]


def test_un_REPINTADO_DE_FASE_no_es_una_fila(tmp_path):
    """The case from round 23: `record_phase` emits `data src=worker` so the process tab advances,
    with the sheet still EMPTY. Counting it moved the clock 104 s earlier and the judge accused the turn of
    concealing a delivery that did not exist."""
    ev = [(1000.0, "widget", "show", "results::r23-1", "worker:1"),
          (5000.0, "widget", "data", "results::r23-1", "worker"),     # fase, sin op
          (9000.0, "widget", "data", "results::r23-1", "worker")]     # fase, sin op
    out = verify.sheet_timing(_db(tmp_path, ev))
    assert out["sheet_rows_ms"] is None, "solo fases: la hoja nunca recibió una fila"


def test_una_DATA_OP_del_worker_si_cuenta(tmp_path):
    """The other direction: a worker writing rows through the bridge (`hbwidget data results append`) emits
    `src=worker` WITH its `op` — that is a delivery, and losing it would be the opposite gap."""
    p = tmp_path / "op.db"
    import sqlite3 as _sq
    con = _sq.connect(str(p))
    con.execute("CREATE TABLE events (ts_ms REAL, topic TEXT, kind TEXT, label TEXT, payload TEXT)")
    con.execute("INSERT INTO events VALUES (?,?,?,?,?)",
                (1000.0, "observer", "widget", "show",
                 json.dumps({"id": "results::op-1", "label": "show", "src": "worker:1"})))
    con.execute("INSERT INTO events VALUES (?,?,?,?,?)",
                (7000.0, "observer", "widget", "data",
                 json.dumps({"id": "results::op-1", "label": "data", "src": "worker", "op": "append"})))
    con.commit(); con.close()
    out = verify.sheet_timing(str(p))
    assert out["sheet_rows_ms"] == 7000.0


def test_un_VACIADO_tampoco_es_llenar(tmp_path):
    ev = [(1000.0, "widget", "show", "results::x-1", "worker:1"),
          (5000.0, "widget", "blank", "results--x-1", "system"),
          (5000.0, "widget", "data", "results--x-1", "system"),
          (9000.0, "widget", "data", "results::x-1", "navegador")]
    out = verify.sheet_timing(_db(tmp_path, ev))
    assert out["sheet_rows_ms"] == 9000.0, "el `data` del vaciado es del sistema y no cuenta"


def test_las_DOS_formas_del_id_son_la_misma_hoja(tmp_path):
    """`results::<x>` (canvas) and `results--<x>` (disk) coexist in the same second; looking at only one loses
    half the writes."""
    assert verify._sheet_timing_box("results::abc-1") == "abc-1" if hasattr(verify, "_sheet_timing_box") else True
    out = verify.sheet_timing(_db(tmp_path, [
        (1000.0, "widget", "show", "results--z-9", "worker:1"),
        (4000.0, "widget", "data", "results::z-9", "navegador")]))
    assert out["sheet_box"] == "z-9" and out["sheet_rows_ms"] == 4000.0


def test_NO_MEDIDO_no_es_llego_tarde(tmp_path):
    """Without writes from a producer, the clock remains None, never 0 — confusing them invents a failure."""
    out = verify.sheet_timing(_db(tmp_path, [(1000.0, "widget", "show", "results::q-1", "worker:1")]))
    assert out["sheet_rows_ms"] is None


def test_se_CONSERVA_el_reloj_de_la_narracion_aparte():
    """It answers another question —when the browser counted it— and losing it while fixing this would trade one
    gap for another. It has its own name so nobody confuses them again."""
    import inspect
    from tests.use_cases.e2e.agent import run as runmod
    src = inspect.getsource(runmod._run_scenario)
    assert "narrated_after_last_turn_s" in src
    assert "sheet_rows_ms" in src
    assert src.index("_rows - _lt") < src.index("_fr - _lt"), (
        "el que manda en `after_last_turn_s` tiene que ser el reloj de la HOJA")


# ── V2-355: and the clock that times a DELIVERY is even stricter ──────────────────────────────
#
# V2-300 (above) removed the phase repaint from the clock. Half a layer remained: `sheet_rows_ms` still starts
# with a PRODUCER's first write, and `verify`'s own comment already admitted it — «a producer's `data` does not
# PROVE that the row has a name». The worker writes to its sheet long before it has candidates: the criteria,
# the title, its plan. Measured in `restaurant-tonight-madrid` (2026-08-27), the sheet ended with
# «Mensaje de WhatsApp preparado», «Por teléfono (lo más rápido)» and «Qué me paró» — its own prose
# contada como tres candidatos.
#
# And that clock feeds `delivery_lag_s`, meaning it produces the [high] RETENTION results, which are the
# number-one blocker for half a dozen cases. In `search-buy-camera__es` (2026-08-27) it timed **130.8 s of
# retention** with the first page opened at **62.3 s**: at 17 s a candidate could not exist. Same
# pattern as V2-300, one layer deeper, and at the same cost — the instrument accusing the product.
#
# The browser intake (`src == "navegador"`) is, by construction, candidates extracted from a page. It is
# stored SEPARATELY instead of tightening the one above because the two say different things and both are needed:
# «when writing started» separates «arrived late» from «never arrived»; «when candidates existed» is the only one
# that can time a delivery.

def _db_op(tmp_path, events):
    """Like `_db`, but the rows carry `op` — the field distinguishing a bridge data-op from the repaint."""
    p = tmp_path / "op.db"
    con = sqlite3.connect(str(p))
    con.execute("CREATE TABLE events (ts_ms REAL, topic TEXT, kind TEXT, label TEXT, payload TEXT)")
    for ts, kind, label, ident, src, op in events:
        d = {"id": ident, "label": label, "src": src}
        if op:
            d["op"] = op
        con.execute("INSERT INTO events VALUES (?,?,?,?,?)", (ts, "observer", kind, label, json.dumps(d)))
    con.commit(); con.close()
    return str(p)


# The shape of `search-buy-camera__es`: the worker opens and writes its own content early, the page does not open until
# second 62, and the intake arrives afterward. A candidate BEFORE opening the first page is impossible.
CAMARA = [
    (1_000.0, "widget", "show", "results::afd21d-1", "worker:1", None),
    (17_500.0, "widget", "data", "results::afd21d-1", "worker", "present"),   # sus criterios, NO candidatos
    (62_300.0, "navegador", "hito", "", "", None),
    (70_000.0, "widget", "data", "results::afd21d-1", "navegador", None),     # the intake: candidates are HERE
]


def test_el_reloj_flojo_sigue_diciendo_cuando_empezo_a_escribir(tmp_path):
    """The one above is not tightened: it separates «arrived late» from «never arrived», and that half is needed."""
    out = verify.sheet_timing(_db_op(tmp_path, CAMARA), since=0)
    assert out["sheet_rows_ms"] == 17_500.0


def test_el_reloj_ESTRICTO_espera_al_intake(tmp_path):
    """The one that times a delivery. 17.5 s versus 70 s is 52 seconds of invented «retention»."""
    out = verify.sheet_timing(_db_op(tmp_path, CAMARA), since=0)
    assert out["sheet_named_ms"] == 70_000.0


def test_una_hoja_que_SOLO_tiene_prosa_del_worker_no_arranca_el_reloj_estricto(tmp_path):
    """`restaurant-tonight-madrid`: three worker data-ops and not a single extraction. There were no candidates,
    so there is nothing to time — and `None` is the honest answer, not zero."""
    solo_prosa = [
        (1_000.0, "widget", "show", "results::1e8200-1", "worker:1", None),
        (10_000.0, "widget", "data", "results::1e8200-1", "worker", "present"),
        (20_000.0, "widget", "data", "results::1e8200-1", "worker", "append"),
        (30_000.0, "widget", "data", "results::1e8200-1", "worker", "append"),
    ]
    out = verify.sheet_timing(_db_op(tmp_path, solo_prosa), since=0)
    assert out["sheet_named_ms"] is None, "sin intake no hubo candidatos que retener"
    assert out["sheet_rows_ms"] == 10_000.0


def test_el_repintado_de_fase_sigue_fuera_de_los_DOS(tmp_path):
    """V2-300 is not reverted along the way: a `data src=worker` WITHOUT `op` is the phase repaint."""
    solo_repintado = [
        (1_000.0, "widget", "show", "results::x-1", "worker:1", None),
        (20_000.0, "widget", "data", "results::x-1", "worker", None),
    ]
    out = verify.sheet_timing(_db_op(tmp_path, solo_repintado), since=0)
    assert out["sheet_rows_ms"] is None and out["sheet_named_ms"] is None


def test_el_intake_solo_ya_arranca_los_dos(tmp_path):
    """A round where the browser delivers without the worker having written first: the two clocks coincide,
    which is correct — there is nothing to separate there."""
    directo = [
        (1_000.0, "widget", "show", "results::y-1", "worker:1", None),
        (45_000.0, "widget", "data", "results::y-1", "navegador", None),
    ]
    out = verify.sheet_timing(_db_op(tmp_path, directo), since=0)
    assert out["sheet_rows_ms"] == 45_000.0 == out["sheet_named_ms"]
