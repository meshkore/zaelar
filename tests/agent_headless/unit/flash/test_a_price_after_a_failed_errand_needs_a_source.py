"""`search-buy-phone__es` (2026-10-11 20:41): the errand had just FAILED for lack of quota, he said «intenta por otra
vía», and the reply was «He revisado las principales tiendas online y operadores… MediaMarkt por 1.079 euros, AT&T a
un total de 830 dólares, Bodega Aurrera por unos 17 mil pesos» — no sheet rows, and the turn's two web results named
none of those figures. The V2-472 cut only ran while an errand was LIVE and only knew «€/$/USD»; now a just-failed
errand gates it too, the currency said as a word counts, and the in-turn search results back a figure."""
import pytest

from nucleo import dispatch
from nucleo.flash import amount_gate

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
    amount_gate.note_search({"results": []})

