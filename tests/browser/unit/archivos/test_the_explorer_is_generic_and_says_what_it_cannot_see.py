#
# V2-658 — the file manager: the agent's own library FIRST (full write actions, no connection needed), a
# generic cloud provider BESIDE it (read + search + open only — a write action refuses BY NAME).
#
# What is worth guarding here is not «it lists files» (a real drive needs a live account and lives in the live
# node) but the decisions that make the merge correct and that a later edit can quietly undo:
#
#   · `local` is the DEFAULT provider and needs no connection — `connected` reads True from the first render.
#   · A cloud provider's write actions (rename/copy/delete) are refused BY NAME, never silently no-op'd.
#   · The library has no real nested folders — a shelf is a CLASSIFICATION (by extension), so `open_folder`
#     only ever goes one level deep and there is no cross-shelf move.
#   · Opening a file never reaches into `widgets.youtube`/`widgets.musica` directly — only `nucleo.library_router`.
#   · NO ACTION PAYLOAD MAY CARRY A CREDENTIAL (V2-520), and `view_data` stays network-free (V2-557).
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
    """A private workspace — a unit test never touches the operator's real library or cloud drive."""
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
    """A stand-in for `connectors.files.service` — the seam the widget talks through for cloud providers."""

    def __init__(self, connected=True, entries=None, reason="", error="", browsable=True, depth=1):
        self.connected, self.reason, self.error = connected, reason, error
        self.entries = entries if entries is not None else []
        self.browsable = browsable
        self.depth = depth
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


def _switch_to_cloud(mod, svc, monkeypatch):
    """Wire the cloud stub AND actually switch the widget onto it — the default provider is `local` now."""
    _wire(mod, svc, monkeypatch)
    out = mod.apply_action("set_provider", {"provider": "gdrive"})
    assert out["ok"], out
    return svc


_FILES = [
    {"id": "d1", "name": "Contratos", "kind": "folder", "mime": "", "size": None,
     "modified": "", "web_url": "", "provider": "gdrive"},
    {"id": "f1", "name": "Contrato Axa.pdf", "kind": "file", "mime": "application/pdf", "size": 120,
     "modified": "2026-01-02T10:00:00Z", "web_url": "https://example.invalid/f", "provider": "gdrive"},
]


# ── the contract with the brain ────────────────────────────────────────────────────────────────────────────
def test_every_declared_action_is_handled_and_every_handled_one_is_declared():
    src = (_WIDGET / "data.py").read_text(encoding="utf-8")
    handled = set(re.findall(r'act == "([a-z_]+)"', src))
    for grp in re.findall(r"act in \(([^)]*)\)", src):
        handled |= {x.strip().strip('"') for x in grp.split(",") if x.strip()}
    assert set(_manifest()["actions"]) == handled


def test_the_actions_that_NAVIGATE_are_view_actions():
    from widgets import actions as wactions
    acts = _manifest()["actions"]
    for name in ("open_folder", "go_up", "go_home", "search_files", "open_file", "refresh"):
        assert wactions.is_view(acts[name], name), f"«{name}» answers a look order and must be a view action"


def test_the_write_actions_are_NOT_view_actions():
    from widgets import actions as wactions
    acts = _manifest()["actions"]
    for name in ("rename_file", "copy_file", "delete_file"):
        assert not wactions.is_view(acts[name], name), f"«{name}» mutates a real file — never a view action"


def test_disconnecting_and_deleting_ask_first_navigating_never_does():
    from widgets import actions as wactions
    acts = _manifest()["actions"]
    assert wactions.classify(acts["disconnect_provider"], "disconnect_provider") == wactions.CONFIRM
    assert wactions.classify(acts["delete_file"], "delete_file") == wactions.CONFIRM
    for name in ("open_folder", "search_files", "refresh", "set_view", "rename_file", "copy_file"):
        assert wactions.classify(acts[name], name) == wactions.FAST, f"«{name}» is reversible; do not gate it"


def test_NO_action_payload_carries_a_credential():
    blob = json.dumps(_manifest()["actions"]).lower()
    for word in ("client_secret", "client_id", "token", "password", "secret", "refresh_token"):
        assert word not in blob, f"«{word}» must never be an action payload field"


def test_the_routing_line_fits_the_budget_it_is_measured_against():
    from widgets import brief
    m = _manifest()
    assert len(m["whenToUse"]) <= brief._PURPOSE_CAP, len(m["whenToUse"])
    assert brief._purpose(m["whenToUse"]) == m["whenToUse"]
    assert "FRONTERA" in m["whenToUse"]


def test_the_router_is_reached_only_from_the_orchestration_layer_never_directly():
    """`widgets/AGENTS.md`'s isolation rule: a widget never imports another widget's `data.py`."""
    src = (_WIDGET / "data.py").read_text(encoding="utf-8")
    assert "widgets.youtube" not in src and "widgets.musica" not in src
    assert "library_router" in src


# ── local is the default, and needs nothing connected ─────────────────────────────────────────────────────
def test_local_is_the_default_provider_and_is_usable_with_nothing_connected(data):
    vd = data.view_data()
    assert vd["provider"] == "local"
    assert vd["connected"] is True


def test_view_data_never_touches_the_network_even_for_the_provider_row(data, monkeypatch):
    def explode():
        raise AssertionError("view_data reached the connector")
    monkeypatch.setattr(data, "_svc", explode)
    out = data.view_data()
    assert out["provider"] == "local" and out["connected"] is True


def test_the_home_screen_lists_the_five_shelves_with_real_counts(data):
    from library import paths as lib_paths
    (lib_paths.dir_for("video") / "pelicula.mp4").write_bytes(b"x")
    (lib_paths.dir_for("images") / "foto.jpg").write_bytes(b"x")
    (lib_paths.dir_for("images") / "otra.png").write_bytes(b"x")
    out = data.apply_action("refresh", {})
    assert out["ok"], out
    shelves = {e["id"]: e for e in data.view_data()["entries"]}
    assert set(shelves) == {"shelf:video", "shelf:audio", "shelf:documents", "shelf:images", "shelf:downloads"}
    assert shelves["shelf:video"]["count"] == 1
    assert shelves["shelf:images"]["count"] == 2
    assert shelves["shelf:audio"]["count"] == 0


def test_opening_a_shelf_lists_only_its_own_kind(data):
    from library import paths as lib_paths
    (lib_paths.dir_for("video") / "pelicula.mp4").write_bytes(b"x")
    (lib_paths.dir_for("audio") / "cancion.mp3").write_bytes(b"x")
    out = data.apply_action("open_folder", {"folderId": "shelf:video"})
    assert out["ok"] and out["count"] == 1
    names = [e["name"] for e in data.view_data()["entries"]]
    assert names == ["pelicula.mp4"]


def test_opening_a_shelf_by_its_bare_kind_name_also_works(data):
    """The model may say the kind directly (`video`) instead of the internal `shelf:video` id."""
    out = data.apply_action("open_folder", {"folderId": "video"})
    assert out["ok"] and data.view_data()["folder_id"] == "shelf:video"


def test_going_up_from_a_shelf_returns_home_one_level_deep(data):
    data.apply_action("open_folder", {"folderId": "shelf:video"})
    out = data.apply_action("go_up", {})
    assert out["ok"]
    assert data.view_data()["folder_id"] == ""


def test_search_files_matches_across_every_shelf(data):
    from library import paths as lib_paths
    (lib_paths.dir_for("video") / "vacaciones.mp4").write_bytes(b"x")
    (lib_paths.dir_for("images") / "vacaciones.jpg").write_bytes(b"x")
    (lib_paths.dir_for("documents") / "factura.pdf").write_bytes(b"x")
    out = data.apply_action("search_files", {"query": "vacaciones"})
    assert out["ok"] and out["count"] == 2
    names = {m["name"] for m in out["matches"]}
    assert names == {"vacaciones.mp4", "vacaciones.jpg"}


def test_opening_a_playable_local_video_routes_through_the_orchestrator(data, monkeypatch):
    from library import paths as lib_paths
    (lib_paths.dir_for("video") / "pelicula.mp4").write_bytes(b"x")
    calls = []
    monkeypatch.setattr("nucleo.library_router.route_video",
                         lambda rel, title="": calls.append((rel, title)) or {"ok": True})
    out = data.apply_action("open_file", {"fileId": "video/pelicula.mp4"})
    assert out["ok"] and calls, calls


def test_opening_an_unplayable_local_video_refuses_with_a_download_link(data):
    from library import paths as lib_paths
    (lib_paths.dir_for("video") / "pelicula.mkv").write_bytes(b"x")
    out = data.apply_action("open_file", {"fileId": "video/pelicula.mkv"})
    assert out["ok"] is False
    assert out["download_url"], "a refusal with no way round reads as a broken file"


def test_opening_a_playable_local_image_previews_INSIDE_the_card(data):
    from library import paths as lib_paths
    (lib_paths.dir_for("images") / "foto.jpg").write_bytes(b"x")
    out = data.apply_action("open_file", {"fileId": "images/foto.jpg"})
    assert out["ok"] and out["preview"]["kind"] == "image"


def test_renaming_a_local_file_works(data):
    from library import paths as lib_paths
    (lib_paths.dir_for("documents") / "vieja.txt").write_text("x")
    out = data.apply_action("rename_file", {"fileId": "documents/vieja.txt", "name": "nueva.txt"})
    assert out["ok"], out
    assert (lib_paths.dir_for("documents") / "nueva.txt").exists()
    assert not (lib_paths.dir_for("documents") / "vieja.txt").exists()


def test_copying_a_local_file_duplicates_it_in_place(data):
    from library import paths as lib_paths
    (lib_paths.dir_for("documents") / "original.txt").write_text("x")
    out = data.apply_action("copy_file", {"fileId": "documents/original.txt"})
    assert out["ok"], out
    assert (lib_paths.dir_for("documents") / "original (copia).txt").exists()
    assert (lib_paths.dir_for("documents") / "original.txt").exists(), "the original must survive a copy"


def test_deleting_a_local_file_removes_it_from_disk(data):
    from library import paths as lib_paths
    (lib_paths.dir_for("documents") / "borrame.txt").write_text("x")
    out = data.apply_action("delete_file", {"fileId": "documents/borrame.txt"})
    assert out["ok"], out
    assert not (lib_paths.dir_for("documents") / "borrame.txt").exists()


# ── local files never silently download a second copy (V2-658 follow-up) ──────────────────────────────────
def test_a_self_hosted_engine_reveals_an_unplayable_local_file_in_place(data, monkeypatch):
    """The operator's own report: double-clicking an unplayable local video downloaded a SECOND copy into
    his Mac's Downloads folder, next to the one already sitting in Zaelar's own library — a wasteful
    duplicate on the SAME disk. Self-host: reveal it, never silently fetch a copy."""
    from library import paths as lib_paths
    (lib_paths.dir_for("video") / "pelicula.mkv").write_bytes(b"x")           # .mkv: video, unplayable
    monkeypatch.setattr("nucleo.cloud_account.is_cloud_account", lambda: False)
    monkeypatch.setattr(data, "_reveal_in_os", lambda p: True)
    out = data.apply_action("reveal_local_file", {"fileId": "video/pelicula.mkv"})
    assert out["ok"], out
    assert out["path"].endswith("pelicula.mkv") and out["opened"] is True


def test_a_cloud_hosted_engine_refuses_to_reveal_anything_naming_why(data, monkeypatch):
    """No local disk of the OPERATOR's exists to reveal on a cloud Machine — offering the gesture there would
    open a window on a remote server nobody is looking at, so it is refused, by name, instead."""
    from library import paths as lib_paths
    (lib_paths.dir_for("video") / "pelicula.mkv").write_bytes(b"x")
    monkeypatch.setattr("nucleo.cloud_account.is_cloud_account", lambda: True)
    out = data.apply_action("reveal_local_file", {"fileId": "video/pelicula.mkv"})
    assert out["ok"] is False and "nube" in out["error"]


def test_reveal_local_file_is_refused_on_a_cloud_PROVIDER_regardless_of_where_the_engine_runs(data, monkeypatch):
    """Two independent axes: this gate is about which PROVIDER is on screen (Drive has no local disk at all),
    not whether the engine itself is self-hosted — a cloud-drive row must be refused even mid-self-host."""
    svc = _switch_to_cloud(data, _Svc(entries=_FILES), monkeypatch)
    svc.calls.clear()
    monkeypatch.setattr("nucleo.cloud_account.is_cloud_account", lambda: False)
    out = data.apply_action("reveal_local_file", {"fileId": "f1"})
    assert out["ok"] is False and "gdrive" in out["error"]
    assert not svc.calls, "a refused reveal must never round-trip to the cloud provider"


def test_every_local_row_carries_whether_this_is_the_same_machine(data, monkeypatch):
    from library import paths as lib_paths
    (lib_paths.dir_for("documents") / "a.txt").write_text("x")
    monkeypatch.setattr("nucleo.cloud_account.is_cloud_account", lambda: False)
    data.apply_action("open_folder", {"folderId": "shelf:documents"})
    rows = data.view_data()["entries"]
    assert rows and rows[0]["same_machine"] is True

    monkeypatch.setattr("nucleo.cloud_account.is_cloud_account", lambda: True)
    data.apply_action("refresh", {})
    rows = data.view_data()["entries"]
    assert rows and rows[0]["same_machine"] is False


def test_an_unreadable_same_machine_signal_defaults_to_the_safe_no(data, monkeypatch):
    """A broken/unimportable signal must never grant an OS-shell-out affordance nobody asked to expose."""
    monkeypatch.setattr("nucleo.cloud_account.is_cloud_account",
                        lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    assert data._same_machine() is False


# ── a cloud provider cannot write, and says so ─────────────────────────────────────────────────────────────
def test_a_cloud_provider_refuses_rename_copy_and_delete_BY_NAME(data, monkeypatch):
    svc = _switch_to_cloud(data, _Svc(entries=_FILES), monkeypatch)
    svc.calls.clear()
    for action in ("rename_file", "copy_file", "delete_file"):
        out = data.apply_action(action, {"fileId": "f1", "name": "x"})
        assert out["ok"] is False and "gdrive" in out["error"], out
    assert not svc.calls, "a refused write must never round-trip to the provider"


def test_switching_back_to_local_needs_no_connection_either(data, monkeypatch):
    _switch_to_cloud(data, _Svc(entries=_FILES), monkeypatch)
    out = data.apply_action("set_provider", {"provider": "local"})
    assert out["ok"] and data.view_data()["provider"] == "local"


# ── the two states that look alike, for the cloud side ─────────────────────────────────────────────────────
def test_a_permission_that_cannot_list_is_reported_not_swallowed(data, monkeypatch):
    _switch_to_cloud(data, _Svc(entries=[], reason="Le diste el permiso estrecho.", browsable=False), monkeypatch)
    out = data.apply_action("refresh", {})
    assert out["ok"] and out["reason"], out
    assert data.view_data()["reason"]
    assert "estrecho" in data.prompt_digest()


def test_an_empty_folder_says_empty_and_carries_no_reason(data, monkeypatch):
    _switch_to_cloud(data, _Svc(entries=[]), monkeypatch)
    data.apply_action("refresh", {})
    assert data.view_data()["reason"] == ""
    assert "VACÍA" in data.prompt_digest()


def test_switching_to_an_unconnected_cloud_provider_is_refused_by_name(data, monkeypatch):
    _wire(data, _Svc(entries=_FILES, connected=False), monkeypatch)
    out = data.apply_action("set_provider", {"provider": "gdrive"})
    assert out["ok"] is False and "gdrive" in out["error"]
    assert data.view_data()["provider"] == "local", "a refused switch must not strand the card off local"


# ── answering, not just repainting ─────────────────────────────────────────────────────────────────────────
def test_a_cloud_search_hands_its_matches_BACK(data, monkeypatch):
    _switch_to_cloud(data, _Svc(entries=_FILES), monkeypatch)
    out = data.apply_action("search_files", {"query": "axa"})
    assert out["ok"] and out["query"] == "axa"
    names = [m["name"] for m in out["matches"]]
    assert "Contrato Axa.pdf" in names


def test_a_search_with_no_words_is_refused_with_a_sentence(data):
    out = data.apply_action("search_files", {"query": "   "})
    assert out["ok"] is False and "busco" in out["error"]


def test_opening_a_cloud_file_returns_its_link_and_does_NOT_reach_another_widget(data, monkeypatch):
    _switch_to_cloud(data, _Svc(entries=_FILES), monkeypatch)
    out = data.apply_action("open_file", {"fileId": "f1"})
    assert out["ok"] and out["file"]["web_url"].startswith("https://")


def test_an_unknown_action_lists_the_ones_that_exist(data):
    out = data.apply_action("teleport", {})
    assert out["ok"] is False and "search_files" in out["error"]


def test_open_folder_without_a_target_teaches_the_shape_instead_of_guessing(data):
    out = data.apply_action("open_folder", {})
    assert out["ok"] is False and "carpeta" in out["error"]


# ── cloud navigation arithmetic (unchanged from V2-557) ────────────────────────────────────────────────────
def test_going_up_from_one_cloud_level_lands_on_the_ROOT_not_on_itself(data, monkeypatch):
    svc = _switch_to_cloud(data, _Svc(entries=_FILES), monkeypatch)
    data.apply_action("open_folder", {"folderId": "d1"})
    svc.calls.clear()
    data.apply_action("go_up", {})
    assert ("list_folder", "") in svc.calls


def test_going_up_from_two_cloud_levels_lands_on_the_PARENT_not_on_the_root(data, monkeypatch):
    svc = _switch_to_cloud(data, _Svc(entries=_FILES, depth=2), monkeypatch)
    data.apply_action("open_folder", {"folderId": "d1"})
    svc.calls.clear()
    data.apply_action("go_up", {})
    assert ("list_folder", "a") in svc.calls, svc.calls


def test_entering_a_cloud_folder_clears_a_previous_search(data, monkeypatch):
    _switch_to_cloud(data, _Svc(entries=_FILES), monkeypatch)
    data.apply_action("search_files", {"query": "axa"})
    data.apply_action("open_folder", {"folderId": "d1"})
    assert data.view_data()["query"] == ""


def test_refreshing_a_cloud_SEARCH_repeats_the_search_and_not_the_folder(data, monkeypatch):
    svc = _switch_to_cloud(data, _Svc(entries=_FILES), monkeypatch)
    data.apply_action("search_files", {"query": "axa"})
    svc.calls.clear()
    data.apply_action("refresh", {})
    assert svc.calls and svc.calls[0][0] == "search"


# ── the references the model resolves against ──────────────────────────────────────────────────────────────
def test_ref_index_tells_a_shelf_from_a_file_by_the_FIELD_it_fills(data):
    from library import paths as lib_paths
    (lib_paths.dir_for("video") / "pelicula.mp4").write_bytes(b"x")
    data.apply_action("refresh", {})
    idx = {r["label"]: r["field"] for r in data.ref_index()}
    assert idx["Vídeo"] == "folderId"


def test_ref_index_on_a_cloud_folder_tells_a_folder_from_a_file(data, monkeypatch):
    _switch_to_cloud(data, _Svc(entries=_FILES), monkeypatch)
    data.apply_action("refresh", {})
    idx = {r["label"]: r["field"] for r in data.ref_index()}
    assert idx["Contratos"] == "folderId" and idx["Contrato Axa.pdf"] == "fileId"


def test_the_digest_names_the_provider_and_caps_what_it_sends(data):
    from library import paths as lib_paths
    for i in range(60):
        (lib_paths.dir_for("documents") / f"fichero-{i}.txt").write_text("x")
    data.apply_action("open_folder", {"folderId": "shelf:documents"})
    dig = data.prompt_digest()
    assert "biblioteca" in dig
    assert dig.count("fichero-") <= data.DIGEST_ENTRIES
    assert "más" in dig


# ── the cheap-read contract ────────────────────────────────────────────────────────────────────────────────
def test_a_cold_store_asks_for_a_listing_exactly_once(data):
    assert data.view_data()["needs_refresh"] is True
    data.apply_action("refresh", {})
    assert data.view_data()["needs_refresh"] is False


def test_the_connector_is_imported_LAZILY_so_the_catalog_stays_cheap(data):
    src = (_WIDGET / "data.py").read_text(encoding="utf-8")
    head = src.split("def ")[0]
    assert "from connectors" not in head and "import httpx" not in head


# ── the client-side house rules ────────────────────────────────────────────────────────────────────────────
def test_the_card_does_no_network_and_builds_its_dom_safely():
    raw = (_WIDGET / "widget.js").read_text(encoding="utf-8")
    js = re.sub(r"^\s*//.*$", "", raw, flags=re.M)
    assert "fetch(" not in js, "widgets are self-contained; consent goes through a declared action"
    assert not re.search(r"\.(inner|outer)HTML\s*=", js), "build DOM with textContent, never an HTML sink"
    assert "insertAdjacentHTML" not in js and "document.write" not in js
    assert "textContent" in raw
