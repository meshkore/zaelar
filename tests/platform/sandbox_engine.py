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
    but a spawned subprocess bypasses conftest. `tests/journey/runner.py` does NOT set it today — a real,
    pre-existing leak in that runner, noted here rather than silently fixed in another suite's file.
  · `ZAELAR_ENGINE=off` — skips the embedded LiveKit worker AND the `livekit_api` router
    (`server/__init__.py`, `!= "livekit"`). The probe channel does not need LiveKit at all: `/api/flash/say`
    mounts on `active_brain() == "nucleo"` alone, which is what makes a headless sandbox possible.
  · `ZAELAR_TLS_CERT_DIR` → a nonexistent dir, so the second HTTPS listener (44317) never binds and cannot
    clash with the operator's live engine.

Credentials are deliberately NOT isolated: `server/common.py` loads `.env` + `.meshkore/credentials/` from
the repo root, so the sandbox uses the operator's real API keys. That's intended — the point is a clean
DATABASE, not a crippled engine that can't call a model.

⚠️ Do NOT run `make run` (i.e. `scripts/run-livekit.sh`) while a sandbox is alive: that script reaps every
`python -m server` process by NAME, not by port, so it would kill the sandbox too. The reverse is safe —
starting a sandbox never touches an already-running engine.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[2]
_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@dataclass
class SandboxEngine:
    base_url: str
    workspace: Path
    log_path: Path
    process: subprocess.Popen

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


@contextmanager
def sandbox_engine(*, boot_timeout: float = 90.0, keep_workspace: Path | None = None, extra_env: dict | None = None):
    """Boot an isolated engine, yield a `SandboxEngine`, and tear it down (process + workspace) on exit.

    `boot_timeout` defaults higher than journey's 35s: this engine cold-starts a reranker and an embedding
    backend on a machine that may already be running the operator's engine, and a flaky timeout would look
    exactly like a real failure. `keep_workspace` writes into a caller-owned directory instead of a temp one
    (so a failed run's DB/logs survive for inspection); `extra_env` overrides any var for one-off needs.
    """
    tmp = None
    if keep_workspace is None:
        tmp = tempfile.TemporaryDirectory(prefix="zaelar-sandbox-")
        workspace = Path(tmp.name)
    else:
        workspace = keep_workspace
        workspace.mkdir(parents=True, exist_ok=True)

    port = free_port()
    logs = workspace / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    log_path = logs / "sandbox-engine.log"

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
                            log_path=log_path, process=process)
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
            if tmp is not None:
                tmp.cleanup()
