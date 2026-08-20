"""Una búsqueda vacía y una búsqueda IMPOSIBLE no son lo mismo, y el turno tiene que poder distinguirlas (V2-176).

Medido en `cheapest-monitor` (2026-08-20 10:26), diez turnos:

    TESTER  Búscame un monitor bueno para trabajar, que no sea carísimo.
    ZAELAR  Me pongo con ello y te traigo un par de opciones buenas de precio.
    ...
    TESTER  ¿me pasas ya un modelo concreto con precio y tienda, aunque sea una primera opción?
    ZAELAR  Aún no tengo un modelo concreto; la búsqueda va revisando catálogo y todavía no ha soltado
            candidatos. ¿Quieres que la pare o que siga?
    TESTER  Sigue, porfa.
    ZAELAR  Hecho, te aviso al momento.

Veinte eventos de búsqueda, cero candidatos, y el watchdog disparando `stuck/nudge` mientras pasaba. La cadena
de búsqueda estaba ABAJO (cuota agotada más un CAPTCHA), así que el RESULTADO no era alcanzable — y lo único que
sí lo era, decirlo, tampoco: `websearch.search()` devuelve `results: []` con `source: "none"` cuando toda la
cadena falla, que es indistinguible de «busqué bien y no hay nada». El único rastro del derrumbe era un
`logger.warning`.

Mismo remedio que el lado del LLM (`provider_chain.note_failure` + `health_state.record`): la capa registra su
propia salud y el turno la lee. Y se dice el MOTIVO, no un genérico: «se me ha agotado la cuota» y «me piden un
captcha» llevan a decisiones distintas del operador, y ninguna de las dos es esperar.
"""
from __future__ import annotations

import pytest

from nucleo import websearch


@pytest.fixture(autouse=True)
def _clean():
    websearch.note_success()
    yield
    websearch.note_success()


# ── la capa recuerda su propio derrumbe ─────────────────────────────────────────────────────────────────────
def test_a_healthy_layer_says_nothing():
    assert websearch.recent_failure() == {}


def test_a_collapsed_chain_is_remembered():
    websearch.note_failure("google: Weekly Limit Exhausted · ddg: sin resultados")
    assert websearch.recent_failure()


def test_and_a_backend_answering_clears_it():
    """Sin esto, un fallo aislado dejaría al agente diciendo «no puedo buscar» el resto de la sesión."""
    websearch.note_failure("google: timeout")
    websearch.note_success()
    assert websearch.recent_failure() == {}


def test_it_forgets_on_its_own_after_a_while():
    """Un hecho tiene que caducar: la cuota se renueva y el CAPTCHA se va, y nadie llama a `note_success` si
    nadie vuelve a buscar."""
    websearch.note_failure("google: unusual traffic")
    at = websearch.recent_failure()["at"]
    assert websearch.recent_failure(now=at + websearch._FAILURE_MEMORY_S + 1) == {}


@pytest.mark.parametrize("detail,kind", [
    ("google: Weekly Limit Exhausted", "quota"),
    ("brave: 429 too many requests", "quota"),
    ("google: unusual traffic detected", "captcha"),
    ("google: /sorry/index?continue=", "captcha"),
    ("tavily: 401 unauthorized", "credential"),
    ("perplexity: invalid api key", "credential"),
    ("ddg: connection timed out", "network"),
    ("google: algo raro pasó", "error"),
])
def test_the_reason_is_classified_because_the_reasons_lead_somewhere_different(detail, kind):
    websearch.note_failure(detail)
    assert websearch.recent_failure()["kind"] == kind


def test_the_operator_semaphore_is_lit(monkeypatch):
    """«Estado visible, no silencioso»: una capa de búsqueda caída que se pinta en verde es indistinguible de un
    agente que no quiere buscar, y el operador depura lo que no es."""
    seen: list[tuple] = []
    from voice import health_state
    monkeypatch.setattr(health_state, "record", lambda *a, **kw: seen.append(a))
    websearch.note_failure("google: Weekly Limit Exhausted")
    assert seen and seen[0][0] == "search"


# ── y llega al TURNO, que es lo que faltaba ──────────────────────────────────────────────────────────────────
def _state() -> str:
    from nucleo.flash import prompt
    return prompt.live_state()


def test_the_turn_is_told_that_it_cannot_look(monkeypatch):
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    websearch.note_failure("google: Weekly Limit Exhausted")
    st = _state()
    assert "BÚSQUEDAS WEB NO ESTÁN FUNCIONANDO" in st


def test_it_says_WHICH_reason(monkeypatch):
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    websearch.note_failure("google: unusual traffic detected")
    assert "anti-robot" in _state()
    websearch.note_success()
    websearch.note_failure("google: Weekly Limit Exhausted")
    assert "cuota" in _state()


def test_and_it_forbids_the_exact_sentence_the_run_kept_saying(monkeypatch):
    """El daño medido no fue callar el hecho: fue prometer «te aviso en cuanto lo tenga» sobre algo que no iba a
    llegar. La instrucción tiene que atacar ESA frase, no solo informar."""
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    websearch.note_failure("google: Weekly Limit Exhausted")
    st = _state()
    assert "en cuanto lo tenga" in st, "no se nombra la promesa que hay que dejar de hacer"
    assert "navegador" in st, "se prohíbe esperar sin ofrecer nada a cambio"


def test_a_healthy_layer_puts_NOTHING_in_the_turn(monkeypatch):
    """La otra mitad: sin esto, «avisar cuando la búsqueda está caída» y «avisar siempre» pasan el mismo test —
    y un agente que dice que no puede buscar cuando sí puede es peor que el defecto original."""
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    websearch.note_success()
    assert "BÚSQUEDAS WEB NO ESTÁN FUNCIONANDO" not in _state()


def test_the_chain_records_its_own_collapse(monkeypatch):
    """La guarda que importa: que `search()` LLAME a `note_failure`. Un registro que nadie escribe es un arreglo
    muerto — esta tanda ya ha producido varios."""
    monkeypatch.setattr(websearch, "_order", lambda: ["ddg"])
    monkeypatch.setitem(websearch._BACKENDS, "ddg",
                        lambda q, k: (_ for _ in ()).throw(RuntimeError("Weekly Limit Exhausted")))
    res = websearch.search("monitor para trabajar")
    assert res["source"] == "none" and not res["results"]
    f = websearch.recent_failure()
    assert f and f["kind"] == "quota"
    assert "ddg" in f["detail"], "el registro no dice qué backend cayó"


def test_and_a_backend_that_answers_leaves_the_layer_healthy(monkeypatch):
    monkeypatch.setattr(websearch, "_order", lambda: ["ddg"])
    monkeypatch.setitem(websearch._BACKENDS, "ddg",
                        lambda q, k: {"query": q, "answer": "", "results": [{"title": "t", "snippet": "s",
                                                                            "url": "https://x.test"}],
                                      "source": "ddg", "ai": False})
    websearch.note_failure("google: timeout")
    websearch.search("monitor")
    assert websearch.recent_failure() == {}
