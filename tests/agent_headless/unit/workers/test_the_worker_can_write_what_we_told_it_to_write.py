"""Le pedíamos escribir un fichero y no le dábamos la tool para hacerlo.

El payload de los puentes va por `@fichero` desde V2-379, y el prompt lo dice con todas las letras:
*«escríbelo con Write a un fichero de tu directorio y pásalo con `@fichero.json`»*. Pero `Write` no estaba en
la allowlist que se le pasa al CLI, así que el CLI pedía una aprobación que en headless **nadie va a dar**.

Medido el 2026-08-28 en `find-best-hotel-city__us` (plató 24/7), con la cadena entera visible por primera vez
gracias a los arreglos de la misma noche:

    ⚠️ Claude requested permissions to write to …/zaelar-workers/6b9810-1/informe.json,
       but you haven't granted it yet.
    ⚠️ Exit code 2 · no puedo leer el payload de informe.json: [Errno 2] No such file or directory

Nueve turnos ciegos y nota 1/5 en esa ronda. Una instrucción que el sistema hace imposible de cumplir no es
una instrucción: es una trampa para el modelo Y para quien lea el transcript.
"""
from __future__ import annotations

from nucleo.workers import claude_session as CS


def test_el_worker_PUEDE_escribir():
    assert "Write" in CS._DEFAULT_TOOLS


def test_y_solo_Write():
    """Ni `Edit` ni `NotebookEdit`: un worker estrena directorio de usar y tirar, y escribir su propio JSON es
    la operación más pequeña que hay. MODIFICAR ficheros que ya existen es otra cosa y nadie la ha pedido."""
    assert "Edit" not in CS._DEFAULT_TOOLS and "NotebookEdit" not in CS._DEFAULT_TOOLS
    assert set(CS._DEFAULT_TOOLS) == {"Read", "Write"}


def test_el_prompt_y_la_allowlist_dicen_lo_MISMO():
    """La mitad que importa: el defecto no era que faltara una tool, era que faltaba **la que el prompt pide**.
    Si mañana el prompt enseña otra forma, esto tiene que volver a mirarse."""
    from nucleo import dispatch_prompts as DP
    reglas = DP._drawer_rules("/x/.venv/bin/python")
    assert "Write" in reglas, "el prompt dejó de pedir Write y esta allowlist se quedó sin motivo"


def test_con_deny_tools_sigue_SIN_NADA():
    """Input no confiable (§v3·P): la puerta de arriba no se toca — un worker sin confianza no gana una tool
    porque el de al lado la necesite."""
    import inspect
    src = inspect.getsource(CS)
    i = src.index("if spec.deny_tools:")
    assert "tools: list[str] = []" in src[i:i + 160]
