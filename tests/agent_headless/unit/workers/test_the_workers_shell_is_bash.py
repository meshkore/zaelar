"""The worker's Bash tool runs in bash, never the operator's zsh (demo run, 2026-09-26).

`nav_cli goto https://www.amazon.com/s?k=27+inch+4k+monitor` failed with «(eval):1: no matches found» — zsh aborts
a command whose unquoted `?` matches no file; bash passes the word through. A worker that loses a step to its
host's shell options is a RESOURCE failure, not a reasoning one."""
import pytest

from nucleo.workers.providers import claude as cs


def test_bash_wins_over_zsh():
    assert cs.worker_shell("/bin/zsh").endswith("/bash")


@pytest.mark.parametrize("kind", ["generic", "dev"])
def test_every_worker_env_gets_it_after_the_dev_allowlist(monkeypatch, kind):
    """At the spawn: bash for every worker, the DEV one included — set after its allowlist, or it would get the
    operator's shell back (or none)."""
    from nucleo.workers.base import WorkerSpec
    from tests.agent_headless.unit.workers.claude_spawn import spawn_of
    env = spawn_of(monkeypatch, spec=WorkerSpec(task_id="t-sh", kind=kind), host_env={"SHELL": "/bin/zsh"})["env"]
    assert env["SHELL"].endswith("/bash"), env.get("SHELL")
