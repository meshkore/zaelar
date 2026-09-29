"""`hbmesh` names its two forms when a worker misuses it (V2-776 K3, 2026-09-29).

Demo passes 56-58: `hbmesh: error: unrecognized arguments: --agent ybana` and `unrecognized arguments: Vallarta`
— the worker invented a flag and passed the errand unquoted, twice per pass, one lost round each time. The
worker learns the CLI from its own usage line, so the usage line is the guide: on any parse error the CLI
answers JSON with the exact two forms, the rule «the errand is ONE quoted argument» and «no other flag exists».
"""
import io
import json
from contextlib import redirect_stdout

import pytest

from nucleo import mesh_cli


def _misuse(argv):
    out = io.StringIO()
    with redirect_stdout(out), pytest.raises(SystemExit) as ex:
        mesh_cli.main(argv)
    assert ex.value.code == 2
    return json.loads(out.getvalue().strip().splitlines()[-1])


def test_an_unquoted_errand_and_an_invented_flag_get_the_forms():
    for argv in (["find", "warm", "trip", "to", "Puerto", "Vallarta"], ["find", "--agent", "ybana", "monitors"],
                 ["serve", "--agent", "x", "book a table"]):
        got = _misuse(argv)
        assert got["ok"] is False and "unrecognized" in got["reason"]
        assert 'hbmesh find "<errand>"' in got["usage"][0] and 'hbmesh serve "<errand>"' in got["usage"][1]
        assert "ONE quoted argument" in got["hint"] and "no other flag" in got["hint"]


def test_a_well_formed_call_still_runs(monkeypatch):
    seen = {}
    import types
    fake = types.SimpleNamespace(find=lambda errand, limit=5: seen.update(errand=errand) or {"agents": [], "intent": "x"})
    monkeypatch.setitem(__import__("sys").modules, "nucleo.mesh_agents", fake)
    out = io.StringIO()
    with redirect_stdout(out):
        assert mesh_cli.main(["find", "warm trip to Puerto Vallarta"]) == 0
    assert seen["errand"] == "warm trip to Puerto Vallarta"
