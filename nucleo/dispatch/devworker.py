"""nucleo/dispatch/devworker.py — the confined DEV WORKER parameter/prompt builders for cluster-originated
escalations with code permission (split out of dispatch.py, 2026-08-17 modularization pass). Low coupling: no
session/pool state touched, only 3 internal call sites in dispatch.py (all module-qualified or by-name
imports, both preserved via re-export here).

V2-076: a cluster peer conversation escalation arrives with trusted=False (never inherits the operator's trust)
but, if the operator granted `code` to that cluster, it must still be able to WRITE code and PUSH it to the
authorized repo — nothing else. Instead of the binary `_tools_for(trusted)`, this mounts a worker with an EXACT
scope: Read/Write/Edit confined to a TEMPORARY directory (never the project itself — write isolation); git ONLY
through the `nucleo.cli.git` bridge (never bare Bash git) and ONLY to the authorized repo
(ZAELAR_ALLOWED_REPO); no memory bridges (ZAELAR_NO_BRIDGE_TOOLS) — a cluster dev never reads/writes the
operator's memory; PYTHONPATH set to the engine root so the bridge is importable from the temp cwd."""
from __future__ import annotations

import os

# ── THE BOUNDED DEV WORKER (V2-076): an escalation born in a cluster with `code` permission. It arrives untrusted,
# so it gets a worker of exactly that reach: Read/Write/Edit in a temp cwd, git only through `nucleo.cli.git` to the
# authorised repo (ZAELAR_ALLOWED_REPO), no memory bridges (ZAELAR_NO_BRIDGE_TOOLS), and the engine on PYTHONPATH.
_ENGINE_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # nucleo/dispatch/ → engine
def _git_tools() -> list[str]:
    """Mismo criterion that the bridges of `claude_session._BRIDGE_TOOLS`: TODAS the ways of write the interprete,
    for that the dev worker no is quede pidiendo a aprobacion that in headless nadie va a dar."""
    try:
        from nucleo.workers.providers.claude import _INTERPRETERS
        return [f"Bash({py} -m nucleo.cli.git:*)" for py in _INTERPRETERS]
    except Exception:
        return ["Bash(python -m nucleo.cli.git:*)", "Bash(.venv/bin/python -m nucleo.cli.git:*)"]


_DEV_TOOLS = ["Read", "Write", "Edit", *_git_tools()]


def _dev_worker_params(context: dict) -> dict | None:
    """If the contexto of escalada pide a dev worker (V2-076: `dev` + `repo` authorized), returns sus parametros
    ACOTADOS; if no, None (worker normal). Puro/testeable."""
    ctx = context or {}
    if not (ctx.get("dev") and ctx.get("repo")):
        return None
    repo = str(ctx.get("repo"))
    return {
        "tools": list(_DEV_TOOLS),
        "repo": repo,
        "env": {"ZAELAR_NO_BRIDGE_TOOLS": "1", "ZAELAR_ALLOWED_REPO": repo, "PYTHONPATH": _ENGINE_ROOT},
    }


def _dev_prompt(req: str, repo: str) -> str:
    return (
        "Eres un worker de DESARROLLO en una colaboración de código AUTORIZADA por el operador. Trabajas en el "
        "DIRECTORIO ACTUAL (una carpeta temporal AISLADA) — NO escribas ni leas fuera de ella.\n"
        f"Repo autorizado: {repo} (es el ÚNICO que puedes tocar).\n"
        "Flujo:\n"
        "1. Clónalo:  python -m nucleo.cli.git clone repo   (queda en ./repo)\n"
        "2. Escribe/edita el código dentro de ./repo con Read/Write/Edit.\n"
        "3. Commit + push:  python -m nucleo.cli.git commit repo -m \"<mensaje>\"  y luego  python -m nucleo.cli.git push repo\n"
        "NO tienes acceso a la memoria del operador, a otros repos, ni a Bash abierto (solo el puente cli.git). "
        "Si algo requiere más permisos, dilo y termina — no lo fuerces.\n\n"
        f"TAREA: {req}")

