#
# tests/widget_harness.py — the per-widget mini-harness. Runs OUTSIDE the server, from the repo root:
#
#   ./.venv/bin/python -m tests.widget_harness            # every widget in the catalog
#   ./.venv/bin/python -m tests.widget_harness agenda …   # just these
#
# Three checks per widget, all local and fast:
#   contract — generator._validate(): manifest + `export function render` + data.py compiles + view_data() runs
#              and returns a dict (the same gate a generated widget must pass to enter the catalog).
#   golden   — the SHAPE of view_data() (top-level keys → types) against widgets/<id>/golden.json. Live data
#              changes every call, so the golden pins structure, not values: a key that disappears or changes
#              type is exactly the regression a careless modify introduces. First run records the golden.
#   render   — widget.js parses as an ES module (`node --input-type=module --check`); skipped if node is absent.
#              A real DOM render happens in the browser; this catches the syntax-level breakage class.
#   screens  — the manifest DECLARES how it lives on several screens (`"screens"`: shared | single, V2-792) and the
#              declaration agrees with its output channel (`widgets/screen_policy.py`).
#
# Two more passes, on request, because a widget is not finished until it behaves with the agent open on the computer
# AND the phone at once:
#   --two-screens  opens a desktop browser and a phone browser on one engine and checks the widget does what its
#                  policy says (`tests/browser/e2e/mobile/two_screens.py`; add --headed to watch both windows).
#   --manual       prints the operator's manual pass for each widget, with a real phone and a real computer
#                  (`.meshkore/docs/ops/zaelar-two-screen-test.md`).
#
import json
import os
import shutil
import subprocess
import sys

from widgets import paths

HERE = paths.BUILTIN_ROOT


def _golden_path(wid: str) -> str:
    return os.path.join(paths.dir_for(wid) or paths.new_dir(wid), "golden.json")


def _shape(d: dict) -> dict:
    return {k: type(v).__name__ for k, v in sorted(d.items())}


def check_contract(wid: str) -> tuple[bool, str]:
    from widgets import generator
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
    for js in paths.client_files(paths.dir_for(wid) or paths.new_dir(wid)):
        try:
            src = open(js, encoding="utf-8").read()
            r = subprocess.run([node, "--input-type=module", "--check", "-"], input=src,
                               capture_output=True, text=True, timeout=15)
        except Exception as e:
            return False, f"node check failed to run: {e}"
        if r.returncode != 0:
            return False, f"{os.path.basename(js)}: " + (r.stderr or "syntax error").strip().splitlines()[-1][:160]
    return True, "parses as ES module"


def check_screens(wid: str) -> tuple[bool, str]:
    from widgets import screen_policy
    p = os.path.join(paths.dir_for(wid) or paths.new_dir(wid), "manifest.json")
    try:
        man = json.load(open(p, encoding="utf-8"))
    except Exception as e:
        return False, f"manifest unreadable: {e}"
    bad = screen_policy.problem(man, required=True)
    return (False, bad) if bad else (True, f"{screen_policy.of(man)} — two-screen pass: --two-screens / --manual")


#: The operator's manual pass, per policy. Short on purpose: it is read with a phone in one hand.
_MANUAL = {
    "shared": [
        "On the COMPUTER, ask for «{name}». It opens on the computer; the phone shows «{name} · open on the computer — Open here» and does not open it.",
        "On the PHONE, ask for «{name}» too. It opens on the phone and STAYS open on the computer.",
        "Change something in it from one screen (by voice or by hand). The other screen shows the change without a reload.",
        "Type an order on the screen that does NOT hold the voice. It is answered, and the line shows on both chats.",
    ],
    "single": [
        "On the COMPUTER, ask for «{name}» and let it play. The phone shows «{name} · playing on the computer — Bring here» and plays nothing.",
        "Open the phone app (or reload it). It does NOT start «{name}» again; the chip is there.",
        "On the PHONE, ask for «{name}» with something new. The computer STOPS and closes it at once; the phone opens and plays it. Never both sounding.",
        "From the phone, say «pause» / «volume down». It obeys wherever it is playing.",
        "Say «put it on the computer» (or tap «Bring here» on the computer). It moves back; the phone keeps the chip.",
        "Tap the mic on the computer. The phone gives up the voice at once (its mic and speaker off).",
    ],
}


def manual_steps(wid: str) -> list[str]:
    from widgets import registry, screen_policy, runtime
    man = next((w for w in runtime.catalog() if w.get("id") == wid), {"id": wid})
    name = registry.display_name("widgets", wid, str(man.get("name") or man.get("title") or wid))
    return [s.format(name=name) for s in _MANUAL[screen_policy.of(man)]]


def two_screens(widget_ids: list[str], headed: bool = False) -> int:
    script = os.path.join(paths.BUILTIN_ROOT, "..", "tests", "browser", "e2e", "mobile", "two_screens.py")
    return subprocess.call([sys.executable, os.path.abspath(script), *widget_ids, *(["--headed"] if headed else [])])


def run(widget_ids: list[str] | None = None) -> int:
    from widgets import runtime
    ids = widget_ids or [w["id"] for w in runtime.catalog()]
    failures = 0
    for wid in ids:
        results = [("contract", *check_contract(wid)), ("golden", *check_golden(wid)), ("render", *check_render(wid)),
                   ("screens", *check_screens(wid))]
        bad = [r for r in results if not r[1]]
        failures += len(bad)
        mark = "✓" if not bad else "✗"
        print(f"{mark} {wid}")
        for name, ok, detail in results:
            print(f"    {'✓' if ok else '✗'} {name:9s} {detail}")
    print(f"\n{'OK' if not failures else 'FAIL'} — {len(ids)} widget(s), {failures} failing check(s)")
    return 1 if failures else 0


def main(argv: list[str]) -> int:
    ids = [a for a in argv if not a.startswith("--")] or None
    if "--manual" in argv:
        from widgets import runtime
        for wid in ids or [w["id"] for w in runtime.catalog() if not w.get("transient")]:
            print(f"\n▸ {wid} — manual two-screen pass (a computer and a phone, one agent)")
            for i, step in enumerate(manual_steps(wid), 1):
                print(f"   {i}. {step}")
        return 0
    if "--two-screens" in argv:
        return two_screens(ids or [], headed="--headed" in argv)
    return run(ids)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
