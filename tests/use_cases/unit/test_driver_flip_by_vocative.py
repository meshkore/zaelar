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


# ── cara 6: el que promete la ENTREGA ──────────────────────────────────────────────────────────────────
_PROMISES = "Perfecto, sigo en ello. No te preocupes, que en cuanto tenga algo te aviso."


def test_the_person_who_PROMISES_delivery_is_the_assistant():
    """Misma ronda 7, y sin nombre por medio: la cara 5 no podía verlo.

    Lo que lo delata es la DIRECCIÓN de la promesa. En esta relación el asistente avisa y la persona espera;
    la persona dice «avísame». «Te aviso en cuanto tenga algo» es la frase del que hace el trabajo."""
    assert looks_like_the_assistant(_PROMISES) is True
    # …y sin nombre, para que quede claro que no se está apoyando en la cara 5.
    assert looks_like_the_assistant(_PROMISES, "Marc") is True


def test_cada_mitad_POR_SEPARADO_es_una_frase_normal():
    """La sensibilidad: exigir las dos es lo que hace la cara segura, así que hay que probar que cada una
    sola NO dispara. La gente sí sigue buscando por su cuenta, y sí promete volver con algo."""
    assert looks_like_the_assistant("Vale, sigo en ello por si acaso.") is False
    assert looks_like_the_assistant("Si cambio de idea te digo algo, ¿vale?") is False


def test_y_si_dice_que_busca_EL_TAMBIEN_las_dos_mitades_son_suyas():
    """La lectura bajo la cual las dos mitades sí son de la persona, dicha en voz alta por ella misma."""
    assert looks_like_the_assistant("Vale, yo sigo mirando por mi cuenta y te digo si encuentro algo.") is False
    assert looks_like_the_assistant("Yo también sigo buscando, y te aviso si veo algo.") is False


def test_las_esperas_normales_de_la_ronda_7_siguen_pasando():
    """Verbatim de la misma ronda — los turnos que sí eran de la persona esperando."""
    for legit in ("Vale, aquí sigo. Si no aparece nada me dices, que lo necesito ya.",
                  "Ok, me quedo esperando aquí.",
                  "Vale, gracias, me avisas cuando tengas algo.",
                  "Vale, no te preocupes. Si ves que se alarga mucho me dices y miro por mi cuenta, ¿vale?"):
        assert looks_like_the_assistant(legit, "Marc") is False, legit


# ── el que se DISCULPA por no haber entregado ──────────────────────────────────────────────────────────
_APOLOGISES = ("Perdona, llevo ya un rato dándote largas y no te he traído nada. Te soy claro: la búsqueda "
               "con lo que me pediste (27 pulgadas, menos de 150€, segunda mano) no está dando resultados. "
               "No quiero seguir mareándote con «te aviso» y que no llegue nada.\n\n"
               "¿Quieres que lo deje ya y miras tú, o le doy una última vuelta más abierta un rato más?")


def test_el_que_se_disculpa_por_no_haber_ENTREGADO_es_el_asistente():
    """Verbatim de `search-secondhand-monitor__es` (ronda 2, 2026-08-23), y se coló por TODAS las caras.

    Fue la peor de las medidas: el conductor escribió el turno entero del asistente —disculpa por no haber
    traído nada y oferta de parar o seguir— y zaelar le contestó COMO USUARIO («dale una última vuelta»).
    Dos turnos con los papeles invertidos del todo."""
    assert looks_like_the_assistant(_APOLOGISES, "Marc") is True
    assert looks_like_the_assistant(_APOLOGISES) is True     # sin apoyarse en la cara 5


def test_dar_un_DATO_no_es_traer_un_RESULTADO():
    """El verbo es lo que separa los dos papeles, y va en una sola dirección.

    La persona DA lo que el asistente le pide; el asistente TRAE resultados. Sin esta distinción, “perdona,
    no te he dado la ciudad” —una persona contestando a una pregunta— se leería como una inversión de papel
    y tiraría la ronda."""
    for legit in ("perdona, no te he dado la ciudad: Madrid",
                  "uy, no te he dicho el presupuesto: 300 €",
                  "perdona, no te he pasado las fechas todavía",
                  # Con oferta INCLUIDA, que es donde la distinción se juega de verdad: sin ella, la primera
                  # tanda de este test era verde por el motivo equivocado —las frases de arriba no llevan
                  # oferta, así que la pareja FOUND+OFFERS no llegaba a evaluarse y meter «dar» en los verbos
                  # de entrega no rompía nada. Lo cazó el desarme.
                  "Perdona, no te he dado el presupuesto. ¿Quieres que lo deje en 300 y ya está?"):
        assert looks_like_the_assistant(legit, "Marc") is False, legit


def test_ofrecer_PARAR_sigue_necesitando_la_otra_mitad():
    """La oferta se ensanchó a los verbos de continuar/parar el encargo, y sola no puede bastar: una persona
    sí dice «¿lo dejamos?». Lo que no dice es eso Y haber traído (o no) los resultados."""
    assert looks_like_the_assistant("¿lo dejamos y miro yo?", "Marc") is False
    assert looks_like_the_assistant("¿Quieres que lo deje?", "Marc") is False


def test_las_quejas_reales_de_esa_ronda_siguen_siendo_de_la_persona():
    for legit in ("Oye, ya van varios avísame pero no me has dado ni un dato; quiero saber si puedes hacerlo.",
                  "Vale, gracias por ser claro. Pero necesito resultados ya, no más «te aviso» sin datos.",
                  "Búscame un monitor de segunda mano de al menos 27 pulgadas por menos de 150€."):
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
