"""A REPORT errand's working rows are never announced as «candidates on the results sheet» (V2-781).

Measured in `docs-report-lands-as-document__es` (2026-10-10): «hazme un informe sobre coches eléctricos para ciudad»
— the errand's surface is the document; its worker kept a research sheet, and the delivery backstop read it (the
T528 source, `dispatch.pending_summaries`) and glued «ya hay candidatos en la hoja de resultados: «RENAULT 4…»» to
two replies about a report.
"""
from nucleo.flash import live_blocks


def _pending(monkeypatch, surface):
    from nucleo import dispatch
    from nucleo.flash import errand_sheet
    from widgets.navegador import tasks
    monkeypatch.setattr(tasks, "active_summaries", lambda: [])
    monkeypatch.setattr(dispatch, "pending_summaries",
                        lambda: [{"request": "informe sobre coches eléctricos", "sheet": "ab12", "surface": surface}])
    monkeypatch.setattr(errand_sheet, "rows_of_sheet", lambda sheet, n=3: ["«RENAULT 4 E-Tech — 25.000 €»"])


def test_a_report_errand_gives_no_rows(monkeypatch):
    _pending(monkeypatch, "informe")
    assert live_blocks.any_live_task_rows(3) == ("", [])


def test_a_list_errand_still_does(monkeypatch):
    _pending(monkeypatch, "lista")
    goal, rows = live_blocks.any_live_task_rows(3)
    assert rows and "RENAULT" in rows[0]
