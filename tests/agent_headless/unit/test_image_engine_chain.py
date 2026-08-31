"""V2-466 — the image-search chain: never rely on just one.

Operator request (2026-08-28) after seeing Google ask for a captcha for an entire afternoon: «we cannot rely
on Google all the time; let’s have a list of search engines and iterate from one to the next».

The order is NOT based on reputation; it is what was MEASURED that day from this machine with the same query:

    google      captcha              →  0 resultados
    ecosia      captcha (proxia)     →  0
    ddg/brave/startpage/qwant        →  pintan la galería solo tras interacción
    yandex      30 tiles             →  el coche CORRECTO
    bing        52 tiles             →  el coche EQUIVOCADO 9 de cada 10 (SF90, F8, dos F80)

That is why Bing remains LAST rather than being the first fallback, which is where it was.
"""
from __future__ import annotations

import asyncio

from nucleo import browser_search as BS, image_search as I


def _falso(**por_motor):
    """Replaces the three legs with fixed responses, to measure the CHAIN rather than the network."""
    async def _mk(name):
        async def _leg(q, k=12):
            return dict(por_motor.get(name) or {"query": q, "items": [], "source": name, "blocked": False})
        return _leg
    return _mk


def _instalar(monkeypatch, **por_motor):
    mk = _falso(**por_motor)
    for name, attr in (("google", "search_images"), ("yandex", "search_images_yandex"),
                       ("bing", "search_images_bing")):
        monkeypatch.setattr(BS, attr, asyncio.run(mk(name)), raising=False)


def _items(n=3, site="www.ferrari.com"):
    return [{"url": f"https://x/{i}.jpg", "thumb": f"https://t/{i}", "title": f"foto {i}",
             "site": site, "page": "https://p", "w": 800, "h": 600} for i in range(n)]


# ── the order ───────────────────────────────────────────────────────────────────────────────────────────
def test_el_orden_es_google_yandex_bing():
    """Hand-verified: each row came from a measurement, and Bing being last is not an aesthetic detail."""
    assert BS._IMAGE_ENGINES == ("google", "yandex", "bing")


def test_si_google_contesta_no_se_pregunta_a_nadie_mas(monkeypatch):
    _instalar(monkeypatch, google={"query": "x", "items": _items(), "source": "google", "blocked": False})
    r = asyncio.run(BS.images("x"))
    assert r["source"] == "google" and "degraded_from" not in r


def test_google_BLOQUEADO_pasa_a_yandex_y_NO_a_bing(monkeypatch):
    """The defect that prompted this: the captcha sent requests straight to the weakest index."""
    _instalar(monkeypatch,
              google={"query": "x", "items": [], "source": "google", "blocked": True},
              yandex={"query": "x", "items": _items(), "source": "yandex", "blocked": False},
              bing={"query": "x", "items": _items(9), "source": "bing", "blocked": False})
    r = asyncio.run(BS.images("x"))
    assert r["source"] == "yandex"
    assert r["degraded_from"] == "google" and r["degraded_because"] == "blocked"
    assert r["blocked"] is True, "el captcha del primero sigue siendo un hecho del turno"


def test_bing_solo_cuando_los_dos_de_arriba_fallan(monkeypatch):
    _instalar(monkeypatch,
              google={"query": "x", "items": [], "source": "google", "blocked": False},
              yandex={"query": "x", "items": [], "source": "yandex", "blocked": False},
              bing={"query": "x", "items": _items(), "source": "bing", "blocked": False})
    r = asyncio.run(BS.images("x"))
    assert r["source"] == "bing" and r["tried"] == ["google", "yandex"]
    assert r["degraded_because"] == "empty", "vacío ≠ bloqueado: uno pide reformular, el otro esperar"


def test_con_TODOS_caidos_se_dice_a_cuantos_se_preguntó(monkeypatch):
    """«No hay fotos de eso» y «los tres índices están caídos» piden cosas distintas."""
    _instalar(monkeypatch, google={"query": "x", "items": [], "source": "google", "blocked": True})
    r = asyncio.run(BS.images("x"))
    assert r["items"] == [] and r["tried"] == ["google", "yandex", "bing"]
    assert r.get("blocked") is True, "el bloqueo del primero es lo que explica el turno"


# ── the Yandex parser, without a network ───────────────────────────────────────────────────────────────
def test_yandex_saca_la_foto_a_TAMAÑO_COMPLETO_del_enlace():
    """The fragile part—the `img_url` inside the tile link—is what must be testable without a network."""
    rows = [{"href": "https://yandex.com/images/search?pos=0&img_url=https%3A%2F%2Fd.com%2Fa.jpg&rpt=simage",
             "alt": "Ferrari Amalfi 2026", "thumb": "https://avatars.mds.yandex.net/t.jpg", "w": 480, "h": 320}]
    it = I.parse_yandex_rows(rows)[0]
    assert it["url"] == "https://d.com/a.jpg"
    assert it["thumb"].startswith("https://avatars.mds.yandex.net/")
    assert it["site"] == "d.com", "sin editor declarado, se atribuye a quien la sirve (igual que en Bing)"
    assert it["title"] == "Ferrari Amalfi 2026"


def test_un_tile_sin_img_url_se_salta_sin_llevarse_a_los_demas():
    rows = [{"href": "https://yandex.com/images/search?pos=0", "alt": "roto", "thumb": "https://t/x"},
            {"href": "https://yandex.com/images/search?img_url=https%3A%2F%2Fok.com%2Fb.jpg", "alt": "ok",
             "thumb": "https://t/y"}]
    out = I.parse_yandex_rows(rows)
    assert len(out) == 1 and out[0]["url"] == "https://ok.com/b.jpg"


def test_la_misma_foto_dos_veces_es_una_y_se_respeta_el_tope():
    rows = [{"href": f"https://y/?img_url=https%3A%2F%2Fd.com%2F{i}.jpg", "alt": "x", "thumb": "https://t/x"}
            for i in (1, 1, 2, 3, 4)]
    assert len(I.parse_yandex_rows(rows)) == 4
    assert len(I.parse_yandex_rows(rows, k=2)) == 2


def test_una_lista_ilegible_sale_vacia_y_no_revienta():
    """Same total contract as its Google sibling: a format change degrades to the next index; it does not
    bring down the turn."""
    for basura in ([], None, [{"href": ""}], ["texto suelto"], [{"href": "no-es-una-url"}]):
        assert I.parse_yandex_rows(basura) == []
