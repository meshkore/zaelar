"""nucleo/docsheet.py — the DOCUMENT sheet as an errand surface (V2-644).

`nucleo/sheets.py` is where a LIST of findings lands (surfaces `lista`/`item` → the results sheet). This is
its sibling for the errand whose deliverable is ONE written thing to READ — surface `informe`: the operator
asked for a report, so the `documento` widget opens at COMMISSION time, bound to the errand, and shows a live
process view (which sources are being looked at, what is happening) until the worker writes the report into
it through the ordinary `widget_cli` bridge.

Same three rules as the results sheet, for the same reasons:
  - opened when COMMISSIONED, not at delivery — the whole point is that the operator stops staring at nothing;
  - the process view is DERIVED from the dispatcher's live record on every read (`sheets.task_progress`),
    never stored while alive — a stored copy on screen is always stale;
  - everything here is fail-soft: a failure in the VIEW must never bring down the errand.

Why the `documento` widget and not a second results sheet: the borders are the widget's own (`results` = a set
you compare; `documento` = one thing you read, V2-549). A report streamed into a comparison surface reads as a
list of links — which is exactly what the operator reported when the Juncal research landed there.
"""
from __future__ import annotations

from nucleo.sheets import PHASES_KEPT, _phrases


def _title_of(rec) -> str:
    return str(getattr(rec, "title", "") or getattr(rec, "goal", "") or "").strip()[:120]


def doc_open(rec) -> None:
    """Bind the `documento` sheet to this errand and put it on screen, blank, with its process view."""
    try:
        from widgets.documento import data as _doc
        _doc.begin_task(_title_of(rec), task_id=str(getattr(rec, "task_id", "") or ""))
    except Exception:  # noqa: BLE001
        pass
    try:
        from voice.observer import emit
        emit("widget", "show", extra={"id": "documento", "src": f"worker:{getattr(rec, 'task_id', '')}"})
    except Exception:  # noqa: BLE001
        pass


def doc_retitle(rec) -> None:
    """The errand's composed NAME reaches the process header (same gesture as `sheets.retitle`). Fail-soft:
    the provisional name is already truthful."""
    try:
        from widgets.documento import data as _doc
        _doc.retitle_task(_title_of(rec), task_id=str(getattr(rec, "task_id", "") or ""))
    except Exception:  # noqa: BLE001
        pass


def doc_close(rec) -> None:
    """The errand is OVER: persist the process history so the report keeps the account of how it was reached.

    The live record disappears with the errand, so without this the Proceso tab would go blank the moment the
    work finished — the results sheet learned the same lesson (`_sheet_close`): a report whose explanation has
    disappeared accounts for half of what happened."""
    try:
        from widgets.documento import data as _doc
        _doc.finish_task(task_id=str(getattr(rec, "task_id", "") or ""),
                         phases=_phrases(rec)[-PHASES_KEPT:])
    except Exception:  # noqa: BLE001
        pass
