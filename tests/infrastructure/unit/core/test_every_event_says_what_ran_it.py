"""Every event says WHAT RAN IT — exact build, commit and process (V2-837 G1-G3).

Measured on a 3,399-event cloud session: 3,002 events said `b90+nogit` (the image had no `.git`, so the commit was
unknowable), 397 said no version at all (every one from the memory bridge, which publishes a hand-built dict
straight to the bus and skipped `emit()`'s stamp), and none said which process ran it. The stamp now lives at the
stream's single gate (`voice.observer.stamp_identity`, applied by `bus.sse.publish`), the commit can be baked into
an image at build time, and the process travels as a compact `inst` block.

The class test walks EVERY event family the observer knows (plus an unknown kind, an interim and a hand-built dict)
and fails on any event that reaches the bus without `ver` = build+commit and `inst` = host/pid/boot.

Disarm: delete the `stamp_build(ev)` call in `stamp_identity` → the hand-built and interim cases go red (and every
family loses `inst`); make `version.sha()` ignore `ZAELAR_COMMIT` → the baked-commit case goes red.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

import version
from voice import observer

ROOT = pathlib.Path(__file__).resolve().parents[4]


@pytest.fixture
def published(monkeypatch):
    """What reaches the bus on the `observer` topic — the same dict the durable log stores."""
    import bus
    got: list[dict] = []
    real = bus.emit_sync

    def _capture(topic, ev, *a, **k):
        if topic == "observer":
            got.append(dict(ev))
        return None if topic == "observer" else real(topic, ev, *a, **k)
    monkeypatch.setattr(bus, "emit_sync", _capture)
    return got


def _assert_stamped(ev: dict, what: str) -> None:
    ver = str(ev.get("ver") or "")
    assert "+" in ver and ver.split("+", 1)[1], f"{what}: `ver` must say build AND commit, got {ver!r}"
    inst = ev.get("inst")
    assert isinstance(inst, dict) and inst.get("pid") and inst.get("boot") and "host" in inst, \
        f"{what}: `inst` must say which process ran it, got {inst!r}"


def test_every_event_family_reaches_the_bus_stamped(published):
    kinds = sorted(set(observer._CAT)) + ["a-kind-nobody-mapped"]
    for i, kind in enumerate(kinds):
        # a distinct label per call: the observer collapses identical (kind, label) floods within 150 ms
        observer.emit(kind, f"v2-837 probe {i}", text="", extra={"id": f"probe-{i}"})
    seen = {e.get("kind") for e in published}
    missing = [k for k in kinds if k not in seen]
    assert not missing, f"families never published: {missing}"
    for ev in published:
        _assert_stamped(ev, f"kind={ev.get('kind')}")


def test_a_hand_built_dict_and_an_interim_are_stamped_too(published):
    """The memory bridge's shape (the 397 unversioned rows) and a live partial transcript."""
    from bus import sse
    sse.publish({"kind": "memory", "op": "state", "label": "state"})
    observer.emit("interim", "…", text="hola")
    assert {e["kind"] for e in published} == {"memory", "interim"}
    for ev in published:
        _assert_stamped(ev, ev["kind"])


def test_nothing_publishes_on_the_observer_topic_around_the_gate():
    """The stamp holds only if every event passes `bus.sse.publish`: no product code may put a dict on the
    `observer` topic with `bus.emit_sync`/`bus.emit` directly."""
    offenders = []
    for p in ROOT.rglob("*.py"):
        rel = p.relative_to(ROOT).as_posix()
        if rel.startswith((".venv/", "tests/", "node_modules/")) or "/node_modules/" in rel or rel == "bus/sse.py":
            continue
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        for n in ast.walk(tree):
            if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in ("emit_sync", "emit")
                    and n.args and isinstance(n.args[0], ast.Constant) and n.args[0].value == "observer"):
                offenders.append(f"{rel}:{n.lineno}")
    assert not offenders, f"published on `observer` without the stamp gate: {offenders}"


def test_the_commit_baked_into_an_image_wins_over_a_missing_repository(monkeypatch):
    monkeypatch.setattr(version, "_CACHE", {})
    monkeypatch.setenv(version.COMMIT_ENV, "abc1234")
    assert version.sha() == "abc1234"
    assert version.short().endswith("+abc1234")
    monkeypatch.setattr(version, "_CACHE", {})
    monkeypatch.setenv(version.COMMIT_ENV, "ab$(rm)12")          # an arg is data: only its alphanumerics survive
    assert version.sha() == "abrm12"


def test_the_image_declares_the_commit_build_arg():
    df = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "ARG ZAELAR_COMMIT" in df and "ENV ZAELAR_COMMIT=${ZAELAR_COMMIT}" in df, \
        "the build arg must reach the runtime environment, or the image says `nogit` again"
    assert df.index("ARG ZAELAR_COMMIT") > df.index("COPY version.py"), "declared after the code layers (cache)"


def test_a_forked_process_is_another_instance(monkeypatch):
    monkeypatch.setattr(version, "_CACHE", {})
    monkeypatch.setenv("ZAELAR_REGION", "region-x")
    a = version.instance()
    assert a["region"] == "region-x" and a["pid"]
    version._CACHE["inst_pid"] = -1                             # what a child sees after fork: the parent's cache
    assert version.instance()["pid"] == a["pid"] and version._CACHE["inst_pid"] != -1, "re-read, never inherited"


def test_the_stamp_is_small():
    """It rides on every stored event: the whole addition (`inst` + the commit in `ver`) stays under 100 bytes."""
    import json
    ev = observer.stamp_build({"kind": "x"})
    added = len(json.dumps({"inst": ev["inst"]}, ensure_ascii=False)) + len(version.sha())
    assert added < 100, added
