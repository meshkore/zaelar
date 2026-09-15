"""V2-702 — a widget's data push has to arrive at the CARD, and instanced sheets it never did.

The operator clicked «Ver detalle» on a search result and nothing happened. The button was not dead and the
backend was not refusing: the action landed and the sheet on disk said `view:"detail"` afterwards. What never
happened was the REPAINT.

`widgets/store.py::save()` is the single choke point that tells the canvas "this widget's data changed", and it
notified using the key it had just written — the DISK key. A directory name may only hold `[A-Za-z0-9_-]`
(`store._safe_id`), so an instanced sheet is `results--7aadbb-1` on disk, while the canvas indexes its open
cards by the CANVAS id, `results::7aadbb-1` (`frontend/app/widgets/desktop.js::show`, and
`widgets/results/sheet_names.py` names both separators in its own docstrings). So
`desktop.refreshData("results--7aadbb-1")` looked up a window that does not exist and returned silently.

The blast radius is much wider than one button: EVERY data push to an instanced sheet was dropped — a worker's
`present` and `append` while a search runs, a `choose`, a tab change. What still arrived were the progress
ticks, because `nucleo/sheets.py` emits through `results.instance_id()`, which already speaks canvas. Measured
on the operator's own timeline for the incident sheet: 167 events under `results::7aadbb-1` (the progress path)
against 16 under `results--7aadbb-1` (every real data write), and only the first 167 ever moved a pixel.

The property under test is the TRANSLATION, not the notification: whatever the store writes, the id it announces
is the one the canvas can look up.
"""
from __future__ import annotations

import re
from pathlib import Path

from widgets import store

_ENGINE = Path(__file__).resolve().parents[4]


def test_an_instanced_sheet_is_announced_by_its_CANVAS_id():
    """`results--t1` on disk is the card `results::t1` on screen."""
    assert store.canvas_id("results--7aadbb-1") == "results::7aadbb-1"
    assert store.canvas_id("navegador--t3") == "navegador::t3"


def test_a_plain_widget_keeps_its_own_name():
    """Most widgets are not instanced at all, and the translation must be invisible to them."""
    for wid in ("results", "contactos", "agenda", "mensajeria"):
        assert store.canvas_id(wid) == wid


def test_a_widget_whose_NAME_contains_the_separator_is_not_cut_in_half():
    """The separator is only a separator when there is something on both sides of it. A widget legitimately
    called `foo--bar`, or an id that starts or ends with the sequence, keeps the name it has: a bad split would
    invent a card id that matches nothing, which is the exact failure this function exists to remove."""
    assert store.canvas_id("--orphan") == "--orphan"
    assert store.canvas_id("orphan--") == "orphan--"
    assert store.canvas_id("") == ""


def test_only_the_FIRST_separator_splits():
    """An instance suffix may itself contain a dash pair (they come from correlation ids); the base is what is
    before the first one."""
    assert store.canvas_id("results--a--b") == "results::a--b"


def test_the_id_the_store_ANNOUNCES_is_the_id_the_canvas_looks_up(tmp_path, monkeypatch):
    """The end-to-end half, with the real `save()`: write an instanced sheet and read back what was emitted.

    This is the assertion that would have caught the incident. It does not check that an event is emitted — the
    old code emitted one — it checks WHICH id rides it.
    """
    seen = []
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    import voice.observer as obs
    monkeypatch.setattr(obs, "emit",
                        lambda kind, label, **kw: seen.append((kind, label, (kw.get("extra") or {}).get("id"))))
    store._last_hash.clear()
    store.save("results--7aadbb-1", {"items": [{"title": "VIER Olla Alta OI18"}], "view": "detail"})
    pushes = [s for s in seen if s[0] == "widget" and s[1] == "data"]
    assert pushes, "guardar una hoja no avisó al canvas"
    assert pushes[-1][2] == "results::7aadbb-1", (
        f"el canvas indexa sus tarjetas por «results::7aadbb-1» y el aviso llegó como «{pushes[-1][2]}» — "
        "`refreshData` no encuentra ninguna ventana con ese id y se calla")


def test_the_canvas_really_does_index_by_the_double_colon():
    """The other side of the contract, asserted against the CANVAS's own source rather than trusted.

    This test would otherwise be measuring one half of an agreement: if `desktop.js` ever switched to the disk
    spelling, everything above would stay green while the screen went still again.
    """
    src = (_ENGINE / "frontend" / "app" / "widgets" / "desktop.js").read_text(encoding="utf-8")
    assert 'rawId.includes("::")' in src, (
        "el canvas ya no parte los ids de instancia por «::» — la traducción de store.canvas_id() apunta al "
        "separador equivocado")
    # …and it looks the card up by the COMPLETE id, which is what makes the spelling matter.
    assert re.search(r"async refreshData\(id\)\s*\{\s*const w = this\.wins\.get\(id\)", src), (
        "refreshData ya no busca la tarjeta por su id completo")


def test_the_two_separators_are_written_down_where_they_are_used():
    """A convention that lives only in two files' habits is one rename away from this bug coming back."""
    sheet_names = (_ENGINE / "widgets" / "results" / "sheet_names.py").read_text(encoding="utf-8")
    assert "_INSTANCE_SEP" in sheet_names and "::" in sheet_names
    store_src = (_ENGINE / "widgets" / "store.py").read_text(encoding="utf-8")
    assert "_DISK_SEP" in store_src and "canvas_id" in store_src


def test_the_progress_path_and_the_data_path_now_agree():
    """`nucleo/sheets.py` announces progress through `results.instance_id()` and the store announces data
    through `canvas_id()`. Two spellings for one card is what the incident WAS, so they are asserted equal."""
    from widgets.results import sheet_names
    for inst in ("7aadbb-1", "t1", "a--b"):
        assert sheet_names.instance_id(inst) == store.canvas_id(sheet_names.sheet_key(inst))
