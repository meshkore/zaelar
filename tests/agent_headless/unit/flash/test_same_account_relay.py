"""V2-458 — dos escalones que comparten cuenta no son dos escalones.

Medido con el motor vivo el 2026-08-28: la cadena de voz del operador lleva `deepseek-v4-flash` y
`deepseek-v4-pro`, los dos contra `DEEPSEEK_API_KEY`. Con la cuenta a cero el titular devolvió 402, el relevo
fue al hermano, el hermano devolvió 402 — y ahí se agotó el único reintento que V2-252 concede, así que el turno
salió mudo **con AIMLAPI respondiendo 200 una fila más abajo**.
"""
from __future__ import annotations

import time

import pytest

from nucleo.flash import provider_chain as pc

_402 = ("Error code: 402 - {'error': {'message': 'Insufficient Balance', 'type': 'unknown_error'}}")
_429 = "429 — [1310][Weekly Limit Exhausted. Your limit will reset at 2027-01-01 01:39:02]"


@pytest.fixture()
def cadena(monkeypatch):
    """La cadena REAL del operador, en miniatura: dos escalones de una cuenta y uno de otra."""
    tiers = [
        {"name": "deepseek-directo", "base_url": "https://api.deepseek.com",
         "model": "deepseek-v4-flash", "api_key": "SECRETO-DEEPSEEK", "plan": "titular"},
        {"name": "deepseek-directo-pro", "base_url": "https://api.deepseek.com",
         "model": "deepseek-v4-pro", "api_key": "SECRETO-DEEPSEEK", "plan": "relevo hermano"},
        {"name": "aimlapi-failover", "base_url": "https://api.aimlapi.com/v1",
         "model": "deepseek/deepseek-v4-flash", "api_key": "SECRETO-AIMLAPI", "plan": "otro proveedor"},
    ]
    monkeypatch.setattr(pc, "chain", lambda role=pc.ROLE_CLUSTER: [dict(t) for t in tiers])
    pc._store.clear() if hasattr(pc._store, "clear") else None
    for t in tiers:
        pc._store.set(t["name"], 0, pc._health.REASON_HEALTH)
    return tiers


def test_un_saldo_agotado_apaga_a_los_hermanos_de_la_MISMA_cuenta(cadena, monkeypatch):
    nxt = pc.note_failure(_402, cadena[0], role=pc.ROLE_VOICE)
    assert nxt is not None, "tiene que haber relevo: AIMLAPI es otra cuenta y está sana"
    assert nxt["name"] == "aimlapi-failover", (
        "el relevo se saltó al hermano de la misma cuenta, que es lo que costaba el turno")
    assert not pc._store.available("deepseek-directo-pro"), "el hermano gasta del mismo saldo: cae con él"
    assert pc._store.available("aimlapi-failover"), "otra cuenta no tiene por qué caer"


def test_una_CUOTA_agotada_NO_arrastra_a_nadie(cadena):
    """La distinción de V2-243, que este cambio no puede borrar: una cuota es del MODELO y se repone sola.

    Sin esta mitad, «apaga a los que comparten cuenta» apagaría media cadena cada vez que un modelo concreto
    llega a su límite semanal — y ese límite no dice nada del modelo de al lado.
    """
    pc.note_failure(_429, cadena[0], role=pc.ROLE_VOICE)
    assert not pc._store.available("deepseek-directo")
    assert pc._store.available("deepseek-directo-pro"), "una cuota del flash no agota la del pro"


def test_sin_credencial_resoluble_no_se_apaga_a_nadie(cadena, monkeypatch):
    """«No lo sé» nunca puede apagar un escalón sano: sin credencial que comparar, no se empareja."""
    monkeypatch.setattr(pc, "chain", lambda role=pc.ROLE_CLUSTER: [
        {**cadena[0], "api_key": ""}, dict(cadena[1]), dict(cadena[2])])
    monkeypatch.setattr(pc, "_token_for", lambda t: "")
    pc.note_failure(_402, {**cadena[0], "api_key": ""}, role=pc.ROLE_VOICE)
    assert pc._store.available("deepseek-directo-pro")


def _aviso(cadena) -> str:
    """Lo que se AVISA, capturado del emisor real.

    Se recoge por `emit`, no por `caplog`: este repo loguea con loguru, que no pasa por el logging de la
    stdlib — así que un `caplog` aquí devuelve una cadena VACÍA y todo lo que se asserte sobre ella pasa sin
    mirar nada. La primera versión de los dos casos de abajo hacía exactamente eso, y el del secreto es el que
    duele: habría certificado que no se filtra una credencial sin haber leído una sola letra.
    """
    visto = []
    import voice.observer as obs
    orig = obs.emit
    obs.emit = lambda *a, **k: visto.append(" ".join(str(x) for x in a) + " " + str(k))
    try:
        pc.note_failure(_402, cadena[0], role=pc.ROLE_VOICE)
    finally:
        obs.emit = orig
    return " ".join(visto)


def test_el_aviso_NOMBRA_a_los_que_se_lleva_por_delante(cadena):
    """Dos escalones apagados y uno nombrado deja al operador buscando por qué el otro tampoco responde."""
    texto = _aviso(cadena)
    assert texto, "el aviso tiene que existir, o los dos casos de abajo no miden nada"
    assert "deepseek-directo-pro" in texto and "misma cuenta" in texto


def test_el_secreto_no_sale_en_el_aviso(cadena):
    texto = _aviso(cadena)
    assert texto
    assert "SECRETO-DEEPSEEK" not in texto


def test_dos_escalones_que_nombran_la_clave_distinto_pero_resuelven_igual_son_la_misma_cuenta(monkeypatch):
    """Se comparan las credenciales RESUELTAS, no los nombres de las variables de entorno."""
    tiers = [
        {"name": "a", "base_url": "https://api.mismo.com/v1", "env": ["CLAVE_UNO"], "plan": ""},
        {"name": "b", "base_url": "https://api.mismo.com/v2", "env": ["CLAVE_DOS"], "plan": ""},
    ]
    monkeypatch.setattr(pc, "chain", lambda role=pc.ROLE_CLUSTER: [dict(t) for t in tiers])
    monkeypatch.setattr(pc, "_token_for", lambda t: "el-mismo-valor")
    assert pc._same_account_as(tiers[0], pc.ROLE_VOICE) == ["b"]


def test_la_misma_clave_en_PROVEEDORES_distintos_no_los_hace_la_misma_cuenta(monkeypatch):
    """La mitad que hace segura la regla, y no es hipotética: lo destapó un test que ya existía.

    `test_the_text_channel_relays_too` siembra `Z_AI_API_KEY` y `AIMLAPI_KEY` con el MISMO literal, así que una
    regla que mirase solo la credencial habría apagado Z.AI al fallar AIMLAPI — un proveedor sano fuera de
    juego por una coincidencia de valores. Por eso hace falta también el host.
    """
    tiers = [
        {"name": "zai", "base_url": "https://api.z.ai/api/anthropic", "env": ["Z_AI_API_KEY"], "plan": ""},
        {"name": "aimlapi", "base_url": "https://api.aimlapi.com/v1", "env": ["AIMLAPI_KEY"], "plan": ""},
    ]
    monkeypatch.setattr(pc, "chain", lambda role=pc.ROLE_CLUSTER: [dict(t) for t in tiers])
    monkeypatch.setattr(pc, "_token_for", lambda t: "la-misma-k")
    assert pc._same_account_as(tiers[0], pc.ROLE_VOICE) == []


def test_sin_host_no_se_empareja_con_nadie(monkeypatch):
    tiers = [{"name": "a", "base_url": "", "api_key": "k", "plan": ""},
             {"name": "b", "base_url": "", "api_key": "k", "plan": ""}]
    monkeypatch.setattr(pc, "chain", lambda role=pc.ROLE_CLUSTER: [dict(t) for t in tiers])
    assert pc._same_account_as(tiers[0], pc.ROLE_VOICE) == []
