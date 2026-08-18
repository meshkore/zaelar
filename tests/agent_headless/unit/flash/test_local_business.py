"""V2-144 (`book-barber-slot__es`) — a whole class of task had no destination, so it got a worker with no
browser.

«Resérvame hora en la peluquería de siempre para el sábado por la mañana» classified as `generic`. Measured
before touching anything: `site_catalog.category_of` → None, `dispatch._classify_kind` → "generic",
`router_guards._needs_real_work` → False. So even after the operator gave the neighbourhood («Valencia, Ruzafa»)
there was nowhere for a search to happen, the promise backstop had nothing to escalate, and the turn became
«me pongo a buscar peluquerías en Ruzafa» with 0 searches and 0 browser tasks behind it — followed, two turns
later, by «todavía está buscando, lleva poco más de un minuto» about a task that never existed.

One missing category, three cases: a hairdresser here, a pharmacy in `reorder-prescription`, a gym in
`renew-gym-membership`. All of them are the same request — find a LOCAL business and get in touch with it.

The pattern demands a booking/contact verb next to the business, never the noun on its own: «¿a qué hora abre la
farmacia?» is a quick fact that `web_search` answers inside the turn, and routing that to a browser worker would
break the case that measures exactly that.
"""
from __future__ import annotations

import asyncio

import pytest

from memory import db as memdb
from memory import embeddings as mememb
from nucleo import dispatch
from nucleo.flash import probe
from nucleo.flash import prompt
from nucleo.flash import router_guards as g
from nucleo.flash import site_catalog as sc


@pytest.fixture(autouse=True)
def _hash_backend(monkeypatch):
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    mememb.reset()
    yield
    mememb.reset()


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    memdb.reset_db()
    memdb.get_db()
    yield
    memdb.reset_db()


@pytest.mark.parametrize("text", [
    "Resérvame hora en la peluquería de siempre para el sábado por la mañana.",
    "pide cita con mi dentista",
    "búscame una peluquería en Ruzafa",
    "llama al taller y pide cita",
    "busca los gimnasios de Sevilla",
    "busca el teléfono de la farmacia del barrio",
    "book me an appointment at the hairdresser",
])
def test_a_local_business_errand_gets_a_browser(text):
    assert sc.category_of(text) == "local_business"
    assert sc.category_of(text) in sc.TRANSACTIONAL_CATEGORIES
    assert dispatch._classify_kind(text) == "web"
    assert g._needs_real_work(text) is True


@pytest.mark.parametrize("text", [
    # The quick-fact case, verbatim. A fact `web_search` answers in the turn — a browser worker would be a
    # regression, and there is a case in this suite that measures it.
    "¿A qué hora abre mañana el Museo del Prado y cuánto cuesta la entrada general?",
    "¿a qué hora abre la farmacia?",
    "¿cuánto cuesta un corte de pelo?",
    "pon música",
])
def test_a_question_about_one_is_not_an_errand(text):
    assert sc.category_of(text) is None
    assert dispatch._classify_kind(text) == "generic"


@pytest.mark.parametrize("text,expected", [
    ("reserva mesa en Casa Lucio esta noche", "restaurant_booking"),
    ("resérvame una noche de hotel en Burgos el 20 de septiembre", "hotel_booking"),
    ("consígueme dos entradas para el musical del sábado", "event_tickets"),
])
def test_the_more_specific_categories_still_win(text, expected):
    """`category_of` returns the FIRST match, so the new pattern sits after them on purpose."""
    assert sc.category_of(text) == expected


def test_the_catalog_has_a_destination_in_both_locales():
    for locale in ("es", "us"):
        entry = sc.entry_for("local_business", locale)
        assert entry is not None and entry.url


class _PromisesToSearch:
    async def stream(self, *_a, **_kw):
        yield "Perfecto. Me pongo a buscar peluquerías en el barrio de Ruzafa, Valencia, y te digo cuál encuentro."


def test_the_promise_after_the_missing_datum_now_starts_something(fresh_db, monkeypatch):
    """The real turn: the operator finally gives the neighbourhood and zaelar says it is on it. Before this,
    nothing fired — and two turns later it reported a task that had never existed."""
    monkeypatch.setattr("nucleo.flash.fast_client.FastClient", _PromisesToSearch)
    monkeypatch.setattr("nucleo.dispatch.has_active", lambda: False)
    sess = probe._session("t-v144")
    sess.seeded = True
    sess.window[:] = [
        {"role": "user", "content": "Resérvame hora en la peluquería de siempre para el sábado por la mañana."},
        {"role": "assistant", "content": "¿Cuál es el nombre?"},
        {"role": "user", "content": "la de siempre, no me lo sé"},
        {"role": "assistant", "content": "¿En qué ciudad vives?"}]
    res = asyncio.run(probe.run_turn("En Valencia, por el barrio de Ruzafa.", sid="t-v144", ingest=False))
    probe._SESSIONS.pop("t-v144", None)
    assert res["action"] == "escalate"


def test_the_prompt_says_not_to_ask_for_what_it_can_look_up(fresh_db):
    """Turn 1 asked for the phone number. A phone is exactly what a search returns; asking for it blocks the
    task on something zaelar can find. What was genuinely missing was the neighbourhood — and the operator gave
    it the moment he was asked for it."""
    system, _ = prompt.build_flash_system()
    assert "pide solo lo que NO puedes averiguar" in system
