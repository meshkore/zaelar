#
# git_cli.py — BOUNDED git BRIDGE for the dev worker (V2-076). Same pattern as the other CLI bridges (mem_cli,
# nav_cli, widget_cli): a worker NEVER uses bare `Bash(git:*)` (git can escape to arbitrary execution through hooks,
# aliases, or `git -c core.sshCommand=…`). Instead, the worker calls THIS CLI, which exposes only
# safe operations and REFUSES any repo that is not AUTHORIZED by the operator (`ZAELAR_ALLOWED_REPO`, injected by
# `dispatch` from the cluster permissions profile). Thus, an escalation from an agent-to-agent conversation can only
# touch the experiment repo, never another repository or the system.
#
# Operations: clone (the authorized repo into a working directory), commit, push. Nothing else — neither arbitrary
# remote add, nor config, nor fetch from other origins. The authorized repo is resolved through `gh` (respects the host's auth).
#
from __future__ import annotations

import argparse
import os
import subprocess
import sys

_ALLOWED_ENV = "ZAELAR_ALLOWED_REPO"   # e.g. "meshkore/zalo-zaelar-trading-algo-experiment"


def _allowed_repo() -> str:
    return (os.getenv(_ALLOWED_ENV) or "").strip()


def _fail(msg: str) -> int:
    print(f"git_cli: {msg}", file=sys.stderr)
    return 2


def _run(args: list[str], cwd: str | None = None) -> int:
    """Runs git with a timeout and without inheriting interactive prompts. Returns the return code; prints output."""
    env = dict(os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0"       # never ask for credentials through the TTY (fails cleanly if there is no auth)
    try:
        p = subprocess.run(args, cwd=cwd, capture_output=True, text=True, env=env, timeout=120)
    except Exception as e:  # noqa: BLE001
        print(f"git_cli: git falló: {type(e).__name__}: {e}", file=sys.stderr)
        return 1
    if p.stdout:
        print(p.stdout.strip())
    if p.stderr:
        print(p.stderr.strip(), file=sys.stderr)
    return p.returncode


def _repo_url(repo: str) -> str:
    return f"https://github.com/{repo}.git"


def _origin_url(dir: str) -> str:
    """Actual URL of the `origin` remote for `dir` (or "" if it has none/is not a repo). No long timeout — only reads
    local config; does not touch the network."""
    try:
        p = subprocess.run(["git", "-C", dir, "remote", "get-url", "origin"],
                            capture_output=True, text=True, timeout=10)
    except Exception:
        return ""
    return (p.stdout or "").strip()


def _verify_authorized_dir(dir: str, repo: str) -> str:
    """'' if `dir` is actually a clone of the AUTHORIZED repo (origin matches); otherwise, the reason for rejection.

    CRITICAL (2026-07-26 audit, P0 finding): before this check, `commit`/`push` only checked that
    `dir/.git` existed — never that its REAL `origin` was the authorized repo. A worker could point `dir` to
    ANY git repo (including the engine's own repo, or one whose `origin` had been rewritten after the clone)
    and `commit`/`push` accepted it without further checks. This revalidates the link on every operation, not only during `clone`.
    """
    if not os.path.isdir(os.path.join(dir, ".git")):
        return f"'{dir}' no es un repo git (clona primero)"
    origin = _origin_url(dir)
    expected = _repo_url(repo)
    if origin != expected:
        return f"'{dir}' NO es un clon del repo autorizado (origin='{origin or '(ninguno)'}', esperado='{expected}')"
    return ""


def cmd_clone(a) -> int:
    repo = _allowed_repo()
    if not repo:
        return _fail(f"no hay repo autorizado ({_ALLOWED_ENV} vacío) — el operador no concedió permiso de repo")
    if a.repo and a.repo != repo:
        return _fail(f"repo '{a.repo}' NO autorizado (solo '{repo}')")
    os.makedirs(a.dir, exist_ok=True)
    return _run(["git", "clone", _repo_url(repo), a.dir])


def cmd_commit(a) -> int:
    repo = _allowed_repo()
    if not repo:
        return _fail(f"no hay repo autorizado ({_ALLOWED_ENV} vacío)")
    err = _verify_authorized_dir(a.dir, repo)
    if err:
        return _fail(err)
    _run(["git", "-C", a.dir, "add", "-A"])
    return _run(["git", "-C", a.dir, "commit", "-m", a.message or "update"])


def cmd_push(a) -> int:
    repo = _allowed_repo()
    if not repo:
        return _fail(f"no hay repo autorizado ({_ALLOWED_ENV} vacío)")
    err = _verify_authorized_dir(a.dir, repo)
    if err:
        return _fail(err)
    # push ONLY to origin (RE-VERIFIED above on every call, not only when cloning); arbitrary remotes are not allowed.
    return _run(["git", "-C", a.dir, "push", "origin", "HEAD"])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="git_cli", description="Puente git acotado al repo autorizado (V2-076).")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("clone"); c.add_argument("dir"); c.add_argument("--repo", default=""); c.set_defaults(fn=cmd_clone)
    c = sub.add_parser("commit"); c.add_argument("dir"); c.add_argument("--message", "-m", default="update"); c.set_defaults(fn=cmd_commit)
    c = sub.add_parser("push"); c.add_argument("dir"); c.set_defaults(fn=cmd_push)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
