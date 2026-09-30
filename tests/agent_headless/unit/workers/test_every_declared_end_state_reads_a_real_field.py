"""V2-776 · Every `done_when` a widget declares names a field its view actually has (node 3.109).

Audit 2026-09-30: 14 of 242 actions declared an end state, and the actions the v1 demo fires most (the
search, the picture set, the range, the append) declared none — their failures reached nobody. Coverage is
growing, and a clause over a field the view does not have reads `None` forever: an end state that can never
be judged, which is the silent version of the defect. This walks every declared template.
"""
import importlib
import json
import pathlib

import pytest

from nucleo import verify

ROOT = pathlib.Path(__file__).resolve().parents[4] / "widgets"


def _templates():
    out = []
    for m in sorted(ROOT.glob("*/manifest.json")):
        for action, spec in (json.loads(m.read_text(encoding="utf-8")).get("actions") or {}).items():
            if isinstance(spec, dict) and spec.get("done_when"):
                for c in verify._clauses(spec["done_when"])[1]:
                    out.append((m.parent.name, action, c))
    return out


@pytest.fixture
def seeded(tmp_path, monkeypatch):
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))


def test_the_scripted_actions_declare_their_end_state():
    have = {(w, a) for w, a, _ in _templates()}
    for pair in [("youtube", "search"), ("youtube", "play_result"), ("youtube", "pause"), ("imagenes", "show"),
                 ("imagenes", "add"), ("imagenes", "wallpaper"), ("markets", "range"), ("documento", "append"),
                 ("mensajeria", "send_to"), ("agenda", "add_meeting")]:
        assert pair in have, pair


@pytest.mark.parametrize("wid,action,clause", _templates(), ids=lambda v: v if isinstance(v, str) else "")
def test_a_field_clause_names_a_field_of_the_view(seeded, wid, action, clause):
    if verify.kind_of(clause) != "field":
        return
    view = importlib.import_module(f"widgets.{wid}.data").view_data()
    head = str(clause["field"]).split(".", 1)[0]
    assert head in view or "absent_is" in clause, f"{wid}:{action} reads «{head}», which {wid}'s view does not have"


def test_a_key_the_view_omits_until_set_reads_as_its_declared_absence(seeded):
    """S3 (passes 63, 66, 67): «Done.» over a refused `detail`. `results.view` is written only once set, so the
    clause read None — unverifiable — and the failure reached nobody. Absent is «list», and «list» is not detail."""
    from nucleo import spec
    dw = spec.render("results", "detail", {"item": 1})
    assert verify.check(dw) is False
