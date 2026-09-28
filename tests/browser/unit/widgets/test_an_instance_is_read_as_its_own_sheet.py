"""Demo pass 2026-09-28, S3: «open the one that's the best deal» was refused on the monitor sheet, and its corrected
re-call named «Plan C — Menorca al mejor precio», a title from another errand. The read of the card it was fixing,
`results::4e8213-ls1`, had come back EMPTY: the digest imported `widgets.results::4e8213-ls1.data`, which does not
exist. An instance is its base's module and that sheet."""
from widgets import refs


def test_an_instance_id_reads_its_base_with_the_sheet(monkeypatch):
    from widgets.results import data as results
    monkeypatch.setattr(results, "prompt_digest", lambda sheet=None: f"SHEET={sheet}")
    assert refs.prompt_digest("results::4e8213-ls1") == "SHEET=4e8213-ls1"
    assert refs.prompt_digest("results") == "SHEET=None"


def test_a_widget_whose_digest_takes_no_sheet_is_still_read(monkeypatch):
    from widgets.agenda import data as agenda
    monkeypatch.setattr(agenda, "prompt_digest", lambda: "AGENDA")
    assert refs.prompt_digest("agenda::x") == "AGENDA" and refs.prompt_digest("agenda") == "AGENDA"
