"""MODEL EGRESS (T303). One codebase, two deployments.

What is tested: that self-host changes NOTHING, that with mediated egress the provider key stops being
used, and that an incomplete deployment fails instead of slipping through the back door.
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
    # The SDK builds `<base>/chat/completions`: the base must end in /v1, just like the provider's.
    # Without this, the call goes to `<egress>/chat/completions` and returns 404 — this happened on
    # the first real startup, and the symptom did not point to the cause.
    assert base == "https://egress.example/v1"
    assert key == "tok-de-workload"
    assert "CLAVE-MAESTRA" not in (base + key + str(headers))
    assert headers == {"X-Zaelar-Provider": "aimlapi"}


def test_la_familia_de_destino_va_en_CABECERA_no_en_el_cuerpo(monkeypatch):
    """The body is composed by a model. If routing depended on the body, what a model writes
    could change which provider is billed."""
    _mediado(monkeypatch)
    for url, esperado in [("https://api.x.ai/v1", "xai"), ("https://api.z.ai/api/paas/v4", "zai"),
                          ("https://api.mistral.ai/v1", "mistral")]:
        assert llm_egress.route(url, "k")[2] == {"X-Zaelar-Provider": esperado}


def test_un_endpoint_LOCAL_nunca_se_media(monkeypatch):
    """Ollama costs no money and there is nothing to safeguard. Mediating it would send to the cloud
    something the user put on their machine specifically so it would not leave it."""
    _mediado(monkeypatch)
    assert llm_egress.route("http://localhost:11434/v1", "ollama") == \
        ("http://localhost:11434/v1", "ollama", {})


def test_sin_credencial_NO_se_cae_hacia_atras_al_proveedor(monkeypatch, caplog):
    """The failure this prevents: a half-mediated deployment that "works" by going direct with the
    provider key. That is not graceful degradation; it is a leak that goes unnoticed because
    everything responds correctly."""
    _mediado(monkeypatch, token=None)
    base, key, _ = llm_egress.route("https://api.aimlapi.com/v1", "CLAVE-MAESTRA")
    assert base.startswith("https://egress.example"), "se cayó al proveedor directo"
    assert key == "", "viajó la clave del proveedor pese a haber salida mediada"


def test_quien_factura_es_quien_llama(monkeypatch):
    """With mediated egress, the other end records the ledger entry, using the tokens that IT saw.
    Recording it here too would charge twice for the same turn."""
    monkeypatch.setattr(llm_egress, "mediated", lambda: False)
    assert llm_egress.bills_upstream() is False
    _mediado(monkeypatch)
    assert llm_egress.bills_upstream() is True
