#
# dev_worker_guard.py — jail de filesystem REAL para el dev-worker (V2-076, auditoría 2026-07-26, cierre del
# hallazgo P0 residual "el confinamiento al cwd temporal es solo convención de prompt").
#
# Claude Code YA restringe Write/Edit al cwd+subcarpetas por defecto (frontera de working-directory del propio
# CLI), pero Read/Glob/Grep NO tienen esa frontera — un dev-worker podía leer secretos fuera de su cwd (.env,
# config/*.json, memory/_data/zaelar.db) y, si el permiso 'code' del cluster incluye un repo autorizado, filtrarlos
# escribiéndolos DENTRO del propio workdir y comiteándolos al repo (nucleo/git_cli.py ya re-verifica que el repo
# sea el autorizado, pero eso no impedía la LECTURA inicial del secreto).
#
# Este módulo es un hook PreToolUse (https://code.claude.com/docs/en/agent-sdk/hooks.md): Claude Code lo invoca
# como subproceso ANTES de ejecutar Read/Write/Edit/MultiEdit/Glob/Grep/NotebookEdit, con el tool_use en JSON por
# stdin; si el path resuelto cae FUERA de `ZAELAR_DEV_WORKER_ROOT` (env, fijado por dispatch.py al crear el
# workdir), deniega con `permissionDecision:"deny"`. Se invoca vía `--settings <path a write_settings_file()>`.
#
# FAIL-OPEN por diseño (mismo patrón que susurro/homeostasis/websearch en este repo): cualquier fallo de ESTE
# guard (JSON malformado, env no puesto, excepción) NUNCA debe poder tumbar un worker legítimo — un bug aquí
# permite, no bloquea. Es defensa en profundidad sobre la frontera nativa del CLI, no el único control.
#
from __future__ import annotations

import json
import os
import sys

# Qué tools tienen un campo de ruta y CUÁL — conservador: solo se comprueban estas; cualquier otra tool (incluida
# Bash, ya acotada por --allowedTools a solo `nucleo.git_cli`) pasa sin tocar.
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
    """True si la tool/ruta del payload PreToolUse está permitida. Puro/testeable sin stdin real."""
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


# ── construcción del --settings <path> que activa el hook ──────────────────────────────────────────────────────
# (el import `nucleo.dev_worker_guard` del hook resuelve porque dispatch.py ya pone PYTHONPATH=engine root en el
# env del proceso — heredado por el subproceso del hook, no hace falta repetirlo aquí.)


def settings_dict(python_exe: str | None = None) -> dict:
    python_exe = python_exe or sys.executable
    cmd = f'{python_exe} -m nucleo.dev_worker_guard'
    matcher = "Read|Write|Edit|MultiEdit|Glob|Grep|NotebookEdit"
    return {"hooks": {"PreToolUse": [{"matcher": matcher, "hooks": [{"type": "command", "command": cmd}]}]}}


def write_settings_file(path: str, *, python_exe: str | None = None) -> str:
    """Escribe el settings.json del guard en `path` (fichero, NO dentro del workdir del worker — evita que el
    propio worker pueda tocarlo) y devuelve `path`. Idempotente/determinista, sin estado."""
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(settings_dict(python_exe=python_exe), fh)
    return path


if __name__ == "__main__":
    sys.exit(main())
