"""Every shipped widget keeps its shape, and none grows back (refactor2710-12 T-05).

The shape: no Python file over 400 lines, no client module (`widget.js` or `js/*.js`) over 600 — a file over that
splits into a folder of concerns (`data.py` stays the contract, `js/` holds the client's parts). The files that were
over before this pass and are owned by a later one are listed with the size they had: they may only shrink. And each
widget's total, Python and client, may only shrink from what was measured when the shape landed (2026-10-28).
"""
from __future__ import annotations

from pathlib import Path

ENGINE = Path(__file__).resolve().parents[4]
WIDGETS = ENGINE / "widgets"
PY_MAX, JS_MAX = 400, 600

#: Over the shape today, owned by a later pass. Empty since refactor2710-99 split the last nine; only shrink.
GRANDFATHERED: dict[str, int] = {}
#: widget → (Python lines, client lines), measured 2026-10-28; results lowered by V2-831 R9 and R9b (tightening paid
#: for the door flattener and its labels). Lower it when a widget shrinks; never raise it.
CEILINGS = {
    "results": (2668, 1577),  # +3 V2-837×V2-838 merge (the door event and the rule read meet in one module); +53 V2-838 (12.838): the door reads his standing exclusions, names the rule, rechecks every sheet when one is written; +86 V2-837 G10 (7.86): one door event per push with its counts (`results/door_event.py`); +68 V2-835 T1/T2 (12.835, 12.837): a declared exclusion at the door, and the pool a present narrows from (results/pool.py); +13 V2-831 audit A7 (4.331): a fact keeps its key, labelled from the pack on every read; +8 audit A8 (4.322): a row with a link or picture of its own is kept (modularity §8)
    "agenda": (5315, 1882),  # +14/−1 V2-834 T36 (S1 audit H7): a meeting is answered as seen — the row minus its declared bookkeeping (`details.as_seen`), one function for open_meeting and show_day instead of two hand-picked subsets; +12/+3 V2-831 T-19 pass 9 Z1 (4.334): their answer needs a source (modularity §8); refactor2710-06 T-06: the notice bounds MOVED in (agenda/notice.py), flash −1 755
    "archivos": (1065, 1127), "clock": (19, 66), "contactos": (2400, 1319),
    "documento": (407, 371), "fotos": (242, 259), "imagenes": (381, 239), "map": (248, 162),  # imagenes +18 V2-834 T37 (S1 audit H8): the picture in front is in its digest
    "markets": (228, 141), "mensajeria": (5503, 2728), "musica": (1654, 1789), "navegador": (5576, 187),  # +107 V2-837 G6 (7.85): every navigation's status, time, size and wall (`navegador/page_outcome.py`); +68 V2-835 T5 (4.351/4.352): a login wait ends with its task/tab/time, a fallen-back launch is labelled and blocked, the wall note informs instead of offering a sign-in
    "search": (127, 93), "timer": (127, 298), "youtube": (3448, 1722),  # +10 V2-833 F0: the page lookups report what they got (map, markets, search: +2 each)
}


def _lines(p: Path) -> int:
    return p.read_text(encoding="utf-8").count("\n") + 1


def _widgets() -> dict[str, Path]:
    return {d.name: d for d in sorted(WIDGETS.iterdir())
            if d.is_dir() and not d.name.startswith(("_", ".")) and (d / "manifest.json").is_file()}


def _files(d: Path):
    for p in sorted(d.rglob("*")):
        if p.suffix in (".py", ".js") and "__pycache__" not in p.parts and "_data" not in p.parts:
            yield p


def _over(sizes: dict[str, int]) -> list[str]:
    bad = []
    for rel, n in sorted(sizes.items()):
        cap = GRANDFATHERED.get(rel, PY_MAX if rel.endswith(".py") else JS_MAX)
        if n > cap:
            bad.append(f"{rel}: {n} > {cap}")
    return bad


def _sizes() -> dict[str, int]:
    return {p.relative_to(WIDGETS).as_posix(): _lines(p) for d in _widgets().values() for p in _files(d)}


def _totals() -> dict[str, tuple[int, int]]:
    out = {}
    for wid, d in _widgets().items():
        py = sum(_lines(p) for p in _files(d) if p.suffix == ".py")
        out[wid] = (py, sum(_lines(p) for p in _files(d) if p.suffix == ".js"))
    return out


def test_no_widget_file_is_over_its_shape():
    assert not _over(_sizes()), "split it into a folder of concerns: " + "; ".join(_over(_sizes()))


def test_no_widget_grows_and_every_widget_has_its_number():
    totals = _totals()
    assert set(totals) == set(CEILINGS), f"a widget without a ceiling (or one gone): {set(totals) ^ set(CEILINGS)}"
    grew = [f"{w}: {totals[w]} > {CEILINGS[w]}" for w in totals
            if totals[w][0] > CEILINGS[w][0] or totals[w][1] > CEILINGS[w][1]]
    assert not grew, grew


def test_a_grandfathered_file_only_shrinks_and_leaves_the_list_when_it_fits():
    sizes = _sizes()
    stale = [rel for rel in GRANDFATHERED if rel not in sizes or sizes[rel] <= (PY_MAX if rel.endswith(".py") else JS_MAX)]
    assert not stale, f"these fit the shape now (or are gone): take them off GRANDFATHERED: {stale}"


def test_disarm_an_oversize_file_is_named(monkeypatch):
    assert _over({"x/data.py": PY_MAX + 1, "x/js/a.js": JS_MAX}) == [f"x/data.py: {PY_MAX + 1} > {PY_MAX}"]
    monkeypatch.setitem(GRANDFATHERED, "x/old.py", 634)
    assert _over({"x/old.py": 635}) == ["x/old.py: 635 > 634"]
