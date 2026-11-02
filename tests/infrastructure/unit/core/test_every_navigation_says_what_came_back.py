"""Every navigation says what came back — status, time, size, wall (V2-837 G6).

0 of 425 browser events of one cloud session carried an HTTP status: a 403 was inferred from a page title, so «the
site blocked us», «the page was slow» and «it loaded with nothing» left the same trace. One listener on the browser
CONTEXT (`widgets/navegador/page_outcome.py`) keeps every main-frame document outcome; the tab's next `screenshot`
row takes it once.

Disarm: drop `_po.attach(_o._context)` from `owner_page` → the wiring case goes red; drop `**_po.take(page)` from a
screenshot emit → the walk goes red; make `classify` ignore the status → the 403 case goes red.
"""
from __future__ import annotations

import ast
import pathlib

from widgets.navegador import page_outcome as po

ROOT = pathlib.Path(__file__).resolve().parents[4]


class _Frame:
    def __init__(self):
        self.page = None


class _Page:
    def __init__(self):
        self.main_frame = _Frame()
        self.main_frame.page = self


class _Req:
    def __init__(self, page, kind="document", frame=None, failure=None):
        self.resource_type, self.frame, self.failure = kind, frame or page.main_frame, failure
        self.timing = {"startTime": 0, "responseStart": 120.4, "responseEnd": 480.6}


class _Resp:
    def __init__(self, req, status, url, headers=None):
        self.request, self.status, self.url, self.headers = req, status, url, headers or {}


def test_a_blocked_page_says_403_antibot_with_its_time_and_size():
    page = _Page()
    po.on_response(_Resp(_Req(page), 403, "https://cars.example/listing", {"content-length": "5120"}))
    assert po.take(page) == {"status": 403, "ms": 481, "bytes": 5120, "wall": "antibot"}
    assert po.take(page) == {}, "taken once: the next row of the tab, not every row"


def test_the_outcome_classes():
    assert po.classify(200, "https://a.example/x") == "none"
    assert po.classify(404, "https://a.example/x") == "http"
    assert po.classify(429, "https://a.example/x") == "antibot"
    assert po.classify(200, "https://www.google.com/recaptcha/api2/anchor") == "captcha"
    page = _Page()
    po.on_failed(_Req(page, failure="net::ERR_NAME_NOT_RESOLVED"))
    out = po.take(page)
    assert out["status"] == 0 and out["wall"] == "http" and "ERR_NAME" in out["error"]


def test_only_the_main_document_counts():
    page = _Page()
    po.on_response(_Resp(_Req(page, kind="image"), 404, "https://a.example/i.png"))
    po.on_response(_Resp(_Req(page, frame=_Frame()), 403, "https://ads.example/frame"))
    assert po.take(page) == {}


def test_it_is_wired_where_the_context_is_born_and_every_screenshot_row_takes_it():
    src = (ROOT / "widgets/navegador/owner_page.py").read_text(encoding="utf-8")
    assert "_po.attach(_o._context)" in src, "one listener on the context covers every tab and every navigation"
    missing = []
    for p in (ROOT / "widgets/navegador").rglob("*.py"):
        for n in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
            if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "_emit"
                    and n.args and isinstance(n.args[0], ast.Constant) and n.args[0].value == "screenshot"):
                if not any(isinstance(k.value, ast.Call) and getattr(k.value.func, "attr", "") == "take"
                           for k in n.keywords if k.arg is None):
                    missing.append(f"{p.relative_to(ROOT)}:{n.lineno}")
    assert not missing, f"a screenshot row that drops the navigation's outcome: {missing}"
