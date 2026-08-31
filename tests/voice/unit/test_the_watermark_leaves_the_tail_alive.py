"""THE WATERMARK: it marks where the sentence ended, acts on what came before, and the rest stays alive.

Operator's request, 2026-08-21, verbatim: «if of those last three words one was meant to conclude the previous
sentence and the other two to start a new one, nothing happens: we set a point in time and pass that text to the
model from there onward». They delegated the mechanism and set the property: nothing they say is lost, and we know
at what point on the timeline a complete sentence was consumed.

HOW IT IS MEASURED, which is not a detail. The request arrived as «if the fragment closes sentence A and brings
the beginning of B, B IS LOST». Measured in practice, that is not what happened:

    offer("pon música de jazz y")                         -> hold
    offer("luego apágala. Y después")                     -> act("pon música de jazz y luego apágala. Y después")

B was not deleted: it TRAVELED INSIDE A's request, and only A was answered. The difference matters here because a
test asserting «B was not lost» passes on the BROKEN code —B is in the delivered text— and only one asserting
«B did not travel in A's request and remains in the buffer» distinguishes the two things.

ONLY A DANGLING TAIL IS PEELED, and that restriction is the function's entire safety mechanism: the remainder must
be INCOMPLETE according to layer 1. Two complete sentences spoken in one go («play music. turn up the volume») are
ONE request with two intentions and must travel together — splitting them would answer half and leave the other
held forever, because nothing else will arrive to complete it. Beginnings are peeled, never instructions.
"""
import asyncio

import pytest

from nucleo.flash import accumulator as acc


@pytest.fixture(autouse=True)
def _sin_juez(monkeypatch):
    """Layer 2 is an LLM. It is disabled here to measure layer 1 and the cut, which is what this file asserts."""
    async def _incompleto(_t):
        return "incomplete", ""
    acc.set_judge(_incompleto)
    yield
    acc.set_judge(None)


def _ofrecer(a, texto, t):
    return asyncio.run(a.offer(texto, now=t))


# ── the property ─────────────────────────────────────────────────────────────────────────────────────────────

def test_the_next_sentence_does_NOT_travel_inside_this_ones_request():
    a = acc.Accumulator()
    assert _ofrecer(a, "pon música de jazz y", 0.0)[0] == "hold"
    action, entregado, _why, _drop = _ofrecer(a, "luego apágala. Y después", 2.0)

    assert action == "act"
    assert entregado == "pon música de jazz y luego apágala."
    assert "Y después" not in entregado, "el principio de la frase siguiente viajó dentro de esta petición"
    assert a.text() == "Y después", "y además tiene que seguir VIVO, no solo fuera de la petición"


def test_a_CLOSED_sentence_is_not_held_behind_a_beginning():
    """THE FORM THE OPERATOR DESCRIBED, and the one the first version of this did NOT cover.

    Peeling was wired only into the four `act` exits, and that branch almost never needs it: for layer 1 or the
    judge to say «complete», the text cannot end dangling, so there is barely any tail to peel there. Its case —«one
    of those three words closes the previous sentence and two start another»— falls into HOLD. Measured against the
    first commit (3b316b4), with layer 2 saying incomplete, which is what a real judge would say about something
    dangling:

        offer("pon música de jazz y")                    -> hold
        offer("luego apágala. Oye, qué tiempo hace en")  -> hold del buffer ENTERO, consumed_at = 0.0

    «play music … turn it off.» was closed, punctuated, and ready, waiting behind the beginning of a sentence. My
    nine tests all passed: they measured the model I had in my head, not the one the operator described."""
    a = acc.Accumulator()
    assert _ofrecer(a, "pon música de jazz y", 0.0)[0] == "hold"
    action, entregado, motivo, _d = _ofrecer(a, "luego apágala. Oye, qué tiempo hace en", 2.0)

    assert action == "act", f"la frase cerrada se quedó retenida detrás del principio de otra ({motivo})"
    assert entregado == "pon música de jazz y luego apágala."
    assert a.text() == "Oye, qué tiempo hace en", "y el principio de la siguiente sigue vivo"
    assert a.consumed_at == 2.0


def test_an_incomplete_head_is_NOT_shipped_early():
    """The other edge of the same change. When evaluating peeling in the HOLD branch, it is no longer valid to rely
    on the whole closing —it does not close, which is why it is held— so the HEAD must be required to close on its own.

    KNOWN LIMIT, recorded here instead of being hidden: the head is judged with the SAME layer 1 as this entire
    module, and that layer accepts a punctuated head even if it begins with a continuation word («and then.» is
    considered complete because the «starts with…» rule is skipped when STT closed the sentence — see
    `looks_incomplete` §2c). Writing a second predicate here to refine this would mean maintaining two judges of the
    same fact, which is the failure this repo has already suffered twice this week. What the guard does guarantee is
    that a head layer 1 sees as partial is NOT delivered."""
    assert acc.dangling_tail("dame el informe de. y") == ("", ""), "«dame el informe de.» está a medias"


def test_the_surviving_tail_is_continued_by_what_comes_next():
    """The tail is not a leftover saved just in case: it is the beginning of the next sentence and completes itself.

    NOTE the setup, which cost me three badly written tests: the cut occurs only on the ACT path. A standalone
    fragment that already ends dangling («close the window. And») is INCOMPLETE as a whole, so it is HELD in full —
    and that is correct; its continuation is being awaited. The cut is needed precisely when the whole DOES close
    and still drags a beginning behind it."""
    a = acc.Accumulator()
    _ofrecer(a, "pon música de jazz y", 0.0)
    _ofrecer(a, "luego apágala. Y después", 2.0)
    assert a.text() == "Y después"
    action, entregado, _w, _d = _ofrecer(a, "sube el volumen.", 4.0)
    assert action == "act"
    assert entregado == "Y después sube el volumen."


def test_the_watermark_marks_WHEN_a_complete_sentence_was_consumed():
    a = acc.Accumulator()
    assert a.consumed_at == 0.0
    _ofrecer(a, "pon música de jazz y", 0.0)
    _ofrecer(a, "luego apágala. Y después", 7.5)
    assert a.consumed_at == 7.5, "sin marca no se puede decir «lo de antes de aquí ya está contestado»"


def test_the_tails_clock_restarts_at_the_cut():
    """The tail was said NOW, not when the sentence dragging it along began. If it kept the old clock, the gap
    valve would measure it from a moment that no longer means anything and discard it too soon."""
    a = acc.Accumulator()
    _ofrecer(a, "pon música de jazz y", 3.0)
    _ofrecer(a, "luego apágala. Y después", 100.0)
    assert a.first_at == a.last_at == 100.0


# ── the restriction that makes it safe ────────────────────────────────────────────────────────────────────────

def test_two_complete_sentences_ship_TOGETHER():
    a = acc.Accumulator()
    action, entregado, _w, _d = _ofrecer(a, "pon música. sube el volumen", 0.0)
    assert action == "act"
    assert entregado == "pon música. sube el volumen", "partir dos instrucciones deja media petición sin contestar"
    assert not a.pending()


def test_a_buffer_with_no_sentence_end_is_not_cut():
    assert acc.dangling_tail("sin puntuación ninguna aquí") == ("", "")


def test_the_cut_takes_the_LAST_split_not_the_first():
    """With three sentences in the buffer, cutting at the first would deliver one per turn and drip into the
    brain what the operator said all at once."""
    cabeza, cola = acc.dangling_tail("abre el correo. borra el spam. Y luego")
    assert cabeza == "abre el correo. borra el spam."
    assert cola == "Y luego"


# ── the valves do not throw away the tail either ──────────────────────────────────────────────────────────────

def test_a_valve_firing_is_not_a_reason_to_throw_the_tail():
    """The four `act` exits each performed the same `clear()` on their own. Precisely in the pathological case —the
    one that triggers the valve— is where the most text was delivered all at once and emptied completely."""
    a = acc.Accumulator()
    # NO sentence ending in the fragments: with one, peeling in the hold branch would deliver before the
    # valve triggers — which is precisely what was fixed above.
    assert _ofrecer(a, "quiero que me busques una cosa y", 0.0)[0] == "hold"
    for i in range(acc.MAX_FRAGMENTS - 1):
        act, _t, motivo, _d = _ofrecer(a, f"otra cosa número {i} y", float(i + 1))
        if act == "act":
            break
    assert act == "act" and "válvula" in motivo, f"no saltó la válvula (motivo: {motivo!r})"
    # Without a sentence ending there is nowhere to cut, so the valve delivers the entire buffer — and that is correct.
    # What is enforced is that the valve goes through `_deliver`, not its own `clear()`: it seals the watermark.
    assert a.consumed_at > 0.0, "la válvula entregó sin sellar la marca de agua"


def test_the_word_valve_is_sized_from_the_operators_own_sessions():
    """The operator requested 10–15 words. Measured by replicating their 129 session files with this accumulator,
    held buffers have median 10 and p90 31, so a limit of 15 would have triggered on 21 of 64 legitimate holds — one
    third— forcing delivery of partial sentences. At 40 it triggers on 3 of 64. The numbers were reported instead of
    applying the request literally; this test is what prevents anyone from lowering it without measuring again."""
    assert acc.MAX_WORDS >= 30, (
        f"MAX_WORDS={acc.MAX_WORDS} dispara sobre retenciones legítimas (p90 medido: 31 palabras)")


# ── and what is DISCARDED due to the long gap is not lost either ─────────────────────────────────────────────
#
# The other half of «nothing the operator says is lost». The gap valve (> MAX_GAP_S) discards the old buffer to avoid
# joining two different topics, and `_speak_acc_drop` exists to rescue the content: it gives the judge one last look
# and, if the request was complete, pushes a `[SYSTEM]` note so it comes out on the next turn. Except that ALL of
# this lived behind `if speak is None or user_speaking(): return`, so rescue depended on there being a live speaker
# and the operator being quiet. In the test channel there is never a speaker; halfway through a sentence, neither.
# In both cases the text disappeared entirely — no note, no judge, no trace. Preserving the CONTENT and acknowledging
# it OUT LOUD are two jobs, and only the second needs a mouth.

def test_a_discarded_chain_is_rescued_even_with_NO_voice(monkeypatch):
    from nucleo.flash import segmenter
    from voice import brain_notes, proactive
    from voice.engine.llm.providers import nucleo as vp

    notas: list[str] = []
    monkeypatch.setattr(brain_notes, "push", lambda t: notas.append(t))
    monkeypatch.setattr(proactive, "speaker", lambda: None)          # test channel: there is no mouth

    async def _juez(_t):
        return "complete", ""
    monkeypatch.setattr(segmenter, "judge", _juez)

    asyncio.run(vp._speak_acc_drop("reserva mesa para cuatro el jueves"))
    assert notas, "sin altavoz el texto del operador se perdió entero"
    assert "reserva mesa para cuatro el jueves" in notas[0]


def test_it_is_rescued_too_while_the_operator_is_still_talking(monkeypatch):
    """The other guard behind the same `return`, and worse than the previous one: here there IS a speaker, so no one
    suspects anything is being lost — the operator was simply speaking at that moment."""
    from nucleo.flash import segmenter
    from voice import brain_notes, proactive
    from voice.engine.llm.providers import nucleo as vp

    notas: list[str] = []
    monkeypatch.setattr(brain_notes, "push", lambda t: notas.append(t))
    monkeypatch.setattr(proactive, "speaker", lambda: (lambda _t: None))
    monkeypatch.setattr(proactive, "user_speaking", lambda: True)

    async def _juez(_t):
        return "complete", ""
    monkeypatch.setattr(segmenter, "judge", _juez)

    asyncio.run(vp._speak_acc_drop("apúntame la ITV del coche para el lunes"))
    assert notas, "hablando encima del agente, lo dicho antes de la pausa se perdía"
