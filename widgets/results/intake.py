"""widgets/results/intake.py — THE ONE DOOR through which a browser finding enters the results sheet (V2-257).

Why a module and not three `apply_action("append", …)` calls: because there ARE three callers, and until today all
three wrote somewhere else. `act_api._hand_over` (what a worker extracts), `owner._automate` (the engine's own
loop) and `dispatch._finalize_web` (the final scrape of the tab) every one of them ended at
`navegador.tasks.set_results()`, which writes the CARD. Meanwhile a `kind:"web"` errand resolves `surface = LIST`,
so `dispatch._sheet_open()` opens the results sheet in front of the operator the moment the errand is placed —
and nothing ever put anything in it. The sheet was empty by construction, and the harness read that as an
extraction failure (`missing_signals: ['widget']`, V2-223). It was not: there was no door.

Three decisions worth stating, because each one has an obvious wrong alternative:

  · **`append`, never `present`.** Several browsers can work on one errand and each finds its own things; the
    sheet is single and has to ACCUMULATE. `present` replaces, so the second browser would erase the first one's
    findings. Deduplication by title+url already lives in the sheet, so a re-extraction of the same page is not a
    second result — and neither is the worker filing its own report on top of what we pushed.
  · **The SOURCE travels with the finding.** Where a row came from is the difference between a result and a
    rumour, and the sheet already has a tab for it. Reporting it here rather than asking the worker to remember
    means it is reported for every route, including the two that have no model in them at all.
  · **`tel` becomes a FACT.** The sheet's item schema is closed (`_ITEM_FIELDS`) and has no phone field; dropping
    it on the floor would be V2-240's defect again — on a service errand the phone number is the datum that
    RESOLVES the errand. `facts` is exactly the structured half the operator asks about later.

Fail-soft everywhere: a browser finding that cannot reach the sheet must never take down the extraction, the
worker, or the turn. It returns how many rows landed so a caller can say so instead of guessing.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

#: Browser rows are noisy at the tail; the sheet keeps its own global cap too.
_MAX_PER_PUSH = 12


def _to_item(row: dict) -> dict | None:
    """One browser row → one sheet item. Returns None for a row with no name: the sheet drops it anyway
    (`_clean_item`), and dropping it here keeps the reported count honest."""
    if not isinstance(row, dict):
        return None
    title = str(row.get("title") or "").strip()
    if not title:
        return None
    item: dict = {"title": title}
    for src, dst in (("subtitle", "subtitle"), ("price", "price"), ("url", "url"), ("image", "image")):
        v = str(row.get(src) or "").strip()
        if v:
            item[dst] = v
    tel = str(row.get("tel") or "").strip()
    _facts = [f for f in (row.get("facts") or []) if isinstance(f, dict)]
    if tel:
        _facts = [{"label": "Teléfono", "value": tel}] + _facts
    if _facts:
        item["facts"] = _facts
    return item


def push(rows, *, sheet: str = "", source_url: str = "", source_name: str = "",
         status: str = "ok") -> int:
    """Put what a browser just found into the sheet. Returns how many rows were handed over (0 if none/failed).

    The count is what LANDED in the payload, not what the sheet decided to keep after deduplication: this
    function's honest claim is «I handed over N», and how many were already there is the sheet's business.
    """
    items = [i for i in (_to_item(r) for r in (rows or [])) if i][:_MAX_PER_PUSH]
    if not items:
        return 0
    # V2-259 — a qué hoja. Es el ENCARGO, no el navegador: dos navegadores del mismo encargo entregan en la
    # misma hoja (V2-257), dos encargos son dos hojas. Sin `sheet` esto entrega en la hoja de siempre, que es lo
    # correcto para un navegador que el operador conduce a mano, sin encargo detrás.
    payload: dict = {"items": items}
    if str(sheet or "").strip():
        payload["sheet"] = str(sheet).strip()
    if source_url or source_name:
        payload["sources"] = [{"name": source_name or "", "url": source_url or "",
                               "status": status, "found": len(items)}]
    try:
        from widgets.results import data as _sheet
        res = _sheet.apply_action("append", payload)
        if not (res or {}).get("ok"):
            logger.warning("results.intake: la hoja rechazó el append (%s)", (res or {}).get("error"))
            return 0
    except Exception as e:  # noqa: BLE001
        logger.warning("results.intake: no pude entregar a la hoja (%s)", e)
        return 0
    try:
        # El aviso de repintado va a SU tarjeta: con varias hojas abiertas, avisar a «results» a pelo despierta
        # a la que no ha cambiado y deja quieta a la que sí.
        from voice.observer import emit
        from widgets.results import data as _d
        emit("widget", "data", extra={"id": _d.instance_id(str(sheet or "")), "src": "navegador"})
    except Exception:
        pass
    return len(items)
