"""The show-promise backstop shows the card the VERDICT names before a contextual guess (demo pass 52, C1).

«johnny show me what i've got tomorrow» — the late catalogue named `agenda`, the act-repair got no call, and the
backstop resolved `identify` BY CONTEXT to the minimized monitor sheet, which came up over the day he asked for."""
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[3]


def test_the_verdicts_card_wins_over_identify_by_context():
    prov = (ENGINE / "voice/engine/llm/providers/nucleo.py").read_text(encoding="utf-8")
    assert '_named_by_verdict = ""' in prov
    assert "_named_by_verdict = _ar_wid" in prov
    head, tail = prov.split("_named_by_verdict = _ar_wid", 1)
    assert "_pw = ((_named_by_verdict or _identify(_op_text))" in tail
