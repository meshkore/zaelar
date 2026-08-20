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

⚠️ **`.meshkore/roadmap/` está GITIGNOREADO a propósito** (`.gitignore`: «roadmap/iniciativas (el futuro)»), así que
las iniciativas son LOCALES a la máquina del operador y no viajan con el repo público. Esto es, por tanto, un guarda
de HIGIENE LOCAL, no una puerta de CI: donde no hay roadmap, se salta entero en vez de fallar. La primera versión de
este fichero no lo hacía y se commiteó un test que reventaba en cualquier clon limpio — el mismo error que ya se
había cazado dos veces hoy (el arnés del lead-in sin event loop, y el `_DATA_DIR` inexistente del test de youtube):
**un test que solo se ha probado en una máquina no está probado.**
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
    # RECURSIVO: una iniciativa ARCHIVADA sigue existiendo. El 2026-08-20 se movieron 110 a
    # `initiatives/archive/` y este guarda —que solo miraba la raíz— pasó a decir que 55 decisiones citadas en
    # `CLAUDE.md` no tenían iniciativa. Lo que comprueba es que la decisión tiene su fichero, no dónde está
    # guardado; archivar no es borrar. Verificado sin ambigüedad: ningún id aparece en los dos sitios.
    for f in sorted(ROADMAP.rglob("V2-*.md")):
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


# El roadmap no viaja con el repo (ver la nota del docstring): sin él no hay nada que comprobar y saltar es la
# respuesta correcta — no fallar, y desde luego no «pasar» en silencio fingiendo que se verificó algo.
pytestmark = pytest.mark.skipif(
    not ROADMAP.is_dir() or not list(ROADMAP.glob("V2-*.md")),
    reason="`.meshkore/roadmap/` es local a la máquina del operador (gitignoreado): nada que verificar aquí")


def test_hay_iniciativas():
    assert _initiative_files(), "hay ficheros V2-*.md pero ninguno parseable: ¿cambió el formato del nombre?"


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


# ── la tarea de verificación se cuelga del CASO, no del arreglo (2026-08-20) ──────────────────────────────
#
# El arnés de casos de uso recoge la mitad de vuelta del contrato leyendo `T<n>-uc-<slug>-verify.md` con
# `status: next` y casando `<slug>` contra ids de ESCENARIO. Una tarea nombrada por el DEFECTO —
# «abrir-pagina», «sesion-acabada», «narrar-trabajo», «login-pendiente»— no resuelve, y entonces anuncia
# trabajo que nadie va a coger: el tablero dice que hay verificación pendiente y no la hay.
#
# Cometido CUATRO veces la misma noche (T428, T429, T435, T437). El arnés ya avisa, pero solo cuando alguien
# corre `--verify`; esto lo caza al cerrar, que es cuando se comete.
#
# Si un arreglo no tiene NINGÚN caso que lo ejercite, eso es un dato en sí mismo y hay que escribirlo — no
# inventarle un nombre de escenario.
TASKS = ENGINE / ".meshkore/modules/nucleo/tasks"


def _pending_verify_slugs() -> list[tuple[str, str]]:
    import re as _re

    out = []
    for f in sorted(TASKS.glob("T*-uc-*-verify.md")):
        try:
            if "status: next" not in f.read_text(encoding="utf-8", errors="replace"):
                continue
        except Exception:
            continue
        m = _re.match(r"T\d+-uc-(.+)-verify\.md$", f.name)
        if m:
            out.append((f.name, m.group(1)))
    return out


@pytest.mark.skipif(not TASKS.is_dir(), reason="sin tareas locales (roadmap gitignoreado)")
def test_toda_tarea_de_verificacion_pendiente_apunta_a_un_caso_real():
    try:
        import sys
        sys.path.insert(0, str(ENGINE))
        from tests.use_cases.e2e.agent import scenarios as _SC
        registry = _SC.registry()
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"no se puede leer el catálogo de escenarios: {e}")

    huerfanas = []
    for name, slug in _pending_verify_slugs():
        # SALIDA EXPLÍCITA. Hay defectos transversales cuyo re-test legítimo es la tanda entera y no un caso
        # (V2-133: «el progreso fabricado» apareció en 8 de 12). Forzarles un id de escenario falso sería peor
        # que el problema. Pero tiene que estar DICHO en la tarea, porque el daño no es el nombre: es que el
        # tablero anuncie una verificación que nadie va a recoger.
        try:
            # sin backticks: la salida se escribe en prosa y a veces con `--verify` en código
            _txt = (TASKS / name).read_text(encoding="utf-8", errors="replace").replace("`", "")
            if "NO la recoge --verify" in _txt:
                continue
        except Exception:
            pass
        if slug in registry or f"{slug}__es" in registry or slug.replace("-es", "__es") in registry \
                or slug.replace("-us", "__us") in registry:
            continue
        huerfanas.append(f"{name} (slug «{slug}»)")
    assert not huerfanas, (
        "tareas de verificación cuyo slug NO es un id de escenario, así que el arnés no las recogerá y "
        f"anuncian trabajo que nadie va a coger: {huerfanas}. La tarea se cuelga del CASO que ejercita el "
        "arreglo, no del nombre del arreglo. Si ningún caso lo ejercita —porque el defecto es transversal y su "
        "re-test es la tanda entera— escribe «NO la recoge --verify» en la tarea y explica cómo se re-prueba: "
        "es una salida legítima, pero tiene que estar dicha.")
