"""V2-291 — the only existing path for saying “this round does not measure the product” was broken.

`_run_scenario` marks the round as a HARNESS failure when the model acting as the user steps out of its role more
than once (V2-285: its reaction to an impossible turn says nothing about zaelar). That marker was written to
`run_data` **thirty-seven lines before `run_data` existed**, so the entire branch blew up with an
`UnboundLocalError`.

Measured on 2026-08-24 12:35 in `search-buy-camera__es`: the round came out as

    INFRA: cannot access local variable 'run_data' where it is not associated with a value

with **0 turns, no transcript, and no mechanism report** — meaning it also wiped out the evidence of everything
that had actually happened in that round. The path written to recognize a harness failure was itself a harness
failure, and it had never run since it was written.

What this file preserves are the two halves: that the marker reaches `run_data` (and that the marker is what
`status.py` reads so it does not count the round against the case), and that **no write to `run_data` precedes its
definition** — which is the class, not the instance.
"""
import ast
import pathlib

RUN = pathlib.Path(__file__).resolve().parents[2] / "use_cases" / "e2e" / "agent" / "run.py"


def _fn(name: str) -> ast.FunctionDef:
    tree = ast.parse(RUN.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"{name} ya no existe en run.py — si se renombró, este guarda mira al vacío")


def test_nothing_writes_run_data_before_it_exists():
    """THE CLASS, not the case: `_run_scenario` is a long, single-use function — there is no way to instantiate it
    without an engine, sandbox, and model — so what can be checked cheaply is the ORDER. A `run_data[...]` above
    its assignment is an `UnboundLocalError` waiting for its condition to occur, and here the condition was “the
    harness broke”, meaning the one exercised least and most costly to lose."""
    fn = _fn("_run_scenario")
    born = [n.lineno for n in ast.walk(fn)
            if isinstance(n, ast.Assign)
            for t in n.targets if isinstance(t, ast.Name) and t.id == "run_data"]
    assert born, "`run_data` ya no se asigna por nombre: revisa este guarda antes de fiarte de él"
    first = min(born)
    early = [n.lineno for n in ast.walk(fn)
             if isinstance(n, ast.Subscript) and isinstance(n.value, ast.Name)
             and n.value.id == "run_data" and n.lineno < first]
    assert not early, (f"`run_data[...]` en las líneas {early}, y no nace hasta la {first}: esa rama revienta "
                       f"con UnboundLocalError el día que se cumpla su condición")


def test_the_breakage_marker_is_the_one_the_scoreboard_reads():
    """The marker is not enough simply to exist: `status.py` uses IT to decide whether the round counts against the
    case. If someone renames it on one side, the round starts scoring the product again for a failure of ours —
    silently."""
    src = RUN.read_text(encoding="utf-8")
    status = (RUN.parent / "status.py").read_text(encoding="utf-8")
    assert 'run_data["crashed"] = crashed' in src
    assert 'run.get("crashed")' in status


def test_the_marker_survives_next_to_the_evidence():
    """The failed round must reach the report WITH its transcript and mechanism. The broken version not only failed
    to mark it: it wiped out the 0 turns and everything measured, which is what is needed to understand what
    happened."""
    src = RUN.read_text(encoding="utf-8")
    i = src.index('run_data = {"transcript": transcript')
    j = src.index('run_data["crashed"] = crashed')
    assert i < j, "el marcador se escribe antes de que `run_data` traiga la evidencia"
