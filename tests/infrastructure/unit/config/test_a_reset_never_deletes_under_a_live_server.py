"""The reset stops the server FOR REAL before it deletes the database — or deletes nothing.

Measured 2026-09-27: `reset-memory.sh` sent one SIGTERM, slept 2 s and deleted `zaelar.db`. The server ignored the
TERM; the same PID kept answering on a database that no longer existed on disk (`sqlite3` could not even open the
path). Tested by TEXT: running this script in a test would delete the operator's real memory.
"""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[4]
SCRIPT = (ROOT / "scripts/reset-memory.sh").read_text(encoding="utf-8")


def _stop_block() -> str:
    i = SCRIPT.index("# 1) stop the server")
    j = SCRIPT.index("# 2) delete observability")
    return SCRIPT[i:j]


def test_the_stop_waits_for_the_port_and_escalates():
    block = _stop_block()
    assert "kill -9" in block, "a server that ignores SIGTERM has to be forced"
    assert re.search(r"for _ in \$\(seq", block), "the stop has to WAIT for the port, not sleep a fixed time"


def test_nothing_is_deleted_while_the_server_still_listens():
    block = _stop_block()
    tail = block[block.rindex("kill -9"):]
    assert "exit 1" in tail, "if the port is still held after forcing, the script must stop before deleting"
    assert SCRIPT.index("exit 1", SCRIPT.index("# 1) stop the server")) < SCRIPT.index("# 2) delete observability")
