"""A team profile's `refs:` are the context that agent starts with — and they had decayed.

Same shape as `test_context_points_at_real_docs.py`, one folder over. `.meshkore/team/*.md` carry a `refs:`
list in their front-matter: the documents that member reads before working. Nothing loads them at runtime in
this repo, so a renamed doc breaks nothing — the next session just opens a missing file and works without the
context the pointer existed to give.

Measured on the first run (2026-08-29): **12 dead paths across 8 of the 9 profiles**. They were written
against a `.meshkore/context/` and a `.meshkore/workflows/` layout that no longer exists, and had been dead
long enough that nobody could say when. Every profile except `ui-reviewer` was handing its agent at least one
path into thin air.

**Skips when the folder is absent**, and that is not laziness: `.meshkore/team/` is gitignored by the «neither
our past nor our future is published» rule, so on a fresh clone it legitimately does not exist — the same
exclusion the sibling guard already makes for `roadmap/` and `modules/*/tasks/`.
"""
import re
from pathlib import Path

import pytest

ENGINE = Path(__file__).resolve().parents[3]
TEAM = ENGINE / ".meshkore" / "team"

_REF = re.compile(r"^\s*-\s+(\S+)\s*$", re.M)


def _perfiles() -> list[Path]:
    return sorted(TEAM.glob("*.md")) if TEAM.is_dir() else []


def _refs(p: Path) -> list[str]:
    s = p.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---", s, re.S)
    if not m:
        return []
    # Only the list following `refs:` — the front matter contains other lists and other dashes.
    bloque = m.group(1).split("refs:", 1)
    if len(bloque) < 2:
        return []
    salida = []
    for ln in bloque[1].splitlines():
        r = _REF.match(ln)
        if r:
            salida.append(r.group(1))
        elif ln.strip() and not ln.startswith(" "):
            break                      # se acabó la lista: empieza otra clave del front-matter
    return salida


@pytest.mark.skipif(not TEAM.is_dir(), reason=".meshkore/team/ no viaja en el repo (gitignorado)")
@pytest.mark.parametrize("perfil", [p.name for p in _perfiles()])
def test_cada_ref_de_un_perfil_existe(perfil):
    p = TEAM / perfil
    muertas = [r for r in _refs(p) if not (ENGINE / r).exists()]
    assert not muertas, (
        f"«{perfil}» arranca a su agente con {muertas}, que no existe. Un puntero que no lleva a ninguna parte "
        f"es peor que no tenerlo: nadie falla, el agente simplemente trabaja sin ese contexto.")


@pytest.mark.skipif(not TEAM.is_dir(), reason=".meshkore/team/ no viaja en el repo (gitignorado)")
def test_hay_perfiles_que_comprobar():
    """Sensitivity: if the glob stopped finding them, the test above would pass empty and silently — the THREE
    ways for a test not to run, again."""
    assert len(_perfiles()) >= 5


@pytest.mark.skipif(not TEAM.is_dir(), reason=".meshkore/team/ no viaja en el repo (gitignorado)")
def test_el_de_casos_de_uso_existe_y_lleva_lo_que_hace_falta_para_arrancar():
    """The profile that allows the measurement to resume from an empty context. The pieces WITHOUT which
    that session cannot start are checked: the map, harness, stages, and marker."""
    p = TEAM / "use-case-tester.md"
    assert p.exists(), "sin este perfil, retomar la medición exige reconstruir el contexto a mano"
    cuerpo = p.read_text(encoding="utf-8")
    for pieza in ("tests/run_testmap.py", "tests.use_cases.lab", "tests.use_cases.e2e.agent.run",
                  "tests/use_cases/STATUS.md", "43921", "43922"):
        assert pieza in cuerpo, f"el perfil no dice «{pieza}», que hace falta para arrancar"


@pytest.mark.skipif(not TEAM.is_dir(), reason=".meshkore/team/ no viaja en el repo (gitignorado)")
@pytest.mark.parametrize("perfil", ["use-case-tester.md", "dev-main.md", "dev-memory.md", "dev-mobile.md"])
def test_los_dos_que_se_hablan_saben_POR_DONDE(perfil):
    """The tester measures and the developer fixes; they coordinate through a private cluster. If a profile does not say where
    its credentials are, that session falls back to copy-paste by the operator — exactly what the cluster
    exists to eliminate. The POINTER is checked, never a value."""
    cuerpo = (TEAM / perfil).read_text(encoding="utf-8")
    assert "cluster-use-cases.env" in cuerpo, f"«{perfil}» no dice dónde están las credenciales del cluster"
    for var in ("MESHKORE_UC_CLUSTER_ID", "MESHKORE_UC_TOKEN"):
        assert var in cuerpo, f"«{perfil}» no nombra {var}"
    assert (ENGINE / ".meshkore/credentials/cluster-use-cases.env").exists(), (
        "el fichero de credenciales que los perfiles citan no está en el store")


@pytest.mark.skipif(not TEAM.is_dir(), reason=".meshkore/team/ no viaja en el repo (gitignorado)")
def test_el_perfil_de_MEMORIA_dice_por_donde_se_empieza():
    """The profile that allows memory to resume from an empty context. The pieces WITHOUT which
    that session cannot start are checked: the module design, its territory, the operator's REAL database (which is only
    touched in a copy), the sandboxes with the turn's EVIDENCE —the only thing distinguishing «it did not reach it» from «it did not
    obey»— and the inherited backend trap, which makes cases that measure nothing pass green."""
    p = TEAM / "dev-memory.md"
    assert p.exists(), "sin este perfil, retomar la memoria exige reconstruir el contexto a mano"
    cuerpo = p.read_text(encoding="utf-8")
    for pieza in ("zaelar-memory.md", "memory/_data/zaelar.db", "sandbox.db", "events",
                  "ZAELAR_EMBED_BACKEND", "tests/run_testmap.py", "test_memory_owes_nucleo_nothing.py",
                  "mem_processor.py", "python -m tests run memory"):
        assert pieza in cuerpo, f"el perfil no dice «{pieza}», que hace falta para arrancar"
