"""The stop backstop says «stopped» in HIS language (refactor2710-99, node 2.899).

Use case `docs-single-recipe-not-a-list__us` (2026-10-28): the backstop stopped the errand and said «Vale, lo paro.» in
an English session — a Spanish literal in the code. Every line the engine says is a translated string (V2-694): the
backstop's two lines are `stopped_now` / `stopped_also` of the language pack.

Disarm: put the Spanish literal back in `post_stream_settle.stop_ack` and the English case goes red.
"""
from __future__ import annotations

import pytest

from nucleo.flash import post_stream_settle as S


@pytest.mark.parametrize("code,alone,after", [
    ("en", "Okay, I'm stopping it.", " I've stopped that task."),
    ("es", "Vale, lo paro.", " He parado esa tarea."),
])
def test_the_stop_line_is_his_languages(monkeypatch, code, alone, after):
    from i18n import langs
    monkeypatch.setattr(langs, "current_code", lambda: code)
    assert S.stop_ack("") == alone
    assert S.stop_ack("Got it.") == after
