"""EGRESS DE MODELOS (T303). Un solo código, dos despliegues.

Lo que se prueba: que self-host no cambie NADA, que con salida mediada la clave del proveedor deje de
usarse, y que un despliegue incompleto rompa en vez de colarse por la puerta de atrás.
"""
import pytest

from nucleo import llm_egress


@pytest.fixture(autouse=True)
def limpio(monkeypatch):
    monkeypatch.delenv("ZAELAR_GATEWAY_URL", raising=False)
    monkeypatch.delenv("CONTROL_PLANE_SERVICE_TOKEN", raising=False)
    yield


def _mediado(monkeypatch, token="tok-de-workload"):
    monkeypatch.setattr(llm_egress, "mediated", lambda: True)
    monkeypatch.setenv("ZAELAR_GATEWAY_URL", "https://egress.example/")
    if token:
        monkeypatch.setenv("CONTROL_PLANE_SERVICE_TOKEN", token)


def test_self_host_no_cambia_ni_un_byte(monkeypatch):
    monkeypatch.setattr(llm_egress, "mediated", lambda: False)
    assert llm_egress.route("https://api.aimlapi.com/v1", "clave-del-usuario") == \
        ("https://api.aimlapi.com/v1", "clave-del-usuario", {})


def test_con_salida_mediada_la_clave_del_proveedor_ya_no_viaja(monkeypatch):
    _mediado(monkeypatch)
    base, key, headers = llm_egress.route("https://api.aimlapi.com/v1", "CLAVE-MAESTRA")
    # El SDK compone `<base>/chat/completions`: la base tiene que acabar en /v1 igual que la del
    # proveedor. Sin esto la llamada sale a `<egress>/chat/completions` y devuelve 404 — pasó en el
    # primer arranque real y el síntoma no apuntaba a la causa.
    assert base == "https://egress.example/v1"
    assert key == "tok-de-workload"
    assert "CLAVE-MAESTRA" not in (base + key + str(headers))
    assert headers == {"X-Zaelar-Provider": "aimlapi"}


def test_la_familia_de_destino_va_en_CABECERA_no_en_el_cuerpo(monkeypatch):
    """El cuerpo lo compone un modelo. Si el enrutado dependiera del cuerpo, lo que un modelo escriba
    podría cambiar a qué proveedor se factura."""
    _mediado(monkeypatch)
    for url, esperado in [("https://api.x.ai/v1", "xai"), ("https://api.z.ai/api/paas/v4", "zai"),
                          ("https://api.mistral.ai/v1", "mistral")]:
        assert llm_egress.route(url, "k")[2] == {"X-Zaelar-Provider": esperado}


def test_un_endpoint_LOCAL_nunca_se_media(monkeypatch):
    """Ollama no cuesta dinero y no hay nada que custodiar. Mediarlo sería mandar a la nube algo que
    el usuario puso en su máquina justamente para que no saliera."""
    _mediado(monkeypatch)
    assert llm_egress.route("http://localhost:11434/v1", "ollama") == \
        ("http://localhost:11434/v1", "ollama", {})


def test_sin_credencial_NO_se_cae_hacia_atras_al_proveedor(monkeypatch, caplog):
    """El fallo que esto impide: un despliegue mediado a medias que «funciona» saliendo directo con la
    clave del proveedor. Eso no es degradar con elegancia, es una fuga que pasa desapercibida porque
    todo responde bien."""
    _mediado(monkeypatch, token=None)
    base, key, _ = llm_egress.route("https://api.aimlapi.com/v1", "CLAVE-MAESTRA")
    assert base.startswith("https://egress.example"), "se cayó al proveedor directo"
    assert key == "", "viajó la clave del proveedor pese a haber salida mediada"


def test_quien_factura_es_quien_llama(monkeypatch):
    """Con salida mediada el ledger lo apunta el otro extremo, con los tokens que vio ÉL. Contarlo
    también aquí cobraría dos veces el mismo turno."""
    monkeypatch.setattr(llm_egress, "mediated", lambda: False)
    assert llm_egress.bills_upstream() is False
    _mediado(monkeypatch)
    assert llm_egress.bills_upstream() is True
