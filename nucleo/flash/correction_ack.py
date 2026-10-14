"""A correction of a results sheet is acknowledged with WHAT CHANGED, never a bare «Done.» (text channel).

find-concert-tickets ES (2026-10-14, sandbox 021207-es). «perdona, esos no son de Rosalía» — the model answered «Tienes
razón, esos no son de Rosalía…» and called nothing; the second pass carried out `results:criteria` with his
correction, the sheet's door moved twelve rows to the Rejected tab, and the text channel, which drops the model's
words once a repair speaks for the turn (`act_repair.after_the_repair`), said «Hecho.». Twice: «que sea Rosalía
porfa» got the same. He could not tell whether anything had changed.

The op's own answer says it: `results.criteria` returns `off_category`, the rows its recheck took off the list. This
module turns that into the line — how many left, and that what does not fit stays out (the door applies the
correction to every later row, whoever writes it). Read from the op's result, never from his words or the reply.
"""
from __future__ import annotations


def _off(ans) -> int | None:
    """`off_category` from one op answer (flat or under `result`); None when the answer does not carry it."""
    if not isinstance(ans, dict):
        return None
    for src in (ans, ans.get("result") if isinstance(ans.get("result"), dict) else {}):
        v = src.get("off_category")
        if isinstance(v, bool):
            continue
        if isinstance(v, int):
            return v
        if isinstance(v, list):
            return len(v)
    return 0 if "criteria" in ans or "criteria" in (ans.get("result") or {}) else None


def line(parte) -> str:
    """The acknowledgement owed to a `results:criteria` op the turn ran, or "" when it ran none. Never raises."""
    try:
        if not isinstance(parte, dict) or parte.get("executed") != "widget_data" or parte.get("fallidas"):
            return ""
        ops = parte.get("ops") or []
        if not any(str(o.get("widget") or "").split("::")[0] == "results" and o.get("act") == "criteria"
                   for o in ops if isinstance(o, dict)):
            return ""
        n = 0
        for item in parte.get("answers") or []:
            wid, ans = (item if isinstance(item, (list, tuple)) and len(item) == 2 else ("", item))
            if str(wid or "results").split("::")[0] != "results":
                continue
            got = _off(ans)
            n += got or 0
        from i18n import langs as _langs
        lg = _langs.current_language()
        if n == 1:
            return str(lg.correction_dropped_one)
        if n > 1:
            return str(lg.correction_dropped).replace("{n}", str(n))
        return str(lg.correction_noted)
    except Exception as e:  # noqa: BLE001 — the plain ack still speaks
        from loguru import logger
        logger.debug(f"correction_ack: no line — {type(e).__name__}: {e}")
        return ""
