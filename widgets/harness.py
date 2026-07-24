#
# widgets/harness.py — the per-widget mini-harness (INI-006 · W-6). Runs OUTSIDE the server, from the repo root:
#
#   ./.venv/bin/python -m widgets.harness            # every widget in the catalog
#   ./.venv/bin/python -m widgets.harness agenda …   # just these
#
# Three checks per widget, all local and fast:
#   contract — generator._validate(): manifest + `export function render` + data.py compiles + view_data() runs
#              and returns a dict (the same gate a generated widget must pass to enter the catalog).
#   golden   — the SHAPE of view_data() (top-level keys → types) against widgets/<id>/golden.json. Live data
#              changes every call, so the golden pins structure, not values: a key that disappears or changes
#              type is exactly the regression a careless modify introduces. First run records the golden.
#   render   — widget.js parses as an ES module (`node --input-type=module --check`); skipped if node is absent.
#              A real DOM render happens in the browser; this catches the syntax-level breakage class.
#
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def _golden_path(wid: str) -> str:
    return os.path.join(HERE, wid, "golden.json")


def _shape(d: dict) -> dict:
    return {k: type(v).__name__ for k, v in sorted(d.items())}


def check_contract(wid: str) -> tuple[bool, str]:
    from . import generator
    ok, err = generator._validate(wid)
    return ok, err or "valid"


def check_golden(wid: str) -> tuple[bool, str]:
    import importlib
    try:
        mod = importlib.import_module(f"widgets.{wid}.data")
        mod = importlib.reload(mod)
    except Exception as e:
        return False, f"data.py import failed: {e}"
    if not hasattr(mod, "view_data"):
        return True, "no view_data (js-only widget)"
    try:
        out = mod.view_data(q="")
    except TypeError:
        out = mod.view_data()
    if not isinstance(out, dict):
        return False, f"view_data() returned {type(out).__name__}, not dict"
    shape = _shape(out)
    gp = _golden_path(wid)
    if not os.path.isfile(gp):
        json.dump({"view_data_shape": shape}, open(gp, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        return True, "golden recorded (first run)"
    try:
        golden = json.load(open(gp, encoding="utf-8")).get("view_data_shape", {})
    except Exception as e:
        return False, f"golden.json unreadable: {e}"
    missing = [k for k in golden if k not in shape]
    retyped = [f"{k}:{golden[k]}→{shape[k]}" for k in golden if k in shape and shape[k] != golden[k]
               and "NoneType" not in (golden[k], shape[k])]   # a live field may legitimately be null sometimes
    if missing or retyped:
        parts = ([f"missing keys {missing}"] if missing else []) + (["retyped " + ", ".join(retyped)] if retyped else [])
        return False, "shape drift — " + "; ".join(parts)
    return True, f"shape stable ({len(golden)} keys)"


def check_render(wid: str) -> tuple[bool, str]:
    node = shutil.which("node")
    if not node:
        return True, "skipped (no node)"
    js = os.path.join(HERE, wid, "widget.js")
    try:
        src = open(js, encoding="utf-8").read()
        r = subprocess.run([node, "--input-type=module", "--check", "-"], input=src,
                           capture_output=True, text=True, timeout=15)
    except Exception as e:
        return False, f"node check failed to run: {e}"
    if r.returncode != 0:
        return False, (r.stderr or "syntax error").strip().splitlines()[-1][:160]
    return True, "parses as ES module"


def run(widget_ids: list[str] | None = None) -> int:
    from . import runtime
    ids = widget_ids or [w["id"] for w in runtime.catalog()]
    failures = 0
    for wid in ids:
        results = [("contract", *check_contract(wid)), ("golden", *check_golden(wid)), ("render", *check_render(wid))]
        bad = [r for r in results if not r[1]]
        failures += len(bad)
        mark = "✓" if not bad else "✗"
        print(f"{mark} {wid}")
        for name, ok, detail in results:
            print(f"    {'✓' if ok else '✗'} {name:9s} {detail}")
    print(f"\n{'OK' if not failures else 'FAIL'} — {len(ids)} widget(s), {failures} failing check(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(run(sys.argv[1:] or None))
