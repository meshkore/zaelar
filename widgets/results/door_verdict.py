"""widgets/results/door_verdict.py — what the sheet's door DID with rows a worker handed over, said back to it.

search-rent-apartment ES (2026-10-14, sandbox 093858-es). The worker extracted real Fotocasa flats («Apartamento
con 1 baño en Valencia…», «Piso con 2 baños en Valencia…», with price and url) three times; the door
(`category_gate`) filed every one in the Rejected tab — «does not name «ruzafa»» — and the sheet ended with 0 items
after 400 s. The gate's reply carries a `note_for_worker` naming each row and why, but the extraction's door
(`results.intake.push`) returns a bare count and dropped it: the worker read its own listings back, believed they
were on his sheet, and kept browsing.

`intake.push` records here what landed against what it handed, with the door's note; the worker-facing reply of
the same step (`navegador_act` extract, a worker's `web_search`) takes it. Nothing to say → {}: a reply only grows
when the door turned something away.
"""
from __future__ import annotations

_LAST: dict[str, dict] = {}
_MAX_SHEETS = 32


def on_sheet(handed: list[dict], items: list[dict]) -> int:
    """How many handed rows the sheet holds now — a re-sent row the sheet already had counts (it IS on it). By url,
    else by the title's head: the card clips long titles, so the full one never matches its own row."""
    urls = {str(i.get("url") or "").strip().lower() for i in items} - {""}
    heads = {str(i.get("title") or "").strip().lower()[:30] for i in items} - {""}
    return sum(1 for h in handed
               if (str(h.get("url") or "").strip().lower() in urls if str(h.get("url") or "").strip()
                   else str(h.get("title") or "").strip().lower()[:30] in heads))


def record(sheet: str, handed: int, landed: int, reply: dict | None) -> None:
    """The door's verdict on one push to `sheet` (the latest one wins)."""
    note = str((reply or {}).get("note_for_worker") or "").strip()
    if landed >= handed and not note:
        _LAST.pop(str(sheet or ""), None)
        return
    if len(_LAST) >= _MAX_SHEETS:
        _LAST.pop(next(iter(_LAST)))
    _LAST[str(sheet or "")] = {"handed": int(handed), "landed": int(landed), "note": note}


def take(sheet: str) -> dict:
    """`{"door": {...}}` for the worker's reply, once — or {} when every row landed and the door said nothing."""
    v = _LAST.pop(str(sheet or ""), None)
    if not v:
        return {}
    head = f"{v['landed']} of the {v['handed']} rows you handed over landed on his sheet."
    if v["landed"] < v["handed"]:
        head += (" The rest are NOT on it: if one is what he asked for, name it with its link in your report — "
                 "never tell him it is on the sheet.")
    return {"door": {**v, "note": (head + " " + v["note"]).strip()}}
