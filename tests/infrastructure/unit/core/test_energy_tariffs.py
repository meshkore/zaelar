"""Tariffs: the rates Energy is computed from (nucleo/energy_tariffs.py).

THE RATCHET LIVES HERE. The defect these tests exist for was never a wrong number — it was that
nothing tied a number to the provider actually running, so the STT billed Deepgram's rate while
Voxtral ran and no test, log or alarm noticed for months. Fixing the number alone would leave the
mechanism that produced it completely intact.
"""
import json
from pathlib import Path

import pytest

from nucleo import energy_tariffs

# The provisioner's config is the source of truth for what runs inside every tenant Machine. It is
# JavaScript, so it is read as TEXT rather than imported — the alternative (a hand-kept copy of the
# provider names on this side) is the very duplication that caused the drift.
# parents: [0]=core [1]=unit [2]=infrastructure [3]=tests [4]=engine [5]=el workspace zaelar/
_MACHINE_CONFIG = Path(__file__).resolve().parents[5] / "cloud" / "provisioner" / "src" / "machineConfig.js"


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    """Cache en blanco Y `sys_kv` AISLADO.

    Limpiar solo la caché de proceso no basta y se comprobó de la peor forma: `update()` PERSISTE, así
    que los primeros tests escribieron en el `zaelar.db` real del operador y el siguiente los leyó de
    vuelta — dos rojos que no eran del código sino de que la prueba se contaminaba a sí misma… y de
    paso ensuciaba la memoria de producción. Un test no puede depender de un almacén compartido ni
    escribir en él.
    """
    store: dict[str, str] = {}
    from memory import api as memory
    monkeypatch.setattr(memory, "kv_get", lambda k: store.get(k))
    monkeypatch.setattr(memory, "kv_set", lambda k, v: store.__setitem__(k, v))
    energy_tariffs._reset_for_tests()
    yield
    energy_tariffs._reset_for_tests()


def _cloud_provider(var: str) -> str | None:
    """The value BASE_PROVIDER_ENV assigns to `var`, straight out of the provisioner's source."""
    if not _MACHINE_CONFIG.exists():
        return None
    for line in _MACHINE_CONFIG.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith(f"{var}:"):
            return stripped.split(":", 1)[1].strip().strip(",").strip("'\"")
    return None


@pytest.mark.parametrize("var,family", [("ZAELAR_STT", "stt"), ("ZAELAR_TTS", "tts")])
def test_every_provider_the_cloud_actually_runs_has_its_own_rate(var, family):
    """EL TRINQUETE. Cambiar el proveedor de voz en el provisioner sin darle tarifa rompe aquí, en el
    momento del cambio — no tres semanas después mirando una factura que no cuadra.

    Sin esto, un proveedor nuevo cae en el catch-all: cobra, pero a un precio que no es el suyo, y el
    único síntoma es un número plausible."""
    provider = _cloud_provider(var)
    if provider is None:
        pytest.skip(f"{_MACHINE_CONFIG.name} no está disponible (repo cloud aparte)")
    table = {"stt": energy_tariffs.DEFAULT_STT_USD_PER_MIN,
             "tts": energy_tariffs.DEFAULT_TTS_USD_PER_1K_CHARS}[family]
    assert provider in table, (
        f"La nube corre {var}={provider!r} y no hay tarifa para él en energy_tariffs.py. "
        f"Añádela a DEFAULT_{family.upper()}_* — si no, se factura al catch-all y el precio es ficción."
    )


def test_an_unknown_provider_is_never_free():
    """Sub-cobrar en silencio pierde dinero de verdad; sobre-cobrar a un proveedor raro se ve en la
    siguiente factura y se corrige. El fallo por defecto va hacia el lado visible."""
    rate = energy_tariffs.rate_for("stt", "un-proveedor-que-no-existe")
    assert rate > 0
    assert rate == max(energy_tariffs.DEFAULT_STT_USD_PER_MIN.values())


def test_local_backends_are_absent_from_the_tables_on_purpose():
    """Gratis es una PROPIEDAD del proveedor, no una tarifa de cero. Una fila `whisper_local: 0.0`
    sería indistinguible de un precio que alguien olvidó rellenar."""
    assert "whisper_local" not in energy_tariffs.DEFAULT_STT_USD_PER_MIN
    assert "kokoro_local" not in energy_tariffs.DEFAULT_TTS_USD_PER_1K_CHARS


def test_central_rates_win_over_the_bundled_defaults():
    energy_tariffs.update({"stt": {"voxtral": 0.010}})
    assert energy_tariffs.rate_for("stt", "voxtral") == pytest.approx(0.010)


def test_a_partial_central_table_does_not_erase_what_it_does_not_mention():
    """El operador solo edita lo que quiere cambiar, así que la tabla central llega incompleta por
    diseño. Un proveedor que no menciona no es desconocido para NOSOTROS — sigue teniendo su default,
    y no debe caer al catch-all (que le pondría el precio más caro sin motivo)."""
    energy_tariffs.update({"stt": {"voxtral": 0.010}})
    assert energy_tariffs.rate_for("stt", "deepgram") == pytest.approx(
        energy_tariffs.DEFAULT_STT_USD_PER_MIN["deepgram"])


def test_an_empty_payload_is_refused_instead_of_wiping_the_rates():
    """Un control-plane a medio migrar, mal configurado o con un bug puede contestar `{}`. Adoptarlo
    dejaría a la Machine facturando TODO al catch-all. Ausencia no es una instrucción."""
    energy_tariffs.update({"stt": {"voxtral": 0.010}})
    assert energy_tariffs.update({}) is False
    assert energy_tariffs.update(None) is False
    assert energy_tariffs.rate_for("stt", "voxtral") == pytest.approx(0.010)


def test_zero_is_a_legitimate_rate_not_a_missing_one():
    """Un proveedor dentro de su cuota incluida (LiveKit trae 5.000 min WebRTC al mes) tiene coste
    marginal cero DE VERDAD, y cobrarlo sería inventar un gasto. Poner 0 tiene que poder decirse."""
    energy_tariffs.update({"transport": {"livekit": 0.0}})
    assert energy_tariffs.rate_for("transport", "livekit") == 0.0


def test_a_negative_rate_is_dropped():
    """Una tarifa negativa REGALARÍA Energy con cada llamada. El endpoint ya lo valida; esto es la
    segunda cerradura, porque el payload viaja por la red."""
    energy_tariffs.update({"stt": {"voxtral": 0.010}})
    energy_tariffs.update({"stt": {"voxtral": -5.0}})
    assert energy_tariffs.rate_for("stt", "voxtral") == pytest.approx(0.010)


def test_snapshot_says_where_the_rates_came_from():
    assert energy_tariffs.snapshot()["source"] == "bundled_defaults"
    energy_tariffs.update({"stt": {"voxtral": 0.010}})
    assert energy_tariffs.snapshot()["source"] == "central"


def test_the_lease_carries_the_tariffs(monkeypatch):
    """El acoplamiento que sostiene todo: las tarifas llegan piggyback en el arriendo, la única
    llamada periódica que el motor ya hace. Si alguien deja de leerlas ahí, los precios centrales
    dejan de llegar y nadie se entera — la Machine sigue facturando, con los de hace meses."""
    import nucleo.energy_lease as lease
    src = Path(lease.__file__).read_text(encoding="utf-8")
    assert "energy_tariffs.update(" in src, (
        "energy_lease ya no adopta las tarifas de la respuesta del arriendo — el canal central está roto"
    )
