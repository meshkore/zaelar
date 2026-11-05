"""The worker bridge's usage hints name only the subcommands its parser serves (V2-854).

`wait` left the bridge (331f77552: a question is never re-polled), and the generic hint still advertised it: a
worker that followed the hint met a usage error. The parser is the owner of the set; the hint is held to it, and
every declared subcommand has a hint of its own.
"""
import re

import pytest

from nucleo.cli import bridge as WB


def _declared(capsys) -> set[str]:
    with pytest.raises(SystemExit):
        WB.main(["-h"])
    return set(re.search(r"\{([\w,]+)\}", capsys.readouterr().out).group(1).split(","))


def test_the_fallback_hint_names_exactly_the_declared_subcommands(capsys):
    declared = _declared(capsys)
    assert declared and set(re.findall(r"`(\w+)`", WB._hint_for("worker_bridge"))) == declared


def test_each_declared_subcommand_has_its_own_hint(capsys):
    fallback = WB._hint_for("worker_bridge")
    for cmd in _declared(capsys):
        assert WB._hint_for(f"worker_bridge {cmd}") != fallback, f"`{cmd}` falls to the generic hint"
