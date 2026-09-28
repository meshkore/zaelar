"""An engine fault lives in the ◉ status monitor, not in a red banner across the desk (operator, 2026-09-28).

Mid-demo, «Un turno se atascó y lo corté» painted a red strip at the top of the screen. The floating ◉ icon
already turns amber/red and its monitor says where the fault is; a second, louder surface for the same fact
is noise. The alert still refreshes the icon, and a BLOCKING fault (no model at all) keeps its full screen."""
from pathlib import Path

SSE = Path(__file__).resolve().parents[4] / "frontend/app/services/sse.js"


def _alert_branch() -> str:
    src = SSE.read_text("utf-8")
    body = src.split('} else if (d.kind === "alert") {', 1)[1]
    return body.split("} else if (", 1)[0]


def test_an_alert_does_not_raise_the_banner():
    assert "showAlert" not in _alert_branch()


def test_an_alert_still_turns_the_status_icon_and_a_blocking_fault_still_blocks():
    branch = _alert_branch()
    assert "refreshStatus()" in branch
    assert "store.showFault(" in branch and "hb:blocking-fault" in branch
