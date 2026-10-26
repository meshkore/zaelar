"""A use-case sandbox calls the models with the operator's keys, and gives them back when it stops (2026-10-27).

Since 2026-10-26 the server reads the credential store the writer uses (`config.credentials.STORE`), which follows
`ZAELAR_WORKSPACE`. A sandbox has its own workspace, so it read an EMPTY store: every provider key resolved to its
«local» sentinel, DeepSeek answered 401 («your api key ****ocal is invalid») and every use-case round of that day
measured the relay model instead of the product — green or red for the wrong reason. The sandbox's contract was
always «a clean DATABASE, not a crippled engine»; it now lends its store the operator's keys and takes them back.

No engine is started: `Popen` is faked, and the store path the child would read is asked of a real interpreter.
"""
from __future__ import annotations

import os
import stat
import subprocess
import sys
from pathlib import Path

from tests.platform import sandbox_engine as SE


class _FakeProc:
    returncode = None

    def poll(self):
        return None

    def terminate(self):
        pass

    def wait(self, *a, **k):
        pass

    def kill(self):
        pass


def _store(tmp_path) -> Path:
    p = tmp_path / "operator" / "zaelar.env"
    p.parent.mkdir(parents=True)
    p.write_text("DEEPSEEK_API_KEY=sk-test-not-a-real-key\n", encoding="utf-8")
    return p


def test_the_store_the_sandbox_reads_holds_his_keys_and_is_private(monkeypatch, tmp_path):
    ws = tmp_path / "ws"
    # The path the engine inside the sandbox reads its keys from — asked of a real interpreter BEFORE Popen is faked.
    child_store = subprocess.run(
        [sys.executable, "-c", "from config.credentials import STORE; print(STORE)"], cwd=str(SE.ENGINE),
        env={**os.environ, "ZAELAR_WORKSPACE": str(ws)}, capture_output=True, text=True).stdout.strip()
    assert child_store, "could not ask the child which store it reads"
    monkeypatch.setattr(SE, "OPERATOR_STORE", _store(tmp_path))
    monkeypatch.setattr(SE.subprocess, "Popen", lambda argv, **kw: _FakeProc())
    monkeypatch.setattr(SE, "_wait_ready", lambda eng, timeout: None)
    with SE.sandbox_engine(keep_workspace=ws):
        assert Path(child_store).is_file(), f"the sandbox's engine would read an empty store: {child_store}"
        assert Path(child_store).read_text(encoding="utf-8").startswith("DEEPSEEK_API_KEY=sk-test-"), child_store
        assert stat.S_IMODE(Path(child_store).stat().st_mode) == 0o600
    assert not (ws / "credentials" / "zaelar.env").exists(), "a kept workspace must not keep his keys"


def test_without_a_store_the_sandbox_boots_on_dotenv_alone(monkeypatch, tmp_path):
    monkeypatch.setattr(SE, "OPERATOR_STORE", tmp_path / "missing.env")
    assert SE.lend_credentials(tmp_path / "ws") is None
