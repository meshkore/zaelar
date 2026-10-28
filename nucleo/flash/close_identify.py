"""The card a close BACKSTOP reads from his words — never one he told to stay (both channels, 2026-10-14).

The voice lane (`post_stream_lanes`) and the text mirror (`probe_mirrors`) each completed a close the model did not
make with `widgets.runtime.identify` over the WHOLE sentence. «close the video, I'll check the calendar later» then
matched `agenda` outright: the deferral named the calendar by its name, the video only by an alias. The verdict
gesture already reads the close words (`naming.without_kept`); this is the same rule for the word match, so a card
named in a keep / leave / don't-touch / «later» clause is never what a backstop closes.
"""
from __future__ import annotations

from loguru import logger


def identify(text: str, open_ids) -> dict:
    """`runtime.identify` over the close words of `text`; `{}` when the card it reaches is one he told to stay."""
    ids = list(open_ids or [])
    try:
        from widgets import instances as _inst, naming as _naming, runtime as _rt
        res = _rt.identify(_naming.without_kept(text), open_ids=ids) or {}
        stay = {_inst.base_of(k) for k in _inst.kept_named(text, ids)}
    except Exception as e:  # noqa: BLE001
        logger.debug(f"close_identify: skipped — {e}")
        return {}
    if res.get("match") and _inst.base_of(str(res["match"])) in stay:
        return {}
    return res
