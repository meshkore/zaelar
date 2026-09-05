"""Build the artifacts a person installs.

TWO FORMS, because "easy to install" means different things to two different people:

  THE ZIPAPP (`zaelar-daemon.pyz`) is the whole daemon in one file, built by the standard library, with no build
  dependency at all. It needs a Python 3.11+ on the machine — which a developer has and a stranger may not —
  and it is what makes the daemon reproducible: anybody can build the exact artifact we ship, from source, with
  one command and nothing installed.

  THE ONEFILE (`zaelar-daemon` / `zaelar-daemon.exe`) bundles the interpreter, so it runs on a machine with no
  Python at all. That is the one an ordinary user gets, and the reason it needs PyInstaller — a BUILD
  dependency, listed in `requirements-build.txt` and deliberately NOT in the daemon's own `requirements.txt`,
  which is empty and stays that way.

WHY BOTH AND NOT JUST THE SECOND. A build that only works when a third-party tool is installed and working is a
build that stops existing the first time that tool breaks on a new Python. The zipapp is always available, so
there is always a way to ship, and CI can prove the package still assembles even on a runner where PyInstaller
would not.

WHAT THIS DELIBERATELY DOES NOT DO: download anything, sign anything, or publish anything. Signing needs the
operator's identity and publishing needs a decision about where; both are steps in the release playbook, run by
somebody who has those things, not side effects of a build.

    python daemon/packaging/build.py            everything it can build here
    python daemon/packaging/build.py --zipapp   just the portable one
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import shutil
import subprocess
import sys
import tempfile
import zipapp
from pathlib import Path

PACKAGING = Path(__file__).resolve().parent
DAEMON = PACKAGING.parent
ENGINE = DAEMON.parent
DIST = ENGINE / "dist" / "daemon"

# The entry point a zipapp needs at ITS top level. The daemon's own `__main__.py` is one level down, inside the
# package, so the archive gets a two-line shim rather than a copy of anything.
_ZIPAPP_MAIN = '''"""Entry point for the zipapp build. See daemon/packaging/build.py."""
import sys

from daemon.cli import main

raise SystemExit(main(sys.argv))
'''

# Everything under `daemon/` that is not the daemon at run time. Excluded from both artifacts: the build tooling
# has no business inside the thing it builds, and `__pycache__` from the developer's machine is bytes shipped to
# a stranger for no reason.
_EXCLUDE = {"packaging", "__pycache__", ".pytest_cache"}


def _version() -> str:
    """Read the version WITHOUT importing the package, so a build never depends on the daemon importing cleanly
    in whatever environment the build runs in."""
    for line in (DAEMON / "__init__.py").read_text(encoding="utf-8").splitlines():
        if line.startswith("VERSION"):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit("daemon/__init__.py has no VERSION line")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _stage(into: Path) -> Path:
    """A clean copy of the package, with the build tooling and every cache left behind."""
    package = into / "daemon"
    shutil.copytree(
        DAEMON, package,
        ignore=lambda _dir, names: [n for n in names if n in _EXCLUDE or n.endswith((".pyc", ".pyo"))],
    )
    return package


def build_zipapp() -> Path:
    DIST.mkdir(parents=True, exist_ok=True)
    target = DIST / "zaelar-daemon.pyz"
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp)
        _stage(source)
        (source / "__main__.py").write_text(_ZIPAPP_MAIN, encoding="utf-8")
        # `compressed` because the archive travels; the interpreter shebang makes it directly executable on
        # POSIX and is simply ignored on Windows, where it is run as `py zaelar-daemon.pyz`.
        zipapp.create_archive(source, target=target, interpreter="/usr/bin/env python3", compressed=True)
    target.chmod(0o755)
    return target


def build_onefile() -> Path | None:
    """The bundled-interpreter build. Returns None — loudly, not silently — when PyInstaller is not here."""
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("PyInstaller is not installed: skipping the onefile build.\n"
              "  pip install -r daemon/packaging/requirements-build.txt", file=sys.stderr)
        return None

    DIST.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp)
        _stage(source)
        entry = source / "zaelar-daemon-entry.py"
        entry.write_text(_ZIPAPP_MAIN, encoding="utf-8")
        work = source / "build"
        subprocess.run(
            [sys.executable, "-m", "PyInstaller",
             "--onefile", "--console", "--clean", "--noconfirm",
             "--name", "zaelar-daemon",
             "--distpath", str(DIST), "--workpath", str(work), "--specpath", str(source),
             # The daemon reaches its own modules only through ordinary imports, so PyInstaller's analysis
             # finds them — but `daemon.fs` and friends are imported for their SUBMODULES in one place, and a
             # collected package is cheaper than a build that is subtly missing one at run time.
             "--collect-submodules", "daemon",
             "--paths", str(source),
             str(entry)],
            check=True, cwd=source,
        )
    built = DIST / ("zaelar-daemon.exe" if sys.platform == "win32" else "zaelar-daemon")
    if not built.exists():
        raise SystemExit(f"PyInstaller reported success but {built} is not there")
    return built


def write_manifest(artifacts: list[Path]) -> Path:
    """What was built, from what, and what it hashes to.

    The checksums are the whole point: this is how an installer, or a person, can tell the file they have is the
    file that was built. It is NOT a signature — a hash beside the download only proves the two agree, and
    whoever can replace one can replace the other. Signing is a release step, done by somebody who has the
    identity to sign with; see the ops playbook."""
    manifest = {
        "product": "zaelar-daemon",
        "version": _version(),
        "built_on": f"{platform.system().lower()}-{platform.machine().lower()}",
        "python": platform.python_version(),
        "artifacts": [
            {"name": a.name, "bytes": a.stat().st_size, "sha256": _sha256(a)} for a in artifacts
        ],
    }
    target = DIST / "manifest.json"
    target.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    (DIST / "SHA256SUMS").write_text(
        "".join(f"{_sha256(a)}  {a.name}\n" for a in artifacts), encoding="utf-8")
    return target


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Build the zaelar-daemon artifacts.")
    parser.add_argument("--zipapp", action="store_true", help="only the portable, dependency-free build")
    parser.add_argument("--onefile", action="store_true", help="only the bundled-interpreter build")
    args = parser.parse_args(argv[1:])
    both = not (args.zipapp or args.onefile)

    artifacts: list[Path] = []
    if both or args.zipapp:
        artifacts.append(build_zipapp())
    if both or args.onefile:
        one = build_onefile()
        if one:
            artifacts.append(one)
        elif args.onefile:
            return 1

    if not artifacts:
        return 1
    manifest = write_manifest(artifacts)
    print(f"\nzaelar-daemon {_version()} → {DIST}")
    for artifact in artifacts:
        print(f"  {artifact.name}  {artifact.stat().st_size:,} bytes")
    print(f"  {manifest.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
