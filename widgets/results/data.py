#
# results widget — backend. INTENTIONALLY does no searching of its own: the results grid is filled by the BRAIN
# (Hermes) via the [[push:results]]{json}[[/push]] protocol, which renders with the pushed data and skips this
# endpoint entirely. This view_data is the fallback when the widget is shown WITHOUT pushed data — it returns the
# user's current project layout: the two main jobs (Pricewaterhouse and Mage Core) share the first row as primaries,
# and the side projects below in two columns. Items follow the widget contract: primary=true puts items in the
# top row; subtitle shows under the title.
#


def view_data(q: str = "") -> dict:
    return {
        "title": "Proyectos",
        "subtitle": (q or "").strip()[:80],
        "items": [
            {"title": "Pricewaterhouse", "primary": True},
            {"title": "Mage Core", "primary": True},
            {"title": "MeshKore", "subtitle": "Side project"},
            {"title": "CryptoKnight", "subtitle": "Side project"},
            {"title": "Marketing Reddit", "subtitle": "Side project"},
        ],
    }


# "choose" lets the operator PICK one of the pushed items (e.g. an available product name from a real search the
# brain ran and pushed via [[push:results]]). It intentionally does NOT call store.save(): the pushed list is
# ephemeral (never lands in this file — see widget.js), so triggering the canvas's SSE refresh would just re-fetch
# view_data()'s static fallback above and wipe the real list off-screen. The pick is applied instantly client-side
# (widget.js) using this call's return value; this just echoes the choice back for the brain's turn to act on.
def apply_action(action: str, payload: dict | None = None) -> dict:
    payload = payload or {}
    if action == "choose":
        title = str(payload.get("title", "")).strip()
        return {"ok": bool(title), "chosen": title}
    return {"ok": False}
