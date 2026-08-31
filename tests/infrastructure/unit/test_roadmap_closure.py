"""
Initiative CLOSURE: ensuring the context does not fall behind the code (2026-08-14).

Operator request: *“add updating the context, docs, and diagrams to the plan… there should be
workflows to help with this”*. The debt was measurable: the content-alignment log was at 2.88 and the engine
was at 2.94 — **six versions of drift**, with V2-092 and the entire latency block unreflected.

A workflow that someone has to remember to run gets forgotten. This is the AUTOMATIC half: a deterministic guard for
what can be checked without leaving the engine repo.

What it checks:
  1. Every `V2-xxx` initiative cited as a decision in `CLAUDE.md` has its file in `.meshkore/roadmap/`.
     (The typical failure: the decision is written down and the initiative is forgotten — or vice versa.)
  2. IDs are not repeated across files. It has happened before: V2-090 and V2-091 were taken, and the new work started
     numbered as V2-090, which also overwrote two unrelated files via sed.
  3. The `id:` in the frontmatter matches the filename.
  4. Every `delivered` initiative is cited in `CLAUDE.md`. Delivering without leaving the decision written down is
     exactly how six versions of drift accumulate.

What it CANNOT check from here (and why): alignment with `web/` and the content log lives in the
PRIVATE root repo, and this repo is PUBLIC — a test here cannot depend on a file that does not travel with
it. That half is covered by `.meshkore/docs/ops/zaelar-initiative-closure.md` in the root.

⚠️ **`.meshkore/roadmap/` is intentionally GITIGNORED** (`.gitignore`: “roadmap/iniciativas (el futuro)”), so
the initiatives are LOCAL to the operator’s machine and do not travel with the public repo. This is therefore a
LOCAL HYGIENE guard, not a CI gate: where there is no roadmap, it skips entirely instead of failing. The first version
of this file did not do that, and a test was committed that blew up in any clean clone — the same mistake that had
already been caught twice today (the lead-in harness without an event loop, and the nonexistent `_DATA_DIR` in the
YouTube test): **a test that has only been tested on one machine is not tested.**
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ENGINE = Path(__file__).resolve().parents[3]
ROADMAP = ENGINE / ".meshkore/roadmap/initiatives"
CLAUDE = ENGINE / "CLAUDE.md"

_ID_RE = re.compile(r"\bV2-(\d{3})\b")


# Initiative annexes, not initiatives: `V2-046-PROMPT-encargo-…` is the assignment accompanying
# `V2-046-sistema-arena.md`. They intentionally share an ID.
_ANNEX = "-PROMPT-"


def _initiative_files() -> dict[str, Path]:
    out: dict[str, Path] = {}
    # RECURSIVE: an ARCHIVED initiative still exists. On 2026-08-20, 110 were moved to
    # `initiatives/archive/`, and this guard — which only looked at the root — started saying that 55 decisions cited
    # in `CLAUDE.md` had no initiative. It checks that the decision has its file, not where it is
    # stored; archiving is not deletion. Verified unambiguously: no ID appears in both places.
    for f in sorted(ROADMAP.rglob("V2-*.md")):
        if _ANNEX in f.name:
            continue
        m = _ID_RE.search(f.name)
        if m:
            out.setdefault(f"V2-{m.group(1)}", f)
    return out


# ── THE RATchet ───────────────────────────────────────────────────────────────────────────────────────────────
# When this guard was added, 21 decisions cited in `CLAUDE.md` had no initiative file. This is old, real debt
# from when the initiative was not part of closure. We do NOT invent 21 retroactive initiatives: that would be
# fabricating history nobody lived, and a post hoc initiative written without the session in front of you is worthless.
#
# So the guard works as a RATCHET: known debt is declared here, in plain sight, and the test fails if
# someone ADDS a new one. Whenever one of these is properly documented, it is removed from the list and the bar rises.
# A guard that requires cleaning up the past before protecting the future is never adopted.
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


# The roadmap does not travel with the repo (see the docstring note): without it there is nothing to check, and skipping is
# the correct response — do not fail, and certainly do not silently “pass” while pretending something was verified.
pytestmark = pytest.mark.skipif(
    not ROADMAP.is_dir() or not list(ROADMAP.glob("V2-*.md")),
    reason="`.meshkore/roadmap/` es local a la máquina del operador (gitignoreado): nada que verificar aquí")


def test_hay_iniciativas():
    assert _initiative_files(), "hay ficheros V2-*.md pero ninguno parseable: ¿cambió el formato del nombre?"


def test_cada_id_esta_una_sola_vez():
    """It happened before and cost us: V2-090/091 were taken, the new work was numbered V2-090, and a `sed` renumbering
    overwrote two unrelated files (the observability initiative and the public-boundary initiative)."""
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
    """The decision is written in `CLAUDE.md` and the file is forgotten — or vice versa. Either half
    on its own leaves the context telling half a story."""
    body = CLAUDE.read_text(encoding="utf-8")
    files = _initiative_files()
    citados = {f"V2-{m}" for m in _ID_RE.findall(body)}
    faltan = sorted(i for i in citados if i not in files and i not in _DEUDA_SIN_INICIATIVA)
    assert not faltan, (
        f"CLAUDE.md cita {faltan} y no existe su iniciativa en .meshkore/roadmap/initiatives/. "
        f"Cerrar una iniciativa son las DOS mitades — o añádela, o (si es deuda vieja de verdad) declárala en "
        f"_DEUDA_SIN_INICIATIVA con un motivo.")


def test_la_deuda_no_crece_ni_se_queda_rancia():
    """The ratchet works both ways: the debt list cannot grow, and if someone documents one of these,
    they must DELETE it from here (otherwise the guard would stop watching an ID that is already covered)."""
    files = _initiative_files()
    ya_cubiertas = sorted(i for i in _DEUDA_SIN_INICIATIVA if i in files)
    assert not ya_cubiertas, (
        f"{ya_cubiertas} ya tienen iniciativa: quítalas de _DEUDA_SIN_INICIATIVA para que el guarda las vigile")
    assert len(_DEUDA_SIN_INICIATIVA) <= 21, "la deuda histórica solo puede BAJAR"


@pytest.mark.parametrize("iid", sorted(i for i, f in _initiative_files().items() if _status(f) == "delivered"))
def test_toda_iniciativa_entregada_esta_citada_en_CLAUDE(iid):
    """`delivered` without a citation in `CLAUDE.md` = completed work that the next agent will not find. That is how
    six versions of drift accumulated."""
    body = CLAUDE.read_text(encoding="utf-8")
    assert iid in body, (
        f"{iid} está entregada y no se menciona en CLAUDE.md — añade su decisión clave o baja el status")


# ── the verification task hangs off the CASE, not the fix (2026-08-20) ─────────────────────────────────────
#
# The use-case harness picks up the contract’s return half by reading `T<n>-uc-<slug>-verify.md` with
# `status: next` and matching `<slug>` against SCENARIO IDs. A task named after the DEFECT —
# “abrir-pagina”, “sesion-acabada”, “narrar-trabajo”, “login-pendiente” — does not resolve, and then announces
# work nobody will pick up: the board says verification is pending when it is not.
#
# Done FOUR times the same night (T428, T429, T435, T437). The harness already warns, but only when someone
# runs `--verify`; this catches it during closure, which is when the mistake is made.
#
# If a fix has NO case exercising it, that is itself useful information and must be written down — do not
# invent a scenario name for it.
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
        # EXPLICIT EXIT. Some cross-cutting defects are legitimately re-tested across the entire batch rather than in one case
        # (V2-133: “fabricated progress” appeared in 8 of 12). Forcing a fake scenario ID onto them would be worse
        # than the problem. But it must be STATED in the task, because the harm is not the name: it is that the
        # board announces verification nobody will pick up.
        try:
            # no backticks: the exit is written in prose and sometimes includes `--verify` as code
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
