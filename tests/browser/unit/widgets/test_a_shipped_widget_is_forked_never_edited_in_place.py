"""Modifying a SHIPPED widget edits a FORK, never engine source (V2-515, phase 2).

Before: `modify_widget` resolved the folder through `dir_for` and handed the headless agent the SHIPPED
folder itself — the edit rewrote repo source in place, and `_validate(stamp_origin=True)` then relabelled
the shipped manifest `origin:"user"` (a measured 2026-08-28 incident relabelled 15 shipped widgets in one
harness run). Now the edit lands on a copy in the generated root; the copy shadows the original everywhere,
the shipped folder keeps receiving engine updates untouched underneath, and a failed FIRST edit discards
the fork so the shipped version simply resurfaces.
"""
from __future__ import annotations

import json
import os

import pytest

from widgets import generator, paths, runtime


@pytest.fixture
def lab(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    runtime.invalidate()
    yield tmp_path
    paths.forget_modules("clock")
    runtime.invalidate()


def _read(p: str) -> str:
    return open(p, encoding="utf-8").read()


def test_modifying_a_shipped_widget_edits_a_fork_not_the_source(lab, monkeypatch):
    shipped = os.path.join(paths.BUILTIN_ROOT, "clock")
    before = {f: _read(os.path.join(shipped, f)) for f in ("manifest.json", "widget.js")}
    seen = {}

    def fake_agent(prompt: str, token: str = "", *, target: str = ""):   # signature follows T-04
        seen["prompt"] = prompt
        target = paths.dir_for("clock")                     # what the resolver serves at edit time
        seen["target"] = target
        with open(os.path.join(target, "widget.js"), "a", encoding="utf-8") as f:
            f.write("\n// edited by the operator\n")
        return True, ""

    monkeypatch.setattr(generator, "_run_agent", fake_agent)
    res = generator.modify_widget("clock", "add a comment")
    assert res["ok"] is True

    fork = os.path.join(paths.generated_root(), "clock")
    assert seen["target"] == fork                           # the agent was handed the FORK…
    assert "// edited by the operator" in _read(os.path.join(fork, "widget.js"))
    for f, content in before.items():                       # …and the shipped folder is byte-identical
        assert _read(os.path.join(shipped, f)) == content

    man = json.load(open(os.path.join(fork, "manifest.json"), encoding="utf-8"))
    assert man.get("origin") == "user"                      # the FORK is the user's — the config badge reads this
    assert man.get("forked_from", {}).get("origin") == "builtin"
    assert (fork, ) == tuple(f for n, f in paths.iter_folders() if n == "clock")   # the fork shadows it


def test_the_prompt_names_the_fork_folder_not_the_shipped_one(lab, monkeypatch):
    """The prompts used to hardcode `widgets/<id>/` — a fork is useless if the agent is still pointed at
    engine source."""
    seen = {}
    monkeypatch.setattr(generator, "_run_agent",
                        lambda prompt, token="", *, target="": (seen.update(prompt=prompt), (True, ""))[1])
    generator.modify_widget("clock", "anything")
    fork_ref = generator._folder_ref(os.path.join(paths.generated_root(), "clock"))
    assert fork_ref in seen["prompt"]
    assert "widgets/clock/" not in seen["prompt"].replace(fork_ref, "")


def test_a_failed_first_edit_discards_the_fork(lab, monkeypatch):
    """The rollback of a fresh fork is DELETION: the shipped version resurfaces, nothing to restore."""
    def breaking_agent(prompt: str, token: str = "", *, target: str = ""):   # signature follows T-04
        os.remove(os.path.join(paths.dir_for("clock"), "widget.js"))
        return True, ""

    monkeypatch.setattr(generator, "_run_agent", breaking_agent)
    res = generator.modify_widget("clock", "break it")
    assert res["ok"] is False
    assert not os.path.isdir(os.path.join(paths.generated_root(), "clock"))     # fork gone
    assert paths.dir_for("clock") == os.path.join(paths.BUILTIN_ROOT, "clock")  # shipped one stands


def test_modifying_a_user_widget_stays_in_its_own_folder(lab, monkeypatch):
    wid = "tmptest-propio"
    folder = os.path.join(paths.generated_root(), wid)
    os.makedirs(folder)
    json.dump({"id": wid, "title": "Propio", "keywords": ["tmptestpalabraunica"], "entry": "widget.js"},
              open(os.path.join(folder, "manifest.json"), "w", encoding="utf-8"))
    open(os.path.join(folder, "widget.js"), "w", encoding="utf-8").write("export function render(){}")
    runtime.invalidate()

    def fake_agent(prompt: str, token: str = "", *, target: str = ""):   # signature follows T-04
        with open(os.path.join(paths.dir_for(wid), "widget.js"), "a", encoding="utf-8") as f:
            f.write("\n// tweak\n")
        return True, ""

    monkeypatch.setattr(generator, "_run_agent", fake_agent)
    res = generator.modify_widget(wid, "tweak")
    assert res["ok"] is True
    assert "// tweak" in _read(os.path.join(folder, "widget.js"))
    assert json.load(open(os.path.join(folder, "manifest.json"), encoding="utf-8")).get("forked_from") is None


def test_the_validator_never_stamps_a_shipped_manifest(lab):
    """`make test-widgets` runs this same validator over the whole catalog; with `stamp_origin=True` it once
    relabelled 15 shipped widgets as user-created. A manifest under repo source is read, never rewritten."""
    shipped_man = os.path.join(paths.BUILTIN_ROOT, "clock", "manifest.json")
    before = _read(shipped_man)
    generator._validate("clock", stamp_origin=True)
    assert _read(shipped_man) == before
