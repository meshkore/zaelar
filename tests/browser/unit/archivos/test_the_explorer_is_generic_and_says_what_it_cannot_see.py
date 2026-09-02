#
# V2-557 — the cloud file explorer: the contract, the boundaries, and the two states that look alike.
#
# What is worth guarding here is not «it lists files» (that needs a real drive and lives in the live node) but
# the four decisions that make this widget correct and that a later edit can quietly undo:
#
#   · The action that ANSWERS the phrase this widget exists for («find me the Axa contract») has to be a VIEW
#     action and has to hand its matches BACK. An unflagged one turns a pure show order into a bare card
#     (V2-547) and a silent one leaves the turn with nothing to say (V2-541).
#   · NO ACTION PAYLOAD MAY CARRY A CREDENTIAL. Voice reaches exactly these declared actions, and V2-520's rule
#     is that voice transports intent and never a secret. This is the guard that keeps a client_secret from
#     drifting into the manifest the day somebody finds it convenient.
#   · `view_data` must stay CHEAP: it runs on every render and again on every SSE push.
#   · A permission that cannot list is NOT an empty drive — the widget has to be able to say which one it is.
#
from __future__ import annotations

import importlib
import json
import pathlib
import re

import pytest

_ENGINE = pathlib.Path(__file__).resolve().parents[4]
_WIDGET = _ENGINE / "widgets" / "archivos"


def _manifest() -> dict:
    return json.loads((_WIDGET / "manifest.json").read_text(encoding="utf-8"))


@pytest.fixture()
def data(tmp_path, monkeypatch):
    """A private store. A unit test never touches the operator's live explorer."""
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    from nucleo import workspace
    from widgets import store as wstore
    importlib.reload(workspace)
    importlib.reload(wstore)
    from widgets.archivos import data as mod
    importlib.reload(mod)
    yield mod
    importlib.reload(workspace)
    importlib.reload(wstore)


class _Svc:
    """A stand-in for `connectors.files.service` — the seam the widget talks through. Every test drives the
    widget by swapping THIS, which is also the proof that the widget is provider-agnostic: nothing in it names
    Drive or Graph."""

    def __init__(self, connected=True, entries=None, reason="", error="", browsable=True, depth=1):
        self.connected, self.reason, self.error = connected, reason, error
        self.entries = entries if entries is not None else []
        self.browsable = browsable
        self.depth = depth                 # how deep under the root the opened folder sits
        self.calls = []

    def status(self):
        provs = [{"id": "gdrive", "label": "Google Drive", "app_configured": True,
                  "connected": self.connected, "tier": "browse", "tier_label": "todo",
                  "browsable": self.browsable, "note": ""}]
        return {"ok": True, "providers": provs,
                "connected": ["gdrive"] if self.connected else [], "active": "gdrive" if self.connected else ""}

    def providers_public(self):
        return [{"id": "gdrive", "label": "Google Drive", "note": "", "default_tier": "browse",
                 "tiers": [{"id": "browse", "label": "todo", "browsable": True, "note": ""}]}]

    def _res(self, extra):
        out = {"ok": not self.error, "provider": "gdrive", "entries": self.entries,
               "next": "", "reason": self.reason}
        if self.error:
            out["error"] = self.error
        out.update(extra)
        return out

    def list_folder(self, provider="", folder_id="", page=""):
        self.calls.append(("list_folder", folder_id))
        return self._res({})

    def search(self, query, provider=""):
        self.calls.append(("search", query))
        return self._res({"query": query})

    def item(self, file_id, provider=""):
        self.calls.append(("item", file_id))
        return {"ok": True, "provider": "gdrive",
                "entry": {"id": file_id, "name": "Contrato Axa.pdf", "kind": "file",
                          "mime": "application/pdf", "size": 120, "modified": "2026-01-02T10:00:00Z",
                          "web_url": "https://example.invalid/f", "parents": []}}

    def breadcrumb(self, folder_id, provider="", max_depth=12):
        if not folder_id:
            trail = []
        elif self.depth <= 1:
            trail = [{"id": folder_id, "name": "Contratos"}]
        else:
            trail = [{"id": "a", "name": "Documentos"}, {"id": folder_id, "name": "Contratos"}]
        return {"ok": True, "provider": "gdrive", "trail": trail}


def _wire(mod, svc, monkeypatch):
    monkeypatch.setattr(mod, "_svc", lambda: svc)
    return svc


_FILES = [
    {"id": "d1", "name": "Contratos", "kind": "folder", "mime": "", "size": None,
     "modified": "", "web_url": "", "provider": "gdrive"},
    {"id": "f1", "name": "Contrato Axa.pdf", "kind": "file", "mime": "application/pdf", "size": 120,
     "modified": "2026-01-02T10:00:00Z", "web_url": "https://example.invalid/f", "provider": "gdrive"},
]


# ── the contract with the brain ────────────────────────────────────────────────────────────────────────────
def test_every_declared_action_is_handled_and_every_handled_one_is_declared():
    """The validation gate rejects either mismatch: a declared action nobody handles is a dead entry, and a
    handled one nobody declared is invisible to the brain (V2-520)."""
    src = (_WIDGET / "data.py").read_text(encoding="utf-8")
    handled = set(re.findall(r'act == "([a-z_]+)"', src))
    for grp in re.findall(r"act in \(([^)]*)\)", src):
        handled |= {x.strip().strip('"') for x in grp.split(",") if x.strip()}
    assert set(_manifest()["actions"]) == handled


def test_the_actions_that_NAVIGATE_are_view_actions():
    """«ábreme la carpeta de contratos» and «búscame el contrato» are pure show orders, and the voice rail
    refuses to run a data-op on one unless the action declares itself display-only (V2-545)."""
    from widgets import actions as wactions
    acts = _manifest()["actions"]
    for name in ("open_folder", "go_up", "go_home", "search_files", "open_file", "refresh"):
        assert wactions.is_view(acts[name], name), f"«{name}» answers a look order and must be a view action"


def test_disconnecting_asks_first_and_navigating_never_does():
    from widgets import actions as wactions
    acts = _manifest()["actions"]
    assert wactions.classify(acts["disconnect_provider"], "disconnect_provider") == wactions.CONFIRM
    for name in ("open_folder", "search_files", "refresh", "set_view"):
        assert wactions.classify(acts[name], name) == wactions.FAST, f"«{name}» is reversible; do not gate it"


def test_NO_action_payload_carries_a_credential():
    """V2-520's boundary, pinned here: voice reaches exactly these payloads. A `client_secret` field in one
    would put a credential in front of the model on every turn that lists this widget's actions — the app is
    registered ONCE in the config tab instead."""
    blob = json.dumps(_manifest()["actions"]).lower()
    for word in ("client_secret", "client_id", "token", "password", "secret", "refresh_token"):
        assert word not in blob, f"«{word}» must never be an action payload field"


def test_the_routing_line_fits_the_budget_it_is_measured_against():
    """`brief._purpose` cuts at 300 chars, and the half that gets cut is the FRONTERA clause — the one that
    keeps «enséñame la receta» out of here (V2-547)."""
    from widgets import brief
    m = _manifest()
    assert len(m["whenToUse"]) <= brief._PURPOSE_CAP, len(m["whenToUse"])
    assert brief._purpose(m["whenToUse"]) == m["whenToUse"], "it must survive whole, not merely be truncated well"
    assert "FRONTERA" in m["whenToUse"]


# ── the two states that look alike ─────────────────────────────────────────────────────────────────────────
def test_a_permission_that_cannot_list_is_reported_not_swallowed(data, monkeypatch):
    svc = _wire(data, _Svc(entries=[], reason="Le diste el permiso estrecho.", browsable=False), monkeypatch)
    out = data.apply_action("refresh", {})
    assert out["ok"] and out["reason"], out
    assert data.view_data()["reason"], "the card can only print what view_data carries"
    assert "estrecho" in data.prompt_digest(), "and the brain has to be able to SAY it"


def test_an_empty_folder_says_empty_and_carries_no_reason(data, monkeypatch):
    _wire(data, _Svc(entries=[]), monkeypatch)
    data.apply_action("refresh", {})
    assert data.view_data()["reason"] == ""
    assert "VACÍA" in data.prompt_digest()


def test_with_nothing_connected_the_error_names_the_way_out(data, monkeypatch):
    _wire(data, _Svc(connected=False), monkeypatch)
    out = data.apply_action("refresh", {})
    assert out["ok"] is False
    assert "Conectores" in out["error"], "a refusal that cannot say how to fix it gets diagnosed as a bug"


# ── answering, not just repainting ─────────────────────────────────────────────────────────────────────────
def test_a_search_hands_its_matches_BACK(data, monkeypatch):
    _wire(data, _Svc(entries=_FILES), monkeypatch)
    out = data.apply_action("search_files", {"query": "axa"})
    assert out["ok"] and out["query"] == "axa"
    names = [m["name"] for m in out["matches"]]
    assert "Contrato Axa.pdf" in names, (
        "«do I have an Axa contract?» is a QUESTION — a data-op that only repaints leaves the turn mute (V2-541)")


def test_a_search_with_no_words_is_refused_with_a_sentence(data, monkeypatch):
    _wire(data, _Svc(entries=_FILES), monkeypatch)
    out = data.apply_action("search_files", {"query": "   "})
    assert out["ok"] is False and "busco" in out["error"]


def test_opening_a_file_returns_its_link_and_does_NOT_reach_another_widget(data, monkeypatch):
    """Widgets are dumb and brain-mediated: this hands back the metadata and the BRAIN decides whether it
    becomes a document on the canvas or a page in the browser."""
    _wire(data, _Svc(entries=_FILES), monkeypatch)
    out = data.apply_action("open_file", {"fileId": "f1"})
    assert out["ok"] and out["file"]["web_url"].startswith("https://")
    src = (_WIDGET / "data.py").read_text(encoding="utf-8")
    assert "widgets.documento" not in src and "widget_cli" not in src


def test_an_unknown_action_lists_the_ones_that_exist(data, monkeypatch):
    _wire(data, _Svc(), monkeypatch)
    out = data.apply_action("teleport", {})
    assert out["ok"] is False and "search_files" in out["error"]


def test_open_folder_without_a_target_teaches_the_shape_instead_of_guessing(data, monkeypatch):
    _wire(data, _Svc(), monkeypatch)
    out = data.apply_action("open_folder", {})
    assert out["ok"] is False and "folderId" in out["error"]


# ── navigation arithmetic ──────────────────────────────────────────────────────────────────────────────────
def test_going_up_from_one_level_lands_on_the_ROOT_not_on_itself(data, monkeypatch):
    svc = _wire(data, _Svc(entries=_FILES), monkeypatch)
    data.apply_action("open_folder", {"folderId": "d1"})
    svc.calls.clear()
    data.apply_action("go_up", {})
    assert ("list_folder", "") in svc.calls, (
        "the trail is root→…→current, so with a single crumb the parent is the root")


def test_going_up_from_two_levels_lands_on_the_PARENT_not_on_the_root(data, monkeypatch):
    """The counterweight: without it, «always go to the root» would satisfy the test above."""
    svc = _wire(data, _Svc(entries=_FILES, depth=2), monkeypatch)
    data.apply_action("open_folder", {"folderId": "d1"})
    svc.calls.clear()
    data.apply_action("go_up", {})
    assert ("list_folder", "a") in svc.calls, svc.calls


def test_entering_a_folder_clears_a_previous_search(data, monkeypatch):
    _wire(data, _Svc(entries=_FILES), monkeypatch)
    data.apply_action("search_files", {"query": "axa"})
    data.apply_action("open_folder", {"folderId": "d1"})
    assert data.view_data()["query"] == "", (
        "a folder listing under a stale search label is a listing pretending to be something it is not")


def test_refreshing_a_SEARCH_repeats_the_search_and_not_the_folder(data, monkeypatch):
    svc = _wire(data, _Svc(entries=_FILES), monkeypatch)
    data.apply_action("search_files", {"query": "axa"})
    svc.calls.clear()
    data.apply_action("refresh", {})
    assert svc.calls and svc.calls[0][0] == "search"


def test_switching_to_an_unconnected_provider_is_refused_by_name(data, monkeypatch):
    _wire(data, _Svc(entries=_FILES), monkeypatch)
    out = data.apply_action("set_provider", {"provider": "onedrive"})
    assert out["ok"] is False and "onedrive" in out["error"]


# ── the references the model resolves against ──────────────────────────────────────────────────────────────
def test_ref_index_tells_a_folder_from_a_file_by_the_FIELD_it_fills(data, monkeypatch):
    _wire(data, _Svc(entries=_FILES), monkeypatch)
    data.apply_action("refresh", {})
    idx = {r["label"]: r["field"] for r in data.ref_index()}
    assert idx["Contratos"] == "folderId" and idx["Contrato Axa.pdf"] == "fileId", (
        "one field for both would let «open the budget» enter a folder named like the file")


def test_the_digest_names_where_it_is_and_caps_what_it_sends(data, monkeypatch):
    many = [{"id": f"f{i}", "name": f"fichero-{i}", "kind": "file", "mime": "", "size": None,
             "modified": "", "web_url": "", "provider": "gdrive"} for i in range(60)]
    _wire(data, _Svc(entries=many), monkeypatch)
    data.apply_action("open_folder", {"folderId": "d1"})
    dig = data.prompt_digest()
    assert "Contratos" in dig, "the brain has to know WHERE it is to answer «what is in here»"
    assert dig.count("fichero-") <= data.DIGEST_ENTRIES
    assert "más" in dig, "a truncated listing that does not say it is truncated reads as the whole folder"


# ── the cheap-read contract ────────────────────────────────────────────────────────────────────────────────
def test_view_data_never_touches_the_connector(data, monkeypatch):
    """It runs on every render and again on every SSE push; a fetch in there is an HTTP round trip per repaint."""
    def explode():
        raise AssertionError("view_data reached the connector")
    monkeypatch.setattr(data, "_svc", explode)
    out = data.view_data()
    assert out["connected"] is False and out["entries"] == []


def test_a_cold_store_asks_for_a_listing_exactly_once(data, monkeypatch):
    _wire(data, _Svc(entries=_FILES), monkeypatch)
    assert data.view_data()["needs_refresh"] is True
    data.apply_action("refresh", {})
    assert data.view_data()["needs_refresh"] is False, "a fresh cache must not re-ask on every repaint"


def test_the_connector_is_imported_LAZILY_so_the_catalog_stays_cheap(data):
    """The catalog imports every widget's data.py to build the prompt. A module-level `httpx` here would be
    paid by turns that never mention a file."""
    src = (_WIDGET / "data.py").read_text(encoding="utf-8")
    head = src.split("def ")[0]
    assert "from connectors" not in head and "import httpx" not in head


# ── the client-side house rules ────────────────────────────────────────────────────────────────────────────
def test_the_card_does_no_network_and_builds_its_dom_safely():
    """Every name it prints comes from somebody's cloud drive. `<img onerror=…>` is a legal file name."""
    raw = (_WIDGET / "widget.js").read_text(encoding="utf-8")
    # Full-line comments are stripped so a file that DOCUMENTS the rule does not fail it (the same thing
    # `widgets/validator.py` does), and the HTML sinks are matched as the ASSIGNMENT they are rather than as a
    # bare word — the dangerous thing is `x.innerHTML = …`, not the noun appearing in a sentence about it.
    js = re.sub(r"^\s*//.*$", "", raw, flags=re.M)
    assert "fetch(" not in js, "widgets are self-contained; consent goes through a declared action"
    assert not re.search(r"\.(inner|outer)HTML\s*=", js), "build DOM with textContent, never an HTML sink"
    assert "insertAdjacentHTML" not in js and "document.write" not in js
    assert "textContent" in raw
