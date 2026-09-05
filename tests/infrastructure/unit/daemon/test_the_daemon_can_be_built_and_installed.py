"""What a stranger installs (V2-575 · P4).

The daemon's promise is not "it runs from a checkout" — that is where it is written, not where it lives. It is
"it runs on your Mac or your PC with the minimum of installation problems", and everything about that claim
breaks in ways the other daemon nodes cannot see: the archive assembles but excludes a module, the installer
names a file the build does not produce, the build tooling ends up INSIDE the artifact it built.

WHAT IS CHECKED HERE AND WHAT IS NOT. This builds the real portable artifact and runs it, which is fast (it is
fifty kilobytes) and is the strongest thing that can be checked without another operating system. The
standalone binary needs PyInstaller, and the installers need a machine to install onto — those are checked by
`.github/workflows/daemon-artifacts.yml`, on a macOS runner and a Windows one, where they start the real binary
and confirm its guards survived the build. Saying which half runs where is the point: a test that quietly did
not cover Windows would read exactly like one that did.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

ENGINE = Path(__file__).resolve().parents[4]
PACKAGING = ENGINE / "daemon" / "packaging"


@pytest.fixture(scope="module")
def built(tmp_path_factory) -> dict:
    """The real build, into a throwaway `dist`. Nothing is mocked: the thing under test is whether the archive
    the operator ships actually assembles and runs."""
    out = tmp_path_factory.mktemp("dist")
    # Imported by file rather than `exec`-ed: the script resolves its own location from `__file__`, which an
    # `exec` does not set — so an `exec` would be testing a build script that cannot find the package it
    # builds, which is not the one that ships.
    spec = importlib.util.spec_from_file_location("daemon_build_under_test", PACKAGING / "build.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.DIST = out
    archive = module.build_zipapp()
    module.write_manifest([archive])
    return {"archive": archive, "dist": out, "version": module._version()}


# ── it assembles, and what comes out is the daemon ────────────────────────────────────────────────────────

def test_the_portable_build_needs_nothing_installed(built):
    """No build dependency at all: the standard library's own `zipapp`. That is what guarantees there is always
    a way to ship, on any machine, even the day a third-party build tool breaks on a new Python."""
    assert built["archive"].exists() and built["archive"].stat().st_size > 0


def test_the_archive_carries_every_module_the_daemon_imports(built):
    """A packaging step that silently drops a module does not fail at build time — it fails at run time, on
    somebody else's computer, with an ImportError they cannot act on."""
    inside = {name for name in zipfile.ZipFile(built["archive"]).namelist() if name.endswith(".py")}
    for module in sorted((ENGINE / "daemon").rglob("*.py")):
        relative = module.relative_to(ENGINE)
        if "packaging" in relative.parts or "__pycache__" in relative.parts:
            continue
        assert str(relative) in inside, f"{relative} is in the daemon and not in the artifact"


def test_the_build_tooling_is_not_inside_the_thing_it_built(built):
    """The build script, its pinned PyInstaller requirement and the installers have no business travelling to a
    user's machine — they are how the artifact is MADE, and shipping them is shipping a second, confusing copy
    of the instructions."""
    inside = zipfile.ZipFile(built["archive"]).namelist()
    assert not [name for name in inside if "packaging" in name], (
        f"the packaging tree shipped inside the artifact: {[n for n in inside if 'packaging' in n]}"
    )


def test_the_artifact_runs_and_agrees_about_its_own_version(built):
    """Run, not imported. The whole reason this node exists is that a package which imports fine from a
    checkout can still fail to execute from an archive."""
    result = subprocess.run([sys.executable, str(built["archive"]), "version"],
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == built["version"], (
        "the built artifact reports a different version from daemon/__init__.py, so the engine's "
        "'your daemon is out of date' check would be comparing against the wrong number"
    )


def test_the_artifact_reports_its_state_without_a_repo_around_it(built, tmp_path):
    """`status` resolves the state directory, reads the config and probes the port — the first four things that
    happen on a real machine, and none of them are exercised by importing the package."""
    env = {"ZAELAR_WORKSPACE": str(tmp_path), "PATH": "/usr/bin:/bin", "HOME": str(tmp_path)}
    result = subprocess.run([sys.executable, str(built["archive"]), "status"],
                            capture_output=True, text=True, timeout=60, env=env)
    assert result.returncode == 0, result.stderr
    reported = json.loads(result.stdout)
    assert reported["roots"] == [], "a fresh install can read nothing until the user chooses"
    assert str(tmp_path) in reported["state_dir"]


def test_the_manifest_names_what_was_built_and_what_it_hashes_to(built):
    """The checksums are how an installer — or a person — can tell the file they have is the file that was
    built. Not a signature, and the docstring in `build.py` says so: a hash beside a download only proves the
    two agree, and whoever can replace one can replace the other."""
    manifest = json.loads((built["dist"] / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["version"] == built["version"]
    entry = next(a for a in manifest["artifacts"] if a["name"] == built["archive"].name)
    assert len(entry["sha256"]) == 64 and entry["bytes"] == built["archive"].stat().st_size


# ── the build tooling stays out of the daemon's own dependency set ────────────────────────────────────────

def test_the_build_dependency_is_not_a_run_dependency():
    """`daemon/requirements.txt` is empty and a sibling test enforces it, because "runs on a bare Python with
    nothing installed" is the property that makes a single-file installer possible at all. PyInstaller is a
    BUILD dependency and lives in its own file; the day somebody merges the two, the daemon stops being
    installable the easy way and nothing else would say so."""
    build_reqs = (PACKAGING / "requirements-build.txt").read_text(encoding="utf-8")
    run_reqs = (ENGINE / "daemon" / "requirements.txt").read_text(encoding="utf-8")
    assert "pyinstaller" in build_reqs.lower()
    assert "pyinstaller" not in run_reqs.lower(), "the build tool leaked into the daemon's own requirements"
    assert "==" in build_reqs, "the build tool is unpinned: the artifact a stranger runs would drift on its own"


# ── the installers and the build agree about the names ────────────────────────────────────────────────────

@pytest.mark.parametrize("script", ["macos/install.sh", "macos/uninstall.sh",
                                    "windows/install.ps1", "windows/uninstall.ps1"])
def test_every_platform_has_its_installer_and_its_way_back_out(script):
    """An uninstaller is not a courtesy. Software a user cannot remove is software they will not install, and a
    daemon that reads their documents is exactly the kind they think twice about."""
    assert (PACKAGING / script).exists()


@pytest.mark.parametrize("script,names", [
    ("macos/install.sh", ("zaelar-daemon", "zaelar-daemon.pyz")),
    ("windows/install.ps1", ("zaelar-daemon.exe", "zaelar-daemon.pyz")),
])
def test_the_installers_look_for_the_names_the_build_actually_produces(script, names):
    """The failure this prevents is the worst kind of trivial: rename an artifact, and the installer says "no
    artifact found" on a machine where the artifact is sitting right next to it."""
    text = (PACKAGING / script).read_text(encoding="utf-8")
    for name in names:
        assert name in text, f"{script} does not know about {name}"


@pytest.mark.parametrize("script", ["macos/install.sh", "windows/install.ps1"])
def test_no_installer_asks_for_administrator_rights(script):
    """A per-user daemon that needs elevation to install is both a worse install and a worse daemon: it would
    then be able to reach every account on the machine, which is precisely the blast radius the whole
    permission circuit exists to keep small."""
    text = (PACKAGING / script).read_text(encoding="utf-8").lower()
    for elevation in ("sudo ", "runas", "-verb runas", "requireadministrator", "runlevel highest"):
        assert elevation not in text, f"{script} escalates ({elevation.strip()!r})"


@pytest.mark.parametrize("script", ["macos/uninstall.sh", "windows/uninstall.ps1"])
def test_uninstalling_keeps_the_users_choices_unless_they_say_otherwise(script):
    """Uninstalling is often a step in troubleshooting. Throwing away the token and the folder allowlist turns
    "let me reinstall this" into "let me set it all up again", so the destructive path is opt-in and says what
    it deleted."""
    text = (PACKAGING / script).read_text(encoding="utf-8").lower()
    assert "purge" in text, f"{script} has no explicit way to delete the state"
    assert "kept" in text, f"{script} does not tell the user what it left behind"


def test_the_workflow_builds_on_the_platforms_people_install_on():
    """The Windows half of this was written on a machine with no Windows and no PowerShell. That is a fact
    about how it was made, and the only thing that turns it from an untested claim into a measured one is a
    runner that is actually Windows — so the workflow existing, and naming both platforms, is itself the
    guarantee this file cannot give."""
    workflow = (ENGINE / ".github" / "workflows" / "daemon-artifacts.yml").read_text(encoding="utf-8")
    assert "macos-latest" in workflow and "windows-latest" in workflow
    assert "Host: evil.example" in workflow or "evil.example" in workflow, (
        "the workflow builds the binary but never checks its guards survived the build — the one regression "
        "that would ship a daemon that starts and defends nothing"
    )
