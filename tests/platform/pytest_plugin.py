"""Pytest bridge that publishes collection and per-test lifecycle events."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from .events import EventWriter

_writer: EventWriter | None = None


def _out() -> EventWriter | None:
    global _writer
    run_dir = os.getenv("ZAELAR_TEST_RUN_DIR")
    if run_dir and _writer is None:
        _writer = EventWriter(run_dir, run_id=os.getenv("ZAELAR_TEST_RUN_ID"))
    return _writer


def _suite(nodeid: str) -> str:
    selected = os.getenv("ZAELAR_TEST_SUITE", "tests")
    if selected != "all":
        return selected
    parts = Path(nodeid.split("::", 1)[0]).parts
    if len(parts) >= 2 and parts[0] == "tests":
        return {
            "agent_headless": "agent-headless",
            "browser": "browser",
            "cluster": "cluster",
            "connectors": "connectors",
            "memory": "memory",
            "voice": "voice",
            "infrastructure": "infrastructure",
            "platform": "infrastructure",
        }.get(parts[1], "infrastructure")
    # Compatibility for external/legacy nodeids while callers migrate to tests/<domain>/.
    if "memory" in parts:
        return "memory"
    if "voice" in parts:
        return "voice"
    if "widgets" in parts:
        return "browser"
    if "connectors" in parts:
        return "connectors"
    if "nucleo" in parts:
        return "agent-headless"
    return "infrastructure"


def pytest_collection_finish(session: pytest.Session) -> None:
    if writer := _out():
        for index, item in enumerate(session.items, start=1):
            writer.emit(
                "test.discovered",
                test_id=item.nodeid,
                suite=_suite(item.nodeid),
                label=item.name,
                index=index,
                total=len(session.items),
            )
        writer.emit("collection.finished", total=len(session.items))


def pytest_runtest_logstart(nodeid: str, location) -> None:
    if writer := _out():
        writer.emit("test.started", test_id=nodeid, suite=_suite(nodeid), label=nodeid.split("::")[-1])


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo):
    outcome = yield
    report = outcome.get_result()
    exceptional_phase = report.when in {"setup", "teardown"} and (report.failed or report.skipped)
    if report.when != "call" and not exceptional_phase:
        return
    if not (writer := _out()):
        return
    status = "skipped" if report.skipped or hasattr(report, "wasxfail") else "passed" if report.passed else "failed"
    error = ""
    if report.failed:
        error = str(report.longrepr)
    writer.emit(
        "test.finished",
        test_id=item.nodeid,
        suite=_suite(item.nodeid),
        label=item.name,
        status=status,
        duration_ms=round(report.duration * 1000, 2),
        phase=report.when,
        error=error[-12000:],
    )
