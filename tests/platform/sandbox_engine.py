"""A disposable, fully ISOLATED zaelar engine — own port, own database, own workspace, own logs.

Why this exists as shared infrastructure: `tests/journey/runner.py` had the only implementation of this in
the repo, inlined inside its `run()`, so every other suite that wanted a clean engine had to either
reimplement it or (much worse) run against the operator's live one on 43917 — which means testing against
their real memory, their real widgets, their real cluster tokens, and racing whatever they're doing at that
moment. `tests/platform/` is where cross-suite infrastructure already lives (`cli.py`, `events.py`), so the
context manager goes here and `journey`'s recipe becomes reusable.

Usage:
    from tests.platform.sandbox_engine import sandbox_engine
    with sandbox_engine() as eng:
        eng.base_url            # "http://127.0.0.1:<free port>"
        eng.post("/api/flash/say", {...})

What makes the isolation real (each of these was verified against the code that reads it, not assumed):
  · `ZAELAR_WORKSPACE` is the load-bearing one — `nucleo/workspace.py::root()` feeds it to `widgets/store.py`
    (widget data), `config/{settings,v2,connectors,credentials}.py`, `observability/identity.py`
    (config/identity.json, i.e. the install's user_id) and `connectors/meshkore/store.py` (cluster tokens).
    Several of those compute their paths AT IMPORT TIME, which is exactly why this spawns a SUBPROCESS
    instead of monkeypatching in-process — an env var set after import would already be too late.
  · `ZAELAR_DB` — memory AND the durable bus/`events` log (`memory/db.py`, `bus/log.py`).
  · `ZAELAR_LOG_DIR` — `voice/observer.py`'s LOG_DIR resolves from the REPO ROOT, *not* the workspace, so
    without this an isolated engine appends its events to the operator's real
    `.meshkore/logs/timeline-latest.jsonl`. That is the 2026-07-25 incident (test events mistaken for a live
    session) waiting to happen again; the root `conftest.py` sets this for pytest for precisely that reason,
    but a spawned subprocess bypasses conftest.
    This note used to end "`tests/journey/runner.py` does NOT set it today — a real, pre-existing leak in
    that runner, noted here rather than silently fixed in another suite's file". It stayed true for months,
    which is the lesson: documenting a leak in the module that does NOT have it does not fix it. On
    2026-08-20 journey was ported to this helper and the leak was measured first — 4 steps took the
    operator's timeline from 80 to 243 lines on the old boot, and left it at 80 on this one. Node 7.14
    (`tests/platform/tests/test_sandbox_isolation.py`) now holds the contract, including that journey boots
    through here and not on its own.
  · `ZAELAR_ENGINE=off` — skips the embedded LiveKit worker AND the `livekit_api` router
    (`server/__init__.py`, `!= "livekit"`). The probe channel does not need LiveKit at all: `/api/flash/say`
    mounts on `active_brain() == "nucleo"` alone, which is what makes a headless sandbox possible.
  · `ZAELAR_TLS_CERT_DIR` → a nonexistent dir, so the second HTTPS listener (44317) never binds and cannot
    clash with the operator's live engine.

Credentials are deliberately NOT isolated: `server/common.py` loads `.env` + `.meshkore/credentials/` from
the repo root, so the sandbox uses the operator's real API keys. That's intended — the point is a clean
DATABASE, not a crippled engine that can't call a model.

⚠️ KNOWN LEAK (worked around, not fixed) — generated widget CODE. `widgets/store.py` honours the workspace (widget *data* is
isolated), but `widgets/generator.py` and `widgets/lifecycle.py` write the widget's code to
`HERE/<widget_id>/`, where `HERE` is the real `engine/widgets/` directory — so a sandbox run that generates a
widget leaves a new folder in the operator's repo. Leaving them was measured to CORRUPT later runs, not merely litter the repo:
`build-workout-tracker-widget` PASSED on the run that created its widget and then failed twice, because every
later sandbox found the folder already in the catalog and answered "ya lo tienes — es el widget que ves en
pantalla" about a widget present in no workspace and on no screen (a `MODIFY` where a `CREATE` was expected is
the signature). So teardown now removes the widgets THIS sandbox generated, identified from its own
`widget-agent: CREATE '<id>'` log lines (`own_generated_widgets()`) — never a sweep of everything new, since
the operator's live engine writes to the same directory in the same window and a sweep cannot tell whose widget
is whose. `new_widget_dirs()` still reports anything left over. The proper fix is still making
`widgets/generator.py` and `widgets/lifecycle.py` workspace-aware, which is a product change (a
workspace-relative catalog would also stop the sandbox from seeing the built-in widgets).

⚠️ Do NOT run `make run` (i.e. `scripts/run-livekit.sh`) while a sandbox is alive: that script reaps every
`python -m server` process by NAME, not by port, so it would kill the sandbox too. The reverse is safe —
starting a sandbox never touches an already-running engine.
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import re
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[2]
_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _widget_dirs() -> set[str]:
    wroot = ENGINE / "widgets"
    try:
        return {p.name for p in wroot.iterdir()
                if p.is_dir() and not p.name.startswith(("_", "."))}
    except Exception:
        return set()


@dataclass
class SandboxEngine:
    base_url: str
    workspace: Path
    log_path: Path
    process: subprocess.Popen
    widgets_before: frozenset = frozenset()

    def new_widget_dirs(self) -> list[str]:
        """Widget folders that appeared in the REAL `engine/widgets/` while the sandbox was up — see the
        module docstring's leak note."""
        return sorted(_widget_dirs() - set(self.widgets_before))

    def own_generated_widgets(self) -> list[str]:
        """Of those, the ones THIS sandbox generated — read from its own log, not guessed.

        The distinction is what makes cleanup safe. A blind sweep of "everything new" could delete a widget the
        operator's live engine created in the same window, since both write to the same directory (the leak this
        works around). The sandbox's own `widget-agent: CREATE '<id>'` lines name exactly what it made, so only
        those are ours to remove.
        """
        try:
            log = self.log_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return []
        mine = set(re.findall(r"widget-agent: CREATE '([^']+)'", log))
        return sorted(mine & set(self.new_widget_dirs()))

    def get(self, path: str, *, timeout: float = 15.0) -> tuple[int, object]:
        req = urllib.request.Request(self.base_url + path, headers={"User-Agent": _UA})
        return self._send(req, timeout)

    def post(self, path: str, body: dict, *, timeout: float = 90.0) -> tuple[int, object]:
        req = urllib.request.Request(
            self.base_url + path, data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json", "User-Agent": _UA}, method="POST")
        return self._send(req, timeout)

    @staticmethod
    def _send(req, timeout: float) -> tuple[int, object]:
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read()
                return r.status, json.loads(raw or b"{}")
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            try:
                return exc.code, json.loads(raw or b"{}")
            except json.JSONDecodeError:
                return exc.code, {"error": raw.decode("utf-8", "replace")}

    def log_tail(self, lines: int = 60) -> str:
        if not self.log_path.exists():
            return ""
        return "\n".join(self.log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:])


def _wait_ready(eng: SandboxEngine, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        # Fail FAST and LOUD if the child died — a boot crash must not present as a generic timeout, which
        # is what sends you looking for a network problem that isn't there.
        if eng.process.poll() is not None:
            raise RuntimeError(f"sandbox engine exited during boot (code {eng.process.returncode})\n"
                               f"{eng.log_tail(80)}")
        try:
            status, _ = eng.get("/api/status", timeout=1.5)
            if status == 200:
                return
        except Exception:
            pass
        time.sleep(0.25)
    raise TimeoutError(f"sandbox engine did not answer on {eng.base_url} in {timeout}s\n{eng.log_tail(80)}")


def preferred_port(want: int) -> int:
    """`want` if it's free, otherwise an ephemeral one. A STABLE port matters for a sandbox the operator is
    meant to watch (they can bookmark it), but it must never be a hard requirement — two batches at once, or
    a leftover process, would otherwise fail the boot instead of just moving over."""
    try:
        with socket.socket() as s:
            s.bind(("127.0.0.1", want))
        return want
    except OSError:
        return free_port()


@contextmanager
def sandbox_engine(*, boot_timeout: float = 90.0, keep_workspace: Path | None = None,
                   port: int | None = None, extra_env: dict | None = None,
                   log_path: Path | None = None):
    """Boot an isolated engine, yield a `SandboxEngine`, and tear it down (process + workspace) on exit.

    `boot_timeout` defaults higher than journey's old 35s: this engine cold-starts a reranker and an embedding
    backend on a machine that may already be running the operator's engine, and a flaky timeout would look
    exactly like a real failure. `keep_workspace` writes into a caller-owned directory instead of a temp one
    (so a failed run's DB/logs survive for inspection); `extra_env` overrides any var for one-off needs.

    `log_path` puts the engine's stdout/stderr somewhere the CALLER owns. It matters when the workspace is a
    throwaway: the log is the evidence of a boot crash, and with the default path it dies with the workspace
    at exactly the moment it is most needed. `journey` passes its run's `artifacts/` so a failure survives
    the run (and so the terminal can print a path that still exists when the operator reads it).
    """
    tmp = None
    if keep_workspace is None:
        tmp = tempfile.TemporaryDirectory(prefix="zaelar-sandbox-")
        workspace = Path(tmp.name)
    else:
        workspace = keep_workspace
        workspace.mkdir(parents=True, exist_ok=True)

    port = port or free_port()
    logs = workspace / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    if log_path is None:
        log_path = logs / "sandbox-engine.log"
    else:
        log_path.parent.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env.update({
        "PORT": str(port), "HOST": "127.0.0.1",
        "BRAIN": "nucleo",                 # the probe channel + workers mount on this, not on LiveKit
        "ZAELAR_ENGINE": "off",            # no embedded LiveKit worker, no /api/token
        "ZAELAR_WORKSPACE": str(workspace),
        "ZAELAR_DB": str(workspace / "memory" / "_data" / "sandbox.db"),
        "ZAELAR_LOG_DIR": str(logs),       # keeps the operator's real timeline clean — see module docstring
        "ZAELAR_TLS_CERT_DIR": str(workspace / "no-tls"),
        "ZAELAR_HOMEOSTASIS": "0",         # no engine-recycling/log-rotation watchdog in a throwaway
        "MESHKORE_AUTORECONNECT": "0",     # never dial the operator's real clusters
        "WA_ENABLED": "0", "TG_ENABLED": "0",
    })
    if extra_env:
        env.update({k: str(v) for k, v in extra_env.items()})

    (workspace / "memory" / "_data").mkdir(parents=True, exist_ok=True)

    with log_path.open("wb") as log:
        process = subprocess.Popen([sys.executable, "-m", "server"], cwd=str(ENGINE), env=env,
                                   stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        eng = SandboxEngine(base_url=f"http://127.0.0.1:{port}", workspace=workspace,
                            log_path=log_path, process=process,
                            widgets_before=frozenset(_widget_dirs()))
        try:
            _wait_ready(eng, boot_timeout)
            yield eng
        finally:
            process.terminate()
            try:
                process.wait(12)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(5)
            # Remove the widget CODE this sandbox generated. Not doing so was measured to CORRUPT later runs,
            # not just litter the repo: `build-workout-tracker-widget` passed on the run that created its
            # widget and then failed twice, because every later sandbox found the folder already there and
            # answered "ya lo tienes — es el widget que ves en pantalla" about a widget that was in no
            # workspace and on no screen. A `MODIFY` where a `CREATE` was expected is the signature.
            # Scoped to what THIS sandbox created (`own_generated_widgets`), never a sweep of everything new.
            for wid in eng.own_generated_widgets():
                try:
                    shutil.rmtree(ENGINE / "widgets" / wid)
                    print(f"  ✓ sandbox limpió el widget que generó: widgets/{wid}")
                except Exception as exc:
                    print(f"  ⚠️ no pude limpiar widgets/{wid}: {exc}")
            if tmp is not None:
                tmp.cleanup()
