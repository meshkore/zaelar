"""We told the web worker that it ran at the repository root, and then blocked its `cd` (V2-277).

Measured in `search-secondhand-monitor__es` (2026-08-24 00:56), three times in a row at 42 s and in one round
that ended up delivering zero:

    task  · paso ⚠️ error   cd in '/Users/…/zaelar/engine' was blocked. For security, Claude Code may only
                            change directories to the allowed working directories for this session: …

It was not the model being stubborn. `_web_prompt` began its command manual with “HOW TO DRIVE (from the
repository root…)” — a statement that V2-117 made FALSE by confining the worker’s cwd to its own temporary
directory. We told it where it was, incorrectly, and blocked the command it would have used to get there.

And the second half, which is the structural one: V2-211’s DRAWER RULES —what it may and may not do in
that shell— lived inside `_with_interpreter`, which only `_build_prompt` calls. That meant the WEB worker,
**the one that composes the most shell because it drives a browser**, was the only one that never received them.
The same asymmetry as V2-257 (the sheet was shown to the generic worker and not the web worker), with the same
party harmed.

This file captures the general pattern, not the specific case: EVERY prompt that offers a bridge carries the
drawer rules. A test of `_web_prompt` alone would leave the next builder making the same mistake.
"""
import inspect
import re

import pytest

from nucleo import dispatch_prompts as dp

_CTX = "CONTEXTO DE MEMORIA: nada relevante."


def _prompts() -> dict:
    """The REAL, rendered builders. They are called as production calls them, not read directly."""
    return {
        "web": dp._web_prompt("Busca un monitor de segunda mano de 27 pulgadas por menos de 150€", _CTX),
        "generic": dp._build_prompt("Investiga el mercado de monitores de segunda mano", _CTX, True),
    }


@pytest.mark.parametrize("name", ["web", "generic"])
def test_todo_prompt_con_puente_lleva_las_reglas_del_cajon(name):
    p = _prompts()[name]
    assert "-m nucleo." in p, "este builder ya no ofrece puentes: revisa el test antes que el código"
    assert "TU CAJÓN" in p, f"el prompt «{name}» ofrece puentes y no dice qué le está permitido"
    for regla in ("NO SALGAS DE TU DIRECTORIO", "UN comando por llamada", "Solo los puentes"):
        assert regla in p, f"al prompt «{name}» le falta la regla «{regla}»"


@pytest.mark.parametrize("name", ["web", "generic"])
def test_y_NINGUNO_afirma_que_el_worker_corre_en_la_raiz_del_repo(name):
    """The cwd has been CONFINED since V2-117. A statement to the contrary invites the `cd` that we blocked."""
    p = _prompts()[name]
    assert "raíz del repo" not in p, (
        "el prompt sigue diciendo que se corre desde la raíz del repo — es falso desde V2-117 y es "
        "exactamente lo que produce los tres `cd blocked` medidos")


def test_la_regla_vive_UNA_vez_y_las_dos_la_LEEN():
    """Two copies of a rule drift apart without warning, and the warning comes when someone measures something odd.

    It is the lesson this repository has already paid for four times in one week (V2-252, V2-254, V2-256, V2-261):
    the problem was not the rule, but having it duplicated.
    """
    src = inspect.getsource(dp)
    assert src.count("NO SALGAS DE TU DIRECTORIO") == 1, "la regla del cajón volvió a estar escrita dos veces"
    assert "_drawer_rules(" in src


def test_las_reglas_se_pueden_dar_SIN_intérprete_y_siguen_siendo_las_mismas():
    """The web builder already writes the absolute path on every line, so it does not need the header — but the
    list of what is outside the drawer cannot shrink because of that."""
    con = dp._drawer_rules("/x/.venv/bin/python")
    sin = dp._drawer_rules()
    assert "INTÉRPRETE:" in con and "INTÉRPRETE:" not in sin
    for regla in ("NO SALGAS DE TU DIRECTORIO", "UN comando por llamada", "Solo los puentes",
                  "Si un comando te pide aprobación"):
        assert regla in con and regla in sin


def test_el_prompt_web_sigue_dando_la_ruta_ABSOLUTA_del_interprete():
    """The other half of V2-211: without it, the worker tries `python`/`python3` until it runs into the allowlist."""
    p = _prompts()["web"]
    for linea in re.findall(r"^.*-m nucleo\.nav_cli.*$", p, re.M)[:3]:
        assert re.search(r"(^|\s)/\S+/python\s+-m nucleo\.", linea), (
            f"una línea de comando sin intérprete absoluto: {linea.strip()[:90]}")
