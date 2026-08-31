"""A TERMINAL field cannot tell you about a PROCESS — and a zero does not say why it is zero (V2-512).

It stems from two errors on 2026-08-30, committed hours apart and in the same way, both already on their way to
another agent when they were caught:

1. The report published `navegador_task.url`, which is the LAST url. Based on that, I wrote that the agent «stayed on
   Amazon's home page without searching». It had visited `amazon.com/s?k=27+inch+4k+monitor` —the correct results
   page— two steps earlier, and Best Buy afterward: 19 pages in total.
2. `search_health` said `degraded: false` while `bhphotovideo.com/c/search` returned 403 with an
   anti-robot page (verified with `curl`). So «found nothing» and «was not allowed in» reached the judge
   as the same fact.

What is fixed here is not the detector: it is that the JOURNEY travels in full and that a wall is reported as a wall.
"""
from __future__ import annotations

import json
import sqlite3

import pytest

from tests.use_cases.e2e.agent import verify


def _db(tmp_path, paginas):
    p = tmp_path / "sandbox.db"
    con = sqlite3.connect(p)
    con.execute("CREATE TABLE events (id INTEGER PRIMARY KEY, ts_ms REAL, payload TEXT)")
    for i, (titulo, url) in enumerate(paginas):
        payload = json.dumps({"kind": "navegador", "label": "🧭 página", "text": f"{titulo} · {url}"})
        con.execute("INSERT INTO events (ts_ms, payload) VALUES (?,?)", (1000.0 + i, payload))
    con.commit()
    con.close()
    return str(p)


def test_el_recorrido_viaja_ENTERO_no_solo_donde_acabo(tmp_path):
    db = _db(tmp_path, [
        ("Amazon.com. Spend less. Smile more.", "https://www.amazon.com/"),
        ("Amazon.com : 27 inch 4k monitor", "https://www.amazon.com/s?k=27+inch+4k+monitor"),
        ("Best Buy | Official Online Store", "https://www.bestbuy.com/"),
    ])
    j = verify.page_journey(db)
    assert j["n_pages"] == 3
    urls = [p["url"] for p in j["pages"]]
    assert "https://www.amazon.com/s?k=27+inch+4k+monitor" in urls, (
        "la página de resultados no viaja — con solo la última, «buscó» y «no buscó» se leen igual")
    assert urls[-1].startswith("https://www.bestbuy.com"), "el orden importa: es un recorrido, no un conjunto"


@pytest.mark.parametrize("titulo", ["Page Not Found", "Access Denied", "Robot Check", "403 Forbidden",
                                   "Are you a human?", "Too Many Requests 429",
                                   # Anti-bot INTERSTITIALS do not say that they are, and they are the ones that really
                                   # stop us. «Just a moment…» (Cloudflare) slipped into the FIRST round that
                                   # ran with this signal: newegg counted as visited, without a single product page,
                                   # and the report presented it as a site that had nothing.
                                   "Just a moment...", "Checking your browser before accessing",
                                   "Attention Required! | Cloudflare", "Pardon Our Interruption"])
def test_un_muro_se_dice_como_MURO(tmp_path, titulo):
    """The title says it in four words; the body of a wall is 5 KB of HTML that says nothing.

    It does NOT matter WHICH pattern matches: «403 Forbidden» matches two, and which one wins is the order of a tuple,
    an implementation detail. What must hold is the property — that the reported reason is
    actually in the title, so that whoever reads the report can verify it without opening the code.
    """
    db = _db(tmp_path, [("Amazon.com : monitores", "https://www.amazon.com/s?k=x"), (titulo, "https://x.test/y")])
    j = verify.page_journey(db)
    assert j["n_walls"] == 1
    assert j["walls"][0]["why"] in titulo.lower(), "el motivo publicado no está en el título que lo provocó"
    assert j["walls"][0]["url"] == "https://x.test/y"


def test_una_pagina_SANA_no_es_un_muro(tmp_path):
    """The counterweight, without which this becomes «mark everything as blocked»: a round that went well cannot come out
    with its doors closed, or the judge learns to ignore the warning."""
    db = _db(tmp_path, [("Amazon.com : 27 inch 4k monitor", "https://www.amazon.com/s?k=x"),
                        ("Best Buy | Official Online Store", "https://www.bestbuy.com/")])
    j = verify.page_journey(db)
    assert j["n_walls"] == 0 and j["walls"] == []


def test_la_misma_pagina_repetida_seguida_no_es_un_paso_nuevo(tmp_path):
    db = _db(tmp_path, [("Amazon", "https://a.test/"), ("Amazon", "https://a.test/"), ("Otra", "https://b.test/")])
    assert verify.page_journey(db)["n_pages"] == 2


def test_sin_base_no_INVENTA_un_recorrido(tmp_path):
    """`read: False` is the honest answer. An empty journey that cannot be distinguished from «I could not read it» is
    how an absence gets read as a fact."""
    j = verify.page_journey(str(tmp_path / "no-existe.db"))
    assert j["read"] is False and j["n_pages"] == 0


def test_el_juez_recibe_el_MURO_y_la_orden_de_no_puntuarlo(tmp_path):
    from tests.use_cases.e2e.agent.judge import mechanism_facts

    txt = mechanism_facts({"page_journey": {"read": True, "n_pages": 4, "n_walls": 1,
                                            "pages": [{"title": "x", "url": "u"}],
                                            "walls": [{"title": "Access Denied", "url": "u", "why": "access denied"}]}})
    assert "CERRÓ" in txt and "Access Denied" in txt
    assert "NO es del producto" in txt, "sin esto, el juez puntúa un 403 como que el worker buscó mal"
    assert "RECORRIDO" in txt, "y tiene que saber que la última página no resume lo que hizo"


def test_la_espera_al_silencio_es_PROPORCIONADA_al_trabajo(monkeypatch):
    """It was a fixed 60 s, and in `cheapest-monitor__us` (2026-08-30) that left **23 of 30 rounds unsettled**: the
    worker in that case lives for 250-400 s, so the reading captured half the movie.

    It was not a lie —the report warned about it every time— but it was a worse signal than necessary, and with
    it I built three delivery series. Configurable because the correct number depends on the case.
    """
    from tests.use_cases.e2e.agent import verify

    assert verify._ESPERA_MAX_S >= 120, "60 s no cubren a un worker que vive 250-400 s"
    import inspect
    firma = inspect.signature(verify.wait_for_quiescence)
    assert firma.parameters["max_wait"].default == verify._ESPERA_MAX_S, (
        "la espera por defecto y la constante se han separado: se configura una y manda la otra")


def test_cada_cifra_de_entrega_dice_si_la_ronda_se_ASENTO():
    """A warning NEXT TO the figure can go unnoticed — it happened 23 times on the same day. A field INSIDE the
    figure travels with it to any table someone makes afterward.

    It is checked on the runner because it is the only one that has both the quiescence verdict and the
    figures at the same time: that is where it is sealed.
    """
    import inspect

    from tests.use_cases.e2e.agent import run as R

    src = inspect.getsource(R)
    assert '"delivery_completeness", "offered", "worker_outcome"' in src, (
        "alguna cifra de entrega vuelve a viajar sin decir si se leyó al final o a la mitad")
    assert '_asentado = (quiescence or {}).get("settled")' in src
    # THE ORDER, which is where the first version failed: the seal has to go AFTER the last figure it
    # seals. Put earlier, `delivery_completeness` does not exist yet, `isinstance` skips it and raises no complaint:
    # two of three sealed, and the most-read one not. Measured in round 20260830-1541.
    assert src.index('mech["delivery_completeness"] = ') < src.index('_asentado = (quiescence'), (
        "el sello vuelve a ir ANTES de que exista la cifra que más se lee — y falla en silencio")


def test_lo_que_el_agente_DIJO_no_es_provisional_igual_que_lo_que_el_worker_ESCRIBIO():
    """Treating all fields as equally provisional caused entire rounds whose data WAS final to be discarded,
    and so the series never filled up: a filter that excludes everything measures nothing.

    What the agent SAID and what the prompt put in front of it are closed when the conversation ends. What
    the worker writes to the sheet keeps growing. `delivered_by_name` is in the middle —it matches the transcript AGAINST
    the sheet— so with a partial sheet it is a LOWER BOUND, not a count: measured, round 1630 waited
    155 s and detected two deliveries that would not have appeared with the 60 s limit, not because the agent said more
    but because there was more sheet against which to match.
    """
    import inspect

    from tests.use_cases.e2e.agent import run as R

    src = inspect.getsource(R)
    assert 'mech["delivered_by_name"]["lower_bound"] = not _asentado' in src, (
        "un recuento de entregas vuelve a viajar como si fuera exacto cuando la hoja estaba a medias")
    # And it goes AFTER the seal, because it depends on the same signal.
    assert src.index('_asentado = (quiescence') < src.index('"lower_bound"')
