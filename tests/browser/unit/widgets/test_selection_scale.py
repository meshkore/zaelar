"""Tests for PROGRESSIVE WIDGET SELECTION (V2-085) — the guarantee that the prompt is **O(K), not O(N)**.

The contract defended here, and which must be deliberately broken for these tests to fail:

  1. Expanding the catalog does NOT bloat the turn. A "¿qué hora es?" with 10,000 widgets costs the same as with 100.
  2. Trimming the catalog is NOT amnesia: the widget the operator NAMES is promoted into the prompt even if it is at
     position 9,999 (the `named` layer, via `runtime.rank` — name/alias, V2-082).
  3. OPEN widgets are never trimmed (they are the operator's screen) and take precedence over everything else (V2-078).
  4. When some of the catalog is left out, the prompt SAYS SO — so the model does not deny capabilities that exist or
     invent ids, and knows that `show_widget`/`widget_data` resolve the name against the full catalog.
  5. `GET /widgets` returns a compact INDEX, not the full manifests.
"""
import json

import pytest

from widgets import brief, runtime, selection


def _fake_catalog(n: int) -> list[dict]:
    """N synthetic widgets with distinctive names/aliases (`contador <i>`) and a declared action."""
    return [{"id": f"w{i:05d}", "title": f"Widget número {i}", "name": f"contador {i}",
             "aliases": [f"contador {i}"],
             "whenToUse": f"Cuenta y muestra la métrica número {i} del operador en tiempo real.",
             "actions": {"add": {"desc": "añade", "payload": {"v": 1}}}}
            for i in range(n)]


@pytest.fixture
def catalog(monkeypatch):
    """Install a synthetic catalog of size N, skipping the disk scan and its mtime-based caches."""
    def _install(n: int):
        cat = _fake_catalog(n)
        monkeypatch.setattr(runtime, "_signature", lambda: ("synthetic", n))
        monkeypatch.setitem(runtime._cache, "sig", ("synthetic", n))
        monkeypatch.setitem(runtime._cache, "list", cat)
        monkeypatch.setitem(runtime._index, "sig", None)     # the alias index is rebuilt from this catalog
        return cat
    return _install


# ── 1. O(K), not O(N) ────────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("n", [100, 1000, 10000])
def test_prompt_block_is_bounded_regardless_of_catalog_size(catalog, n):
    catalog(n)
    stats: dict = {}
    txt = brief.for_prompt(open_ids=[], recent_ids=[], query="qué hora es", stats=stats)
    assert stats["n_total"] == n
    assert stats["n_selected"] <= selection.MAX_WIDGETS
    assert stats["hidden"] == n - stats["n_selected"]
    # The actual limit: the widget block for a turn that is NOT about widgets fits comfortably in 4 KB for ANY N.
    assert len(txt) < 4000, f"bloque de widgets desbordado con {n} widgets: {len(txt)} chars"


def test_growing_the_catalog_does_not_grow_an_unrelated_turn(catalog):
    """The direct contract test: the SAME irrelevant turn with 100 and 10,000 widgets weighs nearly the same."""
    catalog(100)
    small = brief.for_prompt(open_ids=[], recent_ids=[], query="qué hora es")
    catalog(10000)
    big = brief.for_prompt(open_ids=[], recent_ids=[], query="qué hora es")
    assert abs(len(big) - len(small)) < 200, "el catálogo se está colando en un turno que no va de widgets"


# ── 2. Naming a widget pulls it out of the catalog queue ────────────────────────────────────────────────────
@pytest.mark.parametrize("n", [100, 1000, 10000])
def test_named_widget_surfaces_from_the_tail(catalog, n):
    catalog(n)
    last = n - 1
    stats: dict = {}
    txt = brief.for_prompt(open_ids=[], recent_ids=[], query=f"abre el contador {last}", stats=stats)
    assert f"w{last:05d}" in stats["selected_ids"], "el widget NOMBRADO no llegó al prompt"
    assert f"w{last:05d}" in txt
    assert stats["n_named"] >= 1


def test_named_widget_is_ranked_above_filler(catalog):
    catalog(500)
    picked = selection.candidates("abre el contador 499", [], [])
    reasons = {p["w"]["id"]: p["reason"] for p in picked}
    assert reasons.get("w00499") == selection.NAMED
    # …and it comes before filler in the list the model sees.
    ids = [p["w"]["id"] for p in picked]
    assert ids.index("w00499") < ids.index([i for i in ids if reasons[i] == selection.FILL][0])


# ── 3. Open widgets take precedence and are not trimmed ─────────────────────────────────────────────────────
def test_open_widgets_always_present_and_first(catalog):
    catalog(5000)
    opened = ["w04000", "w04001"]
    stats: dict = {}
    brief.for_prompt(open_ids=opened, recent_ids=[], query="qué tal", stats=stats)
    assert stats["selected_ids"][:2] == opened
    assert stats["n_open"] == 2


def test_recent_widgets_ride_along_bounded(catalog):
    catalog(5000)
    recent = [f"w0{i:04d}" for i in range(3000, 3010)]      # 10 recent widgets, more than MAX_RECENT
    stats: dict = {}
    brief.for_prompt(open_ids=[], recent_ids=recent, query="qué tal", stats=stats)
    assert stats["n_recent"] == selection.MAX_RECENT
    assert set(stats["selected_ids"]) & set(recent) == set(recent[:selection.MAX_RECENT])


def test_open_beats_recent_and_neither_is_duplicated(catalog):
    catalog(200)
    stats: dict = {}
    brief.for_prompt(open_ids=["w00100"], recent_ids=["w00100", "w00101"], query="", stats=stats)
    ids = stats["selected_ids"]
    assert ids[0] == "w00100" and ids.count("w00100") == 1
    assert stats["n_open"] == 1


# ── 4. Trimming is ANNOUNCED (neither deny capabilities nor invent ids) ─────────────────────────────────────
def test_truncation_is_announced_with_the_escape_hatch(catalog):
    catalog(1000)
    txt = brief.for_prompt(open_ids=[], recent_ids=[], query="hola")
    assert "EXTRACTO" in txt and "show_widget" in txt
    assert "PREGÚNTALE" in txt


def test_no_truncation_notice_when_everything_fits(catalog):
    catalog(5)
    stats: dict = {}
    txt = brief.for_prompt(open_ids=[], recent_ids=[], query="hola", stats=stats)
    assert stats["truncated"] is False and stats["hidden"] == 0
    assert "EXTRACTO" not in txt


def test_real_catalog_is_not_truncated_today(monkeypatch):
    """Zero regression for the operator: the real catalog fits entirely under the limit (if it ever stops fitting,
    this test warns before the operator notices it in a conversation)."""
    stats: dict = {}
    brief.for_prompt(open_ids=[], recent_ids=[], query="hola", stats=stats)
    assert stats["truncated"] is False, (
        f"el catálogo real ({stats['n_total']}) ya no cabe en MAX_WIDGETS={selection.MAX_WIDGETS}; "
        "revisa el techo antes de asumir que el recorte es inocuo")


# ── 5. The endpoint returns an index, not manifests ──────────────────────────────────────────────────────────
def test_widgets_index_is_much_smaller_than_full_manifests():
    from widgets import server_api
    cat = runtime.catalog()
    if not cat:
        pytest.skip("sin catálogo real en este entorno")
    full = len(json.dumps(cat, ensure_ascii=False))
    idx = len(json.dumps([server_api._index_row(w) for w in cat], ensure_ascii=False))
    assert idx * 3 < full, f"el índice no está comprimiendo nada (índice {idx} vs manifests {full})"


def test_index_row_keeps_identity_and_drops_payload_schemas():
    from widgets import server_api
    row = server_api._index_row({"id": "x", "title": "X", "name": "equis", "aliases": ["equis", "ex"],
                                 "whenToUse": "P" * 500, "actions": {"a": {"payload": {"k": 1}}},
                                 "usage": "prosa larga"})
    assert row["id"] == "x" and row["name"] == "equis" and "ex" in row["aliases"]
    assert "actions" not in row and "usage" not in row          # load on demand: /widgets/{id}/manifest
    assert len(row["whenToUse"]) <= server_api._INDEX_PURPOSE_MAX


# ── The state never swallows the entire catalog ─────────────────────────────────────────────────────────────
def test_state_widget_registry_is_capped(tmp_path, monkeypatch):
    from memory import state
    monkeypatch.setattr(state, "read", lambda: {})
    written: dict = {}
    monkeypatch.setattr(state, "write", lambda cur: written.update(cur))
    rows = state.set_widget_registry([{"id": f"w{i}", "name": f"n{i}", "aliases": []} for i in range(5000)])
    assert len(rows) == state._REGISTRY_CAP + 1                 # prefix + marker
    assert rows[-1]["_truncated"] is True and rows[-1]["total"] == 5000
