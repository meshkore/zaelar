"""The per-tenant tree exists before anything writes into it (V2-562).

A self-host clone gets `config/`, `credentials/`, `i18n/` and the rest from git, so every writer found its parent
already there and no call site ever needed a `mkdir`. A cloud Machine mounts an EMPTY Volume, and there the same
code writes into directories nobody created — which raises `FileNotFoundError` inside code that treats persistence
as best-effort, so it is caught, logged at WARNING and stepped over. Nothing breaks loudly; a preference simply
never sticks.

The guard that matters is the LAST one: it reads the real call sites out of the source and fails if a module
resolves a workspace path whose root is not declared in `SUBDIRS`. A hand-copied list would keep passing while a
new persistent path silently reopened the hole.
"""
import json
import re
from pathlib import Path

import pytest

from nucleo import workspace


ENGINE_ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture()
def empty_workspace(tmp_path, monkeypatch):
    """A workspace root that is EMPTY, which is what a freshly mounted Volume actually looks like."""
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    assert list(tmp_path.iterdir()) == []
    return tmp_path


def test_ensure_creates_every_declared_subdirectory(empty_workspace):
    workspace.ensure()
    missing = [rel for rel in workspace.SUBDIRS if not (empty_workspace / rel).is_dir()]
    assert missing == []


def test_ensure_is_idempotent_and_keeps_what_is_already_there(empty_workspace):
    workspace.ensure()
    (empty_workspace / "config" / "settings.json").write_text('{"kept": true}', encoding="utf-8")
    workspace.ensure()
    assert json.loads((empty_workspace / "config" / "settings.json").read_text()) == {"kept": True}


def test_ensure_returns_the_root_it_prepared(empty_workspace):
    assert workspace.ensure() == empty_workspace


def test_ensure_never_raises_on_a_root_it_cannot_create(monkeypatch, tmp_path):
    """A read-only or exotic filesystem must not stop the agent from booting.

    The counterweight to this is the guard above: never raising is only acceptable BECAUSE the directories are
    genuinely created in the normal case."""
    blocked = tmp_path / "nope"
    blocked.write_text("I am a file, not a directory", encoding="utf-8")
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(blocked))
    assert workspace.ensure() == blocked          # no exception


def test_settings_can_be_written_on_a_bare_volume(empty_workspace, monkeypatch):
    """The measured incident: `/data/config` did not exist, so `settings.json` could never be written and the
    language onboarding ran again on EVERY cold boot.

    ⚠️ NOT via `importlib.reload`, which was the obvious route and is a trap twice over: the root `conftest.py`
    aims `settings.SETTINGS_FILE` at a temp file for the WHOLE session (the invariant that a test never touches
    the operator's real state), and a reload silently reinstates the real repo path — so the reload both pointed
    at `~/.../engine/config/settings.json` and left every later test reading it. What broke was an unrelated
    i18n test several files away, which is exactly how expensive that class of leak is to diagnose.
    """
    from config import settings as settings_mod

    target = empty_workspace / "config" / "settings.json"
    monkeypatch.setattr(settings_mod, "SETTINGS_FILE", target)
    settings_mod.update({"stt_language": "es"})
    assert json.loads(target.read_text())["stt_language"] == "es"


def test_every_workspace_root_used_in_the_code_is_declared(  # the guard that keeps this from regressing
):
    """Read the real call sites and demand their first path segment be declared.

    `workspace.root() / "config" / …` and `os.path.join(str(workspace.root()), "widgets", "_data")` are the two
    shapes in use; both are matched. A module that starts writing under a NEW root fails here instead of failing
    silently on somebody's Volume.
    """
    declared = {rel.split("/")[0] for rel in workspace.SUBDIRS}
    pattern = re.compile(r"workspace\.root\(\)\s*\)?\s*[,/]\s*[\"']([A-Za-z0-9_.-]+)[\"']")

    found: dict[str, set[str]] = {}
    for py in ENGINE_ROOT.rglob("*.py"):
        rel = py.relative_to(ENGINE_ROOT).as_posix()
        if rel.startswith(("tests/", ".venv/")) or "/__pycache__/" in rel:
            continue
        for root in pattern.findall(py.read_text(encoding="utf-8", errors="ignore")):
            found.setdefault(root, set()).add(rel)

    assert found, "the scan found no call sites at all — the pattern stopped matching, so it guards nothing"
    undeclared = {r: sorted(f) for r, f in found.items() if r not in declared}
    assert not undeclared, (
        "these modules resolve a workspace path whose root is not in workspace.SUBDIRS, so on a fresh Volume "
        f"their writes fail best-effort and vanish: {undeclared}"
    )


def test_the_boot_entrypoint_prepares_the_tree_before_importing_the_app():
    """ORDER is the whole point: `server/__init__` loads settings.json at import time, so an `ensure()` that ran
    after it — or inside a FastAPI startup hook — would be too late for the very write this exists for."""
    src = (ENGINE_ROOT / "server" / "__main__.py").read_text(encoding="utf-8")
    assert "_workspace.ensure()" in src, "boot no longer prepares the per-tenant tree"
    assert src.index("_workspace.ensure()") < src.index("from server import app"), (
        "ensure() must run BEFORE the app import, which is what reads the persistent paths"
    )
