"""The task battery's engine: a real, isolated sandbox per language, driven over the text channel (V2-851 §9).

Opt-in: `ZAELAR_TEST_LIVE_BATTERY=1` (the folder is under `e2e/`, which the default sweep never enters). It calls
the cloud models with the operator's keys, lent by `tests/platform/sandbox_engine.py` and taken back at teardown.

`ZAELAR_BATTERY_BASELINE=1` runs the cases in BASELINE mode: each passes only when red on the assertion
`expected_red.json` names for it — the proof, on the frozen code, that the case measures the missing mechanism.
`ZAELAR_BATTERY_REPEAT=3` repeats every case (the phase gate is 3/3 on mechanism).
"""
from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

import pytest

from tests.platform.sandbox_engine import free_port, spawn_engine, stop_engine

from . import seed
from .probe import Check, Infra, Probe

HERE = Path(__file__).resolve().parent
LIVE = os.getenv("ZAELAR_TEST_LIVE_BATTERY") == "1"
BASELINE = os.getenv("ZAELAR_BATTERY_BASELINE") == "1"
REPEAT = max(1, int(os.getenv("ZAELAR_BATTERY_REPEAT", "1") or 1))
EXPECTED_RED = json.loads((HERE / "expected_red.json").read_text(encoding="utf-8"))


def pytest_collection_modifyitems(config, items):
    if LIVE:
        return
    skip = pytest.mark.skip(reason="live battery: set ZAELAR_TEST_LIVE_BATTERY=1 (boots a sandbox, calls cloud models)")
    for item in items:
        if str(HERE) in str(item.fspath):
            item.add_marker(skip)


def pytest_generate_tests(metafunc):
    if "rep" in metafunc.fixturenames:
        metafunc.parametrize("rep", range(REPEAT), ids=[f"r{i + 1}" for i in range(REPEAT)])


class _Engines:
    """One sandbox per language, booted on first use and shared by the cases of that language."""

    def __init__(self, root: Path):
        self.root = root
        self.by_lang: dict = {}

    def get(self, lang: str):
        eng = self.by_lang.get(lang)
        if eng is not None and eng.process.poll() is None:
            return eng
        ws = self.root / f"ws-{lang}-{uuid.uuid4().hex[:6]}"
        eng = boot(ws, lang)
        self.by_lang[lang] = eng
        return eng

    def close(self):
        for eng in self.by_lang.values():
            stop_engine(eng)


def boot(workspace: Path, lang: str, *, port: int | None = None):
    """An engine whose language is configured for the process: the text channel locks THAT one on the first line
    (`i18n/init/detect.ensure_for_text`), never a guess from the case's opening words.

    Its directory holds the language's people (`seed.PEOPLE`, written before the boot through the contacts store,
    durable across `/reset/hard`), and its messaging is the LOOPBACK account (`loopback/sitecustomize.py`): a send
    is appended to `<workspace>/loopback/sent.jsonl` and echoed, never delivered."""
    try:
        names = seed.seed_people(workspace, lang)
    except Exception as e:  # noqa: BLE001
        raise Infra(f"seeding the directory failed: {e}") from e
    if len(names) < len(seed.PEOPLE[lang]["contacts"]):
        raise Infra(f"the directory holds {names}, not the seeded people")
    try:
        return spawn_engine(workspace=workspace, port=port or free_port(), boot_timeout=180.0,
                            extra_env=seed.loopback_env({"ZAELAR_LANGUAGE": lang}))
    except Exception as e:  # noqa: BLE001
        raise Infra(f"sandbox did not boot: {e}") from e


def restart(eng, lang: str):
    """Stop an engine and boot ANOTHER process on the same workspace — what a restart is to the row (the port is a
    fresh one: nothing in the row depends on it, and a port in TIME_WAIT would read as a boot failure)."""
    stop_engine(eng)
    return boot(eng.workspace, lang)


@pytest.fixture(scope="session")
def engines(tmp_path_factory):
    pool = _Engines(tmp_path_factory.mktemp("task-battery"))
    yield pool
    pool.close()


@pytest.fixture
def probe_for(engines):
    """`probe_for(lang)` → a Probe on that language's shared sandbox, reset, on a session of its own."""
    def _make(lang: str) -> Probe:
        try:
            p = Probe(engines.get(lang), session=f"bat-{uuid.uuid4().hex[:8]}")
            p.reset()
            return p
        except Infra as e:
            pytest.fail(f"INFRA: {e}")
    return _make


@pytest.fixture
def own_engine(tmp_path):
    """An engine of the case's own, for the cases that restart it or kill its worker (C4, C10). `own_engine(lang)`
    boots it; `own_engine.restart(eng, lang)` stops it and boots the same workspace again."""
    made: list = []

    def _make(lang: str):
        try:
            eng = boot(tmp_path / f"own-{lang}", lang)
        except Infra as e:
            pytest.fail(f"INFRA: {e}")
        made.append(eng)
        return eng

    def _restart(eng, lang: str):
        made.remove(eng)
        try:
            again = restart(eng, lang)
        except Infra as e:
            pytest.fail(f"INFRA: {e}")
        made.append(again)
        return again
    _make.restart = _restart
    yield _make
    for eng in made:
        stop_engine(eng)


@pytest.fixture
def fresh_for(own_engine):
    """`fresh_for(lang)` → a Probe on an engine of the case's own. For the cases whose premise a shared sandbox can
    erase: an ambiguous name stops being ambiguous once an earlier case taught the directory his choice (the ask-once
    memory keeps it), so C1-C3 would measure the neighbour's answer instead of the door's question."""
    def _make(lang: str) -> Probe:
        return Probe(own_engine(lang), session=f"bat-{uuid.uuid4().hex[:8]}")
    return _make


@pytest.fixture
def check(request):
    case = request.node.originalname or request.node.name
    chk = Check(request.node.nodeid)
    chk.expected = EXPECTED_RED.get(case, "") if BASELINE else ""
    return chk


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item):
    """An `Infra` raised inside a case is reported as INFRA, never as a product red."""
    outcome = yield
    exc = outcome.excinfo
    if exc and isinstance(exc[1], Infra):
        outcome.force_exception(pytest.fail.Exception(f"INFRA: {exc[1]}", pytrace=False))
