"""A canvas change names who made it, and the stamp names the build that runs (V2-807 T-15).

The canvas report used to stamp EVERY open/close it diffed as `src: "user"`. A card the client opened from its
own code — a voice fast path on interim text, a restore, the echo of an engine close-all — therefore read on the
timeline and to the arbiter as the operator's own hand («operator-hands»). And every event carried a version
constant bumped by hand, dozens of releases behind the build that was running.

Now the host names a cause per change (`by`) at the call site, the server keeps `user` for a gesture of his hands
only, and the stamp comes from `update/BUILD`.
"""
from __future__ import annotations

import asyncio
import json
import pathlib
import re

import pytest

ENGINE = pathlib.Path(__file__).resolve().parents[4]


@pytest.fixture
def emitted(monkeypatch):
    from server import livekit_api as lk
    from voice import observer
    monkeypatch.setitem(lk._active, "sid", None)            # no live session: every report counts
    out: list = []
    real = observer.emit

    def _spy(kind, label="", text="", role="", extra=None, **kw):
        if kind == "widget":
            out.append((label, dict(extra or {})))
        return real(kind, label, text, role, extra, **kw)

    monkeypatch.setattr(observer, "emit", _spy)
    from memory import api as memory
    memory.set_state({"open_widgets": []})
    return out


def _post(payload):
    from server import canvas_api
    return json.loads(asyncio.run(canvas_api.canvas_state(payload)).body)


def _src(emitted, label, wid):
    return [e.get("src") for lb, e in emitted if lb == label and e.get("id") == wid]


@pytest.mark.parametrize("cause,src", [
    ("fast-path", "client:fast-path"),
    ("restore", "client:restore"),
    ("engine", "client:engine"),
    ("hand", "user"),
])
def test_an_open_carries_the_cause_the_client_named(emitted, cause, src):
    _post({"open": ["navegador::t1"], "by": {"navegador::t1": cause}})
    assert _src(emitted, "show", "navegador") == [src]


def test_a_change_with_no_named_cause_is_never_his_hand(emitted):
    """An old tab sends no `by`: unknown is `client`, not `user`."""
    _post({"open": ["documento"]})
    assert _src(emitted, "show", "documento") == ["client"]


def test_a_close_all_echo_is_not_his_hand(emitted):
    _post({"open": ["documento", "mensajeria"], "by": {"documento": "hand", "mensajeria": "engine"}})
    emitted.clear()
    _post({"open": [], "by": {"documento": "engine", "mensajeria": "engine"}})
    assert _src(emitted, "close", "documento") == ["client:engine"]
    assert _src(emitted, "close", "mensajeria") == ["client:engine"]


def test_a_cause_is_sanitized_before_it_becomes_provenance():
    from voice import canvas_src
    assert canvas_src.of("Hand") == "user"
    assert canvas_src.of("fast path; drop") == "client:fastpathdrop"
    assert canvas_src.of(None) == "client"


def test_every_canvas_report_is_still_an_echo_nobody_obeys():
    from voice import canvas_src
    for src in ("user", "client", "client:engine", "client:fast-path"):
        assert canvas_src.is_report(src), src
    for src in ("flash", "worker:t1", "actionmap", "system", "clientele"):
        assert not canvas_src.is_report(src), src


def test_the_arbiter_does_not_read_client_code_as_his_hands():
    from nucleo.acts import canvas_arbiter as arb
    v = arb.decide("show", "navegador", "client:fast-path", text="pon también la web de punto com")
    assert v.rule != "operator-hands"
    assert arb.decide("show", "agenda", "client:restore").rule == "lifecycle"
    assert arb.decide("show", "agenda", "user").rule == "operator-hands"


def test_both_hosts_name_the_cause_and_send_it():
    """The contract on the two hosts: the report carries `by`, the × button is a hand, the SSE echo is the engine."""
    desk = (ENGINE / "frontend/app/widgets/desktop.js").read_text("utf-8")
    deck = (ENGINE / "frontend/mobile/app/shell/Deck.js").read_text("utf-8")
    sse = (ENGINE / "frontend/app/services/sse.js").read_text("utf-8")
    for src in (desk, deck):
        i = src.index('fetch("/api/canvas/state"')
        assert re.search(r"\bdev, by\b", src[i:i + 300]), "the report must carry the causes (`by`)"
        assert re.search(r'by:\s*"hand"', src), "a close button is a gesture of his hand"
    assert 'by: "engine"' in sse
    assert "/^client(:|$)/" in sse, "the SSE echo test must recognise every canvas report, not only `user`"


def test_the_version_stamp_is_the_running_build():
    import update
    import version
    assert update.build() >= 1
    assert version.short().startswith(f"b{update.build()}+")
    assert version.VERSION not in version.short().split("+", 1)[0]
