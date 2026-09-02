"""V2-553 — the update channel: one number a person can compare, and an honest «do I have to reload?».

The operator asked for two things that pull in opposite directions: a bar that offers to reload the browser
when a new version lands, and NO bar when «solo se ha tocado algo del backend». A version number alone
cannot serve both — every release moves it, including the ones that change nothing the browser runs. So the
reload question is answered by MEASURING the bytes the browser executes (`ui_rev`), and the number the user
reads is a separate, deliberately boring integer (`build`).

These tests pin the four things that would make the channel lie:
  · a build number that does not survive to production,
  · a `ui_rev` that moves when the backend changes (a bar nobody needs) or stands still when the frontend
    changes (the bar that never comes),
  · a `ui_rev` derived from timestamps, which a Docker COPY and a fresh clone both invent,
  · a release that ships without bumping the number, leaving every user on «v24» forever.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ENGINE = Path(__file__).resolve().parents[3]
if str(ENGINE) not in sys.path:
    sys.path.insert(0, str(ENGINE))

import update  # noqa: E402


# ── the number the user reads ───────────────────────────────────────────────────────────────────────────

def test_the_build_number_is_a_positive_integer():
    assert update.BUILD_FILE.is_file(), "update/BUILD is the whole source of truth for the user-facing version"
    assert update.build() >= 1, "0 means «unknown» to every caller; a shipped engine must know its own number"


def test_the_build_number_is_TRACKED_by_git():
    """It is the one field that has to survive into the cloud image, and the image is built from what git
    holds. A BUILD file that exists only on this disk ships as «unknown» to every paying account."""
    r = subprocess.run(["git", "ls-files", "--error-unmatch", "update/BUILD"],
                       cwd=ENGINE, capture_output=True, text=True)
    assert r.returncode == 0, "update/BUILD is not tracked — it would not reach the image, and cloud shows no version"


def test_the_number_does_not_come_from_git():
    """`version.sha()` returns "nogit" inside every Machine: the Dockerfile does not COPY `.git`. Anything
    the user is shown has to come from a plain file, which is why the build number is one."""
    dockerfile = (ENGINE / "Dockerfile").read_text(encoding="utf-8")
    assert "COPY .git " not in dockerfile and "COPY .git/" not in dockerfile
    assert "COPY update ./update" in dockerfile, "the package carrying BUILD must be in the image"


def test_bump_only_ever_goes_up(tmp_path, monkeypatch):
    f = tmp_path / "BUILD"
    f.write_text("7\n", encoding="utf-8")
    monkeypatch.setattr(update, "BUILD_FILE", f)
    monkeypatch.setattr(update, "_CACHE", {})
    assert update.build() == 7
    assert update.bump() == 8
    assert f.read_text().strip() == "8"
    assert update.bump(0) == 9, "a bump of «nothing» is still a release; the floor is +1"


def test_a_missing_number_is_zero_and_not_a_crash(tmp_path, monkeypatch):
    monkeypatch.setattr(update, "BUILD_FILE", tmp_path / "absent")
    monkeypatch.setattr(update, "_CACHE", {})
    assert update.build() == 0, "an unreadable file must degrade to «unknown», never take the boot down with it"


# ── the digest that decides whether a reload is worth asking for ────────────────────────────────────────

def _rev(root: Path) -> str:
    update._CACHE.clear()
    old = update._UI_ROOT
    update._UI_ROOT = root
    try:
        return update._digest_ui()
    finally:
        update._UI_ROOT = old
        update._CACHE.clear()


def test_a_frontend_change_moves_the_revision_and_a_backend_change_does_not(tmp_path):
    """The operator's rule, in one test. The «backend» half is structural rather than simulated: the digest
    only ever walks `frontend/`, so a change anywhere else is invisible to it by construction — which is
    exactly the property that keeps a backend-only release from interrupting anyone."""
    ui = tmp_path / "frontend"
    (ui / "app").mkdir(parents=True)
    (ui / "app" / "main.js").write_text("export const a = 1;\n", encoding="utf-8")
    (ui / "app" / "styles.css").write_text("body{color:red}\n", encoding="utf-8")
    before = _rev(ui)

    (ui / "app" / "main.js").write_text("export const a = 2;\n", encoding="utf-8")
    assert _rev(ui) != before, "an edited module must be a new revision, or the bar never appears"

    (ui / "app" / "main.js").write_text("export const a = 1;\n", encoding="utf-8")
    assert _rev(ui) == before, "reverting the bytes reverts the revision — a rollback puts the tab back in date"

    # A file a browser never fetches (this is what «backend» looks like inside the walked tree).
    (ui / "app" / "notes.py").write_text("# nothing a browser runs\n", encoding="utf-8")
    assert _rev(ui) == before, "a non-browser file must not move the revision: that is the false bar"


def test_renaming_a_module_is_a_new_revision(tmp_path):
    """Same bytes, different URL to fetch. A digest of contents alone would call this «no change» while
    every import in the shell 404s."""
    ui = tmp_path / "frontend"
    ui.mkdir()
    (ui / "a.js").write_text("export const x = 1;\n", encoding="utf-8")
    before = _rev(ui)
    (ui / "a.js").rename(ui / "b.js")
    assert _rev(ui) != before


def test_the_revision_ignores_timestamps(tmp_path):
    """The trap this design exists to avoid. `COPY` in a Docker build and a fresh `git clone` both invent
    mtimes, so a timestamp digest would announce a phantom update on every single deployment — and would
    stay silent about a real one whose file was written with an older timestamp."""
    ui = tmp_path / "frontend"
    ui.mkdir()
    f = ui / "a.js"
    f.write_text("export const x = 1;\n", encoding="utf-8")
    before = _rev(ui)
    os.utime(f, (1_600_000_000, 1_600_000_000))
    assert _rev(ui) == before


def test_a_tree_it_cannot_read_is_UNKNOWN_and_not_a_plausible_digest():
    """«I cannot tell» has to be sayable. An empty digest is a perfectly stable value that every client
    would compare against happily, and the channel would go quiet forever without anyone noticing."""
    assert _rev(Path("/definitely/not/a/frontend")) == update.UNKNOWN


def test_the_client_treats_UNKNOWN_as_no_news():
    """The other half of the sentinel: it only protects anyone if the browser refuses to act on it."""
    js = (ENGINE / "frontend" / "app" / "update" / "watch.js").read_text(encoding="utf-8")
    assert 'rev === "unknown"' in js and "return" in js, \
        "watch.js must bail on the sentinel; otherwise a failed read becomes a permanent reload nag"


# ── the payload and the route ───────────────────────────────────────────────────────────────────────────

def test_the_payload_carries_what_the_browser_reads():
    s = update.state()
    for k in ("build", "version", "sha", "short", "ui_rev", "started_ms", "deploy"):
        assert k in s, f"missing field: {k}"
    assert json.dumps(s), "the payload has to be JSON-serialisable — it is served as-is"


def test_the_route_is_mounted_and_never_cached():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from update.api import router

    app = FastAPI()
    app.include_router(router)
    r = TestClient(app).get("/api/update")
    assert r.status_code == 200
    assert r.json()["build"] == update.build()
    assert "no-store" in r.headers.get("cache-control", ""), \
        "an answer about staleness that is itself cached is the one answer that cannot be trusted"


def test_the_route_is_NOT_public():
    """It is a normal `/api/*` route: on a Machine that takes part in session routing it needs the same
    session as everything else, and the browser asking always has one. The allowlist grows only for things
    that MUST answer to a stranger."""
    from server import ingress

    assert not ingress.is_public_path("/api/update")


# ── the process around it ───────────────────────────────────────────────────────────────────────────────

def test_the_release_refuses_a_tag_whose_number_did_not_move():
    """Forgetting `python -m update bump` is the single mistake this module cannot survive on its own: the
    release lands, every browser reloads, and the badge still reads yesterday's number. The tag gate is
    what makes that loud instead of silent."""
    wf = (ENGINE / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert "update/BUILD" in wf, "the release gate no longer reads the build number"
    assert "fetch-depth: 0" in wf, "the gate compares against the PREVIOUS tag; a shallow checkout has none"


def test_the_module_stays_out_of_the_agent():
    """The operator's constraint on this work: «que no ensucie el código actual del agente… que sea un
    componente de librería o módulo». Two touch points is the budget — the server mounts the router and
    the image ships the package. If a third appears, this is the conversation about whether it should."""
    hits = subprocess.run(
        ["git", "grep", "-l", "-e", "from update", "-e", "import update", "--",
         "nucleo", "voice", "memory", "widgets", "connectors", "bus", "observability"],
        cwd=ENGINE, capture_output=True, text=True).stdout.split()
    assert not hits, f"the update channel leaked into the agent's own packages: {hits}"


@pytest.mark.parametrize("cmd", [[], ["bump"]])
def test_the_release_cli_answers(cmd, tmp_path, monkeypatch):
    """`python -m update` is what a human and CI both call; a CLI that raises at release time is worse than
    no CLI. `bump` is exercised against a throwaway file so the shipped number is never touched by a test."""
    monkeypatch.setattr(update, "BUILD_FILE", tmp_path / "BUILD")
    monkeypatch.setattr(update, "_CACHE", {})
    from update.__main__ import main
    assert main(cmd) == 0
