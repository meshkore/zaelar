"""
RELEVO POR LATENCIA del cerebro de VOZ (V2-094, 2026-08-14).

`provider_chain` existía desde el 2026-08-03 pero solo servía al cerebro de CLUSTER, y solo relevaba por proveedor
ROTO (429 / cuota / credencial). El fallo que el operador vive de verdad es otro: el proveedor LENTO. Medido en la
sesión b70a45d0 — TTFT p50 de 8.370 ms y máximo de 25.703 ms con el prompt CONSTANTE (±9%) y 120 tok/s de
generación, o sea todo el tiempo antes del primer token — y traducido a «parece que te has quedado tonto».

Lo que se fija aquí es la POLÍTICA, que es donde está el riesgo de gastar dinero sin querer:

  · el disparo lee el veredicto de `turn_perf` (no vuelve a medir): `pre_token` y `proveedor` cuentan;
    `frio`, `trabajo`, `prompt`, `reparto` y `ok` no, y CUALQUIERA de ellos rompe la racha;
  · hacen falta turnos lentos SEGUIDOS (un pico aislado no cambia de proveedor);
  · el cooldown es CORTO y hay TECHO DE TURNOS: un relevo por latencia salta justo en los turnos difíciles, que
    son los que más tokens gastan;
  · **en self-host no hay relevo por defecto**: quien se autohospeda paga sus APIs y no puede llevarse la sorpresa
    de que el agente se pase solo a un proveedor que él no eligió.
"""
from __future__ import annotations

import pytest

from nucleo.flash import provider_chain as pc


T1 = {"name": "titular", "base_url": "https://t/v1", "api_key": "k1", "model": "m-titular", "plan": "titular"}
T2 = {"name": "relevo", "base_url": "https://r/v1", "api_key": "k2", "model": "m-relevo", "plan": "relevo"}
T3 = {"name": "ultimo", "base_url": "https://u/v1", "api_key": "k3", "model": "m-ultimo", "plan": "último"}


@pytest.fixture(autouse=True)
def limpio(monkeypatch):
    """Estado en proceso a cero y sin persistencia: el cooldown se guarda en `sys_kv` y un test no puede dejarle al
    operador un proveedor castigado."""
    pc._store._cooldown.clear()
    pc._slow_streak.clear()
    pc._relay_turns.clear()
    pc._store._loaded = True                            # no leas el sys_kv real
    monkeypatch.setattr(pc._store, "_save", lambda: None)
    monkeypatch.setattr(pc, "chain", lambda *a, **k: [dict(T1), dict(T2), dict(T3)])
    yield
    pc._store._cooldown.clear()
    pc._slow_streak.clear()
    pc._relay_turns.clear()


def _v(cause, ttft=9000, total=10000):
    return {"cause": cause, "ttft_ms": ttft, "total_ms": total, "ttft_frac": ttft / total}


# ── el disparo ─────────────────────────────────────────────────────────────────────────────────────────────────
def test_un_solo_turno_lento_no_releva():
    """Un pico aislado es ruido. Relevar por uno cambiaría de modelo —y de precio— continuamente."""
    assert pc.note_slow(_v("pre_token")) is None
    assert pc.pick()["name"] == "titular"


def test_dos_turnos_lentos_seguidos_relevan():
    assert pc.note_slow(_v("pre_token")) is None
    nxt = pc.note_slow(_v("pre_token"))
    assert nxt and nxt["name"] == "relevo"
    assert pc.pick()["name"] == "relevo", "el relevo tiene que ser STICKY, no solo devuelto una vez"


def test_generar_despacio_tambien_cuenta():
    """`proveedor` = escribe despacio. También deja al operador esperando, así que también releva."""
    pc.note_slow(_v("proveedor", ttft=500, total=9000))
    assert pc.note_slow(_v("proveedor", ttft=500, total=9000))["name"] == "relevo"


@pytest.mark.parametrize("cause", ["frio", "trabajo", "prompt", "reparto", "ok"])
def test_las_causas_que_no_son_del_proveedor_no_relevan(cause):
    """Cambiar de proveedor por un arranque en frío lo EMPEORA (el nuevo también paga handshake). Por un prompt
    grande, no arregla nada: eso lo arregla el prompt. Por un 2º pase legítimo, castiga a quien trabaja."""
    for _ in range(5):
        assert pc.note_slow(_v(cause)) is None
    assert pc.pick()["name"] == "titular"


def test_un_turno_sano_ROMPE_la_racha():
    """Hacen falta lentos SEGUIDOS. Sin esto, dos turnos malos separados por una tarde de turnos buenos acabarían
    relevando — y el operador se encontraría en otro proveedor sin motivo actual."""
    pc.note_slow(_v("pre_token"))
    pc.note_slow(_v("ok", ttft=200, total=800))
    assert pc.note_slow(_v("pre_token")) is None, "la racha no se reinició"
    assert pc.pick()["name"] == "titular"


def test_el_ultimo_escalon_no_se_castiga(monkeypatch):
    """Si ya estamos en el último, castigarlo nos dejaría sin proveedor: un turno lento es mejor que ninguno."""
    monkeypatch.setattr(pc, "chain", lambda *a, **k: [dict(T3)])
    for _ in range(4):
        assert pc.note_slow(_v("pre_token")) is None
    assert pc.pick()["name"] == "ultimo"


# ── el techo de gasto ──────────────────────────────────────────────────────────────────────────────────────────
def test_el_relevo_tiene_TECHO_DE_TURNOS_y_devuelve_el_turno_al_titular():
    """LA protección de coste. Un relevo por latencia salta en los turnos DIFÍCILES, que son los que más tokens
    gastan; en la nube el salto a un escalón grande puede ser de 14× el input. Pasado el techo se vuelve al
    titular aunque siga lento: preferimos un turno lento a una factura sorpresa."""
    pc.note_slow(_v("pre_token"))
    pc.note_slow(_v("pre_token"))
    assert pc.pick()["name"] == "relevo"
    for _ in range(pc._RELAY_TURN_BUDGET + 2):
        pc.pick()
    assert pc.pick()["name"] == "titular", "el relevo se quedó indefinidamente en el escalón caro"


def test_el_cooldown_de_latencia_es_corto():
    """La lentitud es transitoria. El de cuota es de media hora porque la cuota tarda en reponerse; quedarse media
    hora en un escalón más caro por dos turnos malos sale carísimo."""
    assert pc._SLOW_COOLDOWN_S <= 10 * 60
    assert pc._SLOW_COOLDOWN_S < pc._DEFAULT_COOLDOWN_S


def test_el_relevo_es_VISIBLE(monkeypatch):
    """Un cambio de proveedor a espaldas del operador es la clase de estado que engaña — y en la nube además
    cambia lo que cuesta cada turno."""
    eventos = []
    import voice.observer as obs
    monkeypatch.setattr(obs, "emit", lambda *a, **k: eventos.append((a, k)))
    pc.note_slow(_v("pre_token"))
    pc.note_slow(_v("pre_token"))
    assert eventos, "el relevo no dejó rastro en el timeline"
    texto = " ".join(str(a) for a, _ in eventos)
    assert "LATENCIA" in texto and "relevo" in texto.lower()


# ── las cadenas por defecto ────────────────────────────────────────────────────────────────────────────────────
def test_en_self_host_NO_hay_relevo_por_defecto(monkeypatch):
    """Quien se autohospeda paga sus propias APIs. Que el agente se pase solo a otro proveedor sería gastarle
    dinero en un sitio que él no eligió. Se activa poniendo `fast.providers` en su config."""
    from nucleo import cloud_account
    monkeypatch.setattr(cloud_account, "is_cloud_account", lambda: False)
    monkeypatch.setattr(pc, "_token_for", lambda t: "k")
    from nucleo.flash import fast_client
    monkeypatch.setattr(fast_client, "spec_from_config",
                        lambda: fast_client.ModelSpec(model="m", base_url="https://x/v1", api_key="k"))
    nombres = [t["name"] for t in pc._voice_chain()]
    assert nombres == ["titular"], f"self-host no puede traer relevos de fábrica: {nombres}"


def test_en_la_nube_la_cadena_es_barata_y_rapida(monkeypatch):
    """El orden NO es por calidad, es por (rapidez al primer token, precio de entrada). Con el input dominando
    14:1 en este cerebro, lo único que cuenta es el precio de entrada: `grok-4-fast` está a 1,4× el titular;
    `grok-4.5` estaría a 14×, y por eso NO entra de fábrica."""
    from nucleo import cloud_account
    monkeypatch.setattr(cloud_account, "is_cloud_account", lambda: True)
    monkeypatch.setattr(pc, "_token_for", lambda t: "k")
    from nucleo.flash import fast_client
    monkeypatch.setattr(fast_client, "spec_from_config",
                        lambda: fast_client.ModelSpec(model="m", base_url="https://x/v1", api_key="k"))
    modelos = [t.get("model") for t in pc._voice_chain()]
    assert "grok-4-fast" in modelos
    assert not any("grok-4.5" in str(m) for m in modelos), "un escalón de 14× no puede ser el defecto"


def test_el_primer_escalon_de_relevo_es_el_que_pasa_la_puerta_de_enrutado(monkeypatch):
    """Un relevo por latencia salta en los turnos DIFÍCILES, así que el escalón no puede enrutar peor que el
    titular «porque total, es solo el relevo».

    Medido el 2026-08-15 (nodo 2.13, 3 rondas × 14 casos = 42 turnos por brazo): `deepseek-v4-flash` DIRECTO,
    que era este escalón, fallaba `mostrar widget` **3 de 3** — 38/42 frente al 41/42 del titular. Un fallo
    3-de-3 no es varianza, es un defecto. `deepseek-v4-pro` por el mismo endpoint iguala al titular (41/42) por
    224 ms más de TTFT, y sigue estando 7,5× por debajo del titular en primer token. Este test fija esa
    decisión: si alguien vuelve a poner Flash aquí para ahorrar, se entera de lo que cuesta."""
    from nucleo import cloud_account
    monkeypatch.setattr(cloud_account, "is_cloud_account", lambda: True)
    monkeypatch.setattr(pc, "_token_for", lambda t: "k")
    from nucleo.flash import fast_client
    monkeypatch.setattr(fast_client, "spec_from_config",
                        lambda: fast_client.ModelSpec(model="m", base_url="https://x/v1", api_key="k"))
    relevos = [t for t in pc._voice_chain() if t["name"] != "titular"]
    assert relevos, "en la nube tiene que haber relevo"
    assert relevos[0]["name"] == "deepseek-directo"
    assert relevos[0]["model"] == "deepseek-v4-pro", \
        "el escalón directo va en V4 Pro: Flash falla `mostrar widget` 3 de 3 (38/42 contra 41/42)"


def test_el_operador_manda_sobre_la_cadena(monkeypatch):
    """`fast.providers` explícito gana siempre: es como un self-host activa su propio relevo (otro DeepSeek, un
    modelo local, lo que quiera) sin heredar nuestras decisiones de coste."""
    monkeypatch.undo()
    import config.v2 as v2
    monkeypatch.setattr(v2, "get", lambda k: {"providers": [dict(T2)]} if k == "fast" else {})
    monkeypatch.setattr(pc, "_token_for", lambda t: "k")
    assert [t["name"] for t in pc.chain(pc.ROLE_VOICE)] == ["relevo"]


def test_el_cooldown_es_compartido_pero_la_cadena_no(monkeypatch):
    """Si a un proveedor se le acabó la cuota, se le acabó para todo el mundo (una sola verdad por proveedor). Lo
    que cambia por consumidor es el ORDEN de la cadena, no la salud."""
    monkeypatch.undo()
    assert pc.ROLE_VOICE != pc.ROLE_CLUSTER
    assert pc._config_key(pc.ROLE_VOICE) == "fast"
    assert pc._config_key(pc.ROLE_CLUSTER) == "cluster"
