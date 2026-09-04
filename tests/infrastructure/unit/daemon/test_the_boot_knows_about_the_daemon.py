"""The daemon starts and stops with the engine — in BOTH process managers (V2-575 · P0).

There are two of them with different teardown (`scripts/zaelar.py`, pidfile + port, the one that works on Windows;
`scripts/run-livekit.sh`, trap + pkill), and wiring only one is how `make run` and `make start` end up disagreeing
about what is running. That disagreement does not fail loudly: it leaves an orphan holding 45817, and the next
start dies on a silent EADDRINUSE — which is the exact failure the reaping section of `run-livekit.sh` was written
for, one process further along.

These are SOURCE checks, deliberately: actually starting the stack would need a live engine, and what is being
guarded here is that a line exists in each launcher, which is precisely what a source read can answer.
"""
from pathlib import Path

import pytest

ENGINE = Path(__file__).resolve().parents[4]      # tests/infrastructure/unit/daemon/ → the engine root


@pytest.fixture(scope="module")
def zaelar_py() -> str:
    return (ENGINE / "scripts" / "zaelar.py").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def run_sh() -> str:
    return (ENGINE / "scripts" / "run-livekit.sh").read_text(encoding="utf-8")


def test_the_port_is_declared_once_and_the_launcher_agrees(zaelar_py):
    """`scripts/zaelar.py` is standard-library-only and imports nothing from the engine — that is what lets a
    Windows user with no venv start and stop their instance — so the port is a literal there and the real
    declaration lives in `daemon/__init__.py`. This is the check that keeps the copy honest."""
    from daemon import PORT

    assert f"DAEMON_PORT = {PORT}" in zaelar_py, (
        f"scripts/zaelar.py does not carry the daemon's real port ({PORT}); stop would not free it"
    )
    assert f"({PORT}, " in zaelar_py, "the daemon's port is not in PORTS, so `stop` leaves it held"


def test_stop_frees_the_daemon_port(zaelar_py):
    """`cmd_stop` iterates PORTS, so being in that list IS being stopped. Asserted through the list rather than
    the function so a refactor of the loop cannot silently drop it."""
    ports_block = zaelar_py.split("PORTS = [", 1)[1].split("]", 1)[0]
    assert "45817" in ports_block


def test_start_launches_the_daemon(zaelar_py):
    assert '"-m", "daemon"' in zaelar_py, "`make start` does not start the daemon"


def test_the_foreground_launcher_starts_and_reaps_it(run_sh):
    assert "-m daemon" in run_sh, "`make run` does not start the daemon"
    assert 'DAEMON_PID' in run_sh.split("cleanup()", 1)[1].split("}", 1)[0], (
        "the daemon is not in cleanup(), so Ctrl-C would leave it running"
    )
    assert 'pgrep -f "[Pp]ython -m daemon"' in run_sh, (
        "no orphan sweep for the daemon: a previous launch's daemon keeps 45817 and the new one dies silently"
    )


def test_the_orphan_sweep_matches_a_capital_P(run_sh):
    """`[Pp]` is load-bearing, not cosmetic — measured on this machine, 2026-09-04.

    The venv interpreter resolves through the framework bundle and presents its command line as
    `…/Python.app/Contents/MacOS/Python -m daemon`, with a CAPITAL P and no lowercase `python` anywhere. A sweep
    written as `pgrep -f "python -m daemon"` matches NOTHING, which is the exact trap `scripts/zaelar.py`'s header
    already records for `python -m server` — and it fails the quiet way: the orphan survives, keeps 45817, and the
    next launch dies on a silent EADDRINUSE.

    `scripts/zaelar.py` is immune by design (it resolves ownership by PORT, never by name); this only guards the
    bash launcher, which has to match a string."""
    assert '"python -m daemon"' not in run_sh, (
        "the daemon sweep matches only a lowercase interpreter name; on macOS the venv python is `Python`"
    )


def test_the_daemon_never_blocks_the_engine_from_starting(zaelar_py):
    """The daemon is ADDITIVE (decision 5): the engine keeps its own in-process browser, so a daemon that fails
    to start costs today's product exactly nothing and must never make `start` return non-zero.

    Read from the daemon's own block rather than the whole file, or the app's legitimate `return 1` right below
    would satisfy this by accident."""
    block = zaelar_py.split("starting zaelar-daemon", 1)[1].split("starting zaelar…", 1)[0]
    assert "return 1" not in block, "a failed daemon start aborts the engine's start"


def test_make_daemon_is_phony():
    """`daemon` is now also a DIRECTORY, so without `.PHONY` make considers the target already built and does
    nothing — with no error and no hint as to why."""
    makefile = (ENGINE / "Makefile").read_text(encoding="utf-8")
    phony = next(line for line in makefile.splitlines() if line.startswith(".PHONY:"))
    assert " daemon " in phony or phony.endswith(" daemon"), "make daemon would be a no-op next to daemon/"


def test_the_daemon_does_not_import_the_engine():
    """The whole reason it can be a single-file installer. The engine's venv is ~1.7 GB across ~394 packages; one
    import of `nucleo`, `server` or `widgets` and the onefile build stops existing.

    Scanned rather than asserted on one file: the point is that NO module in the package acquires the dependency,
    including ones written later."""
    engine_packages = ("nucleo", "server", "widgets", "voice", "memory", "connectors", "observability", "bus")
    offenders = []
    for py in (ENGINE / "daemon").rglob("*.py"):
        for i, line in enumerate(py.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.strip()
            if not stripped.startswith(("import ", "from ")):
                continue
            for pkg in engine_packages:
                if stripped.startswith((f"import {pkg}", f"from {pkg}")):
                    offenders.append(f"{py.name}:{i} {stripped}")
    assert not offenders, f"the daemon imports the engine, so it can no longer be packaged alone: {offenders}"


def test_the_engine_does_not_import_the_daemon_either():
    """The OTHER direction, and it is the one that keeps the cloud image safe.

    `daemon` is deliberately excluded from the Dockerfile (it runs on the user's computer; a container has no
    window to open and no user files to read). That exclusion is only safe while nothing the Machine boots
    imports it — one `import daemon` in `server/` and the image builds perfectly and crash-loops on startup with
    `ModuleNotFoundError`, which is the exact failure `test_docker_boot_copy.py` was written for.

    The engine talks to the daemon over loopback HTTP, never by import — so this stays true when the engine's
    `/api/daemon/*` proxy arrives."""
    offenders = []
    for pkg in ("server", "nucleo", "voice", "memory", "widgets", "connectors", "observability", "bus"):
        for py in (ENGINE / pkg).rglob("*.py"):
            for i, line in enumerate(py.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                stripped = line.strip()
                if stripped.startswith(("import daemon", "from daemon")):
                    offenders.append(f"{py.relative_to(ENGINE)}:{i} {stripped}")
    assert not offenders, (
        "the engine imports the daemon, which is NOT in the cloud image — the Machine would crash-loop at boot: "
        f"{offenders}"
    )


def test_the_daemon_has_no_third_party_dependencies_in_p0():
    """P0 is standard library only, and `requirements.txt` says so. This is what makes `python -m daemon` run on a
    bare Python 3.11+ with nothing installed — verified by actually running it that way, and kept honest here."""
    reqs = (ENGINE / "daemon" / "requirements.txt").read_text(encoding="utf-8")
    lines = [ln.strip() for ln in reqs.splitlines() if ln.strip() and not ln.strip().startswith("#")]
    assert lines == [], f"the daemon grew a dependency without a decision: {lines}"
