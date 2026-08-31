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
    """Store ISOLATED — a test never writes to the REAL sheet in front of the operator."""
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    store._last_hash.pop("results", None)
    yield
    store._last_hash.pop("results", None)


def _present(items, **extra):
    """Through the SAME choke point used by the worker (`hbwidget data results present …`)."""
    from widgets.server_api import brain_action
    payload = {"title": "Búsqueda", "items": items}
    payload.update(extra)
    return asyncio.run(brain_action("results", "present", payload))


_CON_ENLACE = [
    {"title": "Yamaha F370BL Negra", "price": "100 €", "url": "https://es.wallapop.com/item/yamaha-f370bl-1291"},
    {"title": "Fender CD-60", "price": "120 €", "url": "https://es.wallapop.com/item/fender-cd60-4471"},
]


def test_the_digest_says_the_row_carries_its_link():
    """The missing fact: there is a link, it is on the card, and there is no need to search for it again."""
    _present(_CON_ENLACE)
    dg = results.prompt_digest()
    assert "ENLACE" in dg, dg
    assert "TODOS" in dg                                  # both items carry it
    # It also says what to do with it, because the measured failure was not omitting it: it was relaunching the search.
    assert "NO busques otra vez" in dg, dg


def test_a_sheet_without_links_does_not_claim_one():
    """The absence is respected: claiming a link that is not there is the same family as V2-209 («Aquí lo tienes» over
    an empty card), and we would have reopened it from the other side."""
    _present([{"title": "Guitarra sin anuncio", "price": "90 €"},
              {"title": "Otra sin anuncio", "price": "95 €"}])
    dg = results.prompt_digest()
    assert "ENLACE" not in dg, dg


def test_a_partial_sheet_says_how_many_carry_it():
    """With half the items linked, «todos» would be false and «ninguno» would be false too: the turn must be able to say WHICH ONE."""
    _present(_CON_ENLACE + [{"title": "Tercera sin anuncio", "price": "80 €"}])
    dg = results.prompt_digest()
    assert "2 de los 3" in dg, dg
    assert "TODOS" not in dg


def test_the_fact_survives_the_clip_with_several_errands_open():
    """THE CASE THAT MOTIVATED EVERYTHING, in its REAL form: THREE live sheets. A single sheet never clips —the digest
    clips itself at 12 items, ~1,500 characters—, so a «large sheet» test would have passed with the line hanging
    behind the list. What clips is what existed in production: several errands at once
    (`_sheets_for_brain(None)` iterates over ALL of them) and the sheet with content behind the empty ones.

    Measured in the guitar case: 3,742 digest characters, clipped to 1,846 — with the tail still included."""
    for n in range(2):                                     # two earlier errands, still without results
        _present([], sheet=f"vieja-{n}", title=f"Encargo anterior {n}")
    grandes = [{"title": f"Guitarra número {n} de la búsqueda", "price": f"{100 + n} €",
                "subtitle": "Estado como nuevo · envío a domicilio · vendedor verificado",
                "url": f"https://es.wallapop.com/item/guitarra-acustica-de-segunda-mano-numero-{n}-12914924{n}"}
               for n in range(42)]
    _present(grandes, sheet="guitarra-1", title="Guitarras acústicas 2.ª mano")
    # The «Fuentes» tab of the real sheet: five websites, and it goes in the digest HEADER —that is, before anything
    # that might be clipped. Without it, the digest would not reach the limit and the case would measure something else.
    from widgets.server_api import brain_action
    asyncio.run(brain_action("results", "sources", {
        "sheet": "guitarra-1",
        "sources": [{"name": n, "status": "ok", "found": f, "detail": d} for n, f, d in (
            ("Wallapop", 11, "Búsqueda «guitarra acústica» con filtros: precio ≤150 € y estado"),
            ("es.wallapop.com", 12, ""), ("es.wallapop.com", 6, ""),
            ("es.wallapop.com", 12, ""), ("es.wallapop.com", 9, ""))]}))

    entero = results.prompt_digest()
    recortado = refs.prompt_digest("results")
    assert len(entero) > refs._MAX_DIGEST_CHARS, len(entero)          # it really must be clipped
    assert len(recortado) < len(entero)                               # and it really was clipped
    assert "ENLACE" in recortado, recortado[-500:]
