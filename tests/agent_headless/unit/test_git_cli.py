#
# Scoped git bridge (V2-076). Run: .venv/bin/pytest tests/agent_headless/unit/test_git_cli.py -q
#
# The security CRITICAL: the dev worker (which may serve an agent-to-agent conversation) can only touch the repo
# AUTHORIZED by the operator; any other repo or absence of authorization is REJECTED. The guards are tested
# without network access (they do not actually clone).
#
from nucleo import git_cli


class _NS:
    def __init__(self, **kw): self.__dict__.update(kw)


def test_clone_refused_without_authorized_repo(monkeypatch, tmp_path):
    monkeypatch.delenv("ZAELAR_ALLOWED_REPO", raising=False)
    called = {"run": False}
    monkeypatch.setattr(git_cli, "_run", lambda *a, **k: called.__setitem__("run", True) or 0)
    rc = git_cli.cmd_clone(_NS(dir=str(tmp_path / "wd"), repo=""))
    assert rc == 2 and called["run"] is False            # without an authorized repo → does NOT execute git


def test_clone_refuses_non_allowlisted_repo(monkeypatch, tmp_path):
    monkeypatch.setenv("ZAELAR_ALLOWED_REPO", "meshkore/algo")
    called = {"run": False}
    monkeypatch.setattr(git_cli, "_run", lambda *a, **k: called.__setitem__("run", True) or 0)
    rc = git_cli.cmd_clone(_NS(dir=str(tmp_path / "wd"), repo="atacante/otro-repo"))
    assert rc == 2 and called["run"] is False            # repo different from the authorized one → REJECTED


def test_clone_allows_authorized_repo(monkeypatch, tmp_path):
    monkeypatch.setenv("ZAELAR_ALLOWED_REPO", "meshkore/algo")
    seen = {}
    monkeypatch.setattr(git_cli, "_run", lambda args, cwd=None: seen.__setitem__("args", args) or 0)
    rc = git_cli.cmd_clone(_NS(dir=str(tmp_path / "wd"), repo="meshkore/algo"))
    assert rc == 0 and "git" in seen["args"][0] and "meshkore/algo" in " ".join(seen["args"])


def test_push_refused_without_authorized_repo(monkeypatch, tmp_path):
    monkeypatch.delenv("ZAELAR_ALLOWED_REPO", raising=False)
    monkeypatch.setattr(git_cli, "_run", lambda *a, **k: 0)
    assert git_cli.cmd_push(_NS(dir=str(tmp_path))) == 2


def test_commit_refuses_non_git_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(git_cli, "_run", lambda *a, **k: 0)
    assert git_cli.cmd_commit(_NS(dir=str(tmp_path), message="x")) == 2   # there is no .git → fails cleanly


# --- P0 finding (audit 2026-07-26): commit/push must RE-VERIFY the actual origin, not merely that .git exists ---

def test_commit_refuses_dir_with_wrong_origin(monkeypatch, tmp_path):
    """The critical case: `dir` IS a git repo (e.g. a clone of ANOTHER repo, or the engine's own repo), but its
    `origin` is NOT the authorized one — previously it was accepted by merely checking that `.git` existed."""
    monkeypatch.setenv("ZAELAR_ALLOWED_REPO", "meshkore/algo")
    (tmp_path / ".git").mkdir()
    monkeypatch.setattr(git_cli, "_origin_url", lambda d: "https://github.com/atacante/otro.git")
    called = {"run": False}
    monkeypatch.setattr(git_cli, "_run", lambda *a, **k: called.__setitem__("run", True) or 0)
    rc = git_cli.cmd_commit(_NS(dir=str(tmp_path), message="x"))
    assert rc == 2 and called["run"] is False


def test_push_refuses_dir_with_wrong_origin(monkeypatch, tmp_path):
    monkeypatch.setenv("ZAELAR_ALLOWED_REPO", "meshkore/algo")
    (tmp_path / ".git").mkdir()
    monkeypatch.setattr(git_cli, "_origin_url", lambda d: "")   # origin rewritten/absent
    called = {"run": False}
    monkeypatch.setattr(git_cli, "_run", lambda *a, **k: called.__setitem__("run", True) or 0)
    rc = git_cli.cmd_push(_NS(dir=str(tmp_path)))
    assert rc == 2 and called["run"] is False


def test_commit_and_push_allowed_with_matching_origin(monkeypatch, tmp_path):
    monkeypatch.setenv("ZAELAR_ALLOWED_REPO", "meshkore/algo")
    (tmp_path / ".git").mkdir()
    monkeypatch.setattr(git_cli, "_origin_url", lambda d: "https://github.com/meshkore/algo.git")
    seen = []
    monkeypatch.setattr(git_cli, "_run", lambda args, cwd=None: seen.append(args) or 0)
    assert git_cli.cmd_commit(_NS(dir=str(tmp_path), message="x")) == 0
    assert git_cli.cmd_push(_NS(dir=str(tmp_path))) == 0
    assert any("push" in a for a in seen)
