"""An order the verdict is sure of stays on its card, and the reply is the op that ANSWERS (node 2.186).

Demo pass 62, C2 (2026-09-29): «find me a free 45 minutes tomorrow afternoon to talk with ethan, after my last
meeting». The verdict said `agenda:find_free` at 0.91 and the model ran it; `find_free` returned the slot
(16:00-16:45). Then `order_card_after_read` decided the order was about ANOTHER card, a repair pass presented
the slot on the monitors sheet, and the answer loop kept the LAST op's answer — the sheet's view — so he heard
«there's nothing here with tomorrow's meetings». C3, C4 and C5 fell after it.
"""
from nucleo.flash import data_ops, direct_action as da
from nucleo.flash import turn_brief as tb


def _reads(target="agenda:find_free"):
    def read(b, k, d="", min_confidence=0.0):
        if k == tb.REQUEST_KEY:
            return ("order", {"used": True})
        if k == tb.TARGET_KEY:
            return (target, {"used": True}) if target else (d, None)
        return (d, None)
    return read


def test_a_verdict_sure_of_the_touched_card_leaves_no_other_card(monkeypatch):
    monkeypatch.setattr(tb, "read", _reads("agenda:find_free"))
    monkeypatch.setattr(da, "named_cards", lambda text: ["results"])
    assert da.order_card_after_read({"x": 1}, "find me a free 45 minutes tomorrow afternoon", "agenda") == ""


def test_the_re_route_still_works_when_the_verdict_names_the_other_card(monkeypatch):
    monkeypatch.setattr(tb, "read", _reads("mensajeria:send_to"))
    assert da.order_card_after_read({"x": 1}, "send ethan a telegram with the new time", "agenda") == "mensajeria"
    monkeypatch.setattr(tb, "read", _reads(""))
    assert da.order_card_after_read({"x": 1}, "send ethan a telegram with the new time", "agenda") == "mensajeria"


def test_the_reply_is_composed_from_the_op_that_declares_an_answer():
    slot = {"result": {"free": [{"from": "16:00", "to": "20:00", "first_fit": "16:00-16:45"}]}}
    sheet = {"items": [{"title": "Samsung ViewFinity S7"}]}
    got = data_ops.answer_to_speak([("agenda", slot), ("results::2adbe5-ls1", sheet)],
                                   [("agenda", "find_free"), ("results::2adbe5-ls1", "present")])
    assert got == ("agenda", slot)


def test_without_a_declared_answer_the_last_one_stands_and_nothing_is_none():
    got = data_ops.answer_to_speak([("results", {"a": 1}), ("map", {"b": 2})], [("results", "present"), ("map", "show")])
    assert got == ("map", {"b": 2})
    assert data_ops.answer_to_speak([("agenda", {})], [("agenda", "find_free")]) is None
    assert data_ops.answer_to_speak([], []) is None


def test_the_voice_path_uses_the_selector():
    import pathlib
    src = (pathlib.Path(__file__).resolve().parents[3] / "voice/engine/llm/providers/nucleo.py").read_text(encoding="utf-8")
    assert "_op_answer = _data_ops.answer_to_speak(_got, data_done.get(\"ops\"))" in src
