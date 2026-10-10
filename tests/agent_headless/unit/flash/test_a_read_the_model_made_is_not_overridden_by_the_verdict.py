"""A turn whose model READ the card is not completed with the verdict's op (V2-781, what-does-my-week-look-like__us).

«cool, so what do I have on those days?» — the model called `read_widget(agenda, "…2026-10-20 and 2026-10-22…")`,
the right call; the verdict backstop (meant for a turn with NO call) added `show_day {"day": "<his whole
sentence>"}`, which resolved to TODAY, and the reply said «You've got nothing on October 10th».
"""
import inspect

from nucleo.flash import probe_mirrors


def test_a_read_counts_as_the_turns_call():
    assert probe_mirrors.model_already_acted([{"name": "read_widget", "args": {"widget_id": "agenda"}}])
    assert not probe_mirrors.model_already_acted([])


def test_the_verdict_backstop_reads_it():
    assert "model_already_acted(tool_calls)" in inspect.getsource(probe_mirrors)
