"""V2-320 — a manually ordered tier inherits what the CATALOG has MEASURED about that same provider.

`code_agent.providers` lets the operator order the chain by hand, and that list is a COPY of entries from the
catalog made at some point in the past. The ORDER is a preference and belongs to them. CAPABILITY is not: whether
a model can read images is a fact about the model, measured once and true thereafter, and a copy made before the
measurement silently discards it.

That is exactly what happened. The DeepSeek tier in `KNOWN` has `vision: False` —V4 cannot read images,
measured in `search-buy-guitar__es` (2026-08-24 11:23), where the worker used `Read` on the screenshot and replied
«La captura no se pudo leer (formato no soportado). Sigo por DOM» twice, and even narrated it to the operator—.
The hand-made copy of `config/v2.json` does not have that key, so `vision_env()` declared nothing,
`ZAELAR_NAV_VISION` remained unset, and the browser path kept sending a 300-530 KB PNG on
EACH action to a model that cannot open it.

The tier was INACTIVE while DeepSeek had no balance, so it was not visible. As soon as the account was reloaded
(2026-08-25), it became the first healthy tier again — and a reload is the last event anyone would associate
with a blind browser.
"""
import pytest

from nucleo.workers import providers as P


@pytest.fixture
def hand_ordered(monkeypatch):
    """Orders the chain by hand as `config/v2.json` does, without touching the operator's actual config."""
    def _make(entries):
        import config.v2 as v2
        monkeypatch.setattr(v2, "get", lambda k=None: {"providers": entries} if k == "code_agent" else {})
        monkeypatch.setattr(P, "_token_for", lambda t: "tok")
        monkeypatch.setattr(P, "_is_container", lambda: False)
    return _make


_DEEPSEEK_A_MANO = {"name": "deepseek", "base_url": "https://api.deepseek.com/anthropic",
                    "env": ["DEEPSEEK_API_KEY"], "plan": "DeepSeek (pago por token)",
                    "model": "deepseek-v4-flash"}          # ← copied BEFORE `vision` existed


def test_el_catalogo_SIGUE_declarando_que_V4_no_ve():
    """If this fails, the measurement was lost at the source and everything else is decoration."""
    ds = next(k for k in P.KNOWN if k["name"] == "deepseek")
    assert ds.get("vision") is False


def test_la_copia_a_mano_HEREDA_la_ceguera(hand_ordered):
    hand_ordered([_DEEPSEEK_A_MANO])
    ds = next(t for t in P.chain() if t["name"] == "deepseek")
    assert ds.get("vision") is False
    assert P.vision_env(ds) == {"ZAELAR_NAV_VISION": "0"}


def test_y_el_PUENTE_del_navegador_se_entera(hand_ordered):
    """Half the wiring: inheritance can be correct and still fail to reach whoever sends the screenshot (V2-199)."""
    hand_ordered([_DEEPSEEK_A_MANO])
    assert P.worker_sees() is False


def test_lo_que_el_operador_ESCRIBIO_manda(hand_ordered):
    """Only ABSENT keys are filled in. If they declare that they can see, they can see — what is missing is inherited, not overwritten."""
    hand_ordered([dict(_DEEPSEEK_A_MANO, vision=True)])
    ds = next(t for t in P.chain() if t["name"] == "deepseek")
    assert ds.get("vision") is True
    assert P.vision_env(ds) == {}


def test_casa_por_ENDPOINT_aunque_le_cambie_el_nombre(hand_ordered):
    """The endpoint IS the identity: a renamed copy is still the same provider and the same model."""
    hand_ordered([dict(_DEEPSEEK_A_MANO, name="mi-relevo-barato")])
    t = next(t for t in P.chain() if t["name"] == "mi-relevo-barato")
    assert t.get("vision") is False


def test_un_escalon_DESCONOCIDO_no_hereda_nada(hand_ordered):
    """Sensitivity: a provider that is not in the catalog has nothing measured, and assuming it is blind would leave
    a model that can see BLIND — which is the worst error this module could make (see `vision_env`)."""
    hand_ordered([{"name": "otro", "base_url": "https://api.otro.com/anthropic", "env": ["OTRO_KEY"]}])
    t = next(t for t in P.chain() if t["name"] == "otro")
    assert "vision" not in t
    assert P.vision_env(t) == {}


def test_solo_se_heredan_los_rasgos_MEDIDOS_no_las_preferencias(hand_ordered):
    """`model` and `plan` are the operator's choice; inheriting them would overwrite their configuration with the catalog."""
    hand_ordered([{"name": "deepseek", "base_url": "https://api.deepseek.com/anthropic",
                   "env": ["DEEPSEEK_API_KEY"], "model": "deepseek-v4-pro"}])
    t = next(t for t in P.chain() if t["name"] == "deepseek")
    assert t["model"] == "deepseek-v4-pro", "el catálogo le pisó el modelo que eligió el operador"
    assert t.get("vision") is False
    assert "plan" not in P._MEASURED_TRAITS and "model" not in P._MEASURED_TRAITS
