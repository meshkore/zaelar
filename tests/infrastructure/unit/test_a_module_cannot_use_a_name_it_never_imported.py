"""A name used while a module is IMPORTED must exist by then — or the module is dead on arrival.

MEASURED IN PRODUCTION, 2026-09-02. `widgets/instances.py` called `_re.compile(...)` at module level with no
`import re as _re` anywhere in the file. `python -m compileall` is happy (it is valid syntax), the tests were
green (the working tree had the import, the tagged commit did not), and the release shipped it.

It did not crash anything, which is the part worth writing down. All three callers wrap the import in
`try/except Exception` with a deliberate fail-soft fallback, so what actually happened is that three shipped
behaviours quietly stopped existing:

  · V2-259 F3 / V2-530 — «cierra los resultados» with two sheets open stopped ASKING which one and went back
    to closing the base id;
  · V2-300 — «enséñamelo» with a live instance opened the BASE card, empty, next to the full sheet. That is
    the exact symptom measured in round 24 of the guitar corpus, back again and unreported.

Three guards in this repo already say some version of «an absence of error is not an absence of failure».
This one closes the cheapest way to produce one: `compileall` proves a file PARSES, not that importing it
resolves. The check is deliberately narrow — only names loaded while the module body executes (decorators and
default arguments included, function bodies excluded, since those run later and may legitimately rely on names
injected elsewhere). Measured across the eleven shipped packages the day it was written: zero findings, so it
costs nothing and has no exemption list to rot.
"""
from __future__ import annotations

import ast
import builtins
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[3]

#: The packages the Dockerfile ships — the ones whose import failure reaches a user.
SHIPPED = ("nucleo", "memory", "voice", "server", "widgets", "bus", "config",
           "connectors", "observability", "i18n", "update")

_BUILTINS = set(dir(builtins)) | {
    "__name__", "__file__", "__doc__", "__package__", "__spec__", "__loader__",
    "__builtins__", "__path__", "__all__", "__debug__",
}


def _defined_at_module_level(tree: ast.Module) -> set[str]:
    """Everything the module body binds: imports, assignments, defs, loop/with/except targets."""
    out: set[str] = set()
    for top in tree.body:
        nodes = [top] if not isinstance(top, (ast.If, ast.Try, ast.With, ast.For, ast.While)) else ast.walk(top)
        for n in nodes:
            if isinstance(n, ast.Import):
                out |= {(a.asname or a.name.split(".")[0]) for a in n.names}
            elif isinstance(n, ast.ImportFrom):
                out |= {(a.asname or a.name) for a in n.names}
            elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                out.add(n.name)
            elif isinstance(n, ast.Assign):
                for t in n.targets:
                    out |= {x.id for x in ast.walk(t) if isinstance(x, ast.Name)}
            elif isinstance(n, (ast.AnnAssign, ast.AugAssign)):
                out |= {x.id for x in ast.walk(n.target) if isinstance(x, ast.Name)}
            elif isinstance(n, (ast.For, ast.AsyncFor)):
                out |= {x.id for x in ast.walk(n.target) if isinstance(x, ast.Name)}
            elif isinstance(n, (ast.With, ast.AsyncWith)):
                for item in n.items:
                    if item.optional_vars:
                        out |= {x.id for x in ast.walk(item.optional_vars) if isinstance(x, ast.Name)}
            elif isinstance(n, ast.ExceptHandler) and n.name:
                out.add(n.name)
    return out


def _comprehension_targets(tree: ast.Module) -> set[str]:
    out: set[str] = set()
    for n in ast.walk(tree):
        if isinstance(n, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
            for gen in n.generators:
                out |= {x.id for x in ast.walk(gen.target) if isinstance(x, ast.Name)}
    return out


def _loaded_while_importing(tree: ast.Module) -> set[str]:
    """Names read as the module body RUNS. A function body is skipped (it runs later), but its decorators and
    its default arguments are not — those are evaluated at definition time."""
    loads: set[str] = set()

    def collect(node: ast.AST) -> None:
        for x in ast.walk(node):
            if isinstance(x, ast.Name) and isinstance(x.ctx, ast.Load):
                loads.add(x.id)

    def walk(node: ast.AST) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                for dec in getattr(child, "decorator_list", []):
                    collect(dec)
                args = child.args
                for d in list(args.defaults) + [d for d in args.kw_defaults if d is not None]:
                    collect(d)
                continue
            if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Load):
                loads.add(child.id)
            walk(child)

    walk(tree)
    return loads


def _modules() -> list[Path]:
    out: list[Path] = []
    for pkg in SHIPPED:
        for p in sorted((ENGINE / pkg).rglob("*.py")):
            if "__pycache__" not in str(p):
                out.append(p)
    return out


def test_ningun_modulo_usa_un_nombre_que_no_tiene_al_importarse():
    roto: list[str] = []
    for p in _modules():
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except SyntaxError:
            continue  # `compileall` in the release gate owns syntax; this guard owns names
        # `from x import *` makes the defined set unknowable — skip rather than invent a finding.
        if any(isinstance(n, ast.ImportFrom) and any(a.name == "*" for a in n.names) for n in ast.walk(tree)):
            continue
        conocidos = _defined_at_module_level(tree) | _BUILTINS | _comprehension_targets(tree)
        faltan = sorted(_loaded_while_importing(tree) - conocidos)
        if faltan:
            roto.append(f"{p.relative_to(ENGINE)}: {', '.join(faltan)}")
    assert not roto, (
        "módulos que usan un nombre que NO existe cuando se importan (NameError al import):\n  "
        + "\n  ".join(roto)
        + "\n`compileall` demuestra que el fichero PARSEA, no que importarlo resuelva. Y si quien lo importa "
          "lo envuelve en `except Exception`, no se cae nada: se apaga una funcionalidad en silencio."
    )


def test_el_guarda_ve_el_fallo_que_lo_provocó(tmp_path):
    """The 2026-09-02 shape, verbatim: a module-level regex compiled with an alias nobody imported."""
    m = tmp_path / "roto.py"
    m.write_text("SEP = '::'\n_EVERY_RE = _re.compile(r'x')\n", encoding="utf-8")
    tree = ast.parse(m.read_text(encoding="utf-8"))
    conocidos = _defined_at_module_level(tree) | _BUILTINS | _comprehension_targets(tree)
    assert "_re" in (_loaded_while_importing(tree) - conocidos)


def test_el_guarda_no_se_inventa_hallazgos(tmp_path):
    """The shapes that are FINE and would make a naive checker unusable: a name used only inside a function
    body (it runs later), a comprehension target, a builtin, and a conditional import."""
    m = tmp_path / "sano.py"
    m.write_text(
        "import re\n"
        "try:\n"
        "    import ujson as _json\n"
        "except ImportError:\n"
        "    import json as _json\n"
        "PAIRS = [n for n in range(10)]\n"
        "TABLE = {k: len(str(k)) for k in PAIRS}\n"
        "def later():\n"
        "    return _json.dumps(re.escape(HELPER_DEFINED_ELSEWHERE))\n",
        encoding="utf-8")
    tree = ast.parse(m.read_text(encoding="utf-8"))
    conocidos = _defined_at_module_level(tree) | _BUILTINS | _comprehension_targets(tree)
    assert not (_loaded_while_importing(tree) - conocidos)
