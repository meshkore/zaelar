"""Two rounds that end in the same second never share a report file (V2-781, 2026-10-04).

Measured on the pair `find-a-future-release-and-remind-me`: the ES and the EN round both wrote
`report_20261004-035540.{md,json}` and the EN evidence was overwritten — the same class as the shared sandbox
workspace found on the first pair. The name is claimed atomically and a taken one gets a suffix.
"""
from __future__ import annotations

import json

from tests.use_cases.e2e.agent import report


def _result(sid):
    return {"scenario": sid, "tier": 1, "channel": "probe", "run": {"transcript": [], "mechanism_report": {}},
            "verdict": {"scores": {}, "overall": 3, "findings": [], "improvements": []}}


def test_the_same_stamp_twice_gives_two_files(tmp_path):
    a = report.build([_result("case")], "20261004-035540", tmp_path)
    b = report.build([_result("case__us")], "20261004-035540", tmp_path)
    assert a != b and a.exists() and b.exists()
    got = {json.loads(p.with_suffix(".json").read_text(encoding="utf-8"))["results"][0]["scenario"] for p in (a, b)}
    assert got == {"case", "case__us"}
