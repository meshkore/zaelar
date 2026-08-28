"""V2-466 — la cadena de buscadores de imágenes: nunca depender de uno solo.

Petición del operador (2026-08-28) tras ver a Google pidiendo captcha una tarde entera: «no podemos confiar
todo el rato en Google, tengamos una lista de buscadores e iterar de uno a otro».

El orden NO es por reputación, es lo MEDIDO ese día desde esta máquina con la misma consulta:

    google      captcha              →  0 resultados
    ecosia      captcha (proxia)     →  0
    ddg/brave/startpage/qwant        →  pintan la galería solo tras interacción
    yandex      30 tiles             →  el coche CORRECTO
    bing        52 tiles             →  el coche EQUIVOCADO 9 de cada 10 (SF90, F8, dos F80)

Por eso Bing queda el ÚLTIMO y no el primero de recambio, que es donde estaba.
"""
from __future__ import annotations

import asyncio

from nucleo import browser_search as BS, image_search as I


def _falso(**por_motor):
    """Sustituye las tres patas por respuestas fijas, para medir la CADENA y no la red."""
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


# ── el orden ────────────────────────────────────────────────────────────────────────────────────────────
def test_el_orden_es_google_yandex_bing():
    """Clavado a mano: cada fila salió de una medición, y Bing el último no es un detalle estético."""
    assert BS._IMAGE_ENGINES == ("google", "yandex", "bing")


def test_si_google_contesta_no_se_pregunta_a_nadie_mas(monkeypatch):
    _instalar(monkeypatch, google={"query": "x", "items": _items(), "source": "google", "blocked": False})
    r = asyncio.run(BS.images("x"))
    assert r["source"] == "google" and "degraded_from" not in r


def test_google_BLOQUEADO_pasa_a_yandex_y_NO_a_bing(monkeypatch):
    """El defecto que originó esto: el captcha mandaba directo al índice más flojo."""
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


# ── el parser de Yandex, sin red ────────────────────────────────────────────────────────────────────────
def test_yandex_saca_la_foto_a_TAMAÑO_COMPLETO_del_enlace():
    """Lo frágil —el `img_url` dentro del enlace del tile— es lo que tiene que poder probarse sin red."""
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
    """Mismo contrato total que su hermano de Google: un cambio de formato degrada al siguiente índice, no
    tumba el turno."""
    for basura in ([], None, [{"href": ""}], ["texto suelto"], [{"href": "no-es-una-url"}]):
        assert I.parse_yandex_rows(basura) == []
