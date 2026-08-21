"""A route decorator binds to whatever `def` comes next — and it never complains.

Twice now a helper has been inserted BETWEEN a `@router.<verb>(path)` line and the handler it was written for,
so FastAPI registered the HELPER as the endpoint and the real handler became an unreachable module function:

  · 2026-08-20 — `_with_wall` stole `@router.post("/api/navegador/act")`. It takes a dict and returns it
    unchanged, so the bridge answered 200 with the request echoed back and every Brain Worker action turned
    into «ERROR: desconocido».
  · 2026-08-21 (f3052f9, this engine) — `open_instances()` stole `@router.post("/api/canvas/state")`. It takes
    NO payload, so the canvas report was swallowed with a 200: `open_widgets` stopped being written, the V2-039
    audit of what the operator opens by hand went silent, and `_last_inst` was never stamped — which killed the
    very feature the helper had just been added to serve.

Both times every existing test stayed green: a decorator does not care what follows it, and nothing asserted
WHICH function a path resolves to. After the first one a guard was written — for ONE path
(`test_the_bridge_route_still_points_at_the_bridge`). That is why it came back on a different path: the fix
pinned the case instead of closing the class. This closes the class.

The invariant is the SYMPTOM, not the shape: a hijacked decorator always leaves its victim behind as a
module-level `async def` in a route module that no route serves and no code calls. A handler nobody can reach
is never intentional.
"""
import ast
import pathlib
import re

_ROOT = pathlib.Path(__file__).resolve().parents[3]


def _corpus() -> dict[str, str]:
    """Every engine source file, tests excluded: a handler called ONLY from a test is still unreachable in
    production, which is exactly the state this guard exists to reject."""
    out = {}
    for p in _ROOT.rglob("*.py"):
        rel = p.relative_to(_ROOT).as_posix()
        if ".venv" in rel or rel.startswith("tests/"):
            continue
        try:
            out[rel] = p.read_text()
        except Exception:
            continue
    return out


def _is_route(node: ast.AST) -> bool:
    for d in getattr(node, "decorator_list", []):
        f = d.func if isinstance(d, ast.Call) else d
        if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) and f.value.id == "router":
            return True
    return False


def orphan_handlers(path: str, text: str, corpus: dict[str, str]) -> list[tuple[str, int]]:
    """Module-level `async def`s in a route module that carry no route and that nobody calls.

    The `(?<!def )` is load-bearing: without it a function's OWN definition line matches the "somebody calls
    this" probe and every orphan reports itself as used — the guard then passes on the broken tree, which is
    the failure mode a guard must not have. Caught by disarming it against the real defect.
    """
    out = []
    for node in ast.parse(text).body:
        if not isinstance(node, ast.AsyncFunctionDef):
            continue                       # a loose sync helper is ordinary; a loose async HANDLER is not
        if _is_route(node) or node.name.startswith("_"):
            continue
        pat = re.compile(rf"(?<!def ){re.escape(node.name)}\s*\(")
        if any(pat.search(t) for f, t in corpus.items() if f != path):
            continue
        if pat.search(text):
            continue
        out.append((node.name, node.lineno))
    return out


def test_no_route_module_has_a_handler_nobody_can_reach():
    corpus = _corpus()
    modules = {f: t for f, t in corpus.items() if "APIRouter()" in t}
    assert len(modules) >= 15, f"apenas {len(modules)} módulos de rutas: el barrido dejó de barrer"

    found = []
    for f, t in sorted(modules.items()):
        found += [f"{f}:{line} async def {name}" for name, line in orphan_handlers(f, t, corpus)]
    assert not found, (
        "handler sin ruta y sin llamadas — casi siempre un decorador secuestrado por la función de encima:\n  "
        + "\n  ".join(found))


def test_the_canvas_report_route_still_points_at_the_handler():
    """The specific route f3052f9 broke. Kept alongside the class guard because it names the CONSEQUENCE:
    this endpoint must take the payload, and a zero-arg getter answering 200 is how the report vanished."""
    from server import voice_api

    hit = [r for r in voice_api.router.routes if getattr(r, "path", "") == "/api/canvas/state"]
    assert hit, "la ruta del informe del canvas desapareció"
    assert hit[0].endpoint.__name__ == "canvas_state"
    assert "payload" in hit[0].endpoint.__annotations__, "el endpoint del canvas tiene que recibir el informe"
    assert voice_api.open_instances() is not None      # el helper sigue existiendo, pero SIN ruta
