"""The tab SAYS which sheet it belongs to — otherwise, two opposite diagnoses read the same (2026-08-24).

`create()` has sealed the task's sheet in the tab since V2-281, and that seal is how
`nucleo/flash/live_blocks.py::_sheet_has_rows` determines whether the task already has rows. Without a seal it answers
False no matter how many rows there are, and the turn keeps saying «todavía no tengo nada» while the operator sees
the results arrive — measured today in three cases: the sheet filled up 42, 49, and 113 s BEFORE the last turn.

The seal lived only inside the process. From outside, «la pestaña nunca se selló» and «se selló y algo río
abajo lo ignoró» gave EXACTLY the same reading, and choosing incorrectly costs an entire batch measuring the wrong
half. It is the same gap that V2-207 closed with `wall`/`walls_hit`, for the same reason.

This does NOT fix delivery: it makes the question answerable from any report.
"""
from widgets.navegador import data as navdata
from widgets.navegador import tasks as navtasks


def test_la_vista_dice_de_que_hoja_es_la_pestana():
    tid = navtasks.create("busca una guitarra", sheet="results::abc-1")
    try:
        assert navdata._task_view(navtasks.get(tid))["sheet"] == "results::abc-1"
    finally:
        navtasks.drop(tid) if hasattr(navtasks, "drop") else None


def test_una_pestana_SIN_encargo_dice_que_no_tiene_hoja():
    """Empty is the correct answer, not a failure: a tab that the operator opens manually has no task
    behind it, so it has no sheet of its own. It simply cannot be indistinguishable from one that did have one."""
    tid = navtasks.create("el operador navegando a mano")
    try:
        assert navdata._task_view(navtasks.get(tid))["sheet"] == ""
    finally:
        navtasks.drop(tid) if hasattr(navtasks, "drop") else None


def test_el_sello_lo_pone_QUIEN_abre_el_encargo():
    """Wiring guard. `_prepare_web` is the only one that passes it today, and if it stops doing so `_sheet_has_rows`
    becomes blind without anything failing — the failure mode this field exists to make visible."""
    import inspect
    from nucleo import dispatch
    src = "\n".join(l for l in inspect.getsource(dispatch._prepare_web).splitlines()
                    if not l.strip().startswith("#"))
    assert "sheet=sheet_of(rec)" in src, (
        "la pestaña del encargo tiene que nacer sellada; sin sello, el turno no puede ver su propia hoja")
