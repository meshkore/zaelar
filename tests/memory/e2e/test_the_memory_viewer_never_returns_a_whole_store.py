"""The memory viewer never returns a whole store (V2-808, V2-814, V2-815).

The viewer is a MONITOR of the brain: totals, sizes, the last 30 days of each store, and how the memory relates
concepts. One install is one person, but his store grows — weeks of conversation, an import of thousands of
messages — so the contract, endpoint by endpoint:

  * the row lists of the first viewer (facts, conversation, messages, files, apps, system) are retired; the
    graph, a concept and the totals never carry a memory's text;
  * the one tab that shows memories as cards («Cards», restored by V2-815) gets the NEWEST few per layer, capped
    on the server whatever the client asks, each text cut, and its concept maps a ring of at most 24 concepts;
  * totals are COUNTs that agree with what is stored; files are totalled by TYPE with their size; each store
    carries its last 30 days;
  * a browser widget's profile is its browsing session, not data it keeps: it is not counted as app data;
  * the graph is aggregated on the server and never has more nodes than the budget (itself clamped); when the
    window does not fit, only its top level — the concepts — is sent, and the reply says so;
  * the old `/api/memory/map` is bounded too.

Fixture: 200.000 memories and 200.000 archived messages written straight into a temporary database — the size
of a heavy import — so «it is counted» and «it is fast» are measured on the volume that made them necessary.
Disarms (2026-10-26): `memory.viewer.concept` returning its memories' text again turned
`test_no_stored_row_ever_leaves_the_viewer` red; the profile skip removed from `_walk` turned
`test_a_browser_profile_is_not_app_data` red.
"""
from __future__ import annotations

import os
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from memory import db as memdb
from memory import embeddings as mememb

N = 200_000


@pytest.fixture(autouse=True)
def _hash_backend(monkeypatch):
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    mememb.reset()
    yield
    mememb.reset()


@pytest.fixture(scope="module")
def big(tmp_path_factory):
    """One database and one message archive with N rows each, shared by the module (writing them is the cost)."""
    root = tmp_path_factory.mktemp("viewer")
    mp = pytest.MonkeyPatch()
    mp.setenv("ZAELAR_DB", str(root / "zaelar.db"))
    from widgets import store
    mp.setattr(store, "DATA_DIR", str(root / "widgets"))
    from connectors.messaging import archive
    archive.reset()
    memdb.reset_db()
    db = memdb.get_db()
    now = int(time.time())
    kinds = ("fact", "pref", "event", "msg", "conv")
    texts = ("viaje a Soria con la familia", "reunión de trabajo con el cliente", "pagar la hipoteca del banco",
             "partido de pádel el jueves", "receta de la cena")
    rows = [(("short" if i % 3 == 0 else "long"), kinds[i % 5], f"{texts[i % 5]} #{i}", 0.5, (i % 10) / 10,
             now - (N - i) * 30, now - (N - i) * 30) for i in range(N)]
    with db._lock:
        db.conn.executemany("INSERT INTO memories(level, kind, text, importance, weight, created, updated) "
                            "VALUES (?,?,?,?,?,?,?)", rows)
        db.conn.commit()
    conn = archive._conn()
    plats = ("whatsapp", "telegram", "email")
    # ids follow insertion, ts does not: the second half is a BACKFILL of older messages inserted later.
    msgs = [(plats[i % 3], f"c{i % 50}", f"Chat {i % 50}", 0, f"P{i % 7}", "in" if i % 4 else "out",
             float(now - (i if i < N // 2 else N + i) * 10), f"mensaje número {i} sobre el presupuesto" if i % 1000 == 0
             else f"mensaje {i}", "", f"m{i}") for i in range(N)]
    conn.executemany("INSERT INTO messages(platform, chat_id, chat_name, is_group, sender, direction, ts, body, "
                     "media_type, msg_id) VALUES (?,?,?,?,?,?,?,?,?,?)", msgs)
    conn.commit()
    media = os.path.join(store.DATA_DIR, "mensajeria")
    os.makedirs(media, exist_ok=True)
    for i in range(150):
        with open(os.path.join(media, f"img_{i:04d}.jpg"), "wb") as fh:
            fh.write(b"x" * 10)
    for i in range(4):
        with open(os.path.join(media, f"vid_{i:04d}.mp4"), "wb") as fh:
            fh.write(b"x" * 1000)
    # a browser widget: its profile (the browsing session) is big; what it saved for him is small
    nav = os.path.join(store.DATA_DIR, "navegador")
    os.makedirs(os.path.join(nav, "profile-en-US", "Cache"), exist_ok=True)
    with open(os.path.join(nav, "profile-en-US", "Cache", "blob"), "wb") as fh:
        fh.write(b"x" * 500_000)
    with open(os.path.join(nav, "shot.png"), "wb") as fh:
        fh.write(b"x" * 300)
    from server import memory_viewer_api as mva
    mva._stats_cache.update(at=0.0, body=None)
    mva._media_cache.update(at=0.0, rows=None)
    from memory import viewer
    viewer._cache.clear()
    app = FastAPI()
    app.include_router(mva.router)
    from server.memory_routes import router as map_router
    app.include_router(map_router)
    yield TestClient(app)
    archive.reset()
    memdb.reset_db()
    mp.undo()


def _timed(client, url):
    t0 = time.perf_counter()
    r = client.get(url)
    assert r.status_code == 200, r.text
    return r.json(), time.perf_counter() - t0


@pytest.mark.parametrize("path", ["facts", "conversation", "messages", "files", "thumb/img_0001.jpg", "apps",
                                  "system"])
def test_the_row_lists_are_retired(big, path):
    assert big.get(f"/api/memory/viewer/{path}?limit=10").status_code == 404


def test_no_stored_row_ever_leaves_the_viewer(big):
    graph, _ = _timed(big, "/api/memory/viewer/graph?days=0&budget=300")
    key = graph["concepts"][0]["key"]
    one, _ = _timed(big, f"/api/memory/viewer/concept?key={key}&days=0")
    assert one["count"] > 0 and one["related"], one
    assert set(one) == {"key", "label", "count", "short", "last", "related"}, sorted(one)
    stats, _ = _timed(big, "/api/memory/viewer/stats")
    for body in (graph, one, stats):
        blob = str(body)
        assert "hipoteca" not in blob and "presupuesto" not in blob, "a stored text reached the viewer"


def test_the_totals_are_counts_of_what_is_stored(big):
    body, secs = _timed(big, "/api/memory/viewer/stats")
    stores = {s["key"]: s for s in body["stores"]}
    assert stores["memories"]["total"] == N * 3 // 5                 # fact, pref, event — not msg, not conv
    assert stores["conversation"]["parts"]["turns"] == N // 5
    assert stores["messages"]["total"] == N
    assert sum(stores["messages"]["parts"].values()) == N
    files = stores["files"]
    assert files["total"] == 154 and files["types"]["images"] == {"n": 150, "bytes": 1500}
    assert files["types"]["videos"] == {"n": 4, "bytes": 4000} and files["bytes"] == 5500
    assert {"memories", "conversation", "messages", "files", "contacts", "agenda", "apps", "rules", "phrases",
            "events", "vault"} <= set(stores)
    for key in ("memories", "conversation", "messages", "files", "events"):
        assert len(stores[key]["daily"]) == 30, key
    assert sum(stores["files"]["daily"]) == 154, "files written today land in today's bar"
    assert secs < 3, f"the overview counts took {secs:.2f}s"


def test_a_browser_profile_is_not_app_data(big):
    from server import memory_viewer_api as mva
    mva._measure_dirs()
    mva._stats_cache.update(at=0.0, body=None)
    body, _ = _timed(big, "/api/memory/viewer/stats")
    apps = next(s for s in body["stores"] if s["key"] == "apps")
    nav = next(a for a in apps["apps"] if a["key"] == "navegador")
    assert nav["bytes"] == 300, f"the browsing session was counted as app data: {nav}"


def test_the_graph_never_has_more_nodes_than_the_budget(big):
    from memory.viewer import BUDGET_MAX
    body, secs = _timed(big, "/api/memory/viewer/graph?days=0&budget=300")
    assert body["shown"]["nodes"] <= 300
    assert body["shown"]["nodes"] == len(body["concepts"]) + len(body["memories"])
    assert body["total"]["nodes"] > body["shown"]["nodes"], "the honest total is reported beside what is drawn"
    assert body["capped"] is True, "a window larger than the scan cap says so"
    assert secs < 5, f"the aggregation took {secs:.2f}s"
    body, _ = _timed(big, "/api/memory/viewer/graph?days=0&budget=1000000")
    assert body["budget"] == BUDGET_MAX and body["shown"]["nodes"] <= BUDGET_MAX
    keys = {c["key"] for c in body["concepts"]}
    assert all(set(m["c"]) <= keys for m in body["memories"]), "a memory hangs only from concepts that are drawn"
    assert all(lk["a"] in keys and lk["b"] in keys for lk in body["links"])


def test_the_old_map_is_bounded_too(big):
    body, secs = _timed(big, "/api/memory/map")
    from memory.api import MAP_CAP
    assert len(body["layers"]["short"]) <= MAP_CAP and len(body["layers"]["long"]) <= MAP_CAP
    assert body["counts"]["short"] + body["counts"]["long"] == N, "its totals are COUNTs, not the page"
    assert "state" in body
    assert secs < 2, f"the bounded map took {secs:.2f}s"


def test_the_cards_are_capped_and_cut(big):
    from memory.viewer import CARDS_CAP, CARD_TEXT
    body, secs = _timed(big, "/api/memory/viewer/cards?limit=1000000")
    for layer in ("short", "long"):
        cards = body["layers"][layer]
        assert 0 < len(cards) <= CARDS_CAP, (layer, len(cards))
        assert all(len(c["text"]) <= CARD_TEXT for c in cards)
        assert "meta" not in cards[0], "a card carries what it paints, not the row"
        assert len(body["concept_graph"][layer]["nodes"]) <= 24
    assert body["counts"]["short"] + body["counts"]["long"] == N, "the header's totals are COUNTs, not the page"
    newest = body["layers"]["long"][0]["updated"]
    assert all(c["updated"] <= newest for c in body["layers"]["long"]), "the newest come first"
    assert "edges" not in body
    assert secs < 5, f"the cards took {secs:.2f}s"


def test_past_the_budget_only_the_top_level_is_drawn(monkeypatch):
    from memory import viewer
    pills = [{"id": i, "level": "long", "kind": "fact", "w": 0.5, "created": i, "c": [f"c{i % 20}", f"c{(i + 1) % 20}"]}
             for i in range(60)]
    monkeypatch.setattr(viewer, "_window", lambda days, lanes: pills)
    fits = viewer.graph(days=0, budget=200)                 # 20 concepts + 60 memories = 80 ≤ 200
    assert fits["collapsed"] is False and len(fits["concepts"]) == 20 and len(fits["memories"]) == 60
    top = viewer.graph(days=0, budget=50)                    # 80 > 50 → concepts only
    assert top["collapsed"] is True and top["memories"] == [] and len(top["concepts"]) == 20
    assert top["links"], "the top level keeps how the concepts relate"
