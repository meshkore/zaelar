"""A reader pointed at the wrong box does not fail — it invents facts.

Measured on `two-searches-two-sheets` (2026-08-21), the first round after V2-259 landed: the errand wrote to
`results::1` / `results::2` and `results_sheet()` read the bare `results`, which by then was a DIFFERENT box
holding fifteen leftover rows of hotels and cars from earlier rounds. The judge read that and concluded the
agent "claims to have found plumbers with no mechanism backing it" — a finding that looks exactly as credible
as a real one, filed against an agent that had done nothing wrong.

The ids come from `sheet_instances`, so the two readers cannot point at different boxes.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from tests.use_cases.e2e.agent import verify  # noqa: E402


def _fake(monkeypatch, boxes: dict):
    """`boxes` maps the QUERY SUFFIX to the payload — the shape the widget route really takes."""
    seen: list[tuple[str, str]] = []

    def _read(wid, q=""):
        seen.append((wid, q))
        return boxes.get(q)

    monkeypatch.setattr(verify.probe_client, "widget_data", _read)
    return seen


def test_each_instance_is_read_with_its_own_suffix(monkeypatch):
    seen = _fake(monkeypatch, {"1": {"items": [{"title": "Fontanero A"}], "title": "fontanero"},
                               "2": {"items": [{"title": "Coche B"}], "title": "coche"}})
    r = verify.results_sheet(["results::1", "results::2"])
    assert seen == [("results", "1"), ("results", "2")]
    assert r["n_items"] == 2 and r["n_named"] == 2
    assert [b["id"] for b in r["per_box"]] == ["results::1", "results::2"]


def test_the_bare_box_is_NOT_read_when_instances_exist(monkeypatch):
    """The whole point. The bare box survives across rounds and is nobody's errand after V2-259 — reading it
    alongside the instances would fold somebody else's leftovers into this errand's count."""
    seen = _fake(monkeypatch, {"1": {"items": [{"title": "Fontanero A"}]},
                               "": {"items": [{"title": "Hotel de otra ronda"}] * 15}})
    r = verify.results_sheet(["results::1"])
    assert ("results", "") not in seen
    assert r["n_items"] == 1 and "Hotel de otra ronda" not in (r["titles"] or [])


def test_with_no_instances_it_falls_back_to_the_bare_box(monkeypatch):
    """An engine from before V2-259, or a round where no sheet was opened: then the bare box IS the only one,
    and refusing to read it would report an empty sheet that is not empty."""
    seen = _fake(monkeypatch, {"": {"items": [{"title": "Algo"}]}})
    r = verify.results_sheet(None)
    assert seen == [("results", "")]
    assert r["read"] is True and r["n_items"] == 1


def test_a_non_results_instance_id_is_ignored(monkeypatch):
    """`sheet_instances` only ever yields results boxes, but this reader must not turn into a generic widget
    reader by accident: a `navegador::t3` in that list would make it read the browser card as a sheet."""
    seen = _fake(monkeypatch, {"": {"items": []}})
    verify.results_sheet(["navegador::t3"])
    assert seen == [("results", "")]


def test_unreadable_is_not_empty(monkeypatch):
    """`read: False` and `n_items: 0` mean different things and always have: an unread sheet is not an empty
    one, and 0 must never stand for "nobody looked"."""
    _fake(monkeypatch, {})
    r = verify.results_sheet(["results::1"])
    assert r["read"] is False and r["n_items"] == 0


def test_the_two_readers_cannot_point_at_different_boxes():
    """Guard on the wiring, which is the half a behavioural test cannot see: `mechanism_report` must take the
    ids from `sheet_instances` rather than calling `results_sheet()` bare. That is what keeps "which boxes
    were opened" and "what is in them" answering about the SAME boxes."""
    import inspect
    src = inspect.getsource(verify.mechanism_report)
    assert "results_sheet(" in src
    line = next(l for l in src.splitlines() if '"results_sheet"' in l)
    assert "sheet_instances(" in line, f"results_sheet no recibe los ids de sheet_instances: {line.strip()}"


# ── The suffix has to reach the REQUEST, not just the call ────────────────────────────────────────────
# The two cases above mock `widget_data` itself, so they prove `results_sheet` ASKS for the right box and
# nothing more. They passed while `widget_data` was dropping `q` on the floor and reading the bare box on
# every call — the fix had landed in the neighbouring function. A mock placed above the defect cannot see
# it, so these two go under it, at the HTTP boundary.


def _path_seen(monkeypatch) -> list:
    from tests.use_cases.e2e.agent import probe_client
    seen: list[str] = []
    monkeypatch.setattr(probe_client, "_get", lambda path, timeout=20.0: seen.append(path) or {"items": []})
    return seen


def test_the_suffix_reaches_the_request(monkeypatch):
    from tests.use_cases.e2e.agent import probe_client
    seen = _path_seen(monkeypatch)
    probe_client.widget_data("results", "2")
    assert seen == ["/widgets/results/data?q=2"]


def test_no_suffix_asks_for_the_bare_box(monkeypatch):
    """Sensitivity: a `?q=` glued on unconditionally would ask for a box that does not exist, and the reader
    would report every un-instanced widget as unreadable."""
    from tests.use_cases.e2e.agent import probe_client
    seen = _path_seen(monkeypatch)
    probe_client.widget_data("agenda")
    assert seen == ["/widgets/agenda/data"]


def test_the_row_reader_builds_the_same_path(monkeypatch):
    """`widget_rows` is the same request seen at another shape. It is in this test because it spent a commit
    referring to a `q` it did not take as an argument — a `NameError` waiting for the first round whose
    scenario reads the agenda, which is a crash and not a finding."""
    from tests.use_cases.e2e.agent import probe_client
    seen = _path_seen(monkeypatch)
    probe_client.widget_rows("agenda", "meetings")
    probe_client.widget_rows("results", "items", "2")
    assert seen == ["/widgets/agenda/data", "/widgets/results/data?q=2"]


# ── la forma REAL que entrega `sheet_instances`: la pelada Y la instancia ──────────────────────────────
# El guarda de arriba se escribió con `ids=["results::1"]`, y con eso el filtro viejo ya excluía la pelada
# «sola». Pero `sheet_instances` la incluye en cuanto el canvas la abrió, y la tanda del 2026-08-24 03:02
# entregó exactamente `["results", "results::c2567e-1"]`: el filtro partía por `::` y se quedaba con las dos,
# así que las 38 filas acumuladas en la caja de nadie se sumaron a CADA caso. El del monitor salió con seis
# títulos de guitarra; el de la guitarra, con bicicletas.
#
# Este caso no es una variante del de arriba: es la entrada que producción produce, que es la que hay que
# probar (la lección de V2-199/V2-200 aplicada a un lector).

_MEDIDO = ["results", "results::c2567e-1"]


def test_con_la_pelada_EN_la_lista_tampoco_se_lee(monkeypatch):
    seen = _fake(monkeypatch, {"c2567e-1": {"items": [{"title": "Monitor Dell 27"}], "title": "monitor"},
                               "": {"items": [{"title": "Guitarra Yamaha F370BS"}] * 18}})
    r = verify.results_sheet(_MEDIDO)
    assert ("results", "") not in seen, "la caja de nadie vuelve a entrar en la medida del caso"
    assert r["n_items"] == 1
    assert "Guitarra Yamaha F370BS" not in (r["titles"] or [])
    assert [b["id"] for b in r["per_box"]] == ["results::c2567e-1"]


def test_y_lo_que_NO_se_pudo_mirar_se_dice_None_no_cero(monkeypatch):
    """«No lo sé» y «vacía» no pueden verse igual — con instancias abiertas la pelada no se lee a propósito."""
    _fake(monkeypatch, {"c2567e-1": {"items": [{"title": "Monitor Dell 27"}]},
                        "": {"items": [{"title": "Guitarra"}] * 18}})
    assert verify.results_sheet(_MEDIDO)["bare_box"] is None


def test_sin_instancias_la_pelada_ES_la_medida_y_se_cuenta(monkeypatch):
    _fake(monkeypatch, {"": {"items": [{"title": "Algo"}, {"title": "Otro"}]}})
    r = verify.results_sheet(None)
    assert r["n_items"] == 2 and r["bare_box"] == 2
