"""A web-search lead is recognised through the language packs, in any product language (V2-831 audit A6b).

The class: the Origin fact a search row carries («Origen: búsqueda web») was WRITTEN as a Spanish literal by two
producers (`findings.hand_search_rows`, `answer_rows`) and READ by two word tables (`candidacy._ORIGIN_LABELS`,
`_WEB_LEAD_VALUES`) and a third literal (`errand_sheet`). An English session wrote Spanish onto the card, and a row
written in another language was only a lead if someone had typed its words into a table.

The mechanism: one writer (`search.result.origin_fact`, the session's pack) and one reader (`origin_of`, the packs of
both product languages and his); the tables are gone.
"""
from __future__ import annotations

import pytest

from search import candidacy, result


def _row(label: str, value: str) -> dict:
    return {"title": "Barranquismo en Vizcaya: 9 precios", "url": "https://x.invalid/a",
            "facts": [{"label": label, "value": value}]}


@pytest.mark.parametrize("label,value", [("Origen", "búsqueda web"), ("Origin", "web search")])
def test_a_row_written_in_either_language_reads_as_a_lead(label, value):
    assert result.origin_of(_row(label, value)) == "web"
    assert candidacy._is_web_lead(_row(label, value))


def test_another_origin_is_not_a_lead_and_the_field_wins():
    assert not candidacy._is_web_lead(_row("Origin", "listing"))
    assert candidacy._is_web_lead({"title": "x", "origin": "web"})


def test_the_writer_speaks_the_sessions_language():
    from i18n import langs
    fact = result.origin_fact("web")
    assert fact["value"] == langs.words("search.origin_values")["web"]
    assert fact["label"] == langs.words("search.fact_labels")["origin"]
    assert result.origin_of({"facts": [fact]}) == "web"
