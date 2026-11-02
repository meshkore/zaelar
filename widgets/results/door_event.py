"""widgets/results/door_event.py — ONE event per push through the sheet's door (V2-837 G10).

What landed was recorded; why the rest did not travelled only for the category gate and a correction — a dedupe, a
page filed as a source, a row past the list's cap or kept in the pool left no trace, so «the worker found 30 cars and
the sheet shows 3» could not be read off the record. Every `present`/`append` now emits `widget door` with:

    handed      rows the push carried (after cleaning)          landed   rows on the list from this push
    off         {gate: n} — the gate that turned each away (`category · route · ceiling · place · spec`), read off the
                rows the gate filed in Rejected; one it did not file again (already there, or past that tab's cap) is
                `already_rejected`
    candidacy   rows filed as pages (Sources tab)                dedupe   rows the list already had
    capped      rows past the list's cap                         pool     candidates kept off the list
    no_picture  rows on the list whose template draws a photo and that carry none (V2-840 H4) — the gap is counted
                like any other: `media.fill` then fetches what it can (`queued`) and its own `widget media` event
                says what arrived
"""
from __future__ import annotations

from loguru import logger


def off_by_gate(data: dict, rejected_before: int, n_off: int) -> dict:
    """{gate: n} for the `n_off` rows a push lost at the gate, from the Rejected entries it added after
    `rejected_before`; the rest were already there."""
    out: dict[str, int] = {}
    for r in (data.get("rejected") or [])[rejected_before:]:
        g = str((r or {}).get("gate") or "untagged")           # a gate that forgot to say so is visible, never guessed
        out[g] = out.get(g, 0) + 1
    if n_off > sum(out.values()):
        out["already_rejected"] = n_off - sum(out.values())
    return out


def emit(sheet: str, action: str, *, handed: int, landed: int, off: dict | None = None, candidacy: int = 0,
         dedupe: int = 0, capped: int = 0, pool: int = 0, media: dict | None = None) -> None:
    try:
        from voice.observer import emit as _emit
        from widgets.results import data as _d
        gates = {k: int(v) for k, v in (off or {}).items() if v}
        _emit("widget", "door", text=f"{landed}/{handed} landed", extra={
            "id": _d.instance_id(str(sheet or "")), "action": action, "handed": int(handed), "landed": int(landed),
            **({"off": gates} if gates else {}),
            **{k: int(v) for k, v in (("candidacy", candidacy), ("dedupe", dedupe), ("capped", capped),
                                        ("pool", pool)) if v},
            **{k: int(v) for k, v in (media or {}).items() if v}})
    except Exception as e:  # noqa: BLE001 — recording a push never undoes it
        logger.debug(f"door_event.emit: {e!r}")


def _pictures(sheet: str, data: dict) -> dict:
    """The rows without a picture, counted, and the fetches that will try to give them one (`media.fill`)."""
    try:
        from . import media as _media
        got = _media.fill(sheet, data)
        return {"no_picture": got.get("no_picture", 0), "picture_queued": got.get("queued", 0)}
    except Exception as e:  # noqa: BLE001 — a picture that cannot be looked for never undoes the push
        logger.debug(f"door_event._pictures: {e!r}")
        return {}


def _pool_left(data: dict) -> int:
    from . import pool as _pool
    return int(_pool.note(data).get("pool", 0) or 0)


def after_present(sheet: str, payload: dict, prev: dict, data: dict, pages: list) -> None:
    """The `present` push, read after it: what it carried, what the list now shows, what the gate filed in Rejected
    beyond what the sheet already held (`prev`), the pages moved to Sources and the pool."""
    try:
        from . import data as _d
        handed = len(_d._clean_items(payload.get("items")))
        landed = len(data.get("items") or [])
        cand = handed - len(pages)
        emit(sheet, "present", handed=handed, landed=landed, candidacy=len(pages), pool=_pool_left(data),
             off=off_by_gate(data, len(prev.get("rejected") or []), cand - landed), media=_pictures(sheet, data))
    except Exception as e:  # noqa: BLE001
        logger.debug(f"door_event.after_present: {e!r}")


class Push:
    """An `append`, measured: built when the rows arrive (what the list and Rejected held, what was handed), and
    `done()` once the sheet is saved — copies are the rows whose (title, url) the list already had, `capped` the rest
    that did not fit."""

    def __init__(self, data: dict, add: list):
        self.handed = len(add)
        self.items0 = len(data.get("items") or [])
        self.keys0 = {(i.get("title"), i.get("url")) for i in data.get("items") or []}
        self.rej0 = len(data.get("rejected") or [])

    def done(self, sheet: str, data: dict, add: list, pages: list) -> None:
        try:
            landed = len(data.get("items") or []) - self.items0
            dedupe = sum(1 for it in add if (it.get("title"), it.get("url")) in self.keys0)
            emit(sheet, "append", handed=self.handed, landed=landed, candidacy=len(pages), dedupe=dedupe,
                 capped=max(0, len(add) - dedupe - landed), pool=_pool_left(data),
                 off=off_by_gate(data, self.rej0, self.handed - len(pages) - len(add)), media=_pictures(sheet, data))
        except Exception as e:  # noqa: BLE001
            logger.debug(f"door_event.Push.done: {e!r}")
