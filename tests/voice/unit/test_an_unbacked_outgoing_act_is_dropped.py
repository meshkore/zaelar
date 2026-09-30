"""An act that LEAVES and the verdict does not back is dropped, never offered (demo pass 45, 2026-09-29, C2→C5).

«find me a free 45 minutes tomorrow afternoon to talk with rowan» — the verdict read `agenda:find_free`; the model
also called `mensajeria:send_to`. The guard turned the send into a pending CONFIRMATION («Shall I send it?»), and
«ok book it» one turn later was read as its yes: two Telegrams to Rowan he never ordered. The unbacked act is
dropped and the model is told it did not run — nothing is left pending for the next «ok» to answer."""
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[3]


def test_the_unbacked_act_is_dropped_with_a_note_and_no_confirmation():
    prov = (ENGINE / "voice/engine/llm/providers/nucleo.py").read_text(encoding="utf-8")
    seg = prov.split("elif _direct_action.verdict_elsewhere(_brief, wid):", 1)[1].split("def _log_dataop", 1)[0]
    assert "no se ejecuta" in seg
    assert "_bn_drop.push(" in seg and "NO se ejecutó" in seg and "no la pidió" in seg
    assert "return" in seg
    assert "_wactions.CONFIRM" not in seg, "asked instead of dropped is what «ok book it» answered"
