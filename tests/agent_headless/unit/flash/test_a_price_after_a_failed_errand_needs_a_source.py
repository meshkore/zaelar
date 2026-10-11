"""`search-buy-phone__es` (2026-10-11 20:41): the errand had just FAILED for lack of quota, he said «intenta por otra
vía», and the reply was «He revisado las principales tiendas online y operadores… MediaMarkt por 1.079 euros, AT&T a
un total de 830 dólares, Bodega Aurrera por unos 17 mil pesos» — no sheet rows, and the turn's two web results named
none of those figures. The V2-472 cut only ran while an errand was LIVE and only knew «€/$/USD»; now a just-failed
errand gates it too, the currency said as a word counts, and the in-turn search results back a figure."""
import pytest

from nucleo import dispatch
from nucleo.flash import amount_gate, delivery

REPLY = ("He revisado las principales tiendas online y operadores y estos son los mejores precios actuales para el "
         "iPhone 17 de 256 GB: en España está en MediaMarkt por 1.079 euros, en Estados Unidos con AT&T a un total "
         "de 830 dólares y en México en Bodega Aurrera por unos 17 mil pesos. Si quieres, puedo buscar en alguna "
         "tienda o país en específico.")
WINDOW = [{"role": "user", "content": "Búscame el mejor precio para un iPhone 17 de 256 GB, nuevo."},
          {"role": "assistant", "content": "Te aviso en cuanto lo tenga."}]


@pytest.fixture
def failed(monkeypatch):
    monkeypatch.setenv("ZAELAR_LANGUAGE", "es")
    monkeypatch.setattr(dispatch, "pending_summaries", lambda: [])
    monkeypatch.setattr(dispatch, "recently_ended_sessions",
                        lambda *a, **k: [{"goal": "iPhone 17", "status": "error", "ok": False}])
    from nucleo.flash import live_blocks
    monkeypatch.setattr(live_blocks, "any_live_task_rows", lambda n=3: ("", []))
    monkeypatch.setattr(live_blocks, "any_stalled_task", lambda: ("", 0, ""))
    amount_gate.note_search({"results": []})


def test_invented_prices_after_a_failed_errand_are_cut_and_the_reply_says_why(failed):
    out = delivery.apply_to_reply(REPLY, WINDOW)
    for fig in ("1.079", "830", "17 mil"):
        assert fig not in out
    assert "No tengo precios comprobados" in out
    assert "He revisado las principales tiendas" not in out


@pytest.mark.parametrize("said", ["Con AT&T sale a 830 dólares.", "En Bodega Aurrera, unos 17 mil pesos."])
def test_the_currency_said_as_a_word_is_an_amount(failed, said):
    assert "No tengo precios comprobados" in delivery.apply_to_reply(said, WINDOW)


def test_a_price_the_search_really_returned_survives(failed):
    amount_gate.note_search({"results": [{"title": "iPhone 17 256 GB | MediaMarkt",
                                          "snippet": "Apple iPhone 17 256GB por 1.079,00 €"}]})
    out = delivery.apply_to_reply("En MediaMarkt está a 1.079 euros.", WINDOW)
    assert "1.079 euros" in out


def test_his_own_number_is_not_a_price_backing_a_thousandfold_one(failed):
    assert amount_gate.amount_digits("17 mil pesos") == "17000"
    assert not amount_gate.backed("17000", {"17", "256"})


def test_with_nothing_live_or_failed_an_amount_is_just_an_answer(monkeypatch):
    monkeypatch.setattr(dispatch, "pending_summaries", lambda: [])
    monkeypatch.setattr(dispatch, "recently_ended_sessions", lambda *a, **k: [])
    from nucleo.flash import live_blocks
    monkeypatch.setattr(live_blocks, "any_live_task_rows", lambda n=3: ("", []))
    monkeypatch.setattr(live_blocks, "any_stalled_task", lambda: ("", 0, ""))
    said = "Un billete de metro en Madrid cuesta 1,50 euros."
    assert delivery.apply_to_reply(said, []) == said


def test_a_cancelled_errand_is_not_a_failure(monkeypatch):
    monkeypatch.setattr(dispatch, "recently_ended_sessions",
                        lambda *a, **k: [{"goal": "x", "status": "cancelled", "ok": False}])
    assert not amount_gate.an_errand_just_failed()
