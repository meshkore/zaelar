"""Cada cara del bloque del navegador tiene que poder DISPARARSE en producción (V2-201).

Dos veces la misma noche un arreglo pasó sus tests sin hacer nada:

  · **V2-199** — `recently_ended_sessions()` leía `_SESSIONS` para las sesiones acabadas, y `_run_session`
    saca el registro en su `finally`. Los tests colocaban el registro y no lo sacaban nunca.
  · **V2-200** — la cara «YA TIENE RESULTADOS» leía `results` de la tarea, y los tres sitios que lo escriben
    llaman a `finish()` acto seguido: una tarea ACTIVA con resultados no existe. Los tests la fabricaban.

Los dos se encontraron preguntándole al CÓDIGO si el estado que el test construye llega a existir. Este
fichero es esa pregunta, hecha una vez y para siempre: **por cada condición sobre la que el bloque se
ramifica, tiene que existir código de producción que la escriba.**

No prueba que la cara sea CORRECTA —para eso están los tests de al lado— sino que no es código muerto. Es la
diferencia entre «este arreglo está mal» y «este arreglo no existe», que es la que costó dos rondas.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
_PROD_DIRS = ("widgets", "nucleo", "voice", "server", "connectors")


def _production_sources() -> str:
    out = []
    for d in _PROD_DIRS:
        base = ROOT / d
        if not base.is_dir():
            continue
        for py in base.rglob("*.py"):
            try:
                out.append(py.read_text(encoding="utf-8", errors="replace"))
            except Exception:
                continue
    return "\n".join(out)


PROD = None


@pytest.fixture(scope="module", autouse=True)
def _load():
    global PROD
    PROD = _production_sources()
    yield


# (cara, patrón que la escribe en producción, por qué importa)
FACES = [
    ("MURO", r"update_view\(", "el muro sale de la URL que escribe `update_view`, que llama el navegador real"),
    ("SIN MOVERSE", r"add_event\(|update_view\(", "el atasco se mide contra `last_progress`, que mueven ambos"),
    ("PARADA ESPERANDO A QUE ENTRES TÚ", r"set_login_wait\([^)]*,\s*True\)",
     "lo escribe `owner._authenticate` al abrir la ventana de login"),
    ("YA TIENE RESULTADOS", r"session_considered\(|hbnote|considered",
     "la señal VIVA es la amplitud que reporta el worker; `results` de la tarea llega con el final (V2-200)"),
]


@pytest.mark.parametrize("face,pattern,why", FACES, ids=[f[0][:20] for f in FACES])
def test_the_condition_behind_each_face_has_a_production_writer(face, pattern, why):
    assert re.search(pattern, PROD), (
        f"la cara «{face}» del bloque del navegador no tiene quien la escriba en producción: {why}. "
        "Una cara que no puede dispararse es código muerto que además parece un arreglo hecho.")


#: Dónde vive el bloque. Estuvo dentro de `prompt.live_state()` hasta el 2026-08-24, cuando el trinquete de
#: arquitectura lo mandó a `live_blocks.py` (V2-276). Se apunta al fichero y NO a la carpeta entera a
#: propósito: buscar «MURO» en todo el motor pasaría por los tests y por cualquier comentario, y este guarda
#: existe justo para que renombrar una cara falle.
_BLOCK = ROOT / "nucleo" / "flash" / "live_blocks.py"


def test_and_the_block_really_branches_on_all_of_them():
    """La otra mitad: que los patrones de arriba sigan siendo las caras de verdad. Si alguien renombra una,
    este fichero dejaría de vigilar nada sin fallar."""
    src = _BLOCK.read_text(encoding="utf-8")
    for face, _, _ in FACES:
        assert face in src, f"«{face}» ya no aparece en el bloque — actualiza FACES o la cara desapareció"


def test_y_el_bloque_SIGUE_llegando_al_prompt():
    """La mudanza no puede dejar las caras compuestas y sin llamante: eso las haría código muerto otra vez.

    Es literalmente el fallo que este fichero existe para cazar (V2-199/V2-200), aplicado a la extracción que
    lo movió. Se comprueba RENDERIZANDO, no leyendo el `import`.
    """
    from nucleo.flash import live_blocks, prompt
    assert prompt._live_blocks is live_blocks
    import inspect
    assert "navegador_lines()" in inspect.getsource(prompt.live_state), (
        "`live_state` dejó de llamar al bloque: el estado del navegador ya no llega al turno")


def test_an_ACTIVE_task_with_results_is_still_impossible():
    """El hecho concreto que mató a V2-192, fijado aquí también porque es la razón de que la cara de
    resultados lea la señal del worker y no el campo de la tarea."""
    for rel in ("widgets/navegador/owner.py", "nucleo/dispatch.py"):
        src = (ROOT / rel).read_text(encoding="utf-8", errors="replace")
        for m in re.finditer(r"set_results\(", src):
            after = src[m.end():m.end() + 700]
            assert re.search(r"\.finish\(|set_status\([^)]*\"(done|failed|cancelled)\"", after), (
                f"{rel}: un `set_results()` que NO termina la tarea. Si eso pasa a ser posible, la cara de "
                "resultados puede volver a leer el campo de la tarea — pero que sea una decisión.")
