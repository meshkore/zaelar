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

import hashlib
import importlib.util
import json
import re
import shutil
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


def test_the_build_survives_a_console_that_is_not_utf_8(tmp_path):
    """⚠️ MEASURED ON A WINDOWS RUNNER, 2026-09-14, and it failed the whole release. A Windows console defaults
    to cp1252, and the success line printed an arrow — so `UnicodeEncodeError` was raised AFTER every artifact
    had been written. The build worked; the script died formatting its own report, and CI recorded a failed
    build for a directory full of correct files.

    `PYTHONIOENCODING=cp1252` reproduces that console on any machine, which is the only way this node can check
    a Windows property from a Mac."""
    env = {"PATH": "/usr/bin:/bin", "HOME": str(tmp_path), "PYTHONIOENCODING": "cp1252"}
    result = subprocess.run([sys.executable, str(PACKAGING / "build.py"), "--zipapp"],
                            capture_output=True, text=True, timeout=120, env=env, cwd=str(ENGINE))
    assert result.returncode == 0, (
        f"the build died on a non-UTF-8 console after doing its work:\n{result.stderr[-800:]}"
    )


def test_the_published_checksums_name_the_files_the_release_actually_contains(built, tmp_path):
    """⚠️ MEASURED, 2026-09-15, and daemon-v0.2.0 shipped with it broken. `build.py` writes SHA256SUMS under the
    BUILD names, and the release publishes the files under ARCHITECTURE names — so the sums file was published,
    looked right, and listed two files nobody could download. The one-line installer refused to install a
    binary it had downloaded perfectly, because it could not find that binary in its own checksums.

    Renaming the files is therefore not enough, and patching the text of the sums file would be the same lie in
    a better disguise: `release_names.py` recomputes the digests from the files as they will be published."""
    spec = importlib.util.spec_from_file_location("daemon_release_names_under_test", PACKAGING / "release_names.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    # A COPY of the build, because renaming is destructive and `built` is module-scoped: renaming the shared
    # artifact left every later test in this file looking for a file that no longer had that name.
    dist = tmp_path / "dist"
    shutil.copytree(built["dist"], dist)
    published = module.rename_for("testarch", dist=dist)
    assert published, "the rename produced nothing"

    sums = (dist / "SHA256SUMS-testarch").read_text(encoding="utf-8").splitlines()
    listed = {line.split(None, 1)[1] for line in sums if line.strip()}
    on_disk = {a.name for a in published}
    assert listed == on_disk, f"the sums name {listed} and the release carries {on_disk}"

    for line in sums:
        digest, name = line.split(None, 1)
        actual = hashlib.sha256((dist / name).read_bytes()).hexdigest()
        assert digest == actual, f"{name}: the published digest is not the file's"

    assert not (dist / "SHA256SUMS").exists(), (
        "the build-name checksums were left behind — three jobs uploading one `SHA256SUMS` into a flattened "
        "release is the collision the suffixes exist to prevent"
    )


def test_the_one_line_installer_survives_the_bash_that_macos_actually_ships(tmp_path):
    """⚠️ macOS ships bash 3.2, whose parser accepts a byte over 127 as part of a variable NAME — so
    `$ASSET…` expanded as a variable called `ASSET\xe2`, and under `set -u` the install died on line 60 with
    "unbound variable". `bash -n` does not catch it: it is a runtime expansion, not a syntax error. Measured on
    2026-09-15 by running the real command.

    Every `$VAR` immediately followed by a non-ASCII character must be braced."""
    text = (PACKAGING / "get.sh").read_text(encoding="utf-8")
    unbraced = re.findall(r"\$([A-Za-z_][A-Za-z0-9_]*)(?=[^\x00-\x7f])", text)
    assert not unbraced, (
        f"unbraced variables touching a non-ASCII character: {unbraced}. On macOS's bash 3.2 the name swallows "
        f"the first byte of the character and the script dies with 'unbound variable'."
    )


def test_an_option_printed_next_to_a_pipe_is_one_the_pipe_can_carry():
    """⚠️ MEASURED by typing it, 2026-09-15. `curl … | bash --purge` looks obviously right and is not: the
    option is consumed by BASH, which answers with its own usage text and never runs the script — so the user
    reads four screens of shell help and concludes the uninstaller is broken. The piped form needs `-s --`, and
    `iex` cannot take an argument at all (it needs the scriptblock form).

    A hint that only works when you already know the trick is a hint for somebody who did not need it."""
    sh = (PACKAGING / "get.sh").read_text(encoding="utf-8")
    # Comments are skipped: both scripts explain this trap in prose, and a check tripped by its own
    # documentation is a check that teaches people to delete the documentation.
    for line in (l for l in sh.splitlines() if not l.strip().startswith("#")):
        if "| bash" in line and "--purge" in line:
            assert "bash -s --" in line, f"a piped bash line passes an option bash will eat: {line.strip()}"
    assert "bash -s -- --purge" in sh, "get.sh never shows how to uninstall destructively"

    ps = (PACKAGING / "get.ps1").read_text(encoding="utf-8")
    for line in (l for l in ps.splitlines() if not l.strip().startswith("#")):
        if "| iex" in line and "-Purge" in line:
            raise AssertionError(f"`iex` cannot take an argument: {line.strip()}")
    assert "scriptblock]::Create" in ps, "get.ps1 never shows how to uninstall destructively"


# ── where an INSTALLED daemon keeps what it must not lose ─────────────────────────────────────────────────

def _status(archive: Path, cwd: Path, home: Path) -> dict:
    """Run the artifact's own `status` with a clean environment — no `ZAELAR_WORKSPACE`, which is what a real
    installed daemon has and what every other test in this file sets."""
    env = {"PATH": "/usr/bin:/bin", "HOME": str(home)}
    result = subprocess.run([sys.executable, str(archive), "status"],
                            capture_output=True, text=True, timeout=60, env=env, cwd=str(cwd))
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_an_installed_daemon_does_not_try_to_write_inside_its_own_archive(built, tmp_path):
    """⚠️ MEASURED 2026-09-15, and it was silent. `_frozen()` was the only test for "installed" and a zipapp is
    not frozen — so an installed `.pyz` resolved its root to the ARCHIVE FILE and its state to
    `…/zaelar-daemon.pyz/config/daemon`, a directory that can never exist because its parent is a regular file.

    Every write failed, and this module never raises on purpose, so nothing was reported. The consequences are
    the two that matter most: a fresh random token on EVERY start, and a folder allowlist that does not survive
    a restart — the user grants Documents, restarts, and it is gone. Meanwhile `/health` answered perfectly.

    The portable archive is the fallback that exists so there is always a way to ship, which is exactly why
    nobody was looking at it."""
    prefix = tmp_path / "chosen"
    (prefix / "bin").mkdir(parents=True)
    installed = prefix / "bin" / built["archive"].name
    installed.write_bytes(built["archive"].read_bytes())

    reported = _status(installed, cwd=tmp_path, home=tmp_path / "home")
    assert reported["state_dir"] == str(prefix / "config" / "daemon"), (
        f"an installed archive resolved its state to {reported['state_dir']}"
    )
    assert ".pyz" not in reported["state_dir"], "the state directory is inside the archive file"


def test_the_token_is_the_same_on_the_second_start(built, tmp_path):
    """THE SYMPTOM, not the path. A state directory that cannot be created means the config is never written,
    and a daemon that mints a new token every start is one the engine can never stay connected to — it would
    reconnect once and be refused forever after."""
    prefix = tmp_path / "chosen"
    (prefix / "bin").mkdir(parents=True)
    installed = prefix / "bin" / built["archive"].name
    installed.write_bytes(built["archive"].read_bytes())
    home = tmp_path / "home"

    env = {"PATH": "/usr/bin:/bin", "HOME": str(home)}
    first = subprocess.run([sys.executable, str(installed), "token"], capture_output=True, text=True,
                           timeout=60, env=env, cwd=str(tmp_path))
    second = subprocess.run([sys.executable, str(installed), "token"], capture_output=True, text=True,
                            timeout=60, env=env, cwd=str(tmp_path))
    assert first.returncode == 0 and second.returncode == 0, first.stderr + second.stderr
    assert first.stdout.strip() and first.stdout.strip() == second.stdout.strip(), (
        "the daemon minted a new token on its second start — its config is not being persisted"
    )


def test_a_file_run_straight_from_a_download_does_not_claim_the_folder_above_it(built, tmp_path):
    """THE COUNTERWEIGHT to the rule above, and the reason it keys on a `bin` directory. "The state lives beside
    the program" is right for an install and wrong for a file somebody double-clicked in `~/Downloads`, which
    would otherwise claim the whole of `~` as its root."""
    loose = tmp_path / "Downloads"
    loose.mkdir()
    copied = loose / built["archive"].name
    copied.write_bytes(built["archive"].read_bytes())
    home = tmp_path / "home"

    reported = _status(copied, cwd=tmp_path, home=home)
    assert str(loose) not in reported["state_dir"], "a loose download claimed its own folder"
    assert str(home) in reported["state_dir"], (
        f"a loose download should fall back to the user-data directory, got {reported['state_dir']}"
    )


def test_a_source_checkout_still_keeps_its_state_in_the_repo(tmp_path):
    """The other counterweight, and the one that would hurt most: a self-hoster runs `python -m daemon` from
    their clone and their token and allowlist live under the repo's `config/`. The install rule must not move
    them — an "improvement" that silently relocates somebody's existing allowlist reads as it being wiped."""
    from daemon import paths
    root = paths.workspace_root()
    assert root == ENGINE, f"an in-repo daemon resolved its root to {root}"
    assert paths.state_dir() == ENGINE / "config" / "daemon"


@pytest.mark.parametrize("script", ["macos/install.sh", "macos/uninstall.sh",
                                    "windows/install.ps1", "windows/uninstall.ps1"])
def test_the_folder_it_installs_into_can_be_chosen(script):
    """"Somewhere else" is a legitimate answer — an encrypted volume, a small home directory. The UNINSTALLERS
    need it just as much: one that only knows the default location removes the launch agent, reports success,
    and leaves the program and the folder allowlist exactly where the user put them, while they believe it is
    gone."""
    text = (PACKAGING / script).read_text(encoding="utf-8")
    # ⚠️ LIVE LINES ONLY. Every one of these scripts DOCUMENTS the variable in a comment, so looking for the
    # name anywhere in the file stayed green with the actual assignment deleted — the third time today an
    # assertion was satisfied by its own explanation. Block comments (`<# … #>`) are stripped first, then
    # line comments.
    text = re.sub(r"<#.*?#>", "", text, flags=re.S)
    live = "\n".join(l for l in text.splitlines() if not l.strip().startswith("#"))
    assert "ZAELAR_DAEMON_PREFIX" in live, f"{script} cannot be pointed at another folder"


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
