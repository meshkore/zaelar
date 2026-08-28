"""V2-460 — un agente del plató arranca con la sesión EN BLANCO, no con la pantalla de la semana pasada.

Norma del operador (2026-08-28), dicha mirando un agente ES recién levantado que abrió enseñando la hoja de
resultados de un encargo de coches de alquiler de días antes: «lo primero que hay que hacer cuando se lanza
un test de un use case es hacer un reset y dejar la sesión limpia para todos los procesos. Puedes mantener la
memoria o el estado básico, pero el resto tiene que estar listo para empezar una sesión en blanco y poder
centrar la observabilidad en la tarea y el test en curso.»

El runner ya lo hacía ANTES DE CADA CASO desde el 2026-08-21 (misma queja, otro camino). Lo que faltaba era el
arranque a mano: un agente del plató es persistente a propósito —esa es la razón del puerto fijo— así que su
canvas, su trabajo de fondo y su ventana de observabilidad sobreviven al PROCESO, porque lo que persiste es el
workspace en disco. Y lo que sobrevive es exactamente lo que hace ilegible una ronda: el visor ◷ no sabe
separar «este test» de «lo que había antes».
"""
from __future__ import annotations

import json

import pytest

from tests.use_cases.lab import profiles as LP, stage


@pytest.fixture()
def lab(monkeypatch, tmp_path):
    """Plató de mentira: ni arranca un motor ni escribe en el workspace real del operador."""
    monkeypatch.setattr(stage, "LAB_ROOT", tmp_path)
    monkeypatch.setattr(stage, "seed_profile", lambda p: {"state": 4, "pills": 2})
    monkeypatch.setattr(stage, "seed_provider_chain", lambda ws: "aimlapi → deepseek")
    monkeypatch.setattr(stage, "_restore_kv", lambda ws, carried: None)

    class _Proc:
        pid = 4242

    def _spawn(**kw):
        return type("E", (), {"process": _Proc(), "base_url": f"http://127.0.0.1:{kw['port']}"})()

    monkeypatch.setattr(stage, "spawn_engine", _spawn)
    # `_alive` mira el pid DE VERDAD (si devolviera True siempre, `up()` creería que ya hay uno en marcha y
    # saldría sin arrancar nada), y nada responde en el puerto antes de arrancar (si respondiera, `up()` lo
    # leería como un motor AJENO en nuestro puerto y se negaría — que es lo correcto en producción).
    monkeypatch.setattr(stage, "_alive", lambda pid: bool(pid))
    monkeypatch.setattr(stage, "_get", lambda url, timeout=2.0: None)
    return tmp_path


def _meta(profile) -> dict:
    return json.loads((stage.workspace_of(profile) / "lab.json").read_text(encoding="utf-8"))


# ── el arranque ─────────────────────────────────────────────────────────────────────────────────────────
def test_arrancar_deja_la_sesion_en_blanco(monkeypatch, lab):
    posted: list[tuple[str, dict]] = []
    monkeypatch.setattr(stage, "_post", lambda url, payload, timeout=60.0: posted.append((url, payload))
                        or {"session": "abc12345", "reset": {}})
    _, st = stage.up(LP.ES, voice=False)
    assert posted, "arrancó sin limpiar: el operador abre el puerto y ve la ronda anterior"
    assert st.cleaned is True
    assert _meta(LP.ES)["cleaned"] is True


def test_se_limpia_por_RESET_HARD_y_jamas_por_el_que_REINICIA(monkeypatch, lab):
    """Las dos mitades de la norma, y la segunda es la peligrosa.

    `/reset/hard` para los procesos y borra el canvas EN VIVO, dejando en pie memoria y perfil — que es lo
    que hace de este agente Marc de Madrid, o sea lo único que no se puede tirar. `/api/reset/full` con
    `wipe_memory` haría además otra cosa: relanza el motor con un `make run` en el directorio del motor
    REAL, y `scripts/run-livekit.sh` siega todo `python -m server` por NOMBRE — se llevaría por delante el
    plató Y el motor del operador.
    """
    urls: list[str] = []
    monkeypatch.setattr(stage, "_post", lambda url, payload, timeout=60.0: urls.append(url) or {})
    stage.clean_session(LP.ES)
    assert urls == [f"http://127.0.0.1:{LP.ES.port}/reset/hard"]
    assert not any("reset/full" in u for u in urls)


def test_cada_agente_se_limpia_en_SU_puerto(monkeypatch, lab):
    """Un plató limpiando al otro sería peor que no limpiar: mata el trabajo de una ronda que sí iba bien."""
    urls: list[str] = []
    monkeypatch.setattr(stage, "_post", lambda url, payload, timeout=60.0: urls.append(url) or {})
    stage.clean_session(LP.US)
    assert str(LP.US.port) in urls[0] and str(LP.ES.port) not in urls[0]


# ── cuando NO se consigue ───────────────────────────────────────────────────────────────────────────────
def test_una_limpieza_que_falla_no_tumba_el_arranque_pero_SE_DICE(monkeypatch, lab):
    """Pedir la limpieza no es haberla conseguido — la lección que ya costó una tanda entera en el runner,
    donde una espera fija de dos segundos imprimía «motor reseteado» pasara lo que pasara.

    Un agente en pie con la pantalla sucia todavía mide; uno que se niega a arrancar no mide nada. Así que
    no es fatal, pero el estado lo dice y la CLI lo imprime en los dos sentidos.
    """
    monkeypatch.setattr(stage, "_post", lambda url, payload, timeout=60.0: None)
    _, st = stage.up(LP.ES, voice=False)
    assert st.cleaned is False
    assert _meta(LP.ES)["cleaned"] is False


def test_el_estado_ARRASTRA_la_limpieza_o_la_CLI_no_puede_decirla(lab):
    ws = stage.workspace_of(LP.ES)
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "lab.json").write_text(json.dumps({"pid": 1, "port": LP.ES.port, "cleaned": True}), encoding="utf-8")
    assert stage.status(LP.ES).cleaned is True
    (ws / "lab.json").write_text(json.dumps({"pid": 1, "port": LP.ES.port}), encoding="utf-8")
    assert stage.status(LP.ES).cleaned is False, "sin el campo se asume SUCIO, que es lo que no engaña"


# ── lo que NO se puede llevar por delante ───────────────────────────────────────────────────────────────
def test_la_memoria_y_el_perfil_NO_se_tocan_al_limpiar(monkeypatch, lab):
    """La otra mitad de la norma («puedes mantener la memoria o el estado básico»), y no es un detalle: el
    perfil sembrado es lo que hace que «búscame un fontanero» resuelva a Madrid sin que nadie diga la ciudad.
    Borrarlo convertiría cada limpieza en un caso midiendo a otra persona."""
    llamado = {"wipe": 0, "seed": 0}
    monkeypatch.setattr(stage, "wipe", lambda p: llamado.__setitem__("wipe", llamado["wipe"] + 1) or {})
    monkeypatch.setattr(stage, "seed_profile", lambda p: llamado.__setitem__("seed", llamado["seed"] + 1))
    monkeypatch.setattr(stage, "_post", lambda url, payload, timeout=60.0: {"session": "x"})
    stage.clean_session(LP.ES)
    assert llamado == {"wipe": 0, "seed": 0}, "limpiar la sesión no puede tocar la memoria ni resembrar"
