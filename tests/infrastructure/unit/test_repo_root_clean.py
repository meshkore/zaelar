"""
LA RAÍZ DEL REPO NO GUARDA DATOS — este repo es PÚBLICO y por aquí se escapó información personal.

FUGA REAL (2026-08-12, encontrada por una sesión al revisar ficheros sueltos). `informe.json` no solo estaba sin
commitear: estaba **versionado**, dos veces (816efd7, 8a959b8), y la copia que quedaba en HEAD no era un ejemplo —
era el informe de vacaciones del operador con las fechas del viaje, el presupuesto y las **edades de sus hijos**.
En el repositorio público que cualquiera clona.

La causa es estructural, no un descuido: un Brain Worker escribe su entregable en un fichero de **ruta relativa de
su directorio de trabajo**, y ese directorio es hoy la raíz del engine (se lo pide `dispatch` explícitamente,
porque escribir fuera le pide una aprobación que en headless nadie va a dar). Nada lo ignoraba, así que cualquier
`git add -A` de cualquier agente se lo llevaba.

Ignorar los tres nombres de aquel run no cierra la clase: el contrato dice «`informe.json` a secas» como EJEMPLO,
y el worker siguiente puede llamarlo como quiera. Este test es el guarda que sí cierra la clase — comprueba lo
único que importa de verdad: **que en la raíz no acabe versionado nada que no sea código o configuración del
proyecto**, se llame como se llame y tenga la extensión que tenga.

Cuando falle, la pregunta NO es «añado esto a la lista». Es: ¿esto es del proyecto (→ añádelo a `ALLOWED`, con un
commit que lo justifique) o es un artefacto de trabajo (→ va a `.gitignore` o a `TMP/`, nunca al repo)?
"""
from __future__ import annotations

import subprocess
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[3]

# Lo que la raíz del engine tiene derecho a versionar: entrada al proyecto, empaquetado y arranque. Nada de datos.
ALLOWED = {
    ".dockerignore", ".gitignore", "AGENTS.md", "CLAUDE.md", "Dockerfile", "Makefile", "README.md",
    "conftest.py", "fly.accounts.toml", "fly.toml", "requirements.txt", "version.py", "zaelar", "zaelar.ps1",
}


def _tracked_root_files() -> set[str]:
    out = subprocess.run(["git", "ls-files"], cwd=ENGINE, capture_output=True, text=True, check=True).stdout
    return {line for line in out.splitlines() if line and "/" not in line}


def test_no_data_file_is_versioned_at_the_repo_root():
    extra = _tracked_root_files() - ALLOWED
    assert not extra, (
        "hay ficheros versionados en la raíz que no son del proyecto: " + ", ".join(sorted(extra))
        + ". Por aquí se colaron datos personales del operador a un repo PÚBLICO. Si es del proyecto, añádelo a "
          "ALLOWED en este test; si es un artefacto de trabajo, a .gitignore o a TMP/.")


def test_the_workers_draft_names_are_ignored():
    """Los nombres que el contrato de `dispatch` sugiere al worker tienen que estar ignorados HOY, sin depender de
    que alguien se acuerde luego."""
    for name in ("informe.json", "fuentes.json", "resultados.json", "cualquier-cosa.json"):
        r = subprocess.run(["git", "check-ignore", "-q", name], cwd=ENGINE)
        assert r.returncode == 0, f"«{name}» en la raíz NO está ignorado — el próximo `git add -A` lo versiona"


def test_a_real_source_file_is_still_versionable():
    """El patrón no puede ser tan amplio que impida versionar código: si `.gitignore` empezara a tapar fuentes,
    este guarda se convertiría en el problema."""
    for name in ("version.py", "conftest.py", "Makefile"):
        r = subprocess.run(["git", "check-ignore", "-q", name], cwd=ENGINE)
        assert r.returncode != 0, f"«{name}» está ignorado y es del proyecto"
