"""A meeting the agenda absorbs as the same commitment answers `existing: <row>`, never an empty success (T-19 R10).

The same-slot dedupe (V2-208/V2-781) kept ONE row, which is right, but answered as if it had written one: the circuit
read the new title as missing. The reply now says which row already holds it, and carries no `revert` — taking the
«new» piece back out would delete HIS row.
"""
import pytest

from widgets.agenda import data as agenda


@pytest.fixture(autouse=True)
def _isolated_store(tmp_path, monkeypatch):
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)


def _add(title):
    return agenda.apply_action("add_meeting", {"title": title, "date": "2099-11-06", "startTime": "16:00",
                                               "endTime": "17:00"})


@pytest.mark.parametrize("first,second", [("Vet appointment for Pixel", "Pixel — veterinarian"),
                                          ("Veterinario de Pixel", "Pixel — veterinarian")])
def test_the_second_wording_answers_the_row_that_holds_it(first, second):
    fresh = _add(first)
    assert fresh.get("ok") is not False and "existing" not in fresh and fresh.get("revert")
    again = _add(second)
    assert again.get("existing", {}).get("title") == first
    assert again.get("stored", {}).get("title") == first and "revert" not in again
    assert len(agenda.load_db().get("meetings", [])) == 1
