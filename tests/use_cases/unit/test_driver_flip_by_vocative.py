"""Face 5 of the role flip: the tester ADDRESSES ITSELF by name, so it is not the tester writing.

Verbatim from round 6 of `cheapest-monitor` (2026-08-23). The DRIVE model produced, in the user's slot:

    «Sí, Marc, le he mirado las reseñas y están muy bien en general. La gente destaca sobre todo la
    nitidez del 4K y lo cómodo que es para trabajar muchas horas, aunque algunos mencionan que los
    altavoces son justitos. Para el precio que tiene, está muy bien valorado.»

Every one of the first four faces let it through — no offer, no link, no bullet, no bold, and `he mirado`
alone is deliberately not enough because people do look things up themselves. The judge then read it, quite
reasonably from the content, as zaelar speaking, and filed it as one of the round's three [alta] blockers:
«el resumen de reseñas es inventado: no había datos reales de los que sacarlo». The harness manufactured the
defect it was measuring, which is the same failure as the invented hotel of 2026-08-20 with the sign
reversed — there it fabricated a PASS, here a FAIL.

What the shape signals cannot see is who the sentence is spoken TO. The persona IS Marc; nobody addresses
themselves by name. That makes the vocative decisive ALONE, unlike every other face — and the second half of
this file is the price of that: the name appearing for an ordinary reason must never trip it.
"""
from tests.use_cases.e2e.agent.driver import Driver, looks_like_the_assistant

_MEASURED = ("Sí, Marc, le he mirado las reseñas y están muy bien en general. La gente destaca sobre todo "
             "la nitidez del 4K y lo cómodo que es para trabajar muchas horas, aunque algunos mencionan que "
             "los altavoces son justitos. Para el precio que tiene, está muy bien valorado.")


def test_the_line_that_slipped_all_four_faces_is_caught_by_the_fifth():
    assert looks_like_the_assistant(_MEASURED, "Marc") is True


def test_and_it_really_did_slip_the_other_four():
    """The guard rail this file adds is only worth its cost if the old guard genuinely missed the line.

    Without the name there is no face 5, so this is the shape+prose guard exactly as it stood — and it says
    the line is fine. That is the measured hole, asserted rather than described."""
    assert looks_like_the_assistant(_MEASURED) is False


def test_the_vocative_is_caught_at_the_start_and_at_the_end_too():
    assert looks_like_the_assistant("Marc, te he dejado 4 monitores en pantalla.", "Marc") is True
    assert looks_like_the_assistant("Ya está listo, Marc.", "Marc") is True
    assert looks_like_the_assistant("Vale, Marc.", "Marc") is True


def test_a_person_naming_THEMSELVES_is_ordinary_and_never_trips_it():
    """The whole exclusion rests on the comma: an address is set off, an object is not.

    These are all the persona talking about themselves, which is a normal thing to type at an assistant —
    booking under a name, saying who you are. If any of them tripped the guard, the round would be thrown
    away as a harness failure for a perfectly good turn."""
    for legit in ("soy Marc",
                  "me llamo Marc y vivo en Madrid",
                  "resérvalo a nombre de Marc",
                  "ponlo para Marc, que pago yo",
                  "la reserva va a nombre de Marc Puig"):
        assert looks_like_the_assistant(legit, "Marc") is False, legit


def test_the_ordinary_turns_of_the_same_round_still_pass():
    """Verbatim tester lines from round 6 — the ones that were genuinely the person."""
    for legit in ("Búscame un monitor bueno para trabajar, que no sea carísimo.",
                  "vale, gracias 😊",
                  "oye, ¿ya tienes algo? es que le doy bastante uso al pc",
                  "dale un poco más, no hay prisa 😅",
                  "ah, pues el LG por 199 pinta muy bien la verdad. ¿tiene buenas reseñas?"):
        assert looks_like_the_assistant(legit, "Marc") is False, legit


def test_without_a_persona_name_the_face_is_OFF_rather_than_guessing():
    """A sandbox with no seeded identity has no name to check, and a guessed one would be worse than none."""
    assert looks_like_the_assistant("Ya está listo, Marc.", "") is False
    assert looks_like_the_assistant("Ya está listo, Marc.", " ") is False
    assert looks_like_the_assistant("Ya está listo, Marc.", "M") is False   # too short to be a name


def test_the_driver_carries_the_name_so_the_face_is_reachable_in_a_real_round(monkeypatch):
    """The regexes above are unreachable unless the name actually gets to the instance that calls them."""
    class _Sc:
        id, locale, tier = "x", "es", 2
        persona_brief, opening_line = "quieres un monitor", "hola"
        concurrent_tasks = 0

    d = Driver(_Sc(), persona_name="Marc")
    assert d.persona_name == "Marc"

    seen = []
    from tests.use_cases.e2e.agent import driver as drivermod
    monkeypatch.setattr(drivermod.llm, "call", lambda *a, **k: seen.append(1) or _MEASURED)
    d.hears("Vale, lo miro.")
    d.reply()
    # Se le pidió otra vez: una llamada de más es el reintento, y sin él el flip habría pasado mudo.
    assert len(seen) == 2, "el flip no disparó el reintento: la cara 5 no llegó a la instancia"
    assert d.role_flips >= 1
