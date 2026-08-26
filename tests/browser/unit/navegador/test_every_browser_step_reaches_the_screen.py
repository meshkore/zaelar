"""V2-343 — capturábamos cada 4 segundos y enseñábamos cada 162: el paso del navegador llega a la pestaña.

Medido en la sesión `7575e81a` (2026-08-26), sobre los 21,6 minutos del encargo de `search-buy-used-car`:

    🧭 navegador (browser + parsing)   292 eventos   uno cada   4 s   → SOLO al log
    💬 worker (lo que narra)            82 eventos   uno cada  16 s   → SOLO al log
    · paso                              34 eventos   uno cada  38 s   → SOLO al log
    fase → pestaña de PROCESO            8 eventos   una cada 162 s   → la única en pantalla

El motor ya sabía veinte veces más de lo que enseñaba. Y —esto importa para no arreglar lo que no era— **el
dedup no se comía nada**: las 8 que llegaban eran las 8 distintas y todas informativas («14 resultados en la
página», «Coches.net no responde → pruebo Wallapop»). El defecto era que nadie mandaba las demás.

Las dos vías estaban tapadas por separado:
  · `_say_phase` tenía UN llamante, `found()` tras extraer. Las 36 navegaciones, 27 clics y 13 scrolls no.
  · el stream del worker ve cada paso, pero conduce el navegador por Bash → `where=sistema, action=ejecuta`
    → «ejecutando un paso», una CONSTANTE que el dedup colapsa a una línea. Y hace bien.

Por qué esto es un defecto de PRODUCTO y no de instrumentación: mientras la pantalla no tiene nada nuevo que
decir, lo único que el turno puede contestar es «sigo con ello» — que es exactamente lo que el juez puntúa como
vaguedad ronda tras ronda. La frecuencia de la información ES la información.
"""
import asyncio

import pytest

from nucleo import sheets as SH
from widgets.navegador import act_api


class _Tab:
    async def ensure(self):
        return None

    async def navigate(self, url, **kw):
        return {"ok": True, "url": url}

    async def snapshot_for_agent(self):
        return {"url": "https://x", "title": "t"}

    page = None


@pytest.fixture
def dicho(monkeypatch):
    """Recoge lo que el puente manda a la pestaña, por el camino REAL."""
    out = []
    monkeypatch.setattr(act_api, "_emit_nav", lambda *a, **k: None)
    monkeypatch.setattr(act_api, "_say_phase", lambda tid, frase: out.append(frase) if frase else None)
    from widgets.navegador import owner
    monkeypatch.setitem(owner._task_browsers, "t1", _Tab())
    return out


def _act(action, args):
    return asyncio.run(act_api.navegador_act(task_id="t1", action=action, args=args))


# ── la frase de cada paso ─────────────────────────────────────────────────────────────────────────────────
def test_navigating_says_WHERE_it_is_going(dicho):
    """El host es lo que hace distinta una navegación de la siguiente — y por tanto lo que pasa el dedup."""
    _act("navigate", {"url": "https://www.coches.net/ocasion/?cf=diésel"})
    assert dicho and "coches.net" in dicho[0]


def test_two_different_sites_are_two_different_lines(dicho):
    """El caso medido: tres portales en un encargo. Si la frase no llevara el host, serían una sola línea."""
    _act("navigate", {"url": "https://www.coches.net"})
    _act("navigate", {"url": "https://www.milanuncios.com/coches-de-segunda-mano/"})
    assert len(set(dicho)) == 2, f"dos sitios distintos tienen que sonar distinto: {dicho}"


def test_the_parsing_step_announces_itself(dicho):
    """El operador pidió ver el PARSEO por su nombre. Extraer dice que extrae; cuántos salieron lo dice
    `found()` justo después, y son dos frases distintas a propósito: «me pongo» y «esto salió»."""
    _act("extract", {"limit": 14})
    assert any("página" in f for f in dicho)


def test_an_empty_action_says_nothing(dicho):
    """SENSIBILIDAD: subir la frecuencia no puede volverse hablar por hablar."""
    _act("", {})
    assert dicho == []


# ── el contrapeso: el dedup sigue protegiendo ─────────────────────────────────────────────────────────────
class _Rec:
    def __init__(self):
        self.phases = []


def test_three_identical_steps_are_still_ONE_line():
    """SENSIBILIDAD, y es la mitad que impide que este arreglo se convierta en ruido: tres scrolls seguidos
    dan tres veces «recorriendo la página», y tres líneas iguales parecen progreso sin serlo."""
    r = _Rec()
    for _ in range(3):
        SH.record_phase(r, "recorriendo la página", 40)
    assert len(r.phases) == 1


def test_but_a_line_that_CHANGED_gets_through():
    """La otra dirección: sin esto, «arreglado» y «el dedup se lo come todo» se confunden."""
    r = _Rec()
    SH.record_phase(r, "entrando en coches.net", 40)
    SH.record_phase(r, "14 resultados en la página", 40)
    SH.record_phase(r, "entrando en milanuncios.com", 40)
    assert [p["s"] for p in r.phases] == [
        "entrando en coches.net", "14 resultados en la página", "entrando en milanuncios.com"]


# ── guarda de CABLEADO: la decisión sin llamante es el arreglo que no existe (V2-199) ──────────────────────
def test_the_bridge_actually_calls_it_before_dispatching():
    """Sobre la FUENTE sin comentarios: el aviso va ANTES de ejecutar la acción, porque lo que el operador
    necesita es «entrando en coches.net» MIENTRAS entra. Comprobar solo el helper daría verde con la llamada
    borrada — que es justo el estado en el que este fichero encontró el código."""
    from pathlib import Path
    src = "\n".join(ln for ln in Path("widgets/navegador/act_api.py").read_text().splitlines()
                    if not ln.strip().startswith("#"))
    i = src.index("async def navegador_act")
    cuerpo = src[i:i + 1200]
    assert "_say_phase(task_id, _phase_for_action(action, args))" in cuerpo
    assert cuerpo.index("_say_phase(task_id, _phase_for_action") < cuerpo.index("from widgets.navegador import owner")
