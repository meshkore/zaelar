"""The architecture ratchet — frozen on 2026-08-23, the day the audit measured where complexity actually lives.

Every number below is a MEASUREMENT, not a wish: the audit (over `485c283` + the in-flight work that landed with
`2cb5739`/`c3110f8`) found 70k LOC of engine Python whose complexity is not spread but CONCENTRATED — four god
files, two of them holding the SAME turn implemented twice (`_run_inner` = 2,603 lines in one function,
`run_turn` = 1,051), stitched together by 21 literal «impl PARALELA — cablear en AMBOS» markers and by hundreds
of function-local imports that exist to paper over import cycles.

This file is the F0 of the refactor plan: it does not fix any of that. It freezes it, so it can only SHRINK.
Same mechanism as `test_roadmap_closure`'s declared debt: the values are edited DOWNWARD when a file is split
(that edit is the celebration), and never upward — growth in a listed file means EXTRACT, not raise the ceiling.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ENGINE)) if str(ENGINE) not in sys.path else None


def _loc(p: Path) -> int:
    return p.read_text().count("\n") + 1


def _lazy_imports(p: Path) -> int:
    """Imports INSIDE functions — each one is an import cycle papered over, i.e. hidden coupling."""
    n = 0
    for node in ast.walk(ast.parse(p.read_text())):
        if isinstance(node, (ast.Import, ast.ImportFrom)) and node.col_offset > 0:
            n += 1
    return n


# ── the frozen table: {file: (max LOC, max lazy imports)} ────────────────────────────────────────────────────
#
# ⚠️ A ceiling WENT UP on 2026-08-23, the ratchet's second day of life, and it is worth recording because it is
# the proxy failing rather than the rule yielding: `owner.py` and `probe.py` each gained ONE line—the `import` of
# helper `nucleo.errors.brief`—when 10 and 1 copies, respectively, were removed from a language that blew up on
# exceptions without messages (node 7.24). LOC measures size, not complexity, and measured it backwards here. The
# increase is auditable: +1 line, −11 fragile copies. If someone invokes this precedent without being able to say
# WHAT duplication they removed and HOW MANY copies, they are raising the ceiling, which is exactly what this table
# exists to prevent.
# Measured 2026-08-23. Only ever edit DOWNWARD. If a change you are making pushes a file over its ceiling, the
# ratchet is telling you to extract a module — which is the entire point of the audit this was born from.
#
# ── 2026-08-24: THREE ceilings GO DOWN, and it is worth saying why they went up first ───────────────────────
# The ratchet had been red since the night of the 23rd and I broke it, in three consecutive commits (`41355d9`,
# `195a77a`, `58aba18`)—and did not notice because I ran the suites I thought were affected (`agent_headless`,
# `browser`, `use_cases`), while this guard lives in `infrastructure`. Separate lesson from the fix: someone who
# runs only their neighborhood does not see a SHARED ratchet.
#
# The temptation was to invoke the `owner.py`/`probe.py` precedent above, but that is not allowed: it requires being
# able to say WHAT duplication was removed and HOW MANY copies, and I had removed none—I had only written the
# evidence for three fixes, which this repo deliberately preserves and which LOC counts as though it were
# complexity. So extract it, which is what the table requires:
#
#   nucleo/flash/prompt.py     1104 → 843   the BROWSER block (5 facets + 3 helpers)       → flash/live_blocks.py
#   nucleo/dispatch.py         2045 → 1910  the SHEET as the progress surface             → nucleo/sheets.py
#
# ── 2026-08-24, later: 1910 → 1879 ─────────────────────────────────────────────────────────────────────────
# `record_phase` goes with the sheet (V2-281). It is the same concern—what the PROCESS tab renders—and its body
# is pure over the record, so `dispatch` is left only to resolve it, which is all it has. It is extracted instead
# of raising the ceiling by ONE line (a new field in the browser tab): shaving comments to make a number fit is
# exactly the instinct this table exists to correct.
#   nucleo/workers/session.py   879 → 825   the two failure-text constructors                 → workers/handoff.py
#
# ── 2026-08-24, V2-287: 1172 → 1062 ────────────────────────────────────────────────────────────────────────
# `widgets/results/data.py` exceeded the ceiling by TWENTY lines when a fact was added to the prompt digest (that
# the row carries its link), with its evidence behind it. It is extracted instead of raising the ceiling, and the
# boundary was clear: the digest is a PURE function of a sheet dict—it reads neither the store nor writes anything—
# so it moves in full to `widgets/results/digest.py`, while `data.py` keeps `prompt_digest()`, the only function
# that needs to know WHICH sheets exist and the name that `widgets/refs.py` looks up by convention.
#   widgets/results/data.py    1172 → 1061  the prompt digest (header + sheet)              → widgets/results/digest.py
#   widgets/results/data.py    1094 → 1030  the LIVE process (narrative + numbers)         → widgets/results/live.py
#   nucleo/dispatch.py         1768 → 1759  this engine's address (pure function)          → nucleo/engine_url.py
#
# ── 2026-08-24, V2-289: 1879 → 1763 ────────────────────────────────────────────────────────────────────────
# `dispatch.py` exceeded the ceiling by FIVE lines when resolving whether the driving model reads images. It is
# extracted, and the boundary had long been clear: the CLASSIFICATION of the errand (`_classify_kind` + its five
# regexes + the label) is a PURE function over the request TEXT—it does not inspect the session record, touch the
# pool, or write.
#   nucleo/dispatch.py         1879 → 1762  what KIND of errand this is                → nucleo/errand_kind.py
#
# All three were boundaries that were ALREADY drawn—the browser block had its own `try`, the sheet section its
# banner since V2-227, and the two text functions are pure over the record—and in two of the three there was also
# a layer asking its neighbor for what is not its responsibility (`widgets/results/data.py` importing from
# `dispatch` what its box is called). `sheets.py` is born SHEET: it receives the record as an argument instead of
# importing it, which is the cycle V2-112 already paid for.
_CEILINGS: dict[str, tuple[int, int]] = {
    # nucleo.py 3461→3475: 246007a («enséñamelo» resolves to the ERRAND's sheet — round 24 opened the bare
    # box beside a 20-row delivery) net of dde26a2's shared confirm gate (−9). F1/F2 still own this file's debt.
    # …and 3475→3493 on 2026-08-28 (V2-457: `show_images`), raised WITH the audit the rule requires and after
    # after extracting what could be extracted, rather than instead of it. What remains is 18 net lines of WIRING
    # for a new capability in the voice channel: the tool branch (7) lives inside the `_on_tool_call` closure,
    # which shares 13 turn-state dicts through the closure—moving it is the `TurnState` redesign that V2-112 left
    # written and DELIBERATELY deferred to its own session; the declaration, fallback-gate signal, and post-stream
    # block are one line each and do not form a module. What COULD be extracted was extracted:
    # `image_turn.voice_turn()` took the body of the post-stream branch AND language resolution,
    # so this file also gains no lazy import (155 remains 155). The DEBT remains and is the same: F1/F2 of V2-112.
    # A ceiling that cannot be paid without touching the voice hot path at three in the morning is raised with its
    # name above it, which is what this table has been doing since 24-08.
    # 2026-09-02: 3493 → 3470, 155 → 145. First cut of the god file, and deliberately the SMALL one: the
    # pending-confirmation pair (`_similar_pending`, `_human_confirm_question`) → `confirm_gate.py`. It was
    # chosen because it is the only pair in the file that needs NOTHING from it — verified, not assumed —
    # so the move carries no risk of a cycle. The 2713-line `NucleoLLMStream` class is still the real debt.

# ── 2026-09-02, V2-556: THREE ceilings go down, and the biggest drop is a CATALOG that was never logic ────────
# The listing fast pass landed on three files that sat AT their ceiling (3469/3470, 1162/1163, 928/930), so the
# ratchet went red the moment the feature existed — and it stayed red for a day because I ran the suites of my
# neighbourhood (`agent-headless`, `browser`) and this guard lives in `infrastructure`. That is the SAME lesson
# already written twenty lines above, paid a second time. The extractions:
#
#   nucleo/flash/router.py         964 → 326   the TOOL CATALOG (pure data)        → nucleo/flash/router_catalog.py
#   voice/…/providers/nucleo.py   3495 → 3327  the widget-intent readers            → providers/widget_intent.py
#   nucleo/flash/probe.py         1180 → 1147  `_running_goals` → show_target.py; the window write → dialog.py
#
# And three copies of V2-556's own shape collapsed into `listing_turn.py`: the tool DEFINITION (the router only
# places it now), `request_from` (the router and both channels built the same dict), and `voice_turn` (fast pass
# → face → stream, which was written twice — the wording had already drifted apart by one paragraph).
    # 2026-09-03 — V2-567's show-vs-close guard crossed the ceiling by 8; paid by extracting the
    # accumulator NOTICES (plan + spoken drop + nudge, a mouth-only concern) to providers/acc_notices.py,
    # 3335→3244. Aliases keep the historical names; `_spawn` stays with the provider.
    # 2026-09-03, V2-572 — the bare-ack repair block paid by extracting the ACTION-MAP fast lane (a cohesive
    # concern since V2-539: lookup, execute, bookkeeping — and now the spoken ack) → providers/fast_lane.py,
    # 3244→3217. Probe paid the same bill by folding its stream-collect shape into flash/second_pass.py.
    "voice/engine/llm/providers/nucleo.py": (3218, 129),
    # 2026-08-24 — raised WITH the audit the rule demands, after sitting red for hours with nobody's name on it.
    # dispatch.py 1759→1851: 41355d9 (a relay inherits its sheet, +31), 7e3c144 (live errand absorbs non-errands),
    # 1a98f80 (the tab says which sheet it belongs to), 6e3d4d4 (the last sweep tells the conversation, +11).
    # All behaviour fixes measured on live rounds; none extractable alone. The DEBT stands: dispatch is F3's
    # remaining seam list and these lines are candidates when its `_SESSIONS` design question is answered.
    # …and again on 25-08 (the walk's fix sprint): 1851→1927 (e8b0de8 parallel brief, 73daeac dead-worker
    # face, 25d7ebd session-window relay). The treadmill IS the finding: F3's split is the fix, not the table.
    # …and 1927→1960 within the same day (e315b89 V2-314 exhausted-window guard + walk fixes). Same audit.
    # 2026-08-26 — the treadmill PAID one instalment instead of raising again: V2-342 added `_leave_resume`
    # (a cancelled errand keeps its resumable trace) and crossed the ceiling by 23, and the web-continuity
    # subsystem (V2-049 dict + persist/restore/goal_key/entry/leave/find) was a cohesive concern all along →
    # extracted to `nucleo/workers/resume.py`, dispatch 1983→1859. Aliases keep the historical names alive.
    # 2026-09-03 — the treadmill PAID a second instalment instead of raising again: V2-566 added the sheet to
    # the ended-session snapshot and the follow-up that inherits it, crossing the ceiling by 27, and the
    # ENDING as a fact (V2-198/199/222/224/238: the two state enums, `_ENDED_SESSIONS` and its four
    # operations) was a cohesive concern all along → extracted to `nucleo/workers/ended.py`, dispatch
    # 1892→1770. Aliases keep the historical names alive, as `resume.py` did.
    "nucleo/dispatch.py": (1770, 57),
    # owner.py 1580→1706 · lazy 43→44: 3884cb8 (banner sweep per NAVIGATION, look 11,2 s→0,42 s), f25e2a3
    # (`visit` — read a card in its own tab), a1cb398 (consent per DOMAIN, submit 25 s→3,84 s). Three measured
    # perf/feature fixes from the same tuning day. owner.py remains F6's split candidate (by resource).
    # 2026-08-27 — owner 1706→1725: 0bee0d8 V2-358 (the tab listens to main-frame document responses and
    # hands last_status to every capture — the wall signal no needle can miss, measured on coches.net's two
    # bodies for the same 403). Inherent to the tab object (self/page); the WALL classification itself was
    # extracted instead (tasks.py → walls.py, 904→774, staying out of the table).
    "widgets/navegador/owner.py": (1725, 44),
    # 2026-09-02: 1374 → 789, and 15 → 7 lazy imports. The ratchet asked for an extraction and got two:
    # `reminder_guards.py` (the 26 guards for a PROMISED dated notice — a closed set that nothing left
    # behind uses) and `text_norm.py` (the three text helpers BOTH halves need, which is why neither could
    # keep them without importing the other back). Everything moved byte for byte and is re-exported, so no
    # call site changed. The two new files are deliberately NOT listed: a ceiling is earned by a file that
    # has already grown too big, not handed to every module at birth.
    # 2026-09-03, same pass (V2-567): router_guards paid by extracting the V2-210 answer-source family to
    # answer_guards.py (811→762); probe paid by moving alias classification to show_target.py beside its
    # siblings (1152→1144). Both files sat EXACTLY at their ceilings — the ratchet working as designed.
    "nucleo/flash/router_guards.py": (763, 7),
    # probe.py 1168→1176 net: V2-300's grace/latency growth minus F1's confirm-gate retirement (−2 mirrors,
    # 2026-08-24); →1214/89 on 25-08 (49a7c81, 25d7ebd, 73daeac — the walk's fixes land in the same god
    # files they measure). Still F2's split target (`run_turn` into named phases).
    # probe.py 1214→1226 on 2026-08-28 (V2-457), same audit and for the same reason: this channel is the
    # PARALLEL implementation of the voice provider, so a new capability is wired into BOTH or they diverge—
    # something this codebase has already paid for four times (V2-121, V2-176, V2-380, V2-383). They are three
    # branches of an `elif` chain (classify, execute, speak) that do not form a module: shared code already lives
    # in `image_turn`.
    # 2026-09-02: 1226 → 1163. `run_turn` alone was 1136 of 1248 lines, so the only honest extraction was a
    # slice of it: the three SCHEDULING backstops (promise→tag, execute the cron tags, write the commitment)
    # → `probe_scheduling.py`. A closed unit over five of run_turn's locals; moved byte for byte.
    "nucleo/flash/probe.py": (1145, 74),
    "widgets/results/data.py": (1030, 5),
    "memory/api.py": (1076, 19),
    "nucleo/flash/prompt.py": (854, 30),   # 25-08: 41be5cb V2-311 step 3 · 26-08: +3 V2-342 (the COMPLAINT
    # branch in the worker directive: inject before killing—directive prose, nothing extractable)
    "nucleo/workers/session.py": (825, 19),
    "nucleo/flash/router.py": (327, 1),
}

#: No god file may be BORN either: any engine module NOT in the table stays under this. The largest unlisted
#: file today is `connectors/meshkore/bridge.py` at 863, so 900 bounds the whole rest of the tree with margin.
_UNLISTED_MAX = 900

#: The mirror annotation: the turn's decisions copied between the voice provider and probe, each marked «this
#: block lives in both, keep them in sync». 21 on the day of the audit, 18 after F1's first extraction (the
#: vault gate). Each retirement lowers this number; at 0 a NEW mirror is a red test — two channels needing the
#: same rule means extract first.
#:
#: ⚠️ The marker is a CODE ANNOTATION, not narration vocabulary, and the ratchet counts the literal string —
#: so prose ABOUT the pattern counts as the pattern. Caught the first time it mattered: the docstrings written
#: to explain a retired mirror pushed the count from 19 back to 22, i.e. the celebration read as a regression.
#: When you retire one, describe it without quoting the marker.
_MIRROR_MAX = 15

_SKIP_DIRS = {".venv", "tests", "node_modules", "__pycache__", ".git", "frontend/vendor"}


def _engine_py_files():
    for p in ENGINE.rglob("*.py"):
        rel = p.relative_to(ENGINE).as_posix()
        if any(part in _SKIP_DIRS for part in rel.split("/")):
            continue
        yield rel, p


def test_a_listed_file_only_shrinks():
    over = []
    for rel, (max_loc, _max_lazy) in _CEILINGS.items():
        p = ENGINE / rel
        assert p.exists(), f"{rel} está en la tabla y no en el disco: si se partió, baja su techo o retíralo"
        n = _loc(p)
        if n > max_loc:
            over.append(f"{rel}: {n} > {max_loc}")
    assert not over, ("un fichero-dios ha CRECIDO — el trinquete pide extraer un módulo, no subir el techo:\n  "
                      + "\n  ".join(over))


def test_no_god_file_is_born_outside_the_table():
    born = []
    for rel, p in _engine_py_files():
        if rel in _CEILINGS:
            continue
        n = _loc(p)
        if n > _UNLISTED_MAX:
            born.append(f"{rel}: {n} LOC")
    assert not born, ("un fichero nuevo nació gigante — trocéalo antes de que herede la tabla:\n  "
                      + "\n  ".join(born))


def test_hidden_coupling_only_goes_down():
    over = []
    for rel, (_max_loc, max_lazy) in _CEILINGS.items():
        n = _lazy_imports(ENGINE / rel)
        if n > max_lazy:
            over.append(f"{rel}: {n} imports lazy > {max_lazy}")
    assert not over, ("más imports dentro de funciones = más ciclos tapados. Se arregla EXTRAYENDO, no importando "
                      "más tarde:\n  " + "\n  ".join(over))


def test_no_new_parallel_mirror():
    hits = []
    for rel, p in _engine_py_files():
        try:
            n = p.read_text().count("impl PARALELA")
        except Exception:
            continue
        if n:
            hits.append((rel, n))
    total = sum(n for _r, n in hits)
    assert total <= _MIRROR_MAX, (
        f"{total} marcas de «impl PARALELA» (techo {_MIRROR_MAX}). Un espejo NUEVO está vetado: si dos canales "
        f"necesitan la misma decisión, se extrae a un módulo y ambos lo importan. Dónde están: {hits}")


def test_every_testmap_node_id_is_unique():
    """A node's id is how it is referenced from CLAUDE.md and the initiatives. Two nodes with the same id are two
    things claiming to be the same: on 2026-08-23 there were FIVE such pairs (2.14, 2.15, 7.10, 7.11, 7.13), and
    a sixth nearly entered without anyone noticing. The five least-cited ones were renumbered."""
    from tests.platform.catalog import DOMAINS

    seen: dict[str, str] = {}
    dups = []
    for d in DOMAINS:
        for node in d.get("nodes", []):
            nid = node["id"]
            if nid in seen:
                dups.append(f"{nid}: «{seen[nid][:50]}» vs «{node['title'][:50]}»")
            seen[nid] = node["title"]
    assert not dups, "ids de nodo duplicados en el testmap:\n  " + "\n  ".join(dups)


def test_process_identity_has_ONE_owner():
    """F5. Three incidents in 48h had the same shape — a per-instance counter read as global: `escalate._seq`
    keyed the sheet and a restart wiped the previous session's results (32c7dc6); the relay booleans lived on a
    record every relay renews, so six workers ran one errand (0399a1d). The fixes landed where they hurt; this
    closes the CLASS: a module-level sequence counter born anywhere but `nucleo/runtime_ids.py` goes red with a
    name. `itertools.count()` at module level counts too — it is the same pattern wearing a nicer coat."""
    import re
    pat = re.compile(r"^_?[a-z_]*(?:seq|counter)[a-z_]*\s*=\s*(?:0|itertools\.count)", re.M)
    born = []
    for rel, p in _engine_py_files():
        if rel == "nucleo/runtime_ids.py":
            continue
        try:
            src = p.read_text()
        except Exception:
            continue
        for m in pat.finditer(src):
            line = src[:m.start()].count("\n") + 1
            born.append(f"{rel}:{line}: {m.group(0).strip()}")
    assert not born, ("un contador de módulo nació fuera del dueño — usa runtime_ids.next_seq(name), y si el id "
                      "debe sobrevivir a un reinicio, compón boot_id():\n  " + "\n  ".join(born))
