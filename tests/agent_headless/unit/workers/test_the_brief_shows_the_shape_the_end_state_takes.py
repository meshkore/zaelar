"""The brief shows the shape a row's end state takes, and names each bridge with the argument it needs (2026-11-06).

Measured on the use-case battery after 2.1358 landed, eleven errands in both languages: every FIRST `report goal` was
prose («Find a kid-friendly activity… and put the result on his screen»), refused at the door with the grammar, and
rewritten minutes later — one round trip and a late checkpoint 1 per errand, and a row that ended with no end state
when the worker never came back to it. The brief told the worker to record its end state right beside a prose
«DONE WHEN» sentence and never showed the shape the row takes nor what its deliverable card declares; it also named
`cli.mem recall` with no argument, and the worker ran it bare (`error: the following arguments are required: query`).

Now the playbook block carries the grammar's SHAPE (one constant, the door's help reads the same one; placeholders,
no value a worker could copy — V2-852 T10) and what this playbook's deliverable card declares, from its manifest; and
every bridge subcommand the block names whose parser requires a positional carries a placeholder. Both languages.
"""
from __future__ import annotations

import re

import pytest

from nucleo.circuit import spec_declares
from nucleo.workers.prompts import playbook

LANGS = ("es", "en")


@pytest.fixture(params=LANGS)
def lang(request, monkeypatch):
    from i18n import langs
    code = request.param
    monkeypatch.setattr(langs, "current_code", lambda: code)
    monkeypatch.setattr(langs, "current_language", lambda: langs.LANGUAGES[code])
    return code


def _block(name: str) -> str:
    return playbook.block(name, playbook.done_when(name))


@pytest.mark.parametrize("name,card,coll", [
    ("errand", "results", "items"), ("lista", "results", "items"),
    ("document", "documento", "sections"), ("message", "mensajeria", "sent"),
])
def test_the_playbook_carries_the_grammars_shape_and_what_its_card_declares(lang, name, card, coll):
    block = _block(name)
    assert spec_declares.SHAPE in block, f"[{lang}] the {name} playbook shows no shape for the end state"
    assert f"«{card}» declares:" in block and coll in block.split(f"«{card}» declares:", 1)[1][:160], \
        f"[{lang}] the {name} playbook does not say what its deliverable card declares"
    # the shape carries placeholders only — never a widget/value pair a worker could record as its own end state
    assert re.search(r'"widget": "<', spec_declares.SHAPE) and not re.search(r'"widget": "[a-z]', spec_declares.SHAPE)


def test_the_doors_help_and_the_brief_read_one_shape():
    from nucleo.cli import report
    assert spec_declares.SHAPE in report._GOAL_HELP


def _required_positionals(module: str) -> dict[str, bool]:
    """subcommand → does its parser require a positional? Read from the CLI's own argparse, never a list here."""
    import argparse
    import importlib
    from unittest import mock
    mod = importlib.import_module(module)
    if hasattr(mod, "parser"):
        parser = mod.parser()
    else:                                   # the parser is built inside main(): catch it on its way to parse_args
        got: dict = {}

        class _Caught(Exception):
            pass

        def _take(self, *a, **k):
            got["p"] = self
            raise _Caught()
        with mock.patch.object(argparse.ArgumentParser, "parse_args", _take):
            try:
                mod.main([])
            except _Caught:
                pass
        parser = got["p"]
    out: dict[str, bool] = {}
    for a in parser._actions:
        if isinstance(a, argparse._SubParsersAction):
            for sub, p in a.choices.items():
                out[sub] = any(x.option_strings == [] and x.nargs not in ("?", "*") for x in p._actions
                               if not isinstance(x, argparse._HelpAction))
    return out


@pytest.mark.parametrize("name", playbook.NAMES)
def test_every_bridge_the_playbook_names_carries_the_argument_its_parser_requires(lang, name):
    block = _block(name)
    needs = {"nucleo.cli.mem": _required_positionals("nucleo.cli.mem"),
             "nucleo.cli.report": _required_positionals("nucleo.cli.report")}
    bare = []
    for m in re.finditer(r"`(?:python -m )?(?:nucleo\.)?cli\.(mem|report) ([a-z]+)([^`]*)`", block):
        mod, sub, rest = m.group(1), m.group(2), m.group(3)
        req = needs[f"nucleo.cli.{mod}"]
        if req.get(sub) and not re.search(r'<[^>]+>|@\w|"[^"]+"', rest):
            bare.append(f"cli.{mod} {sub}")
    assert not bare, f"[{lang}] the {name} playbook names a bridge without the argument its parser requires: {bare}"
