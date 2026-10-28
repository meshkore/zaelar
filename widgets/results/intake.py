"""widgets/results/intake.py — THE ONE DOOR through which a browser finding enters the results sheet (V2-257).

Three callers (`act_api._hand_over`, `owner._automate`, `dispatch._finalize_web`) used to write only the browser
CARD while a `kind:"web"` errand opened an empty sheet. Decisions with an obvious wrong alternative:
  · **`append`, never `present`** — several browsers can work one errand; the sheet ACCUMULATES (dedup by title+url).
  · **The SOURCE travels with the finding**, for every route, including the two with no model in them.
  · **`tel` becomes a FACT** — the item schema has no phone field, and on a service errand it RESOLVES the errand.
Fail-soft: a finding that cannot reach the sheet never takes down the extraction; it returns how many rows landed.
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


def _claim_shared(errand: str) -> None:
    """V2-831 — the SHARED sheet belongs to one errand at a time. A push that names no sheet but names the errand it
    comes from takes the shared sheet over: rows another errand (or nobody) left there are not this errand's results,
    so the sheet starts blank under the new owner instead of appending onto them (2026-10-28: six school-canteen
    rows from an earlier search sat above a streaming errand's offers). The same errand pushing again appends."""
    from widgets.results import data as _sheet
    cur = _sheet.view_data("")
    if str(cur.get("errand") or "") == errand:
        return
    # an empty sheet keeps what it holds (the title `begin_task` just gave it); one with someone else's rows restarts
    fresh = dict(cur) if not cur.get("items") else _sheet._empty()
    fresh["errand"] = errand
    _sheet._save(fresh, "")


def push(rows, *, sheet: str = "", source_url: str = "", source_name: str = "",
         status: str = "ok", errand: str = "") -> int:
    """Put what a browser just found into the sheet. Returns how many rows were handed over (0 if none/failed).

    The count is what LANDED in the payload, not what the sheet decided to keep after deduplication: this
    function's honest claim is «I handed over N», and how many were already there is the sheet's business.
    """
    items = [i for i in (_to_item(r) for r in (rows or [])) if i][:_MAX_PER_PUSH]
    if not items:
        return 0
    # V2-259 — which sheet. It is the ERRAND, not the browser: two browsers on the same errand deliver to the
    # same sheet (V2-257), while two errands mean two sheets. Without `sheet`, this delivers to the usual sheet,
    # which is correct for a browser the operator is driving manually, with no errand behind it. A caller that has
    # an errand but no sheet passes `errand=`, and the shared sheet is that errand's from then on (V2-831).
    payload: dict = {"items": items}
    if str(sheet or "").strip():
        payload["sheet"] = str(sheet).strip()
    elif str(errand or "").strip():
        try:
            _claim_shared(str(errand).strip())
        except Exception as e:  # noqa: BLE001 — an unclaimed sheet still takes the delivery
            logger.warning("results.intake: could not claim the shared sheet (%s)", e)
    if source_url or source_name:
        payload["sources"] = [{"name": source_name or "", "url": source_url or "",
                               "status": status, "found": len(items)}]
    try:
        from widgets.results import data as _sheet
        res = _sheet.apply_action("append", payload)
        if not (res or {}).get("ok"):
            logger.warning("results.intake: la hoja rechazó el append (%s)", (res or {}).get("error"))
            return 0
        # what the door KEPT, told to the worker that handed it (`door_verdict`) and to the harness's clock below
        from widgets.results import door_verdict
        landed = door_verdict.on_sheet(items, _sheet.view_data(str(sheet or "")).get("items") or [])
        door_verdict.record(str(sheet or ""), len(items), landed, res)
    except Exception as e:  # noqa: BLE001
        logger.warning("results.intake: no pude entregar a la hoja (%s)", e)
        return 0
    try:
        # The repaint notification goes to ITS card: with several sheets open, notifying «results» directly wakes
        # the one that did not change and leaves the one that did unchanged.
        from voice.observer import emit
        from widgets.results import data as _d
        emit("widget", "data", extra={"id": _d.instance_id(str(sheet or "")), "src": "navegador", "landed": landed})
    except Exception as e:  # noqa: BLE001 — a repaint that cannot be announced never undoes the delivery
        logger.debug("results.intake: repaint emit failed (%s)", e)
    return len(items)
