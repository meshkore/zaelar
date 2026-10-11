"""A network agent's rows never open a results sheet for an errand whose deliverable is a DOCUMENT.

three-tasks-at-once (ES, 2026-10-11 11:34, sandbox 113401-es): the car REPORT's worker asked the network «coches
eléctricos ciudad», the oracle handed it a shopping agent, and `mesh_cli serve` pushed that agent's eight rows —
a 1:43 Renault 4 toy, two charging cables, a wall poster, a remote-control car — into a results sheet it opened
for the report, titled «Informe sobre coches eléctricos urbanos». From then on every prompt carried a sheet NAMED
as the report and full of toys, beside the real report in `documento`; asked «¿el informe en qué punto está?», the
turn answered «del informe no me consta ningún dato todavía».

The worker still gets the agent's answer on stdout — what it reads is untouched. Only the automatic push onto a
sheet is refused, and only for an errand whose surface is a document and not a sheet (`nucleo.surfaces`).
"""
from __future__ import annotations

#: The payload key `mesh_cli` sets on its automatic push. It never reaches the widget.
MARK = "from_network"


def refused(rec, action: str, payload: dict) -> str:
    """Why this push is refused ("" = let it through). Pops the mark either way."""
    if action != "widget_data" or not isinstance(payload, dict):
        return ""
    inner = payload.get("payload") if isinstance(payload.get("payload"), dict) else {}
    if not inner.pop(MARK, False):
        return ""
    from nucleo import surfaces
    surface = str(getattr(rec, "surface", "") or "")
    if surfaces.opens_doc(surface) and not surfaces.opens_sheet(surface):
        _emit(rec, surface)
        return "this errand delivers a document, so a network agent's rows do not open a results sheet for it"
    return ""


def _emit(rec, surface: str) -> None:
    try:
        from voice.observer import emit
        emit("widget", "🚫 off-category rows filed as rejected", role="system",
             extra={"why": "network rows for a document errand", "id": str(getattr(rec, "task_id", "")),
                    "surface": surface})
    except Exception as e:  # noqa: BLE001 — an event that cannot be emitted never blocks the bridge
        __import__("logging").getLogger(__name__).debug("network rows gate emit failed: %s", e)
