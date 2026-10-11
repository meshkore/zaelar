"""The round's canvas never obeys the canvas's own echo — the desktop does not either (2.506).

show-real-photo-of-a-new-car__us (sandbox 20261011-115914-en): the round reported `results::8eeb89-1`, the server's
audit normalised it to `widget/show id=results src=user` (V2-039), and the round's own canvas model folded that
back in, reported `results` too, and the engine saw an empty base sheet mounted over its instance — the «ghost card»
the report flagged. `sse.js` drops `src:"user"` events (`_eco`); the round now does the same.
"""
from tests.use_cases.e2e.agent import verify


def test_the_audit_echo_is_not_a_card():
    evs = [{"t_ms": 1, "cat": "widget", "label": "show", "id": "imagenes"},
           {"t_ms": 2, "cat": "widget", "label": "show", "id": "results::8eeb89-1", "src": "worker:1"},
           {"t_ms": 3, "cat": "widget", "label": "show", "id": "results", "src": "user"}]
    assert verify.canvas_now(evs) == ["imagenes", "results::8eeb89-1"]


def test_an_echoed_close_does_not_close_either():
    evs = [{"t_ms": 1, "cat": "widget", "label": "show", "id": "agenda"},
           {"t_ms": 2, "cat": "widget", "label": "close", "id": "agenda", "src": "user"}]
    assert verify.canvas_now(evs) == ["agenda"]
