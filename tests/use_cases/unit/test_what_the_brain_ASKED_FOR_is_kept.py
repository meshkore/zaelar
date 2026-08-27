"""El arnés tiraba a la basura lo que el cerebro PIDIÓ en cada turno (V2-398).

`POST /api/flash/say` devuelve, medido contra la forma real del `return` de `nucleo/flash/probe.py`:

    {"reply": …, "action": "…", "tool_calls": [{"name": …, "args": …}], "executed": …, "trace": …}

y `run.py` se quedaba **solo con `reply`**. Todo lo demás se perdía en el mismo instante en que llegaba.

Lo que eso cuesta se vio en `play-music-and-build-playlist` (2026-08-27 15:23). El usuario pidió DOS cosas
en una frase —«ponla de verdad **y** guárdala en una lista que se llame Curro»— y zaelar contestó «Volumen
al 85 por ciento». El juez escribió el hallazgo «subió el volumen **en vez de** guardar la canción»
**deduciéndolo del texto de la respuesta**, porque no había otra cosa que mirar: `audit.tools_run` venía
`{}` y `widget_ops` solo trae el AGREGADO de la ronda entera.

Y esa deducción es justo la que V2-394 demostró que no se puede hacer: «pidió A en vez de B» y «pidió A y B,
y B lo rechazó el widget en silencio» se leen igual en el transcript y son dos dueños distintos. El dato que
los separa lo tenía el arnés en la mano y lo tiraba.
"""
from tests.use_cases.e2e.agent import judge as J


def _texto(x) -> str:
    return x if isinstance(x, str) else "\n".join(x)


def test_el_juez_ve_lo_que_pidio_el_cerebro_turno_a_turno():
    txt = _texto(J.mechanism_facts({"turn_actions": [
        {"turn": 0, "pedido": ["play_music"], "action": "play_music"},
        {"turn": 1, "pedido": ["set_volume"], "action": "set_volume"},
    ]}))
    assert "PIDIÓ EL CEREBRO" in txt
    assert "play_music" in txt and "set_volume" in txt


def test_un_turno_que_no_pidio_NADA_se_ve_como_tal():
    """«No pidió herramienta ninguna» y «pidió una que falló» son dos hechos opuestos."""
    txt = _texto(J.mechanism_facts({"turn_actions": [{"turn": 0, "pedido": [], "action": "chat"}]}))
    assert "PIDIÓ EL CEREBRO" in txt
    # La marca va PEGADA al turno. Buscar «(ninguna)» suelto no valía: otra sección del mismo parte ya la
    # imprime, así que el guarda pasaba en verde con la marca borrada de esta línea.
    assert "t0→(ninguna)" in txt


def test_lo_que_se_EJECUTO_se_dice_aparte_de_lo_que_se_pidio():
    """Pedir no es hacer: es la frontera entera de V2-394."""
    txt = _texto(J.mechanism_facts({"turn_actions": [
        {"turn": 0, "pedido": ["widget_data"], "action": "widget_data", "ejecutado": "musica"}]}))
    assert "ejecutó" in txt and "musica" in txt


def test_sin_el_dato_el_juez_no_se_lo_inventa():
    txt = _texto(J.mechanism_facts({"results_sheet": {"n_named": 3}}))
    assert "PIDIÓ EL CEREBRO" not in txt


def test_run_py_GUARDA_el_dato_que_ya_tenia_en_la_mano():
    """El arnés recibía `tool_calls` en la respuesta del probe y lo descartaba en la misma línea."""
    import ast
    from pathlib import Path
    tree = ast.parse(Path("tests/use_cases/e2e/agent/run.py").read_text())
    fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "_run_scenario")
    # se lee `tool_calls` de la respuesta del turno en algún sitio de la función
    leidos = {n.args[0].value for n in ast.walk(fn)
              if isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "get"
              and n.args and isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str)}
    assert "tool_calls" in leidos, "la respuesta del probe trae tool_calls y nadie los mira"
    # y acaba en el informe
    asigna = [n for n in ast.walk(fn) if isinstance(n, ast.Subscript)
              and isinstance(n.slice, ast.Constant) and n.slice.value == "turn_actions"]
    assert asigna, "lo que pidió el cerebro no llega al informe de mecanismo"
