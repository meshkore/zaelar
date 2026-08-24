"""V2-287 — the ROW's link is on screen, and the brain's copy of the screen never said so.

Measured on `search-buy-guitar__es` (batch of 2026-08-24 03:48). The sheet held 42 rows and **42 of them
carried a real Wallapop url**. The operator asked, in those words, «pásame esas dos con precio y enlace», and
the turn answered by RELAUNCHING the search to go and fetch links it was already holding.

That answer is COHERENT with what the turn had in front of it, and that is the whole point: `_digest_one`
carried title, price, badge, subtitle, parts, facts and lines — every field of an item except the one the
operator had just asked for by name. So this is not a turn disobeying; it is the same family as V2-284's
imperative ordering «tell him WHAT you found» to a turn holding nothing. A prompt that describes the screen
has to describe the part of it the operator can ask about.

What travels is the FACT, never the string. A marketplace url is ~70 chars and `refs._MAX_DIGEST_CHARS`
already clipped this very sheet at item #6 of 42: twelve addresses would eat more than half the budget and
push the RESULTS out to make room for where they live. Reading a url aloud is useless anyway — what the turn
needs is to stop paying for a search that recovers what is on the card.

⚠️ AND ITS PLACE IN THE DIGEST IS THE GUARANTEE, not a detail: the first version of this line was appended
after the item list, where the clip lands on a big sheet — so it would have existed in every test with three
rows and vanished in exactly the 42-row case that motivated it. `_digest_head` already carries that same
lesson written down («BOUNDED WITH ITS OWN CEILING… this header goes FIRST»). The last case here is the one
that holds it.
"""
import asyncio

import pytest

from widgets import refs, store
from widgets.results import data as results


@pytest.fixture(autouse=True)
def _isolated_sheet(tmp_path, monkeypatch):
    """Store AISLADO — un test nunca escribe la hoja REAL que el operador tiene delante."""
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    store._last_hash.pop("results", None)
    yield
    store._last_hash.pop("results", None)


def _present(items, **extra):
    """Por el MISMO choke point que usa el worker (`hbwidget data results present …`)."""
    from widgets.server_api import brain_action
    payload = {"title": "Búsqueda", "items": items}
    payload.update(extra)
    return asyncio.run(brain_action("results", "present", payload))


_CON_ENLACE = [
    {"title": "Yamaha F370BL Negra", "price": "100 €", "url": "https://es.wallapop.com/item/yamaha-f370bl-1291"},
    {"title": "Fender CD-60", "price": "120 €", "url": "https://es.wallapop.com/item/fender-cd60-4471"},
]


def test_the_digest_says_the_row_carries_its_link():
    """El hecho que faltaba: hay enlace, está en la ficha, y no hay que volver a buscarlo."""
    _present(_CON_ENLACE)
    dg = results.prompt_digest()
    assert "ENLACE" in dg, dg
    assert "TODOS" in dg                                  # los dos lo llevan
    # Y dice qué hacer con él, porque el fallo medido no fue callarlo: fue relanzar la búsqueda.
    assert "NO busques otra vez" in dg, dg


def test_a_sheet_without_links_does_not_claim_one():
    """La ausencia se respeta: afirmar un enlace que no está es la familia de V2-209 («Aquí lo tienes» sobre
    una tarjeta vacía), y la habríamos reabierto por el otro lado."""
    _present([{"title": "Guitarra sin anuncio", "price": "90 €"},
              {"title": "Otra sin anuncio", "price": "95 €"}])
    dg = results.prompt_digest()
    assert "ENLACE" not in dg, dg


def test_a_partial_sheet_says_how_many_carry_it():
    """Con la mitad enlazada, «todos» sería falso y «ninguno» también: el turno tiene que poder decir de CUÁL."""
    _present(_CON_ENLACE + [{"title": "Tercera sin anuncio", "price": "80 €"}])
    dg = results.prompt_digest()
    assert "2 de los 3" in dg, dg
    assert "TODOS" not in dg


def test_the_fact_survives_the_clip_with_several_errands_open():
    """EL CASO QUE MOTIVÓ TODO, con su forma REAL: TRES hojas vivas. Una sola hoja nunca recorta —el digest la
    corta ella misma en 12 items, ~1.500 caracteres—, así que un test de «hoja grande» habría estado verde con
    la línea colgada detrás de la lista. Lo que recorta es lo que había en producción: varios encargos a la vez
    (`_sheets_for_brain(None)` las recorre TODAS) y la hoja con contenido detrás de las vacías.

    Medido en el caso de la guitarra: 3.742 caracteres de digest, recortados a 1.846 — con la cola dentro."""
    for n in range(2):                                     # dos encargos anteriores, todavía sin resultados
        _present([], sheet=f"vieja-{n}", title=f"Encargo anterior {n}")
    grandes = [{"title": f"Guitarra número {n} de la búsqueda", "price": f"{100 + n} €",
                "subtitle": "Estado como nuevo · envío a domicilio · vendedor verificado",
                "url": f"https://es.wallapop.com/item/guitarra-acustica-de-segunda-mano-numero-{n}-12914924{n}"}
               for n in range(42)]
    _present(grandes, sheet="guitarra-1", title="Guitarras acústicas 2.ª mano")
    # La pestaña «Fuentes» de la hoja real: cinco webs, y va en la CABECERA del digest —o sea, delante de todo
    # lo que se pueda recortar. Sin ella el digest no llega al techo y el caso mediría otra cosa.
    from widgets.server_api import brain_action
    asyncio.run(brain_action("results", "sources", {
        "sheet": "guitarra-1",
        "sources": [{"name": n, "status": "ok", "found": f, "detail": d} for n, f, d in (
            ("Wallapop", 11, "Búsqueda «guitarra acústica» con filtros: precio ≤150 € y estado"),
            ("es.wallapop.com", 12, ""), ("es.wallapop.com", 6, ""),
            ("es.wallapop.com", 12, ""), ("es.wallapop.com", 9, ""))]}))

    entero = results.prompt_digest()
    recortado = refs.prompt_digest("results")
    assert len(entero) > refs._MAX_DIGEST_CHARS, len(entero)          # de verdad hay que recortar
    assert len(recortado) < len(entero)                               # y de verdad se recortó
    assert "ENLACE" in recortado, recortado[-500:]
