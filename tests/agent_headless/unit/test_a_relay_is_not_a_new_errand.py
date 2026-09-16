from __future__ import annotations

from pathlib import Path

import pytest

import nucleo.dispatch as D
from nucleo import surfaces
from nucleo.workers.session import SessionRecord
from widgets import store
from widgets.results import data as sheet


@pytest.fixture(autouse=True)
def _aislado(tmp_path, monkeypatch):
    """Separate disk. A unit test does not touch the operator's real sheet, and this one writes for real: what is
    measured is whether the findings SURVIVE, not whether a function was called."""
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(D, "_SESSIONS", {})
    store._last_hash.clear()
    yield
    store._last_hash.clear()


def _encargo(tid: str, goal: str, sheet_id: str = "") -> SessionRecord:
    rec = SessionRecord(task_id=tid, goal=goal, kind="web")
    surfaces.set_once(rec, "lista")
    if sheet_id:
        rec.sheet = sheet_id          # how a HANDOFF arrives: with its predecessor's sheet already set
    rec.status = "running"
    D._SESSIONS[tid] = rec
    return rec


# ── inheritance ────────────────────────────────────────────────────────────────────────────────────────────

def test_un_encargo_nuevo_estrena_su_hoja():
    """The usual case, intact: without an inherited sheet, its own is sealed and starts empty. Without this case,
    "always inherit" would pass, and then two searches would share a box again—which is what V2-259 fixed."""
    D._sheet_open(_encargo("t1", "Busca fontaneros"))
    sheet.apply_action("present", {"sheet": D.sheet_id_for("t1"), "title": "Fontaneros",
                                   "items": [{"title": "Relatores"}]})

    rec2 = _encargo("t2", "Busca un monitor")
    D._sheet_open(rec2)
    assert rec2.sheet == D.sheet_id_for("t2"), "un encargo nuevo tiene que sellar la SUYA"
    assert sheet.view_data(rec2.sheet)["items"] == [], "un encargo nuevo nace con la hoja vacía"
    assert [i["title"] for i in sheet.view_data(D.sheet_id_for("t1"))["items"]] == ["Relatores"]


def test_un_relevo_hereda_la_hoja_y_NO_la_borra():
    """Both halves at once, because one without the other is WORSE than the bug: it inherits the key (one box, not
    two) and does not start a new one—in other words, the thirteen findings its predecessor delivered before
    running out of quota are still there. Inheriting and starting a new one would turn "two boxes, one full" into
    "one empty box."""
    D._sheet_open(_encargo("t1", "Busca un monitor"))
    heredada = D.sheet_id_for("t1")
    sheet.apply_action("present", {"sheet": heredada, "title": "Monitores",
                                   "items": [{"title": "MSI PRO MP273U", "price": "164,00 €"}]})

    relevo = _encargo("t2", "Busca un monitor", sheet_id=heredada)
    D._sheet_open(relevo)
    assert relevo.sheet == heredada, "el relevo abrió una caja al lado en vez de continuar la del encargo"
    assert [i["title"] for i in sheet.view_data(heredada)["items"]] == ["MSI PRO MP273U"], \
        "estrenar la hoja heredada borra lo que la predecesora ya había entregado"


def test_la_hoja_sellada_no_se_reescribe_nunca():
    """Same principle as `surfaces.set_once`: changing it halfway through moves what the operator is already viewing."""
    rec = _encargo("t9", "Busca un monitor", sheet_id="una-hoja-cualquiera")
    D._sheet_open(rec)
    D._sheet_open(rec)
    assert rec.sheet == "una-hoja-cualquiera"


# ── transport: the sheet must TRAVEL with the handoff ──────────────────────────────────────────────────────

#: Every seam that RELAUNCHES a worker session, with the `src` it stamps. Read from the source of whichever
#: module owns it, so the guard survives a move — and grows with the family instead of silently shrinking.
#: `goal_unmet` joined in V2-707 F2 (the harness: an errand that did not reach its declared end state), and
#: the two below were extracted from `_finish` into `workers/relay.py` in the same batch.
_RELAUNCHES = (("nucleo.workers.relay", '"src": "provider_failover"'),
               ("nucleo.workers.relay", '"src": "context_handoff"'),
               ("nucleo.workers.goal", '"src": "goal_unmet"'))


def _relaunch_window(modname: str, marca: str, width: int = 600) -> str:
    import importlib
    import inspect
    src = inspect.getsource(importlib.import_module(modname))
    assert marca in src, f"{modname} ya no relanza con {marca} — ¿se ha movido? apunta el guarda al sitio nuevo"
    i = src.index(marca)
    return src[i:i + width]


def test_todos_los_relanzamientos_mandan_la_hoja():
    """Wiring guard, not a logic guard. `_sheet_open` can inherit perfectly and be useless if the relaunch does
    not pass it the sheet—which is exactly what happened: the context carried `kind`, `trace`, `depth`, and
    `relay_gen`, but not the sheet. There were TWO paths with the same hole, so fixing one left half alive;
    there are THREE now, and a fourth added without the sheet must fail here on the day it is written."""
    for modname, marca in _RELAUNCHES:
        assert '"sheet"' in _relaunch_window(modname, marca), \
            f"{marca}: el relanzamiento no manda la hoja del encargo"


def test_todos_los_relanzamientos_mandan_tambien_la_superficie():
    """V2-698 — the hole beside the hole above. The sheet travelled; the SURFACE did not, so a «voz» errand
    relayed twice (z.ai → deepseek → licencia) was reborn with the default surface and opened a results sheet
    the operator never asked for (measured 2026-09-15, `results::40aa52-2` by `worker:2`)."""
    for modname, marca in _RELAUNCHES:
        assert '"surface"' in _relaunch_window(modname, marca), \
            f"{marca}: the relaunch does not carry the errand's surface"


def test_el_relanzamiento_del_ARNES_manda_ademas_la_condicion():
    """V2-707 F2 — and its own extra piece: a retry that forgot HOW SUCCESS IS MEASURED would be the last one
    nobody checks, which is the half-done delivery the harness exists to stop."""
    assert '"done_when"' in _relaunch_window("nucleo.workers.goal", '"src": "goal_unmet"')


def test_the_dispatcher_reads_the_surface_from_the_context():
    import inspect

    src = inspect.getsource(D.run_listener)
    assert 'ctx.get("surface")' in src, "the relay's record is born without the surface it was sent"


def test_el_dispatcher_lee_la_hoja_del_contexto():
    """The other end of the cable: sending it is useless if nobody picks it up when constructing the record."""
    import inspect

    src = inspect.getsource(D.run_listener)
    assert 'ctx.get("sheet"' in src, "el record del relevo nace sin la hoja que le mandaron"


def test_una_escalada_normal_sigue_naciendo_sin_hoja():
    """The symmetric bug: if `sheet` slipped in with any default value, EVERY new errand would inherit a box and we
    would return to the single sheet that V2-259 split."""
    assert SessionRecord(task_id="1", goal="x", kind="web").sheet == ""
