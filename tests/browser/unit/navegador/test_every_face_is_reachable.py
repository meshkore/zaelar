"""Every face of the browser block must be able to be TRIGGERED in production (V2-201).

Twice on the same night, a fix passed its tests without doing anything:

  · **V2-199** — `recently_ended_sessions()` read `_SESSIONS` for finished sessions, and `_run_session`
    removes the record in its `finally`. The tests placed the record there and never removed it.
  · **V2-200** — the “already found something” face read the task’s `results`, and the three places that
    write it call `finish()` immediately afterward: an ACTIVE task with results does not exist. The tests fabricated it.

Both were found by asking the CODE whether the state constructed by the test can ever exist. This file
asks that question once and for all: **for every condition on which the block branches, production code
must exist that writes it.**

It does not test that the face is CORRECT —that is what the neighboring tests are for—but that it is not
dead code. That is the difference between “this fix is wrong” and “this fix does not exist,” which is what
cost two rounds.
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


# (face, pattern that writes it in production, why it matters)
FACES = [
    ("MURO", r"update_view\(", "el muro sale de la URL que escribe `update_view`, que llama el navegador real"),
    ("SIN MOVERSE", r"add_event\(|update_view\(", "el atasco se mide contra `last_progress`, que mueven ambos"),
    ("PARADA ESPERANDO A QUE ENTRES TÚ", r"set_login_wait\([^)]*,\s*True\)",
     "lo escribe `owner._authenticate` al abrir la ventana de login"),
    ("YA HA ENCONTRADO", r"session_considered\(|hbnote|considered",
     "la señal VIVA es la amplitud que reporta el worker; `results` de la tarea llega con el final (V2-200)"),
]


@pytest.mark.parametrize("face,pattern,why", FACES, ids=[f[0][:20] for f in FACES])
def test_the_condition_behind_each_face_has_a_production_writer(face, pattern, why):
    assert re.search(pattern, PROD), (
        f"la cara «{face}» del bloque del navegador no tiene quien la escriba en producción: {why}. "
        "Una cara que no puede dispararse es código muerto que además parece un arreglo hecho.")


#: Where the block lives. It was inside `prompt.live_state()` until 2026-08-24, when the architecture
#: ratchet moved it to `live_blocks.py` (V2-276). It points to the file and NOT the entire directory on
#: purpose: searching for “MURO” throughout the engine would include the tests and any comment, and this
#: guard exists precisely so that renaming a face fails.
_BLOCK = ROOT / "nucleo" / "flash" / "live_blocks.py"


def test_and_the_block_really_branches_on_all_of_them():
    """The other half: ensuring that the patterns above remain the actual faces. If someone renames one,
    this file would stop monitoring anything without failing."""
    src = _BLOCK.read_text(encoding="utf-8")
    for face, _, _ in FACES:
        assert face in src, f"«{face}» ya no aparece en el bloque — actualiza FACES o la cara desapareció"


def test_y_el_bloque_SIGUE_llegando_al_prompt():
    """The move must not leave the faces composed but with no caller: that would make them dead code again.

    This is literally the failure this file exists to catch (V2-199/V2-200), applied to the extraction that
    moved it. It is checked by RENDERING, not by reading the `import`.
    """
    from nucleo.flash import live_blocks, prompt
    assert prompt._live_blocks is live_blocks
    import inspect
    assert "navegador_lines()" in inspect.getsource(prompt.live_state), (
        "`live_state` dejó de llamar al bloque: el estado del navegador ya no llega al turno")


def test_an_ACTIVE_task_with_results_is_still_impossible():
    """The specific fact that killed V2-192, recorded here as well because it is why the results face
    reads the worker signal rather than the task field."""
    for rel in ("widgets/navegador/owner.py", "nucleo/dispatch.py"):
        src = (ROOT / rel).read_text(encoding="utf-8", errors="replace")
        for m in re.finditer(r"set_results\(", src):
            after = src[m.end():m.end() + 700]
            assert re.search(r"\.finish\(|set_status\([^)]*\"(done|failed|cancelled)\"", after), (
                f"{rel}: un `set_results()` que NO termina la tarea. Si eso pasa a ser posible, la cara de "
                "resultados puede volver a leer el campo de la tarea — pero que sea una decisión.")
