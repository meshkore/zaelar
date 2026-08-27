"""Que nos BLOQUEEN y que el mundo no tenga nada son hechos opuestos, y llegaban idénticos.

Medido en vivo el 2026-08-27, con las consultas que corren los casos US: 4 de 6 volvieron vacías porque
DuckDuckGo estaba sirviendo un desafío anti-bot. Nada en el sistema lo decía. Tres capas fallaban a la vez,
y cada una en silencio:

  1. el bloqueo llega como **HTTP 202**, que es un estado de ÉXITO: `raise_for_status()` lo deja pasar, el
     regex de enlaces no encuentra nada y el llamante recibe `results: []`.
  2. el clasificador buscaba las palabras que usaríamos NOSOTROS para describirlo («captcha», «unusual
     traffic»). La página real dice «Unfortunately, bots use DuckDuckGo too… Select all squares containing a
     duck» y la palabra «captcha» no sale en ningún sitio, así que un bloqueo duro se clasificaba «error».
  3. la fila de observabilidad del buscador llevaba `n: 0` y la consulta, y NI UNA palabra del porqué — así
     que `search_health`, que existe justo para cazar este confundido, rascaba una prosa que no existía y
     declaraba sana una capa de búsqueda muerta.

`browser_search._looks_blocked` ya hacía esto para Google. El escalón de DDG —el último de la cadena, el que
corre cuando no hay ninguna clave ni navegador— no tenía nada.
"""
from __future__ import annotations

import json

from nucleo import websearch as W
from tests.use_cases.e2e.agent import verify as V

_REAL_PAGE = ("<html><body><!--> DuckDuckGo Unfortunately, bots use DuckDuckGo too. Please complete the "
              "following challenge to confirm this search was made by a human. Select all squares containing "
              "a duck: Submit </body></html>")


def test_the_real_block_page_is_recognised():
    """La página REAL, copiada de una respuesta viva — no una que diga «captcha» por comodidad nuestra."""
    assert W._challenge_reason(_REAL_PAGE)
    assert "captcha" in W._challenge_reason(_REAL_PAGE)


def test_a_page_of_results_is_not_a_block():
    """La mitad de sensibilidad: sin esto, «lee los bloqueos» y «lo llama todo bloqueo» pasan igual."""
    assert W._challenge_reason("<html><a href='http://x.es'>Hoteles baratos en Austin</a></html>") == ""
    assert W._challenge_reason("") == ""


def test_the_classifier_knows_the_words_the_page_actually_uses():
    """Antes esto era «error», que es lo mismo que decir nada."""
    assert W._classify_failure("ddg: captcha: DuckDuckGo sirvió un desafío («made by a human»)") == "captcha"
    assert W._classify_failure("bots use duckduckgo too") == "captcha"
    assert W._classify_failure("ddg: sin resultados") == "error", "no todo vacío es un bloqueo"


def test_the_reason_travels_with_the_result(monkeypatch):
    """`note_failure` enciende el semáforo del operador; la fila necesita el motivo ENCIMA."""
    monkeypatch.setattr(W, "_order", lambda: ["ddg"])
    monkeypatch.setitem(W._BACKENDS, "ddg", lambda q, k: (_ for _ in ()).throw(RuntimeError(
        "captcha: DuckDuckGo sirvió un desafío anti-bot («made by a human»)")))
    res = W.search("buy used bicycle", 5)
    assert res["results"] == []
    assert res["failure"]["kind"] == "captcha"
    assert "desafío" in res["failure"]["detail"]


def test_an_honest_empty_world_still_says_so(monkeypatch):
    """Un buscador que responde y no encuentra nada NO puede salir como bloqueo."""
    monkeypatch.setattr(W, "_order", lambda: ["ddg"])
    monkeypatch.setitem(W._BACKENDS, "ddg", lambda q, k: {"query": q, "answer": "", "results": [],
                                                          "source": "ddg", "ai": False})
    res = W.search("xyzzy nada de nada", 5)
    assert res["failure"]["kind"] == "error", "sin señal de bloqueo, no se inventa una"


def _row(**extra) -> dict:
    """La fila del buscador tal y como la devuelve `/api/observability/events`."""
    return {"kind": "search", "cat": "flash",
            "payload": json.dumps({"kind": "search", "label": "🔎 resultados web",
                                   "text": "cheap hotels austin", "n": 0, **extra})}


def test_the_harness_reads_the_field_not_the_prose():
    """Lo medido contra la FORMA real del dato: un campo, no una frase que alguien tuvo que escribir."""
    sano = V.search_health([_row(n=6)])
    assert sano["degraded"] is False and sano["reasons"] == []
    roto = V.search_health([_row(failure={"kind": "captcha", "detail": "desafío anti-bot"})])
    assert roto["degraded"] is True and roto["reasons"] == [("blocked", 1)]


def test_the_old_prose_route_still_works():
    """El WebSearch del propio worker sí escribe su motivo en palabras; esa vía no puede romperse."""
    prosa = V.search_health([{"kind": "search", "text": "Weekly/Monthly Limit Exhausted", "label": ""}])
    assert prosa["degraded"] is True and prosa["reasons"] == [("quota_exhausted", 1)]


def test_a_quota_failure_is_not_reported_as_a_block():
    """Los dos motivos llevan a acciones distintas: uno se espera, el otro se rodea."""
    got = V.search_health([_row(failure={"kind": "quota", "detail": "limit exhausted"})])
    assert got["reasons"] == [("quota_exhausted", 1)]


class _FakeResp:
    def __init__(self, text: str, status: int = 202):
        self.text, self.status_code = text, status

    def raise_for_status(self):
        """202 es un estado de ÉXITO: esto NO lanza, y por eso el bloqueo pasaba de largo."""
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return {}


class _FakeClient:
    def __init__(self, page: str):
        self._page = page

    def __call__(self, *a, **kw):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def post(self, *a, **kw):
        return _FakeResp(self._page)

    def get(self, *a, **kw):
        return _FakeResp("{}", 200)      # el instant-answer, neutralizado


def test_the_ddg_backend_itself_raises_on_the_202_challenge(monkeypatch):
    """LA FONTANERÍA, no una versión mockeada de ella.

    Sin este test se puede quitar el reconocimiento entero de `_ddg` y los demás siguen verdes: todos
    inyectan el fallo por arriba. Medido al desarmarlo el 2026-08-27 — 8 verdes sobre el defecto restaurado.
    """
    import httpx
    monkeypatch.setattr(httpx, "Client", _FakeClient(_REAL_PAGE))
    try:
        W._ddg("buy used bicycle", 5)
    except RuntimeError as e:
        assert "captcha" in str(e)
    else:
        raise AssertionError("un desafío servido como 202 tiene que LEVANTAR, no volver vacío")


def test_and_a_normal_200_with_no_matches_does_not_raise(monkeypatch):
    """La otra mitad: una página de resultados legítima que simplemente no trae nada NO es un bloqueo."""
    import httpx
    monkeypatch.setattr(httpx, "Client", _FakeClient("<html><body>No results found.</body></html>"))
    assert W._ddg("xyzzy", 5)["results"] == []
