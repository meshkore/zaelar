"""File a failing use case as a MeshKore INITIATIVE + TASK — one workspace per use case.

Operator's rule (2026-08-18): *«Los fallos, en lugar de intentar arreglarlos, deberíamos documentarlos en el
sistema de tareas de MeshKore y crear una iniciativa para cada uno de los fallos… Sería una iniciativa por
caso de uso, una tarea en la que tú le vas a poner que tiene que revisar todo esto y que cuando termine te
genera una tarea para que tú vuelvas a probar. Y así utilizaremos cada una de las iniciativas como un
workspace solamente para trabajar cada uno de los use cases y corregirlos hasta el final.»*

So this module does NOT fix anything. It converts a run's evidence into a work order that the agent owning
the FlashBrain/frontend/worker code can pick up cold, and closes the loop by demanding a re-test task back.

Three design points that matter:

1. **ONE initiative per use case, reused across runs.** A re-test does not create a second initiative — it
   APPENDS a dated round to the existing one. That is what makes it a workspace ("corregirlos hasta el
   final") instead of a pile of duplicates. Found by glob on the `-uc-<slug>` infix, so the V2 number never
   has to be remembered.
2. **Numbering is read from disk, never assumed.** `V2-114` is currently double-booked by two other
   sessions and `test_roadmap_closure.py::test_cada_id_esta_una_sola_vez` is red because of it; allocating
   by "max + 1" over a fresh listing is the only safe way, and it must happen at write time (several
   sessions work this repo at once).
3. **`status:` is never `delivered`.** That value is load-bearing: the closure test forces any delivered
   initiative to be cited in `engine/CLAUDE.md`. A freshly filed bug is `open`.

⚠️ These files are LOCAL. `engine/.gitignore` excludes `.meshkore/roadmap/` and `.meshkore/modules/*/tasks/`
by the operator's own «ni nuestro pasado ni nuestro futuro se publican» rule (2026-08-14) — nothing here gets
committed or pushed, and whoever clones the public repo never sees it. That is also why full transcripts are
safe to embed here and NOT in the committed scoreboard: this is the diary, `STATUS.md` is the catalog.
"""
from __future__ import annotations

import datetime as _dt
import json
import re
import time
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[4]
INITIATIVES = ENGINE / ".meshkore" / "roadmap" / "initiatives"
MODULES = ENGINE / ".meshkore" / "modules"

# Task ids are a CLUSTER-WIDE sequence shared with the workspace-root repo (engine reached T143, the root's
# cloud tasks run T293-T308). Starting the floor above both avoids handing two different pieces of work the
# same id across repos.
_TASK_FLOOR = 309


def _slug(scenario_id: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", scenario_id.lower()).strip("-")


def _next_initiative_number() -> int:
    nums = {int(m.group(1)) for p in INITIATIVES.glob("V2-*.md")
            if (m := re.match(r"V2-(\d{3})\b", p.name))}
    return (max(nums) + 1) if nums else 1


def _next_task_number() -> int:
    nums = {_TASK_FLOOR - 1}
    for p in MODULES.glob("*/tasks/T*.md"):
        if m := re.match(r"T(\d+)\b", p.name):
            nums.add(int(m.group(1)))
    return max(nums) + 1


def _status_of(path: Path) -> str:
    try:
        m = re.search(r"^status:\s*(\S+)\s*$", path.read_text(encoding="utf-8")[:400], re.M)
        return m.group(1) if m else ""
    except Exception:
        return ""


def find_initiative(scenario_id: str, *, include_closed: bool = False) -> Path | None:
    """The OPEN initiative for a case, or None.

    A CLOSED one is skipped on purpose: under the two-state model (see `rotate_failure`) a case that failed a
    re-test gets a fresh initiative, and appending a new round to the closed predecessor would put live work
    back into a file whose whole point is that it is finished. Newest first, so a case that has rotated several
    times resolves to its current one.
    """
    hits = sorted(INITIATIVES.glob(f"V2-*-uc-{_slug(scenario_id)}.md"), reverse=True)
    if include_closed:
        return hits[0] if hits else None
    for h in hits:
        if _status_of(h) != "closed":
            return h
    return None


def initiative_state(scenario_id: str) -> str:
    """Which of the TWO states this case's initiative is in (operator's model, 2026-08-18).

    · `awaiting_fix` — it has a fix task describing the error, and the dev agent has not answered yet. This is
      what counts towards "the dev agent always has 5 in front of him".
    · `awaiting_retest` — a verify task says the fix is in and the harness should run the case again.
    · `` (empty) — no open initiative: either never failed, or its last one was closed.

    Deliberately derived from the FILES rather than a status field inside the initiative: the two agents write
    to different files at unpredictable times, and a field one of them forgets to flip would desynchronise the
    whole loop. The tasks ARE the state.
    """
    if not find_initiative(scenario_id):
        return ""
    slug = _slug(scenario_id)
    for p in MODULES.glob(f"*/tasks/T*-uc-{slug}-verify.md"):
        if re.search(r"^status:\s*next\s*$", p.read_text(encoding="utf-8")[:600], re.M):
            return "awaiting_retest"
    return "awaiting_fix"


def awaiting_fix_count() -> int:
    """How many cases are sitting in state 1 — real, un-answered work in front of the dev agent."""
    n = 0
    for p in INITIATIVES.glob("V2-*-uc-*.md"):
        if _status_of(p) == "closed":
            continue
        slug = re.match(r"V2-\d+-uc-(.+)\.md$", p.name)
        if not slug:
            continue
        pending_verify = any(
            re.search(r"^status:\s*next\s*$", t.read_text(encoding="utf-8")[:600], re.M)
            for t in MODULES.glob(f"*/tasks/T*-uc-{slug.group(1)}-verify.md"))
        if not pending_verify:
            n += 1
    return n


def close_initiative(path: Path, *, reason: str, successor: str = "") -> bool:
    """Mark an initiative CLOSED, with why and (if it rotated) what replaced it.

    `status: closed`, never `delivered`: `delivered` is the state that `test_roadmap_closure.py` requires to be
    cited in `engine/CLAUDE.md`, and a use-case round passing is not by itself a decision worth a line in the
    engine's context — the operator decides that, not the harness.
    """
    try:
        body = path.read_text(encoding="utf-8")
        body = re.sub(r"^status:\s*\S+\s*$", "status: closed", body, count=1, flags=re.M)
        stamp = time.strftime("%Y-%m-%d %H:%M", time.localtime())
        tail = [f"\n## CERRADA — {stamp}\n", reason.strip(), ""]
        if successor:
            tail.append(f"El trabajo CONTINÚA en **{successor}**: esta queda cerrada para que el estado de un "
                        f"caso se lea de un vistazo (una iniciativa = un error concreto con su tarea), en vez "
                        f"de un hilo de rondas donde hay que averiguar qué sigue vivo.\n")
        path.write_text(body + "\n".join(tail), encoding="utf-8")
        return True
    except Exception:
        return False


def _module_for(scenario_id: str, mech: dict) -> str:
    """Best guess at the owning module, used only for the task's directory/`category`. `nucleo` is the right
    default: nearly every use-case failure lands in the FlashBrain's routing or the worker dispatcher."""
    reg = (mech or {}).get("task_registry") or {}
    kinds = set(reg.get("distinct_kinds") or [])
    if kinds == {"code"}:
        return "widgets"
    return "nucleo"


# ── evidence rendering ────────────────────────────────────────────────────────────────────────────────────
def _evidence(result: dict, *, scenario, sandboxed: bool) -> str:
    run = result.get("run") or {}
    verdict = result.get("verdict") or {}
    mech = run.get("mechanism_report") or {}
    scores = verdict.get("scores") or {}
    reg = mech.get("task_registry") or {}

    lines = [
        f"- **Veredicto del juez**: overall **{verdict.get('overall')}**/5"
        + (f" · " + " · ".join(f"{k} {v}" for k, v in scores.items()) if scores else ""),
        f"- **Motor**: {'sandbox AISLADO (BD/puerto/workspace propios)' if sandboxed else 'motor VIVO del operador'}",
        f"- **Turnos usados**: {len(run.get('transcript') or []) // 2} de {scenario.turns}",
        f"- **Familias observadas**: {', '.join(mech.get('families_observed') or []) or '(ninguna)'}",
    ]
    missing = mech.get("missing_signals") or []
    lines.append(f"- **Señales que FALTARON**: {', '.join(missing) if missing else '(ninguna)'}")
    if reg:
        lines.append(f"- **Concurrencia REAL medida en vivo** (`/api/tasks`): máximo simultáneo "
                     f"**{reg.get('max_concurrent')}**, {reg.get('distinct_tasks_seen')} tareas distintas, "
                     f"kinds: {', '.join(reg.get('distinct_kinds') or []) or '—'}")
    nav = mech.get("navegador_task") or {}
    if nav:
        lines.append(f"- **Tarea de navegador**: status={nav.get('status')} url={nav.get('url', '')[:120]}")
        concl = (nav.get("results") or {}).get("conclusion") if isinstance(nav.get("results"), dict) else None
        if concl:
            lines.append(f"  - conclusión que dejó: `{str(concl)[:200]}`")

    out = ["### Evidencia medida", "", *lines, ""]

    # A CONFOUND, raised before any of the judge's reasoning, because it changes how that reasoning must be
    # read. If the search layer was dead during the round, "no buscó" / "afirmó datos sin evidencia" says
    # something about this machine, not about the agent — and a fixing agent that redesigns grounding off that
    # verdict would be rebuilding something that was never broken. The verdict is NOT rewritten (inventing
    # facts is still inventing facts); what changes is that the doubt is stated where it cannot be missed.
    sh = mech.get("search_health") or {}
    if sh.get("degraded"):
        why = ", ".join(f"{r} ×{n}" for r, n in (sh.get("reasons") or []))
        out += ["> ⚠️ **CONFOUND del entorno — la capa de BÚSQUEDA estaba degradada en esta ronda** "
                f"({why}; {sh.get('n_search_events')} eventos de búsqueda).",
                ">",
                "> Con la búsqueda caída, «no buscó» o «afirmó un dato sin evidencia» puede ser de la "
                "MÁQUINA y no del agente. Antes de rediseñar nada de grounding, **re-mide esta ronda con una "
                "capa de búsqueda sana** (una key de pago —Tavily/Brave/Perplexity— o esperar el reset de "
                "cuota del proveedor). Lo que SÍ sigue siendo válido de esta ronda: cualquier hallazgo sobre "
                "instrucciones ignoradas, mitades de la petición perdidas, confirmaciones inventadas o "
                "acciones irreversibles sin confirmar — nada de eso depende de que la búsqueda funcione.", ""]

    findings = verdict.get("findings") or []
    if findings:
        out += ["### Hallazgos del juez", ""]
        for f in findings:
            out.append(f"- **{f.get('gravedad', '?')}** · {f.get('turno', '?')} — {f.get('problema', '')}")
        out.append("")

    wd = run.get("watchdog_log") or []
    if wd:
        out += [f"### Intervenciones del watchdog en vivo ({len(wd)})", "",
                "El watchdog compara lo que zaelar DICE contra el mecanismo real, turno a turno. Cada línea "
                "es una discrepancia detectada mientras ocurría:", ""]
        for v in wd[:12]:
            out.append(f"- `{v.get('health')}/{v.get('action')}` — {v.get('reason', '')}")
        if len(wd) > 12:
            out.append(f"- …y {len(wd) - 12} más (ver el informe completo)")
        out.append("")

    improvements = verdict.get("improvements") or []
    if improvements:
        out += ["### Mejoras que propone el juez (punto de partida, no dogma)", ""]
        for i in improvements:
            out.append(f"- **{i.get('area', '?')}** — {i.get('cambio', '')} · _porque_: {i.get('porque', '')}")
        out.append("")

    transcript = run.get("transcript") or []
    if transcript:
        out += ["<details><summary>Transcript completo de la corrida</summary>", "", "```"]
        for t in transcript:
            out.append(f"{t.get('who', '?').upper():7} {t.get('text') or '(sin respuesta)'}")
        out += ["```", "", "</details>", ""]
    return "\n".join(out)


_HANDOFF = """\
> **HANDOFF al equipo que lleva el CÓDIGO del motor** (FlashBrain / dispatch / widgets / frontend). Esta
> iniciativa la abre el arnés de casos de uso (`tests/use_cases/`), que MIDE y NO ARREGLA — por decisión
> explícita del operador (2026-08-18): un fallo de caso de uso se documenta aquí con su evidencia y se
> corrige desde el dominio que lo posee, no a parches desde el test.
>
> **Este fichero es el WORKSPACE de este caso de uso.** No se abre otra iniciativa cuando se vuelva a
> probar: cada nueva corrida AÑADE una ronda fechada aquí abajo, hasta que el caso pase.
>
> **El contrato de vuelta**: cuando dejes el arreglo listo, crea una tarea de VERIFICACIÓN
> (`T<n>-uc-<caso>-verify.md`, `status: next`, `depends_on: [la tarea de arreglo]`, misma `initiative:`) y
> deja en ella qué cambiaste y qué esperas ver. Esa tarea es la señal para que el arnés vuelva a correr el
> caso; sin ella nadie sabe que toca re-probar.
"""

_REPRO = """\
## Cómo reproducirlo (aislado, sin tocar nada del operador)

```bash
cd engine
./.venv/bin/python -m tests.use_cases.e2e.agent.run --scenario {sid} --sandbox
```

`--sandbox` arranca un motor de usar y tirar con su propia BD, puerto, workspace y logs
(`tests/platform/sandbox_engine.py`), así que ni la memoria ni los widgets ni las tareas del operador se
tocan, y la corrida aparece como una instalación/`user_id` distinta en observabilidad. El informe completo
de la corrida queda en `tests/runs/use_cases/` (gitignored). El marcador durable de qué casos pasan está en
`tests/use_cases/STATUS.md`.

⚠️ No lances `make run` mientras haya un sandbox vivo: `scripts/run-livekit.sh` mata todo `python -m server`
por NOMBRE de proceso, no por puerto.
"""


def file_failure(result: dict, *, scenario, sandboxed: bool, force_new: bool = False) -> dict:
    """Create (or append a round to) the initiative for this scenario, plus a fix task the first time.

    Returns a dict describing what happened, for the runner to print. Fail-open: filing is bookkeeping, and
    a problem here must never take down a test batch that already produced a real verdict.
    """
    try:
        INITIATIVES.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y-%m-%d %H:%M", time.localtime())
        today = time.strftime("%Y-%m-%d", time.localtime())
        verdict = result.get("verdict") or {}
        mech = (result.get("run") or {}).get("mechanism_report") or {}
        evidence = _evidence(result, scenario=scenario, sandboxed=sandboxed)
        existing = None if force_new else find_initiative(scenario.id)

        if existing:
            body = existing.read_text(encoding="utf-8")
            rounds = len(re.findall(r"^## Ronda ", body, re.M)) + 1
            body += (f"\n\n## Ronda {rounds} — {stamp}\n\n"
                     f"Sigue FALLANDO (overall {verdict.get('overall')}/5). "
                     f"Veredicto: {verdict.get('veredicto', '')}\n\n{evidence}")
            existing.write_text(body, encoding="utf-8")
            return {"initiative": existing, "task": None, "round": rounds, "created": False}

        num = _next_initiative_number()
        path = INITIATIVES / f"V2-{num:03d}-uc-{_slug(scenario.id)}.md"
        # Title = a clean, stable summary, NOT a truncated verdict: the verdict is one round's opinion and
        # cutting it mid-word ("…que promete parale") makes a permanent filename-level label out of a
        # sentence fragment. The evolving assessment belongs in the rounds below, which is where it goes.
        scores = verdict.get("scores") or {}
        weak = sorted((v, k) for k, v in scores.items() if isinstance(v, (int, float)))[:2]
        weakest = ", ".join(k for _, k in weak)
        title = (f"Caso de uso «{scenario.id}» (tier {scenario.tier}) no pasa"
                 + (f" — flojea en {weakest}" if weakest else ""))
        module = _module_for(scenario.id, mech)
        tnum = _next_task_number()

        path.write_text(
            f"---\nid: V2-{num:03d}\n"
            f"title: {json.dumps(title, ensure_ascii=False)}\n"
            f"date: {today}\nstatus: open\n---\n\n"
            f"# Caso de uso `{scenario.id}` — tier {scenario.tier}, {scenario.locale}\n\n"
            f"{_HANDOFF}\n"
            f"## Qué pide el caso\n\n"
            f"El usuario (simulado por un modelo que imita a una persona real, con petición deliberadamente "
            f"incompleta) abre con:\n\n> {scenario.opening_line}\n\n"
            f"### Qué cuenta como éxito\n\n{scenario.success_checks}\n\n"
            f"{_REPRO.format(sid=scenario.id)}\n"
            f"## Ronda 1 — {stamp}\n\n"
            f"Veredicto del juez: **{verdict.get('veredicto', '')}**\n\n{evidence}\n"
            f"## Tarea de arreglo\n\n"
            f"`.meshkore/modules/{module}/tasks/T{tnum}-uc-{_slug(scenario.id)}-fix.md`\n",
            encoding="utf-8")

        tasks_dir = MODULES / module / "tasks"
        tasks_dir.mkdir(parents=True, exist_ok=True)
        task_path = tasks_dir / f"T{tnum}-uc-{_slug(scenario.id)}-fix.md"
        task_path.write_text(
            f"---\nid: T{tnum}\n"
            f"title: {json.dumps(f'Revisar y arreglar el caso de uso «{scenario.id}»', ensure_ascii=False)}\n"
            f"status: next\npriority: high\nowner: ricart\ncategory: {module}\n"
            f"initiative: V2-{num:03d}\ndepends_on: []\n"
            f"created: {today}\nupdated: {today}\n---\n\n"
            f"# T{tnum} — Arreglar el caso de uso `{scenario.id}`\n\n"
            f"## Qué hay que hacer\n\n"
            f"Leer la iniciativa **V2-{num:03d}** (`.meshkore/roadmap/initiatives/"
            f"V2-{num:03d}-uc-{_slug(scenario.id)}.md`): lleva la petición del usuario, qué cuenta como "
            f"éxito, la evidencia medida de cada corrida (veredicto del juez, informe de mecanismo, "
            f"intervenciones del watchdog y el transcript completo) y el comando exacto para reproducirlo "
            f"en un sandbox aislado.\n\n"
            f"Arreglar la causa en el dominio que la posee. El arnés de casos de uso NO parchea el motor: "
            f"mide. Si la causa resulta estar en el propio arnés, dilo en la iniciativa y arréglalo ahí.\n\n"
            f"## Contrato de cierre (esto es lo que cierra el bucle)\n\n"
            f"Al terminar, **crea una tarea de verificación** en este mismo módulo:\n\n"
            f"- fichero: `T<siguiente>-uc-{_slug(scenario.id)}-verify.md`\n"
            f"- frontmatter: `status: next`, `priority: high`, `owner: ricart`, "
            f"`category: {module}`, `initiative: V2-{num:03d}`, `depends_on: [T{tnum}]`\n"
            f"- cuerpo: qué cambiaste, en qué ficheros, y qué esperas ver en la próxima corrida\n\n"
            f"Esa tarea es la SEÑAL de que toca re-probar. El arnés busca tareas "
            f"`*-uc-*-verify.md` con `status: next` y vuelve a correr ese caso; la nueva corrida se añade "
            f"como una ronda más en V2-{num:03d}. Sin esa tarea, nadie sabe que el caso está listo para "
            f"re-probarse.\n\n"
            f"## No hagas\n\n"
            f"- No abras otra iniciativa para este caso: V2-{num:03d} ES el workspace de este caso de uso.\n"
            f"- No toques `.meshkore/roadmap/state.json` (artefacto del daemon compartido).\n"
            f"- No marques la iniciativa `status: delivered` sin citarla en `engine/CLAUDE.md`: hay un test "
            f"(`test_roadmap_closure.py`) que lo exige.\n",
            encoding="utf-8")
        return {"initiative": path, "task": task_path, "round": 1, "created": True}
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


def pending_verifications() -> list[dict]:
    """Verify tasks the fixing agent has left for us — the other half of the handoff contract.

    A task named `*-uc-<slug>-verify.md` with `status: next` means "I changed something, run this case
    again". Returns the scenario slug so a re-test batch can be assembled from it.
    """
    out = []
    for p in MODULES.glob("*/tasks/T*-uc-*-verify.md"):
        try:
            head = p.read_text(encoding="utf-8")[:600]
        except Exception:
            continue
        if not re.search(r"^status:\s*next\s*$", head, re.M):
            continue
        if m := re.match(r"T\d+-uc-(.+)-verify\.md$", p.name):
            out.append({"slug": m.group(1), "task": p})
    return out


def scenarios_awaiting_verification(registry: dict) -> list[dict]:
    """Resolve each pending verify task to the scenario id the harness can actually run.

    The task file carries a SLUG (`_slug(scenario.id)`, kebab-cased) because that is what makes a readable
    filename — so getting back to `three-tasks-at-once` or `quick-fact-opening-hours__es` means matching
    against the live registry rather than reversing the slug, which is lossy by construction (`__` collapses).
    An unresolvable slug is REPORTED, never skipped in silence: it means someone renamed a scenario out from
    under an open task, and swallowing that would leave the fixing agent waiting for a re-test that never runs.
    """
    by_slug = {_slug(sid): sid for sid in registry}
    out = []
    for pend in pending_verifications():
        out.append({"slug": pend["slug"], "task": pend["task"],
                    "scenario": by_slug.get(pend["slug"])})
    return out


def close_verification(task_path: Path, *, round_no: int | None = None) -> bool:
    """Mark a verify task done once its case has actually been re-run.

    Without this the task keeps matching `status: next` forever and every later `--verify` batch re-runs the
    same case — the loop would never converge. The note says which round holds the evidence so the fixing
    agent reads the outcome in the initiative, not here.
    """
    try:
        body = task_path.read_text(encoding="utf-8")
        body = re.sub(r"^status:\s*next\s*$", "status: done", body, count=1, flags=re.M)
        stamp = _dt.date.today().isoformat()
        body = re.sub(r"^updated:.*$", f"updated: {stamp}", body, count=1, flags=re.M)
        ronda = f" (ronda {round_no})" if round_no else ""
        body += (f"\n## Re-probado por el arnés — {stamp}\n\n"
                 f"El caso se volvió a correr en un sandbox aislado a raíz de esta tarea. El resultado"
                 f"{ronda} está en la iniciativa, con su transcript y su informe de mecanismo. Si sigue "
                 f"fallando, la iniciativa es el sitio donde continúa el trabajo — no hace falta una tarea "
                 f"nueva.\n")
        task_path.write_text(body, encoding="utf-8")
        return True
    except Exception:
        return False


# ── the CONTINUOUS loop (operator, 2026-08-18) ────────────────────────────────────────────────────────────
# «Cada iniciativa de use case solo tiene DOS estados: una tarea del error con lo que hay que arreglar, y una
# segunda tarea indicándote que ya puedes volver a probar. Si no ha funcionado, la cierras y creas una nueva
# con una tarea que indique cuál es el NUEVO error.»
#
# Why rotate instead of appending a round 3: a re-test that fails is not more evidence about the SAME error —
# the previous error was addressed, and what remains is a DIFFERENT one (measured, not assumed: V2-121's round
# 2 had all three of its original blockers genuinely fixed and failed for a fourth reason, in a rule one layer
# up). Piling that onto the same file makes the dev agent read three superseded diagnoses to find the live one.
# One initiative = one concrete error + its task, and its status readable at a glance.

def rotate_failure(result: dict, *, scenario, sandboxed: bool, previous: Path | None = None) -> dict:
    """Close the current initiative for this case and open a SUCCESSOR for the error that remains.

    Returns the same shape as `file_failure` plus `closed`, so a caller can report both halves. Fail-open: the
    verdict is already earned, and bookkeeping must never take down a batch.
    """
    try:
        prev = previous or find_initiative(scenario.id)
        created = file_failure(result, scenario=scenario, sandboxed=sandboxed, force_new=True)
        if created.get("error"):
            return created
        if prev is not None:
            verdict = (result.get("verdict") or {}).get("veredicto", "")
            close_initiative(
                prev,
                reason=("Se re-probó el caso tras el arreglo y **sigue fallando, por un motivo distinto**. Lo "
                        f"que midió esta última corrida: _{verdict[:300]}_"),
                successor=created["initiative"].name)
            created["closed"] = prev
        return created
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


def close_on_pass(scenario_id: str, *, verdict: str, overall) -> dict:
    """A case that PASSES its re-test: close its initiative, the work is done.

    Left deliberately narrow — it closes the workspace and says why, and does NOT touch the scoreboard (that is
    `status.py`'s job and already happened) nor mark anything `delivered` (see `close_initiative`).
    """
    path = find_initiative(scenario_id)
    if path is None:
        return {"closed": None}
    ok = close_initiative(path, reason=(
        f"Re-probado tras el arreglo y **PASA** (nota del juez **{overall}**/5, umbral 4). Veredicto: "
        f"_{verdict[:300]}_\n\nSi este caso vuelve a fallar en el futuro se abrirá una iniciativa NUEVA: esta "
        f"queda como el registro de un error concreto que se cerró, no como un hilo abierto indefinidamente."))
    return {"closed": path if ok else None}
