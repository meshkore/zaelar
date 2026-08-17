"""widgets/navegador/dom.py — regression coverage for the DOM/human-input primitives split out of owner.py
(2026-08-17 modularization pass). Locks in two things: (1) owner.py's re-export keeps identity with dom.py's
originals, so TaskBrowser's bare-name references still resolve; (2) `mouse` is a REQUIRED parameter on the
four human-input functions -- the old `mouse: dict | None = None` fallback to owner.py's module-level `_mouse`
was dead code (only the also-deleted module-level `agent_act()` ever omitted it), and this test is what keeps
that from silently regressing back in.
"""
import asyncio

import pytest

from widgets.navegador import dom, owner


class _FakeMouse:
    def __init__(self):
        self.calls = []

    async def move(self, x, y):
        self.calls.append((x, y))

    async def click(self, x, y, delay=0):
        self.calls.append(("click", x, y))


class _FakePage:
    def __init__(self):
        self.mouse = _FakeMouse()


def test_owner_reexports_are_identical_to_dom_originals():
    names = ("_DANGER_RE", "_INTERACTIVE", "_JS_EXTRACT", "_describe_el", "_JS_DESCRIBE", "_bulk_metas",
              "_snapshot_lines", "_human_move", "_human_click_handle", "_human_type_handle", "_human_click_at")
    for name in names:
        assert getattr(owner, name) is getattr(dom, name), f"owner.{name} diverged from dom.{name}"


@pytest.mark.parametrize("fn,args", [
    (dom._human_move, (None, 0.0, 0.0)),
    (dom._human_click_handle, (None, None)),
    (dom._human_type_handle, (None, None, "text", False)),
    (dom._human_click_at, (None, 0.0, 0.0)),
])
def test_mouse_is_required_not_a_silent_fallback(fn, args):
    with pytest.raises(TypeError):
        asyncio.run(fn(*args))


def test_human_move_updates_the_passed_mouse_dict():
    page = _FakePage()
    m = {"x": 0.0, "y": 0.0}
    asyncio.run(dom._human_move(page, 42.0, 7.0, m))
    assert m == {"x": 42.0, "y": 7.0}
    assert page.mouse.calls, "expected at least one mouse.move() during the bezier walk"


def test_snapshot_lines_caps_at_60_and_fills_refmap():
    handles = [object() for _ in range(65)]
    metas = [{"role": "button", "name": f"btn{i}", "vis": True} for i in range(65)]
    refmap: dict = {}
    lines = dom._snapshot_lines(handles, metas, refmap)
    assert len(lines) == 60
    assert len(refmap) == 60
    assert refmap[1] is handles[0]


def test_snapshot_lines_skips_invisible_and_unnamed_non_input_elements():
    handles = [object(), object(), object()]
    metas = [
        {"role": "button", "name": "", "vis": True},        # unnamed button -> skipped
        {"role": "textbox", "name": "", "vis": True},        # unnamed textbox -> kept (input types are exempt)
        {"role": "link", "name": "ok", "vis": False},        # invisible -> skipped
    ]
    refmap: dict = {}
    lines = dom._snapshot_lines(handles, metas, refmap)
    assert len(lines) == 1
    assert "textbox" in lines[0]
