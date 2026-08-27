"""El informe se compone con trabajo TODAVÍA VIVO, y nada lo decía (V2-397).

Medido sobre los 215 informes del archivo que traen `quiescence`:

    settled: True   84
    settled: False 131      ← 61 %, con la espera agotada en el tope (mediana 60,2 s)

y de esos 131, **130** con la nota «N worker(s) sin final al agotarse la espera: hay trabajo vivo». O sea
que en seis de cada diez rondas el informe se compuso mientras un worker seguía trabajando — todavía por
escribir sus hallazgos, su hoja y sus widgets.

Dos defectos, uno solo de fondo:

1. **EL ORDEN.** `wait_for_quiescence` existe justo para esto y su propia docstring lo dice: «so the
   mechanism is read after the round, not during it». Pero en `run.py` se llamaba DESPUÉS de
   `mechanism_report`, así que protegía las columnas del final (`worker_health`, `proactive_notes`,
   `search_returns`) y no protegía el TRONCO — el flujo de eventos del que salen `families_observed`,
   `widget_ops`, `sheet_instances`, `dropped_actions` y la auditoría entera.

2. **LAS PALABRAS.** `quiescence` no aparecía ni una vez en `judge.py`. El juez leía «la hoja está vacía»,
   «ningún widget escribió» y lo puntuaba como fallo del producto, sin saber que se le estaba enseñando una
   foto sacada a media faena.

No es INFRA y no puede serlo: anular seis de cada diez rondas dejaría el tablero sin medir y escondería
detrás defectos reales. Es un AVISO, y el aviso tiene que llegarle a quien puntúa.
"""
import ast
from pathlib import Path

from tests.use_cases.e2e.agent import judge as J, verify as V


def _texto(x) -> str:
    return x if isinstance(x, str) else "\n".join(x)


def _run_src() -> str:
    return Path("tests/use_cases/e2e/agent/run.py").read_text()


# ── 1. el orden ────────────────────────────────────────────────────────────────────────────────────────────

def _linea_de(nombre: str) -> int:
    """Primera línea de `_run_scenario` donde se LLAMA a `nombre` (AST, no `in src`: el nombre vive también
    en comentarios y el guarda tiene que medir la propiedad, no la presencia — V2-396 lo aprendió caro)."""
    tree = ast.parse(_run_src())
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "_run_scenario")
    for n in ast.walk(fn):
        if isinstance(n, ast.Call) and getattr(n.func, "attr", getattr(n.func, "id", "")) == nombre:
            return n.lineno
    raise AssertionError(f"«{nombre}» no se llama en _run_scenario")


def test_se_espera_al_silencio_ANTES_de_leer_el_tronco():
    assert _linea_de("wait_for_quiescence") < _linea_de("session_events"), (
        "el flujo de eventos se lee antes de esperar a que el motor calle: la auditoría entera sale "
        "de una foto sacada a media faena")


def test_y_ANTES_de_componer_el_informe():
    assert _linea_de("wait_for_quiescence") < _linea_de("mechanism_report")


# ── 2. las palabras ────────────────────────────────────────────────────────────────────────────────────────

def test_una_ronda_con_trabajo_VIVO_se_le_dice_al_juez():
    txt = _texto(J.mechanism_facts({"quiescence": {
        "settled": False, "waited_s": 60.2, "pending_workers": 2,
        "note": "2 worker(s) sin final al agotarse la espera: hay trabajo vivo"}}))
    assert "A MEDIA FAENA" in txt
    assert "2 worker" in txt
    assert "no prueba" in txt


def test_una_ronda_que_SI_calló_no_dice_nada():
    """Sensibilidad: un aviso que sale siempre deja de ser aviso."""
    txt = _texto(J.mechanism_facts({"quiescence": {"settled": True, "waited_s": 6.0, "events": 300}}))
    assert "A MEDIA FAENA" not in txt


def test_sin_el_dato_tampoco_se_inventa():
    assert "A MEDIA FAENA" not in _texto(J.mechanism_facts({"results_sheet": {"n_named": 3}}))


# ── la frase vive en verify, para poder asertarla sin grep ─────────────────────────────────────────────────

def test_la_frase_es_una_funcion_y_no_una_condicion_suelta():
    assert V.measured_in_flight({"quiescence": {"settled": False, "pending_workers": 1,
                                                "waited_s": 60.2}})
    assert V.measured_in_flight({"quiescence": {"settled": True}}) == ""
    assert V.measured_in_flight({}) == ""


def test_el_motor_que_seguia_escribiendo_SIN_workers_tambien_cuenta():
    """La nota minoritaria (1 de 131) es otra cosa: nadie vivo y la tienda sin parar de escribir. Se avisa
    igual — lo que invalida la foto es que se sacara en movimiento, no quién la movía."""
    frase = V.measured_in_flight({"quiescence": {"settled": False, "pending_workers": 0, "waited_s": 60.1}})
    assert frase and "seguía escribiendo" in frase


# ── no se anula la ronda ───────────────────────────────────────────────────────────────────────────────────

def test_NO_es_INFRA():
    """131 de 215 rondas tienen esta forma: anularlas dejaría el tablero sin medir y escondería detrás
    defectos reales. El aviso informa a quien puntúa; no le quita la nota."""
    src = _run_src()
    assert "crashed = verifymod.measured_in_flight" not in src
