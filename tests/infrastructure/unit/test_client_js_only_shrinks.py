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
    "frontend/app/core/store.js": 1158,  # +20 V2-852 T12/T13 (4.371/4.372): the spoken record writes its row from what was owed (`_fromSpoken`), a cut line marked cut, an untraced utterance never paints a traced line; +10 V2-850 (4.357): a voiced reply always reaches the wall
    "frontend/app/services/session-lk.js": 1092,
    "frontend/app/components/ChatWall.js": 1068,  # +2 V2-851 F1c (4.359): the task's question on screen (TaskAsk.js mounted on the wall)
    "frontend/mobile/app/shell/Deck.js": 903,
    "frontend/app/components/ConfigPanel.js": 862,
    "frontend/app/components/DebugPanel.js": 737,
    "frontend/app/components/memory/graph-view.js": 554,
    "frontend/app/services/sse.js": 529,  # +2 V2-851 F1c (4.359): the task's question on screen (`ask`/`task_state` → core/asks.js); +1 V2-850 (4.357): the voice going idle
    "frontend/app/components/WidgetRail.js": 450,
    "frontend/app/components/Orb.js": 435,
    "frontend/app/main.js": 414,
}
#: All the product client lines together, measured on 2026-10-28.
JS_TOTAL_MAX = 36716  # +11 capture gaps 2026-11-06: the ◷ viewer reads the new kinds' fields (`components/debug-detail.js`: connector sender/subject/cause, provider, the pulse beat, a model call's input); +308 V2-854 F5: the contacts card shows his groups in the rail with a strip to add members, message and mirror them, and a person's aliases, relation, groups and agents (`contactos/js/people.js`, rail, detail, shared); +63 V2-852 T07 (4.370): the cancel control on each running process (ProcessEntry, api.taskCancel); T12/T13 (4.371/4.372) as on store.js; +245 V2-851 F1c (4.359): the task's question on screen — core/asks.js (state, the rows, the answer route) and components/TaskAsk.js (the wall line and the process entry's slot); +11 V2-850 (4.357): a voiced reply always reaches the wall; +837 V2-842 (music, 4544306d9): one app with a desktop face and a phone face — sidebar/rail, bottom nav, mini-player, expanded phone player, queue as drawer/sheet


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
