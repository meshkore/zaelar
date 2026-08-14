#!/usr/bin/env python3
"""Find likely Spanish comments and docstrings in the public engine source tree.

This is a review aid, not a translator. Every reported match must be classified as
an internal comment/docstring, intentional runtime text, or a false positive.
"""

from __future__ import annotations

import argparse
import ast
import io
import re
import tokenize
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXTENSIONS = {".py", ".js", ".ts", ".css", ".html", ".md", ".yaml", ".yml"}
SKIP_PARTS = {".git", ".venv", "node_modules", "vendor", "frontend/vad"}
SPANISH = re.compile(
    r"(?:[áéíóúñ¿¡]|\b(?:para|desde|sobre|cuando|cómo|como|más|menos|solo|usuario|mensaje|"
    r"tiempo|música|buscar|búsqueda|clima|advertencia|peligro|contraseña|archivo|"
    r"carpeta|trabajo|agente|tarea|ejecutar|código|fuente|instrucción|requiere|debe|puede|"
    r"también|aquí|conectar|conexión|falló|éxito|inválido|válido)\b)", re.IGNORECASE
)


def excluded(path: Path) -> bool:
    text = path.as_posix()
    return any(part in text for part in SKIP_PARTS)


def python_comments(path: Path):
    source = path.read_text(encoding="utf-8", errors="replace")
    try:
        tokens = tokenize.generate_tokens(io.StringIO(source).readline)
        for token in tokens:
            if token.type == tokenize.COMMENT and SPANISH.search(token.string):
                yield token.start[0], token.string.strip(), "comment"

        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                text = ast.get_docstring(node, clean=False)
                if text and SPANISH.search(text):
                    yield getattr(node, "lineno", 1), text.splitlines()[0].strip(), "docstring"
    except (tokenize.TokenError, IndentationError):
        return


def generic_comments(path: Path):
    for number, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith(("//", "/*", "*", "<!--", "#", "---")) and SPANISH.search(stripped):
            yield number, stripped, "comment"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="*", type=Path, help="Files or directories relative to engine/")
    args = parser.parse_args()
    roots = args.paths or [ROOT]
    files = []
    for item in roots:
        path = item if item.is_absolute() else ROOT / item
        if path.is_file() and path.suffix in EXTENSIONS:
            files.append(path)
        elif path.is_dir():
            files.extend(p for p in path.rglob("*") if p.is_file() and p.suffix in EXTENSIONS and not excluded(p))
    for path in sorted(set(files)):
        matches = python_comments(path) if path.suffix == ".py" else generic_comments(path)
        for line, text, kind in matches:
            print(f"{path.relative_to(ROOT)}:{line}: {kind}: {text}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
