"""The worker's Bash tool runs in bash, never the operator's zsh (demo run, 2026-09-26).

`nav_cli goto https://www.amazon.com/s?k=27+inch+4k+monitor` failed with «(eval):1: no matches found» — zsh aborts
a command whose unquoted `?` matches no file; bash passes the word through. A worker that loses a step to its
host's shell options is a RESOURCE failure, not a reasoning one."""
import pathlib
import re

from nucleo.workers import claude_session as cs


def test_bash_wins_over_zsh():
    assert cs.worker_shell("/bin/zsh").endswith("/bash")


def test_every_worker_env_gets_it_after_the_dev_allowlist():
    src = (pathlib.Path(__file__).resolve().parents[4] / "nucleo/workers/claude_session.py").read_text("utf-8")
    assert re.search(r"env = _dev_env_allowlist\(env\)\n\s+env\[\"SHELL\"\] = worker_shell\(", src), \
        "set AFTER the dev allowlist, or a dev worker would get the operator's shell back"
