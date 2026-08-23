"""Le decíamos al worker web que corría en la raíz del repo, y luego le bloqueábamos el `cd` (V2-277).

Medido en `search-secondhand-monitor__es` (2026-08-24 00:56), tres veces seguidas a los 42 s y en una ronda
que acabó entregando cero:

    task  · paso ⚠️ error   cd in '/Users/…/zaelar/engine' was blocked. For security, Claude Code may only
                            change directories to the allowed working directories for this session: …

No era el modelo cabezota. `_web_prompt` empezaba su manual de comandos con «CÓMO CONDUCIR (desde la raíz
del repo…)» — una frase que V2-117 volvió FALSA al confinar el cwd del worker a su propio directorio
temporal. Le dijimos dónde estaba, mal, y bloqueamos el comando con el que iba a llegar.

Y la segunda mitad, que es la estructural: las REGLAS DEL CAJÓN de V2-211 —lo que puede y no puede hacer en
ese shell— vivían dentro de `_with_interpreter`, al que solo llama `_build_prompt`. O sea que el worker WEB,
**el que más shell compone porque conduce un navegador**, era el único que nunca las recibía. Misma
asimetría que V2-257 (la hoja se le enseñaba al genérico y no al web) y con el mismo perjudicado.

Este fichero guarda la forma general, no el caso: TODO prompt que ofrezca un puente lleva las reglas del
cajón. Un test sobre `_web_prompt` a secas dejaría al siguiente builder cayendo en lo mismo.
"""
import inspect
import re

import pytest

from nucleo import dispatch_prompts as dp

_CTX = "CONTEXTO DE MEMORIA: nada relevante."


def _prompts() -> dict:
    """Los builders REALES, renderizados. Se llaman como los llama producción, no se leen."""
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
    """El cwd está CONFINADO desde V2-117. Una frase que diga lo contrario invita al `cd` que bloqueamos."""
    p = _prompts()[name]
    assert "raíz del repo" not in p, (
        "el prompt sigue diciendo que se corre desde la raíz del repo — es falso desde V2-117 y es "
        "exactamente lo que produce los tres `cd blocked` medidos")


def test_la_regla_vive_UNA_vez_y_las_dos_la_LEEN():
    """Dos copias de una regla se separan sin avisar, y el aviso llega cuando alguien mide algo raro.

    Es la lección que este repo ya pagó cuatro veces en una semana (V2-252, V2-254, V2-256, V2-261): el fallo
    no fue la regla, fue tenerla repetida.
    """
    src = inspect.getsource(dp)
    assert src.count("NO SALGAS DE TU DIRECTORIO") == 1, "la regla del cajón volvió a estar escrita dos veces"
    assert "_drawer_rules(" in src


def test_las_reglas_se_pueden_dar_SIN_intérprete_y_siguen_siendo_las_mismas():
    """El builder web ya escribe la ruta absoluta en cada línea, así que no necesita la cabecera — pero la
    lista de lo que está fuera del cajón no puede encoger por eso."""
    con = dp._drawer_rules("/x/.venv/bin/python")
    sin = dp._drawer_rules()
    assert "INTÉRPRETE:" in con and "INTÉRPRETE:" not in sin
    for regla in ("NO SALGAS DE TU DIRECTORIO", "UN comando por llamada", "Solo los puentes",
                  "Si un comando te pide aprobación"):
        assert regla in con and regla in sin


def test_el_prompt_web_sigue_dando_la_ruta_ABSOLUTA_del_interprete():
    """La otra mitad de V2-211: sin ella el worker prueba `python`/`python3` hasta topar con el allowlist."""
    p = _prompts()["web"]
    for linea in re.findall(r"^.*-m nucleo\.nav_cli.*$", p, re.M)[:3]:
        assert re.search(r"(^|\s)/\S+/python\s+-m nucleo\.", linea), (
            f"una línea de comando sin intérprete absoluto: {linea.strip()[:90]}")
