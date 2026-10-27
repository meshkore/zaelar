"""A disposable engine WITH its voice: the sandbox of `sandbox_engine.py` plus a LiveKit server of its own.

Why it needs its own LiveKit server: the use-case sandbox runs with `ZAELAR_ENGINE=off` (no voice worker), which is
what lets it sit beside the operator's engine. A voice sandbox cannot: its worker must register somewhere, and on the
operator's LiveKit dev server (7880) it would be a SECOND worker — automatic dispatch offers each room to one worker
at a time, so his real sessions could be handed to the throwaway engine and the tester's to his (the split-brain
`scripts/run-livekit.sh` reaps for). So the sandbox starts `livekit-server --dev` on free ports, bound to loopback,
and points its engine (`LIVEKIT_URL`) and the tester (`/api/token` returns that URL) at it. Nothing the operator's
stack listens on is touched.

Everything else is inherited from `spawn_engine`: own workspace, database, logs and engine lock, connectors off,
credentials lent and taken back.

    with voice_sandbox() as eng:
        eng.base_url        # the engine; its /api/token hands out the sandbox's LiveKit URL
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

from tests.platform.sandbox_engine import free_port, spawn_engine, stop_engine

#: The operator's LiveKit dev server port — a voice sandbox must never point at it.
OPERATOR_LIVEKIT_PORT = 7880


def livekit_config(port: int, tcp_port: int, udp_port: int) -> str:
    """The sandbox LiveKit server's config: loopback only, every port its own."""
    return (f"port: {port}\n"
            f"bind_addresses: [\"127.0.0.1\"]\n"
            f"rtc:\n"
            f"  tcp_port: {tcp_port}\n"
            f"  udp_port: {udp_port}\n"
            f"  use_external_ip: false\n"
            f"  node_ip: 127.0.0.1\n")


def voice_env(livekit_port: int) -> dict:
    """What turns a sandbox engine into one with a voice, on ITS LiveKit server. No engine id: with one worker on the
    server automatic dispatch has nothing to choose, and an id would make the engine read as a hosted one."""
    if livekit_port == OPERATOR_LIVEKIT_PORT:
        raise ValueError("a voice sandbox never points at the operator's LiveKit server")
    return {"ZAELAR_ENGINE": "livekit", "LIVEKIT_URL": f"ws://127.0.0.1:{livekit_port}",
            "ZAELAR_USER_ID": "", "FLY_MACHINE_ID": ""}


def seed_language(workspace: Path, lang: str) -> None:
    """A fresh workspace has no language, and with none the agent is STOPPED and `/api/token` refuses the session
    (409). A sandbox has a known language, so it is written where the operator's choice would be."""
    f = workspace / "config" / "settings.json"
    f.parent.mkdir(parents=True, exist_ok=True)
    cur = json.loads(f.read_text()) if f.exists() else {}
    cur["stt_language"] = lang
    f.write_text(json.dumps(cur, ensure_ascii=False, indent=2))


def _wait_port(port: int, proc: subprocess.Popen, timeout: float, log: Path) -> None:
    import socket
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"sandbox livekit-server exited (code {proc.returncode})\n"
                               + log.read_text(errors="replace")[-2000:])
        with socket.socket() as s:
            s.settimeout(0.3)
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return
        time.sleep(0.2)
    raise TimeoutError(f"sandbox livekit-server did not listen on {port} in {timeout}s")


def start_livekit(workspace: Path) -> tuple[subprocess.Popen, int]:
    binary = shutil.which("livekit-server")
    if not binary:
        raise RuntimeError("livekit-server is not installed (`make install-livekit`)")
    port = free_port()
    log = workspace / "logs" / "sandbox-livekit.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("ab") as fh:
        proc = subprocess.Popen([binary, "--dev", "--config-body", livekit_config(port, free_port(), free_port())],
                                stdout=fh, stderr=subprocess.STDOUT, start_new_session=True)
    _wait_port(port, proc, 20.0, log)
    return proc, port


def stop_livekit(proc: subprocess.Popen) -> None:
    proc.terminate()
    try:
        proc.wait(8)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(5)


@contextmanager
def voice_sandbox(*, lang: str = "es", boot_timeout: float = 120.0, keep_workspace: Path | None = None):
    tmp = None if keep_workspace else tempfile.TemporaryDirectory(prefix="zaelar-voice-sandbox-")
    workspace = Path(keep_workspace or tmp.name)
    seed_language(workspace, lang)
    lk, lk_port = start_livekit(workspace)
    eng = None
    try:
        eng = spawn_engine(workspace=workspace, port=free_port(), extra_env=voice_env(lk_port),
                           boot_timeout=boot_timeout)
        eng.livekit_url = f"ws://127.0.0.1:{lk_port}"
        yield eng
    finally:
        if eng is not None:
            stop_engine(eng)
        stop_livekit(lk)
        if tmp is not None:
            tmp.cleanup()
