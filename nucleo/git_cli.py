#
# git_cli.py — PUENTE git ACOTADO para el dev worker (V2-076). Mismo patrón que los demás puentes CLI (mem_cli,
# nav_cli, widget_cli): un worker NUNCA usa `Bash(git:*)` pelado (git escapa a ejecución arbitraria por hooks,
# aliases o `git -c core.sshCommand=…`). En su lugar el worker llama a ESTE CLI, que solo expone operaciones
# seguras y REFUSA cualquier repo que no sea el AUTORIZADO por el operador (`ZAELAR_ALLOWED_REPO`, inyectado por
# `dispatch` desde el perfil de permisos del cluster). Así una escalada de una charla agente-agente solo puede
# tocar el repo del experimento, jamás otro repositorio ni el sistema.
#
# Operaciones: clone (del repo autorizado a un dir de trabajo), commit, push. Nada más — ni remote add arbitrario,
# ni config, ni fetch de otros orígenes. El repo autorizado se resuelve por `gh` (respeta la auth del host).
#
from __future__ import annotations

import argparse
import os
import subprocess
import sys

_ALLOWED_ENV = "ZAELAR_ALLOWED_REPO"   # p.ej. "meshkore/zalo-zaelar-trading-algo-experiment"


def _allowed_repo() -> str:
    return (os.getenv(_ALLOWED_ENV) or "").strip()


def _fail(msg: str) -> int:
    print(f"git_cli: {msg}", file=sys.stderr)
    return 2


def _run(args: list[str], cwd: str | None = None) -> int:
    """Ejecuta git con timeout y sin heredar prompts interactivos. Devuelve el returncode; imprime salida."""
    env = dict(os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0"       # nunca pedir credenciales por tty (falla limpio si no hay auth)
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
    """URL real del remote `origin` de `dir` (o "" si no tiene/no es un repo). Sin timeout largo — solo lee config
    local, no toca red."""
    try:
        p = subprocess.run(["git", "-C", dir, "remote", "get-url", "origin"],
                            capture_output=True, text=True, timeout=10)
    except Exception:
        return ""
    return (p.stdout or "").strip()


def _verify_authorized_dir(dir: str, repo: str) -> str:
    """'' si `dir` es realmente un clon del repo AUTORIZADO (origin coincide); si no, el motivo del rechazo.

    CRÍTICO (auditoría 2026-07-26, hallazgo P0): antes de este check, `commit`/`push` solo comprobaban que
    `dir/.git` existiera — nunca que su `origin` REAL fuera el repo autorizado. Un worker podía apuntar `dir` a
    CUALQUIER repo git (incluido el propio repo del motor, o uno cuyo `origin` se hubiera reescrito tras el clone)
    y `commit`/`push` lo aceptaban sin más. Esto revalida el vínculo en cada operación, no solo en el `clone`.
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
    # push SOLO al origin (RE-VERIFICADO arriba en cada llamada, no solo al clonar); no se admite un remoto arbitrario.
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
