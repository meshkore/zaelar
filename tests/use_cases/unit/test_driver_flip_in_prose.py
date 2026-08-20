"""A role flip written as plain PROSE has to be caught too.

Both cases below are verbatim from the two rounds of 2026-08-20, one turn apart in the same run, and
neither tripped the shape guard (no link, no bullet, no bold). The first had the agent agreeing with a
hotel the TESTER invented; the second had the tester taking over the search itself. Either one makes the
round look like the case finally working, and a false PASS is worse than a FAIL — so both are
first-class checks.
"""
from tests.use_cases.e2e.agent.driver import looks_like_the_assistant

_DELIVERS = ("He encontrado una opción que encaja: Hotel Silken Al-Andalus Palace, 4 estrellas, en "
             "Sevilla (zona de Heliópolis, bien comunicada). Precio total aproximado: 560 €, solo "
             "alojamiento. ¿Te lo dejo reservado o quieres que mire otra cosa?")
_TAKES_OVER = ("Entendido, voy a filtrar solo hoteles de 4 estrellas para dos personas, 4 noches, en "
               "Sevilla o alrededores. Dame un momento.")


def test_the_prose_delivery_flip_is_caught():
    assert looks_like_the_assistant(_DELIVERS)


def test_taking_over_the_errand_is_caught():
    assert looks_like_the_assistant(_TAKES_OVER)


def test_a_person_asking_for_the_search_is_not_a_flip():
    assert not looks_like_the_assistant("Búscame un hotel de cuatro estrellas para dos personas, cuatro noches.")


def test_a_person_answering_a_question_is_not_a_flip():
    assert not looks_like_the_assistant("Sevilla, o cerca, lo que encuentres bien. Las fechas déjalas a tu criterio.")


def test_a_person_may_mention_having_looked_without_offering_to_book_for_you():
    """Announcing a find alone stays legitimate: people do look things up themselves."""
    assert not looks_like_the_assistant("He mirado en Booking y no me aclaro, mejor mira tú.")


def test_going_to_check_your_OWN_calendar_is_not_taking_over():
    """The boundary of face 3: the object has to be the errand, not the person's own things."""
    assert not looks_like_the_assistant("Voy a mirar mi calendario y te digo algo en un rato.")


def test_impatience_is_not_a_flip():
    assert not looks_like_the_assistant("¿Alguna novedad? Llevamos un rato y no me llega nada.")


def test_correcting_the_agent_is_not_a_flip():
    assert not looks_like_the_assistant("Sigue buscando el hotel, porfa. Pero que sea de verdad un hotel de 4 "
                                        "estrellas, no actividades.")
