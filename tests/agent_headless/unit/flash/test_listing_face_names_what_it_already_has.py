"""V2-556 — the fast-pass face must NAME the rows it already has, on BOTH verdicts.

Measured on `search-buy-used-car__es` (2026-09-02, run v3). The escalated branch carried the partial count
as a fact —«De momento hay 4 anuncios provisionales en su hoja»— sitting NEXT TO an imperative that only
ordered «say the deep search is underway». The model obeyed the imperative and dropped the fact: four real
cars (AUDI A3 10.990 €, AUDI Q5 9.590 €, BMW X3 9.980 €, Renault Mégane 11.690 €) were on the sheet and the
turn answered «Muy bien. En cuanto tenga resultados específicos te los digo». One instruction per block, and
the fork INSIDE the imperative — the same lesson V2-222 paid for in `task_block`.

These assert the PROPERTY (the rows reach the face and the order to say them exists), never the wording.
"""
from nucleo.flash import listing_turn as LT


def _res(delivered: bool, n: int, ctx: str) -> dict:
    return {"delivered": delivered, "n": n, "ctx": ctx, "sheet": "s1", "escalated": 0 if delivered else 71}


_CTX = "AUDI A3 1.6TDI S Line — 10.990 EUR\nAUDI Q5 2.0TDI quattro — 9.590 EUR\nBMW X3 2.0d — 9.980 EUR"


def test_the_escalated_face_carries_the_partial_rows():
    """Not enough to serve the turn, but what WAS found is on the sheet — so the face has to say it."""
    face = LT.compose_face(_res(False, 3, _CTX), "búscame un coche diésel por menos de 12 mil")
    assert "AUDI A3" in face and "9.980" in face, "las filas parciales no llegan a la cara"
    assert "NÓMBRALE" in face, "la cara trae las filas y NO ordena nombrarlas — el defecto de run v3"
    assert "A FONDO" in face, "sigue teniendo que decir que la búsqueda profunda va en marcha"


def test_the_escalated_face_without_rows_does_not_promise_any():
    """Zero findings is the other half: the face must not invent an order to name what does not exist."""
    face = LT.compose_face(_res(False, 0, ""), "búscame un coche diésel")
    assert "NÓMBRALE" not in face and "ANUNCIOS PROVISIONALES" not in face
    assert "A FONDO" in face


def test_a_count_without_rows_is_not_announced_either():
    """`n` without `ctx` is a count nobody can name — announcing it produces «hay 4» and nothing else."""
    face = LT.compose_face(_res(False, 4, ""), "búscame un coche")
    assert "ANUNCIOS PROVISIONALES" not in face


def test_the_delivered_face_carries_the_rows_and_forbids_inventing():
    face = LT.compose_face(_res(True, 3, _CTX), "búscame un coche diésel por menos de 12 mil")
    assert "AUDI Q5" in face
    assert "No inventes" in face
    assert "búscame un coche diésel por menos de 12 mil" in face, "la petición literal ancla la respuesta"


def test_both_channels_call_the_SAME_face():
    """The two-channels rule one level up: the CALL was wired twice and so was the WORDING, which drifts.

    Two copies of a prompt do not fail with noise — the model just says something else in one channel. Since the
    ratchet pass the whole sequence (fast pass → face → stream) is `listing_turn.voice_turn`, so what the two
    channels share is a body, not a paragraph.
    """
    import inspect
    from nucleo.flash import probe
    from voice.engine.llm.providers import nucleo as voice_provider
    for mod in (probe, voice_provider):
        src = inspect.getsource(mod)
        assert "voice_turn(" in src, f"{mod.__name__} no usa el cuerpo compartido"
        assert "anuncios provisionales en su hoja" not in src, f"{mod.__name__} conserva una copia de la cara"
        assert "ANUNCIOS ENCONTRADOS" not in src, f"{mod.__name__} conserva una copia de la cara entregada"
