"""A missing row is said to him from the language pack, and the model's reason is internal English (V2-831 R9,
node 4.330).

Demo pass T-19, S3: the first `detail {index: 2}` came back «No encuentro ese resultado en la hoja» — the refusal
carried a hardcoded Spanish `message` (and most readers speak `message or error`, so an English session heard
Spanish) and a Spanish `error` (the hint the MODEL reads). The class: a widget refusal's words for him come from
`i18n/` in the session's language; the `error` beside it is an internal reason, in English like the rest of
`engine/`.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from widgets.results import data as R

_ENG = Path(__file__).resolve().parents[4]


def _pack(code: str) -> dict:
    return json.loads((_ENG / f"i18n/genesis/{code}/ui.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("code", ["en", "es"])
def test_the_refusal_speaks_the_sessions_pack_and_hints_the_model_in_english(monkeypatch, code):
    monkeypatch.setenv("ZAELAR_LANGUAGE", code)
    res = R.apply_action("detail", {"title": "a row nobody pushed", "index": 99})
    assert res["ok"] is False
    assert res["error"] == "no such row on the sheet (pass its title, or a 1-based index)"
    line = _pack(code)[res["say"]]
    assert line and res["message"] == line, f"{code}: said {res.get('message')!r}, the pack says {line!r}"
