"""
CIERRE de iniciativa: que el contexto no se quede atrás del código (2026-08-14).

Petición del operador: *«añade al plan la actualización del contexto, la doc y los diagramas… debería haber
workflows para ayudar en esto»*. La deuda era medible: el log de alineación de contenido iba por la 2.88 y el motor
estaba en la 2.94 — **seis versiones de deriva**, con V2-092 y todo el bloque de latencia sin reflejar.

Un workflow que hay que acordarse de correr se olvida. Esto es la mitad AUTOMÁTICA: un guarda determinista de lo
que se puede comprobar sin salir del repo del motor.

Lo que comprueba:
  1. Toda iniciativa `V2-xxx` citada como decisión en `CLAUDE.md` tiene su fichero en `.meshkore/roadmap/`.
     (El fallo típico: se escribe la decisión, se olvida la iniciativa — o al revés.)
  2. Los ids no se repiten entre ficheros. Ya pasó: V2-090 y V2-091 estaban cogidos y el trabajo nuevo empezó
     numerado como V2-090, que además pisó por sed dos ficheros ajenos.
  3. El `id:` del frontmatter coincide con el nombre del fichero.
  4. Toda iniciativa `delivered` está citada en `CLAUDE.md`. Entregar sin dejar la decisión escrita es exactamente
     cómo se acumulan seis versiones de deriva.

Lo que NO puede comprobar desde aquí (y por qué): la alineación con `web/` y con el log de contenido vive en el
repo PRIVADO de la raíz, y este repo es PÚBLICO — un test de aquí no puede depender de un fichero que no viaja con
él. Esa mitad la cubre `.meshkore/docs/ops/zaelar-initiative-closure.md` en la raíz.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ENGINE = Path(__file__).resolve().parents[3]
ROADMAP = ENGINE / ".meshkore/roadmap/initiatives"
CLAUDE = ENGINE / "CLAUDE.md"

_ID_RE = re.compile(r"\bV2-(\d{3})\b")


# Anexos de una iniciativa, no iniciativas: `V2-046-PROMPT-encargo-…` es el encargo que acompaña a
# `V2-046-sistema-arena.md`. Comparten id a propósito.
_ANNEX = "-PROMPT-"


def _initiative_files() -> dict[str, Path]:
    out: dict[str, Path] = {}
    for f in sorted(ROADMAP.glob("V2-*.md")):
        if _ANNEX in f.name:
            continue
        m = _ID_RE.search(f.name)
        if m:
            out.setdefault(f"V2-{m.group(1)}", f)
    return out


# ── EL TRINQUETE ──────────────────────────────────────────────────────────────────────────────────────────────
# Al montar este guarda salieron 21 decisiones citadas en `CLAUDE.md` sin fichero de iniciativa. Es deuda vieja y
# real, de cuando la iniciativa no era parte del cierre. NO se inventan 21 iniciativas retroactivas: eso sería
# fabricar historia que nadie vivió, y una iniciativa escrita a posteriori sin la sesión delante no vale nada.
#
# Así que el guarda funciona como TRINQUETE: la deuda conocida se declara aquí, a la vista, y el test falla si
# alguien AÑADE una nueva. Cada vez que se documente una de estas de verdad, se borra de la lista y el listón sube.
# Un guarda que exige limpiar el pasado antes de proteger el futuro no se adopta nunca.
_DEUDA_SIN_INICIATIVA = {
    "V2-017", "V2-022", "V2-024", "V2-025", "V2-026", "V2-027", "V2-028", "V2-029", "V2-030", "V2-039",
    "V2-045", "V2-063", "V2-065", "V2-067", "V2-078", "V2-080", "V2-082", "V2-083", "V2-084", "V2-087",
    "V2-089",
}


def _frontmatter_id(p: Path) -> str:
    for line in p.read_text(encoding="utf-8").splitlines()[:12]:
        if line.startswith("id:"):
            return line.split(":", 1)[1].strip()
    return ""


def _status(p: Path) -> str:
    for line in p.read_text(encoding="utf-8").splitlines()[:12]:
        if line.startswith("status:"):
            return line.split(":", 1)[1].strip().lower()
    return ""


def test_hay_iniciativas():
    assert _initiative_files(), "no encuentro el roadmap: ¿cambió la ruta?"


def test_cada_id_esta_una_sola_vez():
    """Ya pasó y salió caro: V2-090/091 estaban cogidos, el trabajo nuevo se numeró V2-090 y un `sed` de
    renumerado pisó dos ficheros ajenos (la iniciativa de observabilidad y la de frontera pública)."""
    vistos: dict[str, list[str]] = {}
    for f in sorted(ROADMAP.glob("V2-*.md")):
        if _ANNEX in f.name:
            continue
        m = _ID_RE.search(f.name)
        if m:
            vistos.setdefault(f"V2-{m.group(1)}", []).append(f.name)
    repes = {k: v for k, v in vistos.items() if len(v) > 1}
    assert not repes, f"ids duplicados en el roadmap: {repes}"


def test_el_frontmatter_coincide_con_el_nombre_del_fichero():
    malos = []
    for iid, f in _initiative_files().items():
        got = _frontmatter_id(f)
        if got and got != iid:
            malos.append(f"{f.name}: id={got}")
    assert not malos, f"frontmatter descuadrado (rompe cualquier búsqueda por id): {malos}"


def test_toda_decision_citada_en_CLAUDE_tiene_su_iniciativa():
    """Se escribe la decisión en `CLAUDE.md` y se olvida el fichero — o al revés. Cualquiera de las dos mitades
    sola deja el contexto contando media historia."""
    body = CLAUDE.read_text(encoding="utf-8")
    files = _initiative_files()
    citados = {f"V2-{m}" for m in _ID_RE.findall(body)}
    faltan = sorted(i for i in citados if i not in files and i not in _DEUDA_SIN_INICIATIVA)
    assert not faltan, (
        f"CLAUDE.md cita {faltan} y no existe su iniciativa en .meshkore/roadmap/initiatives/. "
        f"Cerrar una iniciativa son las DOS mitades — o añádela, o (si es deuda vieja de verdad) declárala en "
        f"_DEUDA_SIN_INICIATIVA con un motivo.")


def test_la_deuda_no_crece_ni_se_queda_rancia():
    """El trinquete, por los dos lados: la lista de deuda no puede engordar, y si alguien documenta una de estas
    tiene que BORRARLA de aquí (si no, el guarda dejaría de vigilar un id que ya está cubierto)."""
    files = _initiative_files()
    ya_cubiertas = sorted(i for i in _DEUDA_SIN_INICIATIVA if i in files)
    assert not ya_cubiertas, (
        f"{ya_cubiertas} ya tienen iniciativa: quítalas de _DEUDA_SIN_INICIATIVA para que el guarda las vigile")
    assert len(_DEUDA_SIN_INICIATIVA) <= 21, "la deuda histórica solo puede BAJAR"


@pytest.mark.parametrize("iid", sorted(i for i, f in _initiative_files().items() if _status(f) == "delivered"))
def test_toda_iniciativa_entregada_esta_citada_en_CLAUDE(iid):
    """`delivered` sin cita en `CLAUDE.md` = trabajo hecho que el próximo agente no va a encontrar. Así se
    acumularon seis versiones de deriva."""
    body = CLAUDE.read_text(encoding="utf-8")
    assert iid in body, (
        f"{iid} está entregada y no se menciona en CLAUDE.md — añade su decisión clave o baja el status")
