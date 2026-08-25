"""V2-320 — un escalón ordenado A MANO hereda lo que el CATÁLOGO tiene MEDIDO sobre ese mismo proveedor.

`code_agent.providers` deja al operador ordenar la cadena a mano, y esa lista es una COPIA de entradas del
catálogo hecha en algún momento pasado. El ORDEN es una preferencia y es suya. La CAPACIDAD no: que un modelo
lea o no imágenes es un hecho sobre el modelo, medido una vez y cierto después, y una copia hecha antes de la
medición lo tira sin decir nada.

Que es exactamente lo que pasó. El escalón DeepSeek de `KNOWN` lleva `vision: False` —V4 no lee imágenes,
medido en `search-buy-guitar__es` (2026-08-24 11:23), donde el worker hizo `Read` de la captura y contestó «La
captura no se pudo leer (formato no soportado). Sigo por DOM», dos veces, y encima se lo narró al operador—.
La copia a mano de `config/v2.json` no tiene esa clave, así que `vision_env()` no declaraba nada,
`ZAELAR_NAV_VISION` se quedaba sin poner, y el camino del navegador seguía mandando un PNG de 300-530 KB en
CADA acción a un modelo que no puede abrirlo.

El escalón estaba INERTE mientras DeepSeek no tenía saldo, así que no se veía. En cuanto se recargó la cuenta
(2026-08-25) volvió a ser el primer escalón sano — y una recarga es el último suceso que alguien relacionaría
con un navegador ciego.
"""
import pytest

from nucleo.workers import providers as P


@pytest.fixture
def hand_ordered(monkeypatch):
    """Ordena la cadena a mano como hace `config/v2.json`, sin tocar la config real del operador."""
    def _make(entries):
        import config.v2 as v2
        monkeypatch.setattr(v2, "get", lambda k=None: {"providers": entries} if k == "code_agent" else {})
        monkeypatch.setattr(P, "_token_for", lambda t: "tok")
        monkeypatch.setattr(P, "_is_container", lambda: False)
    return _make


_DEEPSEEK_A_MANO = {"name": "deepseek", "base_url": "https://api.deepseek.com/anthropic",
                    "env": ["DEEPSEEK_API_KEY"], "plan": "DeepSeek (pago por token)",
                    "model": "deepseek-v4-flash"}          # ← copiado ANTES de que existiera `vision`


def test_el_catalogo_SIGUE_declarando_que_V4_no_ve():
    """Si esto se cae, la medida se perdió en el sitio de origen y todo lo demás es decoración."""
    ds = next(k for k in P.KNOWN if k["name"] == "deepseek")
    assert ds.get("vision") is False


def test_la_copia_a_mano_HEREDA_la_ceguera(hand_ordered):
    hand_ordered([_DEEPSEEK_A_MANO])
    ds = next(t for t in P.chain() if t["name"] == "deepseek")
    assert ds.get("vision") is False
    assert P.vision_env(ds) == {"ZAELAR_NAV_VISION": "0"}


def test_y_el_PUENTE_del_navegador_se_entera(hand_ordered):
    """La mitad de cableado: la herencia puede acertar y no llegar a quien manda la captura (V2-199)."""
    hand_ordered([_DEEPSEEK_A_MANO])
    assert P.worker_sees() is False


def test_lo_que_el_operador_ESCRIBIO_manda(hand_ordered):
    """Solo se rellenan las claves AUSENTES. Si él declara que ve, ve — se hereda lo que falta, no se pisa."""
    hand_ordered([dict(_DEEPSEEK_A_MANO, vision=True)])
    ds = next(t for t in P.chain() if t["name"] == "deepseek")
    assert ds.get("vision") is True
    assert P.vision_env(ds) == {}


def test_casa_por_ENDPOINT_aunque_le_cambie_el_nombre(hand_ordered):
    """El endpoint ES la identidad: una copia renombrada sigue siendo el mismo proveedor y el mismo modelo."""
    hand_ordered([dict(_DEEPSEEK_A_MANO, name="mi-relevo-barato")])
    t = next(t for t in P.chain() if t["name"] == "mi-relevo-barato")
    assert t.get("vision") is False


def test_un_escalon_DESCONOCIDO_no_hereda_nada(hand_ordered):
    """Sensibilidad: un proveedor que no está en el catálogo no tiene nada medido, y suponerle ceguera dejaría
    CIEGO a un modelo que sí ve — que es el peor error que puede cometer este módulo (ver `vision_env`)."""
    hand_ordered([{"name": "otro", "base_url": "https://api.otro.com/anthropic", "env": ["OTRO_KEY"]}])
    t = next(t for t in P.chain() if t["name"] == "otro")
    assert "vision" not in t
    assert P.vision_env(t) == {}


def test_solo_se_heredan_los_rasgos_MEDIDOS_no_las_preferencias(hand_ordered):
    """`model` y `plan` son elección del operador; heredarlos sería pisarle la configuración con el catálogo."""
    hand_ordered([{"name": "deepseek", "base_url": "https://api.deepseek.com/anthropic",
                   "env": ["DEEPSEEK_API_KEY"], "model": "deepseek-v4-pro"}])
    t = next(t for t in P.chain() if t["name"] == "deepseek")
    assert t["model"] == "deepseek-v4-pro", "el catálogo le pisó el modelo que eligió el operador"
    assert t.get("vision") is False
    assert "plan" not in P._MEASURED_TRAITS and "model" not in P._MEASURED_TRAITS
