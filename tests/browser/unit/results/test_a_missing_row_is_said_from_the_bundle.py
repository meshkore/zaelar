"""A missing row is said to him from the language pack, and the model's reason is internal English (V2-831 R9,
node 4.330).

Demo pass T-19, S3: the first `detail {index: 2}` came back «No encuentro ese resultado en la hoja» — the refusal
carried a hardcoded Spanish `message` (spoken whenever the bundle line did not resolve, whatever his language) and
a Spanish `error` (the hint the MODEL reads). The class: a widget refusal's words for him live in `i18n/` under the
`say` key, in every language; the `error` beside it is an internal reason, in English like the rest of `engine/`.
"""
from __future__ import annotations

import json
from pathlib import Path

from widgets.results import data as R

_ENG = Path(__file__).resolve().parents[4]


def test_the_refusal_names_its_bundle_line_and_carries_no_literal_of_its_own():
    res = R.apply_action("detail", {"title": "a row nobody pushed", "index": 99})
    assert res["ok"] is False
    assert "message" not in res, f"a literal sentence bypasses the language pack: {res.get('message')!r}"
    assert res["error"] == "no such row on the sheet (pass its title, or a 1-based index)"
    key = res["say"]
    packs = sorted((_ENG / "i18n/genesis").glob("*/ui.json"))
    assert packs
    missing = [p.parent.name for p in packs if not json.loads(p.read_text(encoding="utf-8")).get(key)]
    assert not missing, f"{key} has no line in: {missing}"
