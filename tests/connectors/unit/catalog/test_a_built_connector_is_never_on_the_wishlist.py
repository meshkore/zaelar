"""V2-686 — the mechanical half of the «a new connector is DONE» checklist, enforced instead of remembered.

The connector workflow (`.meshkore/docs/ops/zaelar-new-widget-or-connector-workflow.md`) lists the places a
new connector has to be wired, and its own rule is that NONE of them fails with noise: every one of them
fails EMPTY, or renders in the wrong place, or offers the operator something he already has. A checklist
nobody runs drifts — and when this file was written it found three live drifts at once:

  * `connectors/catalog/youtube.json` was still `planned` (parked in V2-603 F2 because there was no Google
    OAuth client) long after V2-685 shipped one, so the chat wall's connectors tab was showing the operator
    a «Lo quiero» button for a connector he already had.
  * `connectors/catalog/google-calendar.json` declared id `google-calendar` while its live registry row is
    `google`, so `catalog.search()` — which ranks «connected» by comparing ids against the registry — could
    never know his calendar was linked.
  * `ChatWall.js`'s `CONN_FAMILY_ORDER` was missing `video` and `agenda`, live families since V2-597 and
    V2-679, so both rendered after Infraestructura as «a family nobody expects».

None of the three raised anything anywhere.
"""
from __future__ import annotations

import json
import pathlib

import pytest

ENGINE = pathlib.Path(__file__).resolve().parents[4]
CHATWALL = (ENGINE / "frontend" / "app" / "components" / "ChatWall.js").read_text(encoding="utf-8")
CONFIGPANEL = (ENGINE / "frontend" / "app" / "components" / "ConfigPanel.js").read_text(encoding="utf-8")

# A `built` manifest with NO live registry row. Each entry needs a reason, and each reason has to be a
# statement about the product, never «we have not got round to it».
_NOT_A_ROW = {
    # Meet is an ARGUMENT of add_meeting/update_meeting (V2-685), not a connector the operator connects:
    # its manifest exists so `catalog.search()` can find it by capability words.
    "google-meet",
    # The torrent client is a widget with its own operator switch, not an account to link (V2-637/V2-638).
    "torrent",
}


def _manifests() -> list[dict]:
    from connectors import catalog
    return catalog.load_manifests()


def _live() -> list[dict]:
    from connectors import registry
    return registry.descriptors()


def _families() -> set[str]:
    return {str(d.get("family") or "") for d in _live()} - {""}


def test_no_manifest_offers_a_connector_that_is_already_live():
    """The YouTube defect, stated as a rule: a row the registry serves may not ALSO sit on the wishlist with
    a «Lo quiero» button, because `wishlist()` is `planned` + `not-possible` and the chat wall trusts that
    split to decide which list a row came from."""
    live_ids = {str(d.get("id") or "") for d in _live()}
    offered = [m["id"] for m in _manifests()
               if m.get("state") in ("planned", "not-possible") and m.get("id") in live_ids]
    assert not offered, f"offered as missing while the registry already serves them: {offered}"


def test_every_built_manifest_has_a_live_row_or_says_why_not():
    """A `built` entry never renders in the wishlist, so if no registry row answers to its id it is visible
    NOWHERE except `search()` — which is a legitimate choice (Meet) and a silent mistake everywhere else."""
    live_ids = {str(d.get("id") or "") for d in _live()}
    orphans = [m["id"] for m in _manifests()
               if m.get("state") == "built" and m["id"] not in live_ids and m["id"] not in _NOT_A_ROW]
    assert not orphans, f"built, with no live row and no written reason: {orphans}"


@pytest.mark.parametrize("mid", sorted(_NOT_A_ROW))
def test_a_declared_exception_carries_its_reason(mid):
    """The exception set above is not a list of ids to grow quietly: an entry stays in it only while its own
    manifest explains, in writing, why it is not a row."""
    m = [x for x in _manifests() if x.get("id") == mid]
    if not m:
        pytest.skip(f"{mid} no longer exists in the catalog")
    assert str(m[0].get("notes") or "").strip(), f"{mid} is exempted and its manifest says nothing about it"


@pytest.mark.parametrize("bundle", ["es", "en"])
def test_every_live_family_has_a_name_in_BOTH_bundles(bundle):
    """`t()` returns the KEY when a string is missing and the key is truthy, so a family with no entry
    renders the literal `chat.connFamily.video` on screen — V2-538 already paid for that exact trap, and
    `connFamilySections`'s own comment forbids a `|| fam` fallback that would hide it again."""
    data = json.loads((ENGINE / "i18n" / "bundles" / f"{bundle}.json").read_text(encoding="utf-8"))
    missing = [f for f in _families() if f"chat.connFamily.{f}" not in data]
    assert not missing, f"[{bundle}] live families with no name: {missing}"


def test_every_live_family_has_a_place_in_the_chat_walls_order():
    """A family missing here does not error: it falls into the «sorted after, alphabetically» bucket meant
    for catalog-only wishlist families, and the operator finds his calendar under Infraestructura."""
    order = CHATWALL.split("CONN_FAMILY_ORDER = [", 1)[1].split("]", 1)[0]
    listed = {s.strip().strip('"\'') for s in order.split(",")}
    missing = sorted(_families() - listed)
    assert not missing, f"live families the chat wall does not order: {missing}"


def test_every_live_family_has_a_card_section_in_the_settings_panel():
    """Wiring point 4 of the workflow: the cards exist and NOBODY renders them (trap T3, measured in V2-597
    when the `fotos` rows had no section and there was nowhere to paste the client id)."""
    missing = [f for f in sorted(_families()) if f'["{f}", t(' not in CONFIGPANEL]
    assert not missing, f"live families with no section in the settings panel: {missing}"


def test_no_two_rows_answer_to_the_same_id():
    """The registry is keyed by id everywhere downstream (the panel's connect/disconnect, the catalog's
    connected ranking, the chat wall's rows). V2-685 hit this collision while writing `_google()`."""
    ids = [str(d.get("id") or "") for d in _live()]
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    assert not dupes, f"duplicate registry ids: {dupes}"
