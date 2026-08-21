"""El canal de TEXTO no relevaba, y eso tuvo al arnés ocho horas sin poder medir (V2-252).

Medido por él el 2026-08-21, con la cadena real sembrada en un sandbox nuevo
(`deepseek-directo → aimlapi-failover`). Un turno:

    POST /api/flash/say → {"ok":false,"error":"modelo: 402 Insufficient Balance","spec":"deepseek/deepseek-v4-pro"}

y en el **mismo segundo**, en el mismo log:

    10:05:35  cerebro de voz: «deepseek-directo» SIN SALDO → relevo a «aimlapi-failover»
    10:05:34  memllm[i18n]: relevo a deepseek/deepseek-v4-pro @ aimlapi tras 402

**La voz relevaba. i18n relevaba. El texto no.** No faltaba la política: faltaba aplicarla. `probe.py` capturaba
el error, apuntaba el cooldown y la salud… y devolvía, con un escalón sano esperando al lado.

memoria-dev trajo el precedente y es lo que convierte esto en estructural: **es la TERCERA vez que muerde la
misma forma**. `probe.py` es la implementación PARALELA del provider de voz, y el arnés corre por ese canal
(`channel='probe'`). El 2026-08-18 (V2-118…121, `22f3674`) el síntoma fue otro —las tags `[[cron.create]]` se
capturaban y no se ejecutaban, así que un aviso programado era INALCANZABLE por esa vía— y el 2026-08-15 el
relevo ante un fallo duro se añadió a la voz y no aquí.

Por eso el arreglo no es solo el reintento: la DECISIÓN pasa a `nucleo/flash/provider_failure.py`, una vez, y la
usan los dos canales. Dos copias de una decisión se separan sin avisar, y el aviso llega cuando alguien mide algo
que sale mal por un motivo que no es el que está midiendo.
"""
import inspect
import pathlib

import pytest

from nucleo.flash import provider_chain as pc
from nucleo.flash import provider_failure as pf

UNO = {"name": "z.ai", "base_url": "https://api.z.ai/api/anthropic", "model": "glm", "env": ["Z_AI_API_KEY"]}
DOS = {"name": "aimlapi", "base_url": "https://api.aimlapi.com/v1", "model": "", "env": ["AIMLAPI_KEY"]}
SIN_SALDO = "API Error: 402 Insufficient Balance"


@pytest.fixture
def cadena(monkeypatch):
    monkeypatch.setattr(pc, "chain", lambda *a, **k: [dict(UNO), dict(DOS)])
    monkeypatch.setattr(pc._store, "_cooldown", {})
    monkeypatch.setattr(pc._store, "_loaded", True)
    monkeypatch.setattr(pc._store, "_save", lambda: None)
    monkeypatch.setattr(pc, "_slow_streak", {})
    monkeypatch.setenv("Z_AI_API_KEY", "k")
    monkeypatch.setenv("AIMLAPI_KEY", "k")


# ── la decisión, una sola vez ────────────────────────────────────────────────────────────────────────────────

def test_un_402_devuelve_EL_ESCALON_al_que_ir(cadena):
    v = pf.handle(SIN_SALDO, role=pc.ROLE_VOICE)
    assert v["relay"] and v["relay"]["name"] == "aimlapi"
    assert v["dry"] is False


def test_y_deja_al_titular_en_COOLDOWN(cadena):
    pf.handle(SIN_SALDO, role=pc.ROLE_VOICE)
    assert not pc._store.available("z.ai"), "sin cooldown, el turno siguiente vuelve al mismo sitio"


def test_un_ATASCO_no_es_un_fallo_duro(cadena):
    """V2-246: uno aislado es ruido y no releva; dos seguidos sí. La distinción la hace el módulo, no el canal."""
    assert pf.handle("", role=pc.ROLE_VOICE, stalled=True)["relay"] is None
    assert pf.handle("", role=pc.ROLE_VOICE, stalled=True)["relay"]["name"] == "aimlapi"


def test_con_la_cadena_SECA_lo_dice(cadena, monkeypatch):
    monkeypatch.setattr(pc, "chain", lambda *a, **k: [dict(UNO)])
    v = pf.handle(SIN_SALDO, role=pc.ROLE_VOICE)
    assert v["relay"] is None and v["dry"] is True


def test_un_error_que_NO_es_del_proveedor_no_releva_a_nadie(cadena):
    """Sensibilidad: relevar por un fallo nuestro cambiaría de proveedor sin motivo y encima taparía el fallo."""
    v = pf.handle("TypeError: 'NoneType' object is not subscriptable", role=pc.ROLE_VOICE)
    assert v["relay"] is None
    assert pc._store.available("z.ai"), "un error de código no puede poner a un proveedor sano en cooldown"


def test_no_añade_una_excepcion_a_la_que_ya_hubo(monkeypatch):
    """Corre DENTRO del manejador de errores de un turno: si revienta, se lleva el turno y además el diagnóstico."""
    monkeypatch.setattr(pc, "note_failure", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")), raising=False)
    assert pf.handle(SIN_SALDO, role=pc.ROLE_VOICE)["relay"] is None


# ── y que el canal de TEXTO la aplique ───────────────────────────────────────────────────────────────────────
# GUARDA DE CABLEADO (V2-199), y aquí es el corazón del asunto: la política ya existía y el canal no la aplicaba.
# Un test sobre el predicado habría pasado en verde las tres veces que esto mordió.

def _probe_src() -> str:
    return pathlib.Path(inspect.getfile(pc)).parent.joinpath("probe.py").read_text(encoding="utf-8")


def test_el_canal_de_texto_REINTENTA_con_el_relevo():
    src = _probe_src()
    assert "_pfail.handle(" in src, "el canal de texto no usa la decisión compartida"
    assert "spec = _pchain_err.spec_for(_nxt)" in src, "apunta el cooldown y devuelve, sin reintentar"
    assert "continue" in src


def test_reintenta_UNA_vez_y_no_entra_en_bucle():
    """Un proveedor roto no puede convertirse en un bucle de reintentos: un intento, un relevo, un reintento."""
    src = _probe_src()
    assert "_relay_done = False" in src and "if _nxt and not _relay_done" in src


def test_NO_reintenta_si_el_turno_ya_habia_dicho_algo():
    """Con un 402 el stream muere antes del primer delta, que es el caso real. Pero si ya había salido texto o una
    tool, repetir el turno lo diría DOS veces — y eso es peor que perder el turno."""
    src = _probe_src()
    assert "_virgen = not raw and not buf and not tool_calls" in src
    assert "and _virgen" in src


def test_cuando_ni_asi_se_puede_lo_DICE(cadena):
    """La respuesta lleva `sin_relevo` para que quien mida distinga «se rompió» de «no había a quién preguntar»."""
    src = _probe_src()
    assert '"sin_relevo": bool(_v.get("dry"))' in src


def test_los_DOS_canales_usan_la_MISMA_decision():
    """Lo estructural, y es lo que evita la cuarta vez: la política vive en un sitio y la leen los dos."""
    voz = pathlib.Path(inspect.getfile(pc)).parent.parent.parent / "voice/engine/llm/providers/nucleo.py"
    assert "provider_failure" in voz.read_text(encoding="utf-8")
    assert "provider_failure" in _probe_src()


# ── y el cooldown cae sobre el que FALLÓ, no sobre el que tocaría ahora ──────────────────────────────────────
# Segunda trampa de la misma zona, medida por el arnés el 2026-08-21: hay DOS fuentes de «quién es el titular».
# El turno compone su spec con `spec_from_config()` (que lee `fast.model` / `fast.base_url`) y la cadena se
# ordena por `fast.providers`. Reordenó la escalera y **no cambió nada**, porque el turno no mira esa lista.
#
# Importa porque `note_failure` sin `tier` pregunta a `pick()` — «el que se elegiría AHORA»—, que tras un reorden
# puede no ser el que acaba de fallar: el cooldown cae sobre un proveedor SANO y el roto sigue elegido. Castigar
# al inocente y dejar suelto al culpable, en silencio.

class _Spec:
    def __init__(self, url):
        self._u = url

    def resolved_base_url(self):
        return self._u


def test_el_cooldown_cae_sobre_el_que_de_verdad_corrio(cadena):
    """El turno corrió por el SEGUNDO escalón (el relevo) y falló. Sin el spec, se castigaría al primero."""
    v = pf.handle(SIN_SALDO, role=pc.ROLE_VOICE, spec=_Spec(DOS["base_url"]))
    assert not pc._store.available("aimlapi"), "el que falló tiene que quedar en cooldown"
    assert pc._store.available("z.ai"), "y el que NO corrió no puede pagarlo"
    assert v["relay"] and v["relay"]["name"] == "z.ai"


def test_una_barra_final_no_cambia_de_quien_hablamos(cadena):
    assert pf.tier_for(_Spec(DOS["base_url"] + "/"), pc.ROLE_VOICE)["name"] == "aimlapi"


def test_un_endpoint_DESCONOCIDO_no_castiga_a_nadie_por_error(cadena):
    """Si el turno corrió por un sitio que no está en la cadena, adivinar sería exactamente el fallo que esto
    cierra. Se cae al comportamiento de antes —que lo decida `pick()`— y no se inventa un culpable."""
    assert pf.tier_for(_Spec("https://otro.invalid/v1"), pc.ROLE_VOICE) is None


def test_sin_spec_se_comporta_como_antes(cadena):
    """Compatibilidad: los llamadores que no lo pasen siguen funcionando igual."""
    assert pf.handle(SIN_SALDO, role=pc.ROLE_VOICE)["relay"]["name"] == "aimlapi"


def test_los_dos_canales_PASAN_el_spec():
    """GUARDA DE CABLEADO: el predicado puede estar perfecto y los dos canales seguir sin decirle quién corrió."""
    voz = pathlib.Path(inspect.getfile(pc)).parent.parent.parent / "voice/engine/llm/providers/nucleo.py"
    assert "spec=spec)" in voz.read_text(encoding="utf-8")
    assert "role=_pchain_err.ROLE_VOICE, spec=spec)" in _probe_src()
