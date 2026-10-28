"""Every widget says how it lives on several screens (V2-792, node 4.269).

The operator opens one agent on his computer and his phone at once. A calendar is a reflection — it can be open on
both, and a change shows on both. A video takes the device's sound and picture — it can only live on one, and asking
for it from the phone while it plays on the computer must stop and close it there and open it here. Only the widget
knows which one it is, so it is DECLARED in its manifest (`"screens": "shared" | "single"`), never inferred from a
list in the host, and the code agent that writes a new widget is told to declare it and is refused if it does not.

Pinned here:
  · every built-in widget declares it explicitly, and a widget with an exclusive output channel is `single`;
  · the resolution and its one rule (`runtime.output` cannot be `shared`);
  · every widget the generator creates or modifies leaves with it written, and the contradiction is refused;
  · the generator's contract (shared by the create and modify prompts) asks for it;
  · the compact index carries the RESOLVED policy, so a host never re-derives it;
  · a `show` of a single card asked from another screen MOVES it — the move is announced before the show itself —
    and a show on the screen that already has it announces nothing.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

ENGINE = Path(__file__).resolve().parents[4]
WIDGETS = ENGINE / "widgets"
DESK, PHONE = "desktop:aaaa1111", "mobile:bbbb2222"


def _builtins():
    import subprocess
    tracked = subprocess.run(["git", "ls-files", "widgets/*/manifest.json"], cwd=ENGINE, capture_output=True,
                             text=True).stdout.split()
    return [ENGINE / p for p in tracked]


def test_every_builtin_widget_declares_its_screens():
    mans = _builtins()
    assert len(mans) >= 10, "the tracked catalogue was not found"
    missing = [p.parent.name for p in mans if "screens" not in json.loads(p.read_text(encoding="utf-8"))]
    assert not missing, f"built-in widgets with no \"screens\" declaration: {missing}"


def test_a_widget_that_takes_the_speaker_is_single_and_the_rest_resolve_cleanly():
    from widgets import screen_policy
    for p in _builtins():
        man = json.loads(p.read_text(encoding="utf-8"))
        assert screen_policy.problem(man, required=True) is None, (p.parent.name, screen_policy.problem(man))
    assert screen_policy.of(json.loads((WIDGETS / "youtube" / "manifest.json").read_text())) == "single"
    assert screen_policy.of(json.loads((WIDGETS / "agenda" / "manifest.json").read_text())) == "shared"


def test_the_policy_and_its_one_rule():
    from widgets import screen_policy as sp
    assert sp.of({}) == "shared"
    assert sp.of({"runtime": {"output": "audio"}}) == "single"          # an older widget still behaves
    assert sp.of({"screens": "SINGLE"}) == "single"
    assert sp.problem({}) is None and sp.problem({}, required=True)
    assert sp.problem({"screens": "both"})
    assert sp.problem({"screens": "shared", "runtime": {"output": "audio"}})
    assert sp.problem({"screens": "single"}) is None


def _write_widget(root: Path, wid: str, man: dict) -> None:
    d = root / wid
    d.mkdir(parents=True)
    (d / "manifest.json").write_text(json.dumps(man), encoding="utf-8")
    (d / "widget.js").write_text("export function render(el, data, ctx) { el.textContent = ''; }\n", encoding="utf-8")


@pytest.fixture
def scratch_widget(monkeypatch, tmp_path):
    from widgets import paths
    made = {}

    def make(wid, **extra):
        man = {"id": wid, "title": "Screens probe", "keywords": [f"{wid}-kw"], "entry": "widget.js", **extra}
        _write_widget(tmp_path, wid, man)
        made[wid] = tmp_path / wid
        return wid
    monkeypatch.setattr(paths, "dir_for", lambda wid: str(made[wid]) if wid in made else None)
    monkeypatch.setattr(paths, "is_repo_source", lambda d: True)
    return make


def test_a_widget_the_generator_touches_leaves_declared_and_the_contradiction_is_refused(scratch_widget, tmp_path):
    from widgets import validator
    wid = scratch_widget("zz-screens-missing")
    assert validator._validate(wid)[0]                                   # the catalogue check never rewrites it
    assert "screens" not in json.loads((tmp_path / wid / "manifest.json").read_text())
    assert validator._validate(wid, stamp_origin=True)[0]                # created or modified by the generator
    assert json.loads((tmp_path / wid / "manifest.json").read_text())["screens"] == "shared"
    media = scratch_widget("zz-screens-media", runtime={"output": "audio"})
    assert validator._validate(media, stamp_origin=True)[0]
    assert json.loads((tmp_path / media / "manifest.json").read_text())["screens"] == "single"
    bad = scratch_widget("zz-screens-contra", screens="shared", runtime={"output": "audio"})
    ok, err = validator._validate(bad)
    assert not ok and "single" in err
    good = scratch_widget("zz-screens-good", screens="shared")
    assert validator._validate(good, stamp_origin=True)[0]


def test_the_code_agent_is_asked_to_declare_it():
    from widgets import generator
    c = generator._CONTRACT
    assert "\n- SEVERAL SCREENS? (REQUIRED" in c, "the decision has its own bullet in the contract"
    assert '`"screens": "shared"`' in c and '`"screens": "single"`' in c, "both values are explained to the agent"
    assert generator._CONTRACT in generator._CREATE_PROMPT and generator._CONTRACT in generator._MODIFY_PROMPT
    assert '"screens"' in (WIDGETS / "AGENTS.md").read_text(encoding="utf-8")


def test_the_compact_index_carries_the_resolved_policy():
    from widgets import server_api
    assert server_api._index_row(json.loads((WIDGETS / "youtube" / "manifest.json").read_text()))["screens"] == "single"
    assert server_api._index_row({"id": "x", "title": "X"})["screens"] == "shared"


@pytest.fixture
def two_screens():
    from voice import screens
    screens._reset_for_tests()
    from server import screens_api  # noqa: F401 — registers the widgets' policy with the voice layer
    screens.attach(DESK)
    screens.attach(PHONE)
    yield screens
    screens._reset_for_tests()


def test_a_single_card_asked_from_another_screen_moves_before_it_shows(two_screens, monkeypatch):
    from voice import observer
    seen = []
    real = observer.emit

    def spy(kind, label, text="", role="", extra=None):
        ev = real(kind, label, text=text, role=role, extra=extra)
        if kind in ("screens", "widget") and ev:
            seen.append((kind, label, ev.get("id"), ev.get("to"), ev.get("moved")))
        return ev
    monkeypatch.setattr(observer, "emit", spy)               # the move is emitted through the same door

    two_screens.note_playing("youtube", DESK)                 # the video plays on the computer
    spy("transcript", "final", text="ponme un vídeo de gatos", role="user", extra={"dev": PHONE})
    spy("widget", "show", extra={"id": "youtube", "src": "flash"})
    moves = [s for s in seen if s[0] == "screens"]
    shows = [i for i, s in enumerate(seen) if s[:2] == ("widget", "show")]
    assert moves and moves[0][2:4] == ("youtube", PHONE), seen
    assert seen.index(moves[0]) < shows[0], "the move must reach the computer before the show reaches the phone"
    assert seen[shows[0]][4] is True

    seen.clear()                                               # shown again on the phone: nothing moves
    spy("widget", "show", extra={"id": "youtube", "src": "flash"})
    assert not [s for s in seen if s[0] == "screens"], seen


def test_a_shared_card_never_moves(two_screens, monkeypatch):
    from voice import observer
    out = []
    real = observer.emit
    monkeypatch.setattr(observer, "emit", lambda k, lab, **kw: out.append(k) or real(k, lab, **kw))
    two_screens.stamp({"kind": "transcript", "role": "user", "text": "abre la agenda", "dev": PHONE})
    ev = two_screens.stamp({"kind": "widget", "label": "show", "id": "agenda"})
    assert "screens" not in out and not ev.get("moved")


# ── The rule lives where every future widget is made (operator, 2026-10-25: «que yo no tenga que explicarlo nunca más»)

DOC = ".meshkore/docs/ops/zaelar-two-screen-test.md"


@pytest.mark.parametrize("where", [
    ".meshkore/context/constraints.md",                        # the invariant context every session loads
    ".meshkore/context/glossary.md",
    "widgets/AGENTS.md",                                       # hand editors of a widget
    ".meshkore/docs/ops/zaelar-new-widget-or-connector-workflow.md",   # «make a widget for Y» / a new native app
    DOC,
])
def test_the_rule_is_written_where_widgets_are_made(where):
    text = (ENGINE / where).read_text(encoding="utf-8")
    assert '"screens"' in text or "`screens`" in text or "Screens" in text, f"{where} does not name the policy"
    assert "shared" in text and "single" in text, f"{where} does not name both values"
    if where != DOC and where != ".meshkore/context/glossary.md":
        assert "zaelar-two-screen-test.md" in text, f"{where} does not point at the two-screen test"


def test_the_code_agent_is_told_a_shared_copy_may_be_mounted_twice_and_will_be_tested_on_two_screens():
    from widgets import generator
    c = generator._CONTRACT
    assert "MOUNTED TWICE" in c and "--two-screens" in c and "--manual" in c


def test_the_widget_harness_checks_it_and_carries_both_passes(tmp_path, monkeypatch):
    from tests import widget_harness as harness
    from widgets import paths
    (tmp_path / "zz-h").mkdir()
    (tmp_path / "zz-h" / "manifest.json").write_text(json.dumps({"id": "zz-h", "title": "H"}), encoding="utf-8")
    monkeypatch.setattr(paths, "dir_for", lambda wid: str(tmp_path / wid))
    ok, why = harness.check_screens("zz-h")
    assert not ok and "screens" in why
    monkeypatch.undo()
    assert harness.check_screens("youtube") == (True, "single — two-screen pass: --two-screens / --manual")
    assert any("STOPS and closes" in s for s in harness.manual_steps("youtube"))
    assert any("STAYS open" in s for s in harness.manual_steps("agenda"))
    assert (ENGINE / "tests/browser/e2e/mobile/two_screens.py").is_file()
