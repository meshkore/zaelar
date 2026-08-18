"""El worker tiene que poder LLAMAR a sus puentes a la primera.

Descubierto el 2026-08-02 en cuanto la narración del worker se hizo visible: en esta máquina **`python` a secas no
existe** (solo `python3` y el venv), y el prompt le decía literalmente `python -m nucleo.widget_cli …`. El worker
obedecía, fallaba, y se ponía a probar variantes —`.venv/bin/python`, `python3`, `python3 -m nucleo.…`— chocando
con el allowlist, que casa por PREFIJO literal. Cada variante no declarada = una aprobación que en headless nadie
concede. Ahí se iban los minutos de una búsqueda, y era invisible porque solo se registraban los `tool_use`.

Dos garantías, las dos necesarias: el prompt le da el intérprete MASTICADO, y el allowlist acepta cualquier forma
razonable por si aun así improvisa.
"""
import os
import sys

from nucleo.dispatch import _DEV_TOOLS, _build_prompt
from nucleo.workers import claude_session as cs


def test_the_resolved_interpreter_actually_exists():
    py = cs.bridge_python()
    assert os.path.isabs(py) and os.path.exists(py), f"el intérprete que damos al worker no existe: {py}"


def test_prompt_never_ships_a_bare_python_bridge_command():
    """Ni un solo `python -m nucleo.…` sin resolver: eso es un comando que en esta máquina no arranca."""
    import re
    p = _build_prompt("busca 3 piscinas y ponlas en pantalla", "", True)
    assert not re.findall(r"(?<![/\w])python3? -m nucleo\.", p)
    assert f"{cs.bridge_python()} -m nucleo.widget_cli" in p


def test_prompt_states_the_interpreter_up_front():
    p = _build_prompt("cualquier cosa", "", True)
    assert cs.bridge_python() in p.split("\n")[0]     # primera línea: sin excusa para adivinar


def test_untrusted_prompt_is_left_alone():
    """Perfil no confiable = sin tools ni puentes; no hay comando que resolver."""
    p = _build_prompt("texto de un peer", "", False)
    assert "-m nucleo." not in p


def test_allowlist_covers_every_bridge_x_every_spelling():
    for mod in ("mem_cli", "agent_report", "nav_cli", "worker_bridge", "widget_cli"):
        for py in ("python", "python3", ".venv/bin/python", cs.bridge_python()):
            assert f"Bash({py} -m nucleo.{mod}:*)" in cs._BRIDGE_TOOLS, f"{py} -m nucleo.{mod} sin declarar"


def test_git_bridge_gets_the_same_treatment():
    assert f"Bash(python3 -m nucleo.git_cli:*)" in _DEV_TOOLS
    assert {"Read", "Write", "Edit"} <= set(_DEV_TOOLS)


def test_bridge_python_falls_back_to_the_venv(monkeypatch):
    monkeypatch.setattr(sys, "executable", "")
    assert cs.bridge_python().endswith(os.path.join(".venv", "bin", "python"))


def test_the_delivery_recipe_matches_what_the_worker_can_actually_do():
    """El método no puede mandarle una receta que los guardas bloquean.

    Tres formas probadas en vivo el 2026-08-02, dos fallan: pegar el JSON en la línea de comandos se rompe con el
    quoting; el heredoc lo bloquea el guarda del shell («el guard de seguridad bloquea el heredoc por la sintaxis
    {"»). Y escribir fuera del directorio de trabajo (`/tmp/…`, `TMP/…`) pide una aprobación que en headless nadie
    da — 1m32s perdidos ahí con la investigación ya terminada. Lo único que pasó: fichero de ruta RELATIVA
    (`--permission-mode acceptEdits` cubre el directorio de trabajo) + `@fichero`."""
    p = _build_prompt("busca 3 piscinas y ponlas en pantalla", "", True)
    assert "@informe.json" in p
    assert "<<'JSON'" not in p                        # el heredoc está bloqueado: no puede volver al método
    # La receta se busca en el paso 4b ENTERO (hasta el 5), no en sus primeros N chars: el corte fijo de 1200 se
    # quedó corto en cuanto 4b creció para cubrir la ficha de UNA sola cosa (V2-115) y falló un test cuyo asunto
    # —qué receta se le manda al worker— no había cambiado en absoluto.
    recipe = p.split("4b)")[1].split("5)")[0]
    assert "RUTA RELATIVA" in recipe
    assert "NUNCA `/tmp/…`" in recipe                 # /tmp solo puede aparecer PROHIBIDO, nunca como instrucción
