"""A process the engine spawned is a worker — even orphaned (2026-10-14).

`server/peer_process.classify` is what the operator gate trusts instead of headers a `curl` can forge. Measured
with real processes, this test process playing the engine: its child is a WORKER; a process orphaned out of a
session a worker opened (`( curl … & )`, reparented to launchd/init, so ancestry no longer shows it) is still a
WORKER by its session id; a process carrying a worker's environment markers is a WORKER; its own parent (the
shell that started the suite — his terminal, for all it can tell) is OUTSIDE; the engine itself is SELF; a pid
that is gone is UNKNOWN.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time

import pytest

from server import peer_process as P

pytestmark = pytest.mark.skipif(not hasattr(os, "getsid"), reason="POSIX sessions")

_SLEEPER = "import os,sys,time; open(sys.argv[1],'w').write(str(os.getpid())); time.sleep(20)"


def _orphan(tmp_path, *, new_session: bool, env: dict | None = None) -> tuple[int, int]:
    """(leader_pid, orphan_pid): a shell that backgrounds a python sleeper in a subshell and exits at once."""
    pidfile = tmp_path / f"pid-{time.monotonic_ns()}"
    cmd = f'( "{sys.executable}" -c "{_SLEEPER}" "{pidfile}" & )'
    leader = subprocess.Popen(["/bin/sh", "-c", cmd], start_new_session=new_session,
                              env={**os.environ, **(env or {})})
    leader.wait(timeout=10)
    from tests.waiting import until_sync
    until_sync(lambda: pidfile.exists() and pidfile.read_text().strip(), "the sleeper writing its pid", timeout_s=4)
    return leader.pid, int(pidfile.read_text())


def _kill(pid):
    try:
        os.kill(pid, 9)
    except ProcessLookupError:
        pass


def test_a_child_of_the_engine_is_a_worker():
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(20)"])
    try:
        assert P.classify(child.pid, engine_pid=os.getpid(), worker_sids=frozenset()) == P.WORKER
    finally:
        child.kill()
        child.wait()


def test_an_orphan_of_a_worker_session_is_still_a_worker(tmp_path):
    leader, orphan = _orphan(tmp_path, new_session=True)
    try:
        import psutil
        assert os.getpid() not in {a.pid for a in psutil.Process(orphan).parents()}, \
            "precondition: the orphan's ancestry no longer names the engine"
        assert P.classify(orphan, engine_pid=os.getpid(), worker_sids=frozenset({leader})) == P.WORKER
        assert P.classify(orphan, engine_pid=os.getpid(), worker_sids=frozenset()) == P.OUTSIDE, \
            "without the remembered session nothing else gives it away (the env check is the last net)"
    finally:
        _kill(orphan)


def test_a_worker_environment_is_a_worker(tmp_path):
    _leader, orphan = _orphan(tmp_path, new_session=False, env={"ZAELAR_TASK_TOKEN": "t"})
    try:
        assert P.classify(orphan, engine_pid=os.getpid(), worker_sids=frozenset()) == P.WORKER
    finally:
        _kill(orphan)


def test_his_side_of_the_machine_is_outside_and_the_engine_is_self():
    assert P.classify(os.getppid(), engine_pid=os.getpid(), worker_sids=frozenset()) == P.OUTSIDE
    assert P.classify(os.getpid(), engine_pid=os.getpid(), worker_sids=frozenset()) == P.SELF


def test_a_pid_that_is_gone_or_absent_is_unknown():
    gone = subprocess.Popen([sys.executable, "-c", "pass"])
    gone.wait()
    assert P.classify(gone.pid, engine_pid=os.getpid(), worker_sids=frozenset()) == P.UNKNOWN
    assert P.classify(None, engine_pid=os.getpid(), worker_sids=frozenset()) == P.UNKNOWN


def test_a_process_whose_socket_vanishes_mid_scan_does_not_abort_the_lookup(monkeypatch):
    """use cases (2026-10-14, sandbox 113639-en): one process raised OSError ENOTSOCK while its socket closed; the
    whole lookup failed, the gate answered UNKNOWN and the harness's own turn (POST /api/flash/say) was refused."""
    import psutil
    from server import peer_process

    class _Gone:
        pid = 1
        def uids(self):
            raise OSError(38, "Socket operation on non-socket")
    monkeypatch.setattr(psutil, "net_connections", lambda kind="tcp": (_ for _ in ()).throw(psutil.AccessDenied()))
    monkeypatch.setattr(psutil, "process_iter", lambda: iter([_Gone()]))
    assert peer_process.find_pid("127.0.0.1", 50000, 43921) is None
