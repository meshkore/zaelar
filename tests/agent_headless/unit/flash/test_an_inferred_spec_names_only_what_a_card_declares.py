"""V2-776 L1 · An inferred spec names only what a card declares (node 2.185).

Live pass 62, A1 (2026-09-29): «find me three 27 inch 4k monitors» came without a template, the model was asked
for its end state and wrote `results.view[title~=27]` — a collection no card declares — so the spec was born
«no verificable» and the ending could not be judged. Now the model is told what each card declares (its
collections and its `empty` field), and whatever it still invents is sanitised at birth: an undeclared
collection on a card that declares `empty` becomes «the card is not empty», and nothing readable means None.
"""
from nucleo import spec


def _view(wid):
    return {"empty": False, "items": []} if wid == "results" else ({"empty": True} if wid == "imagenes" else {})


def test_an_undeclared_collection_on_a_card_that_declares_empty_becomes_not_empty(monkeypatch):
    from nucleo import truth
    monkeypatch.setattr(truth, "widget_view", _view)
    got = spec.parse('{"all": [{"widget": "results", "collection": "view", "where": {"title~": "27"}, "expect": "present"}]}')
    assert got == {"all": [{"widget": "results", "field": "empty", "is": "false"}]}


def test_a_declared_collection_is_kept_and_an_undeclared_one_on_a_mute_card_is_dropped(monkeypatch):
    from nucleo import truth
    monkeypatch.setattr(truth, "widget_view", _view)
    got = spec.parse('{"all": [{"widget": "agenda", "collection": "meetings", "where": {"title~": "Ethan"}},'
                     ' {"widget": "contactos", "collection": "cards", "where": {"name~": "x"}}]}')
    assert got == {"all": [{"widget": "agenda", "collection": "meetings", "where": {"title~": "Ethan"}}]}
    assert spec.parse('{"all": [{"widget": "contactos", "collection": "cards", "where": {"name~": "x"}}]}') is None


def test_scalar_desktop_and_canvas_clauses_pass_untouched(monkeypatch):
    from nucleo import truth
    monkeypatch.setattr(truth, "widget_view", _view)
    monkeypatch.setattr(truth, "widget_field", lambda wid, path: "x")
    monkeypatch.setattr(truth, "desktop_wallpaper", lambda: {"url": "", "title": ""})
    got = spec.parse('{"all": [{"desktop": "wallpaper", "expect": "changed"}, {"canvas": "imagenes", "expect": "visible"},'
                     ' {"widget": "youtube", "field": "videoId", "expect": "changed"}]}')
    assert [spec_kind for spec_kind in map(lambda c: c.get("canvas") or c.get("desktop") or c.get("field"), got["all"])] == ["wallpaper", "imagenes", "videoId"]


def test_the_model_is_told_what_each_card_declares(monkeypatch):
    monkeypatch.setattr(spec, "_readable", lambda: {"results": {"collections": [], "empty": True},
                                                    "agenda": {"collections": ["meetings", "tasks"], "empty": False}})
    system = spec._infer_messages("find me three monitors")[0]["content"]
    assert "results: field `empty`" in system and "agenda: collections meetings, tasks" in system
    assert "only these collections and fields" in system


# ── the model's own `done_when` (escalate) goes through the same door at birth ─────────────────────────────────
class _Rec:
    def __init__(self, dw):
        self.done_when, self.uid, self.goal, self.trace_id = dw, "u1", "g", ""


def _born(monkeypatch, dw):
    opened, asked = [], []
    monkeypatch.setattr(spec, "open", lambda d, **k: opened.append(d) or {"id": "s"})
    monkeypatch.setattr(spec, "_schedule", lambda coro: (asked.append(coro.__name__ if hasattr(coro, "__name__") else "x"), coro.close()))
    rec = _Rec(dw)
    spec.born(rec, {"src": "voice"})
    return rec, opened, asked


def test_a_changed_clause_from_the_model_takes_its_baseline_at_birth(monkeypatch):
    from nucleo import truth
    monkeypatch.setattr(truth, "desktop_wallpaper", lambda: {"url": "old.jpg", "title": "old"})
    rec, opened, _ = _born(monkeypatch, {"all": [{"desktop": "wallpaper", "expect": "changed"}]})
    assert opened and "baseline" in opened[0]["all"][0], "without a baseline «changed» can never be judged"
    assert rec.done_when == opened[0]


def test_an_invented_collection_from_the_model_is_sanitised_or_inferred(monkeypatch):
    from nucleo import truth
    monkeypatch.setattr(truth, "widget_view", lambda wid: {"empty": True} if wid == "documento" else {})
    rec, opened, _ = _born(monkeypatch, {"all": [{"widget": "documento", "collection": "documents", "where": {"title~": "Bitcoin"}}]})
    assert opened[0] == {"all": [{"widget": "documento", "field": "empty", "is": "false"}]}
    rec, opened, asked = _born(monkeypatch, {"all": [{"widget": "contactos", "collection": "cards"}]})
    assert opened == [] and asked, "nothing readable left → asked once, as if it had come without one"
