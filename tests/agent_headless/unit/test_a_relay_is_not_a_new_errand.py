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
    """Disco APARTE. Un test unitario no toca la hoja real del operador, y este escribe de verdad: lo que se
    mide es si los hallazgos SOBREVIVEN, no si se llamó a una función."""
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(D, "_SESSIONS", {})
    store._last_hash.clear()
    yield
    store._last_hash.clear()


def _encargo(tid: str, goal: str, sheet_id: str = "") -> SessionRecord:
    rec = SessionRecord(task_id=tid, goal=goal, kind="web")
    surfaces.set_once(rec, "lista")
    if sheet_id:
        rec.sheet = sheet_id          # como llega un RELEVO: con la hoja de su predecesora ya puesta
    rec.status = "running"
    D._SESSIONS[tid] = rec
    return rec


# ── la herencia ────────────────────────────────────────────────────────────────────────────────────────────

def test_un_encargo_nuevo_estrena_su_hoja():
    """El caso de siempre, intacto: sin hoja heredada se sella la suya y nace vacía. Sin este caso, «heredar
    siempre» pasaría, y entonces dos búsquedas volverían a compartir caja — lo que V2-259 arregló."""
    D._sheet_open(_encargo("t1", "Busca fontaneros"))
    sheet.apply_action("present", {"sheet": D.sheet_id_for("t1"), "title": "Fontaneros",
                                   "items": [{"title": "Relatores"}]})

    rec2 = _encargo("t2", "Busca un monitor")
    D._sheet_open(rec2)
    assert rec2.sheet == D.sheet_id_for("t2"), "un encargo nuevo tiene que sellar la SUYA"
    assert sheet.view_data(rec2.sheet)["items"] == [], "un encargo nuevo nace con la hoja vacía"
    assert [i["title"] for i in sheet.view_data(D.sheet_id_for("t1"))["items"]] == ["Relatores"]


def test_un_relevo_hereda_la_hoja_y_NO_la_borra():
    """Las dos mitades a la vez, porque una sin la otra es PEOR que el defecto: hereda la clave (una caja, no
    dos) y no la estrena — o sea que los trece hallazgos que la predecesora entregó antes de quedarse sin cuota
    siguen ahí. Heredar y estrenar convertiría «dos cajas, una llena» en «una caja vacía»."""
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
    """Mismo criterio que `surfaces.set_once`: cambiarla a mitad mueve lo que el operador ya está mirando."""
    rec = _encargo("t9", "Busca un monitor", sheet_id="una-hoja-cualquiera")
    D._sheet_open(rec)
    D._sheet_open(rec)
    assert rec.sheet == "una-hoja-cualquiera"


# ── el transporte: la hoja tiene que VIAJAR con el relevo ───────────────────────────────────────────────────

def test_los_dos_relanzamientos_mandan_la_hoja():
    """Guarda de CABLEADO, no de lógica. `_sheet_open` puede heredar perfectamente y no servir de nada si el
    relanzamiento no le pasa la hoja — que es exactamente lo que pasaba: el contexto llevaba `kind`, `trace`,
    `depth` y `relay_gen`, y no la hoja. Son DOS caminos (relevo de proveedor y retoma por contexto agotado) y
    los dos tenían el mismo agujero, así que arreglar uno solo deja la mitad viva."""
    import inspect

    from nucleo.workers import session as S
    src = inspect.getsource(S.WorkerSession._finish)
    for marca in ('"src": "provider_failover"', '"src": "context_handoff"'):
        i = src.index(marca)
        ventana = src[i:i + 400]
        assert '"sheet"' in ventana, f"{marca}: el relanzamiento no manda la hoja del encargo"


def test_el_dispatcher_lee_la_hoja_del_contexto():
    """La otra punta del cable: mandarla no sirve si nadie la recoge al construir el record."""
    import inspect

    src = inspect.getsource(D.run_listener)
    assert 'ctx.get("sheet"' in src, "el record del relevo nace sin la hoja que le mandaron"


def test_una_escalada_normal_sigue_naciendo_sin_hoja():
    """El defecto simétrico: si `sheet` se colara con cualquier valor por defecto, TODO encargo nuevo heredaría
    una caja y volveríamos a la hoja única que V2-259 partió."""
    assert SessionRecord(task_id="1", goal="x", kind="web").sheet == ""
