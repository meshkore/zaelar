#
# dev_worker_guard.py — jail of filesystem REAL for the dev-worker (V2-076, auditoria 2026-07-26, cierre of the
# hallazgo P0 residual "the containment al cwd temporary es only convencion of prompt").
#
# Claude Code YA restringe Write/Edit al cwd+subcarpetas by defecto (frontera of working-directory of the own
# CLI), but Read/Glob/Grep NO have esa frontera — a dev-worker could read secretos outside of su cwd (.env,
# config/*.json, memory/_data/zaelar.db) and, if the permission 'code' of the cluster incluye a repo authorized, filtrarlos
# escribiendolos DENTRO of the own workdir and comiteandolos al repo (nucleo/git_cli.py already re-verifica that the repo
# sea the authorized, but eso no impedia the LECTURA inicial of the secreto).
#
# Este module es a hook PreToolUse (https://code.claude.com/docs/in/agent-sdk/hooks.md): Claude Code it invoca
# como subproceso ANTES of ejecutar Read/Write/Edit/MultiEdit/Glob/Grep/NotebookEdit, with the tool_use in JSON by
# stdin; if the path resuelto cae FUERA of `ZAELAR_DEV_WORKER_ROOT` (env, fijado by dispatch.py al crear the
# workdir), deniega with `permissionDecision:"deny"`. Se invoca via `--settings <path a write_settings_file()>`.
#
# FAIL-OPEN by diseno (same patron that susurro/homeostasis/websearch in this repo): any failure of ESTE
# guard (JSON malformado, env no puesto, excepcion) NUNCA must poder tumbar a worker legitimo — a bug here
# allows, no bloquea. Es defensa in profundidad sobre the frontera nativa of the CLI, no the only control.
#
from __future__ import annotations

import json
import os
import sys

# What tools have a field of path and CUÁL — conservative: only is comprueban these; any another tool (incluida
# Bash, already acotada by --allowedTools a only `nucleo.git_cli`) pasa without touch.
_PATH_FIELDS = {
    "Read": ("file_path",),
    "Write": ("file_path",),
    "Edit": ("file_path",),
    "MultiEdit": ("file_path",),
    "NotebookEdit": ("notebook_path",),
    "Glob": ("path",),
    "Grep": ("path",),
}

_ROOT_ENV = "ZAELAR_DEV_WORKER_ROOT"


def _allow() -> None:
    print(json.dumps({}))


def _deny(path: str, root: str) -> None:
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": (
                f"zaelar dev-worker: acceso a '{path}' fuera del directorio de trabajo autorizado ('{root}') "
                "— denegado por el guard de confinamiento (auditoría 2026-07-26)."),
        }
    }))


def _within(resolved: str, root: str) -> bool:
    return resolved == root or resolved.startswith(root + os.sep)


def check(payload: dict) -> bool:
    """True if the tool/path of the payload PreToolUse esta allowed. Puro/testeable without stdin real."""
    root = os.environ.get(_ROOT_ENV, "")
    if not root:
        return True    # sin root configurado (p.ej. worker que no es 'dev') → no es este guard quien decide
    root = os.path.realpath(root)
    tool = str(payload.get("tool_name") or "")
    fields = _PATH_FIELDS.get(tool)
    if not fields:
        return True
    tool_input = payload.get("tool_input") or {}
    cwd = payload.get("cwd") or root
    for f in fields:
        raw = tool_input.get(f)
        if not raw:
            continue
        candidate = raw if os.path.isabs(raw) else os.path.join(cwd, raw)
        if not _within(os.path.realpath(candidate), root):
            return False
    return True


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        if check(payload):
            _allow()
            return 0
        tool_input = payload.get("tool_input") or {}
        fields = _PATH_FIELDS.get(str(payload.get("tool_name") or ""), ())
        bad = next((tool_input.get(f) for f in fields if tool_input.get(f)), "?")
        _deny(str(bad), os.path.realpath(os.environ.get(_ROOT_ENV, "")))
        return 0
    except Exception:
        _allow()   # fail-open: un bug de ESTE guard nunca debe tumbar al worker
        return 0


# ── construction of the --settings <path> that activa the hook ──────────────────────────────────────────────────────
# (the import `nucleo.dev_worker_guard` of the hook resuelve because dispatch.py already pone PYTHONPATH=engine root in the
# env of the proceso — heredado by the subproceso of the hook, no does missing repetirlo here.)


def settings_dict(python_exe: str | None = None) -> dict:
    python_exe = python_exe or sys.executable
    cmd = f'{python_exe} -m nucleo.dev_worker_guard'
    matcher = "Read|Write|Edit|MultiEdit|Glob|Grep|NotebookEdit"
    return {"hooks": {"PreToolUse": [{"matcher": matcher, "hooks": [{"type": "command", "command": cmd}]}]}}


def write_settings_file(path: str, *, python_exe: str | None = None) -> str:
    """Escribe the settings.json of the guard in `path` (file, NO inside of the workdir of the worker — evita that the
    own worker pueda tocarlo) and returns `path`. Idempotente/determinista, without state."""
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(settings_dict(python_exe=python_exe), fh)
    return path


if __name__ == "__main__":
    sys.exit(main())
