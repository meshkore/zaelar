"""The client JavaScript only shrinks (refactor2710-99 #106): no new file over the line, no listed file grows.

The Python side has had its ratchets for a long time; the client had only the per-widget shape test
(`tests/browser/unit/widgets/test_every_widget_keeps_its_shape.py`, 600 lines per widget module). That test never
read `frontend/`, where every file over 400 lines lives. This test measures every product `.js` file under
`widgets/` and `frontend/`, counting lines the way the shape test does (newlines + 1). Vendored and minified code
is not ours to split, so it is left out.

The ceilings are what was measured on 2026-10-28. The final threshold is the operator's call; until he makes it,
nothing over 400 may be born, and nothing listed may grow.
"""
from __future__ import annotations

from pathlib import Path

ENGINE = Path(__file__).resolve().parents[3]
JS_LINE = 400

#: Client files over the line today, at what was measured. Lower a row when its file shrinks; drop it when the
#: file fits the line or is gone. Never raise one, and never add one.
JS_CEILINGS = {
    "frontend/app/widgets/desktop.js": 1987,
    "frontend/app/core/store.js": 1128,
    "frontend/app/services/session-lk.js": 1094,
    "frontend/app/components/ChatWall.js": 1066,
    "frontend/mobile/app/shell/Deck.js": 903,
    "frontend/app/components/ConfigPanel.js": 862,
    "frontend/app/components/DebugPanel.js": 737,
    "frontend/app/components/memory/graph-view.js": 554,
    "frontend/app/services/sse.js": 526,
    "frontend/app/components/WidgetRail.js": 450,
    "frontend/app/components/Orb.js": 435,
    "frontend/app/main.js": 414,
}
#: All the product client lines together, measured on 2026-10-28.
JS_TOTAL_MAX = 35241


def _ours(p: Path) -> bool:
    parts = set(p.relative_to(ENGINE).parts)
    return not (parts & {"vendor", "vad", "node_modules", "_data", "__pycache__"}
                or any(x.startswith("_user") for x in parts) or p.name.endswith(".min.js"))


def _sizes() -> dict[str, int]:
    out = {}
    for base in ("widgets", "frontend"):
        for p in sorted((ENGINE / base).rglob("*.js")):
            if _ours(p):
                out[p.relative_to(ENGINE).as_posix()] = p.read_text(encoding="utf-8", errors="ignore").count("\n") + 1
    return out


def _over(sizes: dict[str, int], ceilings: dict[str, int] = JS_CEILINGS) -> list[str]:
    return [f"{rel}: {n} > {ceilings.get(rel, JS_LINE)}" for rel, n in sorted(sizes.items())
            if n > ceilings.get(rel, JS_LINE)]


def test_no_client_file_is_born_over_the_line_and_none_listed_grows():
    assert not _over(_sizes()), f"a client .js file grew past its ceiling — split it by concern: {_over(_sizes())}"


def test_the_client_total_only_shrinks():
    total = sum(_sizes().values())
    assert total <= JS_TOTAL_MAX, f"the client grew: {total} > {JS_TOTAL_MAX} lines"


def test_a_listed_file_that_shrank_lowers_its_row():
    sizes = _sizes()
    stale = [f"{rel}: listed {cap}, measured {sizes.get(rel)}" for rel, cap in JS_CEILINGS.items()
             if sizes.get(rel, 0) < cap]
    assert not stale, f"lower these rows to what they measure (or drop them under {JS_LINE}): {stale}"


def test_disarm_a_grown_or_new_file_is_named():
    """The guard reads the numbers, not the tree: a listed file one line over, and a new one over the line, are named."""
    assert _over({"frontend/app/main.js": 415}) == ["frontend/app/main.js: 415 > 414"]
    assert _over({"frontend/app/x.js": JS_LINE + 1}) == [f"frontend/app/x.js: {JS_LINE + 1} > {JS_LINE}"]
    assert _over({"frontend/app/x.js": JS_LINE}) == []


def test_vendored_and_minified_code_is_not_measured():
    sizes = _sizes()
    assert sizes, "the walk found no client file — the roots moved"
    assert not [r for r in sizes if "/vendor/" in r or "/vad/" in r or r.endswith(".min.js")]
