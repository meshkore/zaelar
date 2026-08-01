from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from tests.platform.events import EventWriter, read_events
from tests.platform.server import run_is_active


def test_event_writer_is_append_only_and_readable(tmp_path):
    writer = EventWriter(tmp_path, run_id="run-1")
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda n: writer.emit("step", step=n), range(100)))
    events = read_events(tmp_path)
    assert len(events) == 100
    assert {event["step"] for event in events} == set(range(100))
    assert all(event["schema"] == 1 and event["run_id"] == "run-1" for event in events)


def test_event_writer_redacts_nested_credentials(tmp_path):
    EventWriter(tmp_path).emit(
        "probe", token="visible-no", data={"password": "visible-no", "safe": "visible-yes"}
    )
    event = read_events(tmp_path)[0]
    assert event["token"] == "[redacted]"
    assert event["data"] == {"password": "[redacted]", "safe": "visible-yes"}


def test_reader_ignores_truncated_crash_tail(tmp_path):
    writer = EventWriter(tmp_path)
    writer.emit("valid")
    with writer.path.open("a", encoding="utf-8") as stream:
        stream.write('{"type":"partial"')
    assert [event["type"] for event in read_events(tmp_path)] == ["valid"]


def test_observatory_ui_cannot_replace_an_active_agent_run(tmp_path):
    run_file = tmp_path / "run.json"
    run_file.write_text('{"status":"running"}', encoding="utf-8")
    assert run_is_active(tmp_path) is True
    run_file.write_text('{"status":"passed"}', encoding="utf-8")
    assert run_is_active(tmp_path) is False
