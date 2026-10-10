"""A results-sheet refusal carries a sentence for HIM beside the hint for the model (V2-781, best-plumber__us).

`detail` on a row it cannot find returned only `error: "no encuentro ese resultado en la hoja (pasa el title o index
1-based)"` — the text channel speaks `message or error`, so the operator's last reply was «…pass the title or index
1-based». The hint stays in `error`; `message` is what is said.
"""
from widgets.results import data as results


def test_a_missing_row_says_a_plain_sentence():
    r = results.apply_action("detail", {"title": "a plumber nobody wrote"})
    assert r.get("ok") is False
    assert "1-based" in r["error"], "the model keeps its hint"
    assert r.get("message") and "1-based" not in r["message"] and "title" not in r["message"]
