"""The worker bridge's usage hints name only the subcommands its parser serves (V2-854).

`wait` left the bridge (331f77552: a question is never re-polled), and the generic hint still advertised it: a
worker that followed the hint met a usage error. The fallback's list is read from the parser, and every declared
subcommand has a hint of its own.
"""
import re

from nucleo.cli import bridge as WB


def test_the_fallback_hint_names_exactly_the_declared_subcommands():
    declared = WB._subcommands()
    assert declared
    assert set(re.findall(r"`(\w+)`", WB._hint_for("worker_bridge"))) == set(declared)


def test_each_declared_subcommand_has_its_own_hint():
    fallback = WB._hint_for("worker_bridge")
    for cmd in WB._subcommands():
        assert WB._hint_for(f"worker_bridge {cmd}") != fallback, f"`{cmd}` falls to the generic hint"
