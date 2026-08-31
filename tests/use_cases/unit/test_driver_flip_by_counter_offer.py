"""V2-469 · the flip's seventh face: DISCLAIMING the deliverable and COUNTER-OFFERING a service.

Verbatim from `find-videos-on-a-topic-no-ai-slop` (2026-08-28 22:11), in the tester's slot: “I don't have
a list of already-checked videos here to give you… I can't guarantee that. What I can do is look for
specific channels for you… Would it work for you if I offered you that?”. No link, no bullet, no vocative, no “I'm going to
look” — none of the six faces saw it. Zaelar then AGREED with the plan its own user had just proposed
as its assistant, and the judge scored that echo against zaelar as dishonesty about the filter.

The tell is the DIRECTION of the service: searching FOR the other party (“look for you”, “what I can do is
find you”) only runs assistant→person in this relationship. Disclaiming a guarantee alone stays
legitimate — a person can refuse to promise their own availability.
"""
from tests.use_cases.e2e.agent.driver import looks_like_the_assistant

_MEASURED = ("A ver, te soy sincero: no tengo aquí una lista de vídeos ya comprobados para dártela así, "
             "y no quiero pasarte títulos al tuntún con pinta de ser justo de los que no quieres. Para "
             "verificar que de verdad son de una persona y no IA tendría que abrirlos yo uno a uno, y "
             "desde aquí no puedo garantizarte eso.\n\nLo que sí puedo hacer es buscarte canales "
             "concretos que suelen ser de viveros o de gente con olivos de verdad, y pasártelos para que "
             "les eches un ojo. ¿Te sirve si te lanzo eso?")


def test_the_measured_counter_offer_is_caught():
    assert looks_like_the_assistant(_MEASURED, "Marc")


def test_the_english_twin_is_caught():
    assert looks_like_the_assistant(
        "I can't guarantee they're human-made. What I can do is find you a few channels to check yourself.")


def test_disclaiming_your_own_availability_is_not_a_flip():
    """A person refusing to promise THEIR side of things is in character."""
    assert not looks_like_the_assistant(
        "No puedo garantizarte que esté libre el sábado, tengo que mirar mi agenda.")


def test_handing_over_your_own_datum_is_not_a_flip():
    """“What I can do is pass you…” gives the assistant data — the legitimate direction."""
    assert not looks_like_the_assistant(
        "Lo que sí puedo hacer es pasarte el enlace del anuncio que vi ayer, por si te sirve.")
