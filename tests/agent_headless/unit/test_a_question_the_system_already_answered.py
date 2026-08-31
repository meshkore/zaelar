"""“Should I stop it or let it continue?” and “I stopped it” reached the SAME prompt (V2-353).

Measured in `search-buy-used-car`, round 13 (2026-08-26, ES set), session `decce3cc`:

    1512,6 s  🔔 He parado «Busca coches de segunda mano…»: agotó su tiempo   ← la tarea muere
       …      (tres minutos de silencio: el operador no habla)
    1709,1 s  📩 «El proceso «Busca coches…» lleva ya 18 minutos. ¿Quieres que lo pare o que siga?»
    1709,1 s  📩 «He parado «Busca coches…»: agotó su tiempo»

The two notices, about the SAME task, at the SAME moment and in the same prompt: one asks whether to stop it and the
other says it has already been stopped. The judge marked the resulting turn [high] — “described the stop as if it
were its own decision” — and was right about the symptom but not the cause: **a contradictory prompt has no
obedient response** (V2-222, and that makes four).

WHY THEY JOIN, using the loop's numbers: the question is emitted at `WORKER_MAX_SECS` (900 s = 15 min) and the
death at `budget + grace`, which for a `web` worker is 1200 + 90 = 21.5 min. There are six minutes between them,
and neither is delivered on the fly when there is no live voice: **they wait for the operator's next turn**. If the
operator does not speak during that window —and in the measured round it took three minutes— both are drained together.

THE KEY is for the question to be RETRACTABLE. A note that asserts something about a LIVE state can stop being
true before delivery, and the one who makes it false —the one who kills the task— is exactly the one in a
position to withdraw it. This is not censorship: the one retracting it pushes its own (“I stopped it”) immediately
afterward. What is avoided is both arriving.

And a repeated key REPLACES: two “it has been running for N minutes” notices about the same task are the same notice
with the updated number, not two things to count.
"""
import pytest

from voice import brain_notes


@pytest.fixture(autouse=True)
def _buzon_limpio():
    brain_notes.drain()
    yield
    brain_notes.drain()


PREGUNTA = "[SISTEMA] El proceso «Busca coches de segunda mano» lleva ya 18 minutos. ¿Quieres que lo pare?"
PARADA = "[SISTEMA] He parado «Busca coches de segunda mano»: agotó su tiempo."


def test_la_pregunta_se_retracta_cuando_deja_de_tener_sentido():
    """The complete measured case."""
    brain_notes.push(PREGUNTA, key="worker-timeout:t3")
    assert brain_notes.retract("worker-timeout:t3") == 1
    brain_notes.push(PARADA)
    assert brain_notes.drain() == [PARADA], "las dos juntas son el prompt que se contradice"


def test_sin_retractar_llegan_las_DOS_que_es_el_defecto():
    """The sensitivity test for the above: without the call, the mailbox delivers both and the model chooses."""
    brain_notes.push(PREGUNTA, key="worker-timeout:t3")
    brain_notes.push(PARADA)
    assert len(brain_notes.drain()) == 2


def test_una_llave_repetida_SUSTITUYE_no_acumula():
    """“It has been running for 15 minutes” and “it has been running for 18 minutes” are the same notice, not two."""
    brain_notes.push("[SISTEMA] lleva ya 15 minutos. ¿La paro?", key="worker-timeout:t3")
    brain_notes.push("[SISTEMA] lleva ya 18 minutos. ¿La paro?", key="worker-timeout:t3")
    out = brain_notes.drain()
    assert out == ["[SISTEMA] lleva ya 18 minutos. ¿La paro?"]


def test_retractar_solo_toca_SU_tarea():
    """Two live jobs: killing one cannot silence the question for the other."""
    brain_notes.push("[SISTEMA] el coche lleva 18 min. ¿La paro?", key="worker-timeout:t3")
    brain_notes.push("[SISTEMA] el hotel lleva 16 min. ¿La paro?", key="worker-timeout:t7")
    brain_notes.retract("worker-timeout:t3")
    assert brain_notes.drain() == ["[SISTEMA] el hotel lleva 16 min. ¿La paro?"]


def test_una_nota_SIN_llave_no_se_puede_retractar_por_accidente():
    """The vast majority of notes have no key and must remain where they are."""
    brain_notes.push("[SISTEMA] el widget ya está construido.")
    brain_notes.push(PREGUNTA, key="worker-timeout:t3")
    brain_notes.retract("worker-timeout:t3")
    assert brain_notes.drain() == ["[SISTEMA] el widget ya está construido."]


def test_retractar_algo_que_no_esta_no_rompe_ni_miente():
    assert brain_notes.retract("worker-timeout:no-existe") == 0
    assert brain_notes.retract("") == 0


def test_el_orden_de_las_notas_se_conserva():
    """The mailbox is a queue: the key cannot reorder what it does not affect."""
    brain_notes.push("primera")
    brain_notes.push("segunda", key="k")
    brain_notes.push("tercera")
    assert brain_notes.drain() == ["primera", "segunda", "tercera"]


def test_el_bucle_CABLEA_la_llave_en_los_dos_lados():
    """Wiring guard on the uncommented source: retraction without a caller is the fix that does not exist, and this
    repository has already suffered that exact pattern twice (V2-199, V2-340)."""
    from pathlib import Path
    src = "\n".join(ln for ln in Path("nucleo/loop.py").read_text().splitlines()
                    if not ln.strip().startswith("#"))
    assert "_TIMEOUT_KEY" in src
    assert "_deliver_keyed(" in src, "la pregunta se empuja sin llave: nunca se podrá retractar"
    assert "worker_timeout_running" in src and "_bn.retract(_TIMEOUT_KEY" in src, "nadie retracta al matar"
