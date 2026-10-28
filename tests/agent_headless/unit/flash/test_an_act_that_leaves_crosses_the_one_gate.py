"""An act that LEAVES crosses the one data-op gate, measured on the gate itself (refactor2710-06 T-02).

Behaviour, through `tests/widget_data_rig.py` — the gate runs whole and stops where an op starts or is held:

  · with a stranger's words in the context and no sure verdict, a reply is ASKED; without them it runs (CRIT-E12);
  · two readers disagree on an act that leaves → the verdict's act runs instead (full12 E3, node 2.106);
  · a sure ordered forward the model only drafted → the forward runs, to the person he named (live bench E3, 2.729);
  · a send to someone his words never named is asked, never sent (the operator, 2026-10-15).
"""
from __future__ import annotations

import pytest

from tests import widget_data_rig as rig


@pytest.fixture(autouse=True)
def _scene(tmp_path, monkeypatch):
    from nucleo import his_words, untrusted
    rig.scene(tmp_path, monkeypatch)
    yield
    untrusted.reset()
    his_words.reset()


def test_a_send_to_someone_his_words_never_named_is_asked(monkeypatch):
    out = rig.run("mensajeria", "send_to", {"contact": "Quinn", "text": "the numbers"},
                  said="send the numbers to the team", monkeypatch=monkeypatch)
    assert not out.ran and [a for _w, a, _p in out.asked] == ["send_to"], out
