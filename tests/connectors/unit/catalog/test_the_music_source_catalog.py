"""V2-631 — the music SOURCE catalog: what plays, what could, and why a door is shut.

The operator's directive after session 7be94951: a default catalog of music sources to search and play from,
ordered by ease of playback and ad load, with a connected source taking priority — «nos da igual de dónde
estemos reproduciendo». The mechanism split, matching what already exists: PRIORITY lives in
`connectors/music/registry.py` (connected Spotify first, YouTube-audio always available), the VISIBLE catalog
lives in `connectors/catalog/*.json` (family `musica`) + the registry's live rows — never in a prompt.

These tests pin the honest half: a source we cannot build says WHY (Amazon has no API, Deezer closed theirs,
SoundCloud stopped registering apps), and the default free source is a visible row, not an invisible fallback.
"""
from __future__ import annotations

from connectors import catalog


def _music_manifests() -> list[dict]:
    return [m for m in catalog.load_manifests() if m.get("family") == "musica"]


def test_the_free_default_source_is_a_visible_connected_row():
    """The source everything actually plays through was invisible in the Conectores tab: only Spotify had a
    row, and the answer to «¿y dónde saca la música?» lived nowhere the operator could see."""
    from connectors import registry
    rows = [r for r in registry.descriptors() if r.get("family") == "musica"]
    yt = next((r for r in rows if r["id"] == "youtube-audio"), None)
    assert yt is not None, f"the free default source has no row: {[r['id'] for r in rows]}"
    assert yt["connected"] is True and yt["auth"] == "none"


def test_every_shut_door_names_its_reason():
    """A `not-possible` source without a why-not is indistinguishable from one nobody bothered to build —
    the wishlist exists to show what we do NOT have, on purpose (INI-027's rule)."""
    for m in _music_manifests():
        if m.get("state") == "not-possible":
            assert m.get("why-not", "").strip(), f"{m['id']} is not-possible with no reason"


def test_the_catalog_covers_the_services_people_actually_name():
    """`router_guards._MUSIC_SERVICES` is the list of services operators say out loud («conéctame a Amazon
    Music») — every one of them must resolve to a catalog row that can say built/planned/why-not, so the
    model never has to invent an answer about a source we never wrote down."""
    ids = {m["id"] for m in _music_manifests()}
    for wanted in ("spotify", "apple-music", "youtube-music", "tidal", "deezer", "amazon-music"):
        assert wanted in ids, f"no catalog manifest for {wanted}"


def test_provider_priority_is_connected_first_and_the_free_source_never_disappears():
    """The operator's rule verbatim: «si el usuario conecta alguna fuente, esa pasará a ser prioritaria. Pero
    si no, tenemos esos catálogos.» — the BUILTIN order in the playback registry is that rule."""
    from connectors.music import registry as mreg
    order = list(mreg._BUILTIN.keys())
    assert order[0] == "spotify" and "youtube" in order
