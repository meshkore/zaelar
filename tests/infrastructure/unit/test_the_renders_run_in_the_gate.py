"""V2-831 T-14 — the widget render tests are part of the default sweep, and a browser change reaches them.

49 render reds sat on main for weeks because `tests/watchdog.py` skipped every `/e2e/` folder by name and the gate
never passed `--include-live`. A render test needs nothing but a local Chromium (every engine route is mocked), so
it belongs in the default sweep; a suite that wants real models, LiveKit or the network still does not.

What is measured:
  · the default sweep picks `tests/browser/e2e/widgets` and still leaves out the genuinely live folders;
  · every folder let in by that entry belongs to a suite whose `suite.json` declares no live requirement — the
    entry is a list of folders, so this is what stops it from quietly letting in one that needs a service;
  · a changed browser file (widget JS, shell JS/CSS) selects the tests that load it, by path, by the `/static/` URL
    the shell serves `frontend/` under, or by the widget id they mount — and not the Python tests of that widget;
  · the gate refuses to run the sweep without Playwright, because 299 skipped renders read as a green.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ENGINE / "tests"))
import watchdog  # noqa: E402

# What a suite may declare and still be deterministic on any developer machine.
LOCAL_REQUIREMENTS = {"python", "node", "chromium", "local-sqlite", "isolated-test-data"}


def _rel(paths):
    return {str(p.relative_to(ENGINE)) for p in paths}


def test_the_default_sweep_runs_the_widget_renders_and_still_skips_the_live_suites():
    dirs = _rel(watchdog.leaf_dirs([watchdog.TESTS], include_live=False))
    for render in ("widgets", "chat", "feedback", "mensajeria", "mobile", "onboarding"):
        assert f"tests/browser/e2e/{render}" in dirs, f"the {render} renders are not in the default sweep"
    live = {d for d in dirs if any(m in "/" + d + "/" for m in watchdog._LIVE)}
    allowed = {d for d in live if any(r in "/" + d + "/" for r in watchdog._RENDER)}
    assert live == allowed, f"a live-marked folder entered the default sweep without the render entry: {live - allowed}"
    assert "tests/voice/e2e" not in dirs and "tests/memory/integration" not in dirs, dirs
    # --include-live still reaches everything the default leaves out
    assert dirs < _rel(watchdog.leaf_dirs([watchdog.TESTS], include_live=True))


def test_a_render_folder_in_the_default_sweep_needs_no_live_service():
    assert watchdog._RENDER, "the render entry is empty"
    for entry in watchdog._RENDER:
        folder = ENGINE / entry.strip("/")
        assert folder.is_dir() and any(folder.glob("test_*.py")), f"{entry} holds no tests"
        suite = ENGINE / "tests" / Path(entry.strip("/")).parts[1] / "suite.json"
        needs = set(json.loads(suite.read_text(encoding="utf-8")).get("requirements") or [])
        assert needs and needs <= LOCAL_REQUIREMENTS, \
            f"{entry} is in the default sweep but its suite declares {sorted(needs - LOCAL_REQUIREMENTS)}"


def _selects(rel, text):
    return any(f.search(text) for f in watchdog._browser_forms(rel))


def test_a_browser_file_selects_the_tests_that_load_it_and_only_those():
    # a widget's client module: the render that mounts the widget, and one that routes its js/ folder
    assert _selects("widgets/agenda/js/bands.js", 'await widget_client.mount(pg, "agenda")')
    assert _selects("widgets/agenda/js/bands.js", 'if path.startswith("/widgets/agenda/js/"):')
    assert _selects("widgets/agenda/widget.js", "served('/widgets/agenda/widget.js')")
    # …but not a Python test of the same widget, nor a render of another widget
    assert not _selects("widgets/agenda/js/bands.js", 'DATA = ENGINE / "widgets/agenda/data.py"')
    assert not _selects("widgets/agenda/js/bands.js", 'await widget_client.mount(pg, "agendas")')
    # the shell: by repo path and by the URL it is served under
    assert _selects("frontend/app/styles.css", "for h in ['/frontend/app/core/palette.css', '/frontend/app/styles.css']")
    assert _selects("frontend/app/styles.css", '<link rel="stylesheet" href="/static/app/styles.css?v=12"/>')
    assert not _selects("frontend/app/styles.css", "/frontend/app/styles.cssx")


def test_the_impacted_run_picks_a_render_when_its_widget_js_changes(monkeypatch):
    monkeypatch.setattr(watchdog, "changed_files", lambda base: ["widgets/contactos/js/sync.js"])
    picked, why = watchdog.impacted_targets("origin/main")
    assert "tests/browser/e2e/widgets/test_contactos_render.py" in _rel(picked), why
    others = _rel(picked) - {str(Path(__file__).resolve().relative_to(ENGINE))}   # this file names it too
    assert all(p.startswith("tests/browser/") for p in others), others


def test_the_gate_refuses_a_sweep_that_cannot_render():
    gate = (ENGINE / "tests" / "gate.sh").read_text(encoding="utf-8")
    sweep = gate.index("tests/watchdog.py --report")
    guard = gate.find("import playwright")
    assert 0 <= guard < sweep, "the gate must check for Playwright before the sweep that holds the renders"
    assert "--include-live" not in gate, "the gate stays off the live suites"
