#
# V2-564 — the Fotos gallery widget: the contract, the boundaries.
#
#   · "search" is the action that ANSWERS the phrase this widget exists for ("do I have photos of Morocco?")
#     and has to hand its matches BACK (V2-541) — a data-op that only repaints leaves the turn mute.
#   · NO ACTION PAYLOAD MAY CARRY A CREDENTIAL (V2-520) — `connect` returns a `url` to open, never a secret.
#   · `view_data` must stay CHEAP: no network, no connector import — it runs on every render and SSE push.
#   · The connector import is deferred, so the widget catalog (built on every prompt) never pays `httpx`.
#
from __future__ import annotations

import importlib
import json
import pathlib
import re

import pytest

_ENGINE = pathlib.Path(__file__).resolve().parents[4]
_WIDGET = _ENGINE / "widgets" / "fotos"


def _manifest() -> dict:
    return json.loads((_WIDGET / "manifest.json").read_text(encoding="utf-8"))


@pytest.fixture()
def data(tmp_path, monkeypatch):
    """A private store. A unit test never touches the operator's real photo index."""
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    from nucleo import workspace
    from widgets import store as wstore
    importlib.reload(workspace)
    importlib.reload(wstore)
    from widgets.fotos import data as mod
    importlib.reload(mod)
    yield mod
    importlib.reload(workspace)
    importlib.reload(wstore)


class _Svc:
    """A stand-in for `connectors.photos.service` — the seam the widget talks through."""

    def __init__(self, connected=True, items=None, total=None, has_more=False, session_pending=False):
        self.connected = connected
        self.items = items if items is not None else []
        self.total = total if total is not None else len(self.items)
        self.has_more = has_more
        self.session_pending = session_pending
        self.calls = []

    def status(self):
        return {"ok": True, "provider": "google-photos", "app_configured": True, "connected": self.connected,
                "session_pending": self.session_pending, "item_count": self.total}

    def start_session(self):
        self.calls.append(("start_session",))
        return {"ok": True, "picker_uri": "https://photos.google.com/picker/s1"}

    def poll_session(self):
        self.calls.append(("poll_session",))
        return {"ok": True, "pending": False, "ready": False, "imported": 0}

    def list_page(self, offset=0, size=120):
        self.calls.append(("list_page", offset))
        return {"ok": True, "items": self.items, "next_offset": len(self.items), "has_more": self.has_more,
                "total": self.total}

    def years(self):
        return [{"year": "2024", "count": len(self.items)}]

    def search(self, query):
        self.calls.append(("search", query))
        hits = [it for it in self.items if query.lower() in (it.get("filename") or "").lower()]
        return {"ok": True, "count": len(hits), "date_from": "", "date_to": "", "label": query, "items": hits}

    def label_last_batch(self, label):
        self.calls.append(("label_batch", label))
        return {"ok": True, "batch_id": "b1", "label": label}

    def disconnect(self):
        self.calls.append(("disconnect",))
        self.connected = False
        return {"ok": True}


def _wire(mod, svc, monkeypatch):
    monkeypatch.setattr(mod, "_svc", lambda: svc)
    return svc


_ITEMS = [
    {"id": "p1", "filename": "camel.jpg", "taken_at": "2024-06-01", "provider": "google-photos",
     "thumb": "/api/photos/thumb/p1"},
    {"id": "p2", "filename": "dune.jpg", "taken_at": "2024-06-02", "provider": "google-photos",
     "thumb": "/api/photos/thumb/p2"},
]


# ── the contract with the brain ────────────────────────────────────────────────────────────────────────────
def test_every_declared_action_is_handled_and_every_handled_one_is_declared():
    src = (_WIDGET / "data.py").read_text(encoding="utf-8")
    handled = set(re.findall(r'act == "([a-z_]+)"', src))
    for grp in re.findall(r"act in \(([^)]*)\)", src):
        handled |= {x.strip().strip('"') for x in grp.split(",") if x.strip()}
    assert set(_manifest()["actions"]) == handled


def test_the_actions_that_ANSWER_A_LOOK_are_view_actions():
    """«enséñame la galería», «búscame las fotos de Marruecos» are pure look orders, and the voice rail
    refuses to run a data-op on one unless it declares itself display-only (V2-545)."""
    from widgets import actions as wactions
    acts = _manifest()["actions"]
    for name in ("refresh", "more", "search", "clear_search"):
        assert wactions.is_view(acts[name], name), f"«{name}» answers a look order and must be a view action"


def test_disconnecting_asks_first_and_looking_never_does():
    from widgets import actions as wactions
    acts = _manifest()["actions"]
    assert wactions.classify(acts["disconnect"], "disconnect") == wactions.CONFIRM
    for name in ("refresh", "more", "search", "clear_search"):
        assert wactions.classify(acts[name], name) == wactions.FAST, f"«{name}» is reversible; do not gate it"


def test_NO_action_payload_carries_a_credential():
    """V2-520's boundary: `connect` starts an OAuth/Picker round trip and hands back a `url` to open — the
    app itself is registered ONCE in ⚙ → Conectores, never through a voice-reachable payload field."""
    blob = json.dumps(_manifest()["actions"]).lower()
    for word in ("client_secret", "client_id", "token", "password", "secret", "refresh_token"):
        assert word not in blob, f"«{word}» must never be an action payload field"


def test_the_routing_line_fits_the_budget_it_is_measured_against():
    from widgets import brief
    m = _manifest()
    assert len(m["whenToUse"]) <= brief._PURPOSE_CAP, len(m["whenToUse"])
    assert brief._purpose(m["whenToUse"]) == m["whenToUse"], "it must survive whole, not merely be truncated well"


def test_usage_states_the_real_search_scope_so_the_brain_never_overclaims():
    """The widget cannot recognize what is IN a photo. If `usage` doesn't say so, the brain narrates a
    capability that does not exist the first time somebody asks "find the photos with a camel"."""
    m = _manifest()
    assert "fecha" in m["usage"].lower() and ("etiqueta" in m["usage"].lower() or "viaje" in m["usage"].lower())


# ── answering, not just repainting ────────────────────────────────────────────────────────────────────────
def test_a_search_hands_its_matches_BACK(data, monkeypatch):
    _wire(data, _Svc(items=_ITEMS), monkeypatch)
    out = data.apply_action("search", {"query": "camel"})
    assert out["ok"] and out["count"] == 1
    names = [m["filename"] for m in out["matches"]]
    assert "camel.jpg" in names, "«do I have Morocco photos?» is a QUESTION, not a repaint (V2-541)"


def test_a_search_with_no_words_is_refused_with_a_sentence(data, monkeypatch):
    _wire(data, _Svc(items=_ITEMS), monkeypatch)
    out = data.apply_action("search", {"query": "   "})
    assert out["ok"] is False and "busco" in out["error"]


def test_connect_returns_a_url_and_never_a_credential(data, monkeypatch):
    svc = _wire(data, _Svc(connected=False), monkeypatch)
    out = data.apply_action("connect", {})
    assert out["ok"] and out["url"].startswith("https://")
    assert ("start_session",) in svc.calls


def test_label_batch_without_a_name_teaches_the_shape_instead_of_guessing(data, monkeypatch):
    _wire(data, _Svc(items=_ITEMS), monkeypatch)
    out = data.apply_action("label_batch", {})
    assert out["ok"] is False and "nombre" in out["error"]


def test_an_unknown_action_lists_the_ones_that_exist(data, monkeypatch):
    _wire(data, _Svc(), monkeypatch)
    out = data.apply_action("teleport", {})
    assert out["ok"] is False and "search" in out["error"]


def test_disconnect_forgets_the_connection(data, monkeypatch):
    svc = _wire(data, _Svc(items=_ITEMS), monkeypatch)
    out = data.apply_action("disconnect", {})
    assert out["ok"]
    assert ("disconnect",) in svc.calls
    assert data.view_data()["connected"] is False


# ── the references the model resolves against ────────────────────────────────────────────────────────────
def test_ref_index_never_lets_the_model_invent_a_photo_id(data, monkeypatch):
    _wire(data, _Svc(items=_ITEMS), monkeypatch)
    data.apply_action("refresh", {})
    ids = {r["id"] for r in data.ref_index()}
    assert ids == {"p1", "p2"}


def test_the_digest_names_the_totals_when_connected_and_says_so_when_not(data, monkeypatch):
    _wire(data, _Svc(connected=False), monkeypatch)
    assert "conectado" in data.prompt_digest()
    _wire(data, _Svc(items=_ITEMS, total=2), monkeypatch)
    data.apply_action("refresh", {})
    assert "2" in data.prompt_digest()


# ── the cheap-read contract ───────────────────────────────────────────────────────────────────────────────
def test_view_data_never_touches_the_connector(data, monkeypatch):
    def explode():
        raise AssertionError("view_data reached the connector")
    monkeypatch.setattr(data, "_svc", explode)
    out = data.view_data()
    assert out["connected"] is False and out["items"] == []


def test_the_connector_is_imported_LAZILY_so_the_catalog_stays_cheap(data):
    src = (_WIDGET / "data.py").read_text(encoding="utf-8")
    head = src.split("def ")[0]
    assert "from connectors" not in head and "import httpx" not in head


def test_background_only_polls_while_a_session_is_pending(data, monkeypatch):
    """No standing library to watch (Google never re-serves it) — polling forever would burn quota to answer
    a question nobody asked, the same reasoning `archivos` already applies to its own connector."""
    svc = _wire(data, _Svc(items=_ITEMS), monkeypatch)

    class _Ctx:
        pass

    data.tick(_Ctx())
    assert svc.calls == [], "no pending session -> tick must not touch the connector at all"

    db = data._load()
    db["session_pending"] = True
    data._save(db)
    data.tick(_Ctx())
    assert ("poll_session",) in svc.calls


# ── the client-side house rules ───────────────────────────────────────────────────────────────────────────
def test_the_card_does_no_network_calls_and_builds_its_dom_safely():
    """Every filename comes from Google. `<img onerror=…>` is a legal filename in every provider."""
    raw = (_WIDGET / "widget.js").read_text(encoding="utf-8")
    js = re.sub(r"^\s*//.*$", "", raw, flags=re.M)
    assert "fetch(" not in js, "widgets are self-contained; the picker round trip goes through a declared action"
    assert not re.search(r"\.(inner|outer)HTML\s*=", js), "build DOM with textContent, never an HTML sink"
    assert "insertAdjacentHTML" not in js and "document.write" not in js
    assert "textContent" in raw or "img.alt" in raw
