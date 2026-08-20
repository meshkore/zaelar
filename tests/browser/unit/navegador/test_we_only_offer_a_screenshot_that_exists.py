"""V2-205 — we told the worker to read a screenshot that was not on disk.

`_shot_path()` returned the PNG's path whether or not the file existed, and `nav_cli` turns any non-empty value
into an INSTRUCTION: «VISTA (captura … — MÍRALA con Read "<path>" …)». So every action before the first
successful capture — or after one that failed — sent the worker to read nothing. Measured on
`find-theatre-tickets__es` (2026-08-20 15:06):

    worker/task «📄 archivo ⚠️ error»: File does not exist.
    Note: your current working directory is /private/var/.../T/zaelar-workers/2

The cwd note in that message is what made it look like a path problem, and it is not: the path is ABSOLUTE, and
V2-117 verified the CLI already permits reading outside the working directory. The fault is ADVERTISING a file
we never checked. The text snapshot is the documented fallback in `_shot_path`'s own docstring — an empty return
takes it, and the CLI prints no VISTA line at all.

Deliberately NOT the same defect as `informe.json` (V2-203), even though both read as «the worker cannot find a
file»: there the worker's OWN write never happened, here we point it at ours. Same symptom, two roots.
"""
import io
from contextlib import redirect_stdout

import pytest

from widgets import store
from widgets.navegador import act_api


@pytest.fixture()
def shots(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    return tmp_path / "navegador"


def test_a_screenshot_that_is_not_there_is_not_offered(shots):
    assert act_api._shot_path("t1") == ""


def test_a_screenshot_that_IS_there_is_offered_with_its_absolute_path(shots):
    shots.mkdir(parents=True, exist_ok=True)
    (shots / "shot-t1.png").write_bytes(b"\x89PNG")
    got = act_api._shot_path("t1")
    assert got.endswith("shot-t1.png") and got.startswith("/")


def test_the_CLI_says_nothing_about_a_view_when_there_is_none():
    """The half that turns the fix into behaviour: an empty `shot` must produce NO instruction. If the printer
    ever prints the line anyway, the worker is sent to read `""` and we are back to a failed Read."""
    from nucleo import nav_cli
    buf = io.StringIO()
    with redirect_stdout(buf):
        nav_cli._print_state({"ok": True, "url": "https://example.com", "title": "x", "shot": ""})
    out = buf.getvalue()
    assert "VISTA" not in out and "MÍRALA" not in out


def test_the_CLI_does_offer_the_view_when_the_shot_is_real():
    """Sensitivity: without this, «never print VISTA» would pass the test above and blind the vision path."""
    from nucleo import nav_cli
    buf = io.StringIO()
    with redirect_stdout(buf):
        nav_cli._print_state({"ok": True, "url": "https://example.com", "title": "x",
                              "shot": "/tmp/shot-t1.png", "viewport": {"width": 1280, "height": 800}})
    out = buf.getvalue()
    assert "MÍRALA con Read" in out and "/tmp/shot-t1.png" in out


def test_a_look_that_produced_no_capture_SAYS_so():
    """`look` exists to produce a capture, so returning none is a failure of the thing asked for — not «nothing
    to report». With `ok` and silence the worker reads success and loses the vision path without knowing."""
    from nucleo import nav_cli
    buf = io.StringIO()
    with redirect_stdout(buf):
        nav_cli._print_state({"ok": True, "url": "https://example.com", "title": "x", "shot": "",
                              "viewport": {"width": 1280, "height": 800}})
    out = buf.getvalue()
    assert "no llegó a escribirse" in out


def test_a_plain_snapshot_without_a_shot_stays_quiet():
    """Sensitivity: `snapshot` never promised a capture, so warning there would be noise on every text step.
    `viewport` is what marks an answer as coming from `look`."""
    from nucleo import nav_cli
    buf = io.StringIO()
    with redirect_stdout(buf):
        nav_cli._print_state({"ok": True, "url": "https://example.com", "title": "x", "shot": ""})
    assert "no llegó a escribirse" not in buf.getvalue()
