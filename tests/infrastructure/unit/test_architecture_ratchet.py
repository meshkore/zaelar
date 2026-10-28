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
#   nucleo/dispatch.py         1879 → 1762  what KIND of errand this is                → nucleo/request/kind.py
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
    # 2026-09-05/06, V2-601 T-01 — the audit found the ratchet RED at HEAD (nobody ran it; that is T-02's CI).
    # Paid by four AST-identical extractions: the V2-209 surface-ack pair → flash/surface_ack.py; sheet naming →
    # results/sheet_names.py (+ stdlib lazies hoisted); the V2-539 probe mirror → flash/probe_actionmap.py; the
    # whole flow lifecycle (V2-096/113/116/123) → providers/flow_lifecycle.py. Ceilings lowered to the measured
    # sizes — the celebration edit this table's header describes.
    # 2026-10-01, V2-778 F1-10 — the tool executor and the post-stream chain left `_run_inner`, moved byte for
    # byte into two nucleo/flash modules (the lazy imports travelled with them: 139 total, as before). The
    # provider's ceiling drops to what it measures; the two new rows are MOVED code, not new growth, and both
    # still have to be split by family under the 900 line that bounds an unlisted file.
    "voice/engine/llm/providers/nucleo.py": (1770, 64),
    "nucleo/flash/tool_executor.py": (1272, 35),
    "nucleo/flash/post_stream.py": (984, 40),
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
    "nucleo/dispatch/__init__.py": (1587, 39),   # 2026-10-01 V2-778 F1-11: run_listener → dispatch_listener.py (1790 → 1587)
    # owner.py 1580→1706 · lazy 43→44: 3884cb8 (banner sweep per NAVIGATION, look 11,2 s→0,42 s), f25e2a3
    # (`visit` — read a card in its own tab), a1cb398 (consent per DOMAIN, submit 25 s→3,84 s). Three measured
    # perf/feature fixes from the same tuning day. owner.py remains F6's split candidate (by resource).
    # 2026-08-27 — owner 1706→1725: 0bee0d8 V2-358 (the tab listens to main-frame document responses and
    # hands last_status to every capture — the wall signal no needle can miss, measured on coches.net's two
    # bodies for the same 403). Inherent to the tab object (self/page); the WALL classification itself was
    # extracted instead (tasks.py → walls.py, 904→774, staying out of the table).
    # 2026-09-02: 1374 → 789, and 15 → 7 lazy imports. The ratchet asked for an extraction and got two:
    # `reminder_guards.py` (the 26 guards for a PROMISED dated notice — a closed set that nothing left
    # behind uses) and `text_norm.py` (the three text helpers BOTH halves need, which is why neither could
    # keep them without importing the other back). Everything moved byte for byte and is re-exported, so no
    # call site changed. The two new files are deliberately NOT listed: a ceiling is earned by a file that
    # has already grown too big, not handed to every module at birth.
    # 2026-09-03, same pass (V2-567): router_guards paid by extracting the V2-210 answer-source family to
    # answer_guards.py (811→762); probe paid by moving alias classification to show_target.py beside its
    # siblings (1152→1144). Both files sat EXACTLY at their ceilings — the ratchet working as designed.
    # V2-713 R1 — 742→666 pagado EXTRAYENDO `show_guard.py`: el guarda del «abre/muéstrame» puro (sus
    # tres clases de verbo, la decisión y su sombra) era un concepto entero dentro de un cajón que
    # mezclaba dinero, login y cierre. Los lazy bajan de 5 a 3 porque los nuevos se fueron con él.
    "nucleo/flash/router_guards.py": (561, 3),   # 2026-10-01 V2-778 F1: commission readers → commission_guards.py
    "nucleo/flash/show_guard.py": (165, 4),
    # nucleo/flash/probe.py left the table with the text channel's own turn (refactor2710-01): the typed
    # channel runs the voice turn, so there is no second copy left to bound.
    "nucleo/flash/prompt.py": (834, 29),   # 25-08: 41be5cb V2-311 step 3 · 26-08: +3 V2-342 (the COMPLAINT
    # branch in the worker directive: inject before killing—directive prose, nothing extractable)
    # 26-09-11: V2-675 · −21 — the CRON line moved to `live_blocks.py` (same precedent as the browser and
    # background-task blocks), paying for the context-pack seam. Lowering the number IS the celebration.
    "nucleo/workers/session.py": (696, 16),   # 2026-10-01 V2-778 F1: its notes → workers/session_notes.py
    "nucleo/flash/router.py": (327, 1),
}

#: No god file may be BORN either: any engine module NOT in the table stays under this. The largest unlisted
#: file was `connectors/meshkore/bridge.py` at 863 until refactor2710-13 split it into a package; 900 still bounds the
#: rest of the tree with margin.
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
#:
#: ⚠️ IT WAS COUNTING THE MARK NOBODY USES (V2-711 T0.6). This ratchet existed, sat GREEN at 13 against a
#: ceiling of 15, and measured «impl PARALELA» — while the mark the two channels are ACTUALLY stitched with
#: is «cablear en AMBOS», which stood at 29 and was invisible to it. Measured 2026-09-16 over the same files
#: this ratchet already walks: `voice/…/nucleo.py` 3+5, `nucleo/flash/probe.py` 10+19,
#: `nucleo/flash/probe_scheduling.py` 0+5. So every mirror written with the second spelling — the common one,
#: the one `probe_scheduling.py`'s own docstring quotes — cost nothing and the number never moved. A ratchet
#: that measures the less-used half of its own vocabulary is a ratchet that reports the wrong debt while
#: passing. Both literals are counted now and frozen TOGETHER at what the tree holds today.
_MIRROR_MARKS = ("impl PARALELA", "cablear en AMBOS")
_MIRROR_MAX = 42

# `.meshkore` holds no product code — docs, roadmap, and the daemon's `snapshots/`, which are
# VERBATIM COPIES of the very files this ratchet measures (standard §20 writes one before each edit).
# Counting them multiplied every god file by however many snapshots the operator's machine happened
# to hold: measured 2026-09-20, the parallel-mirror count read 124 against a ceiling of 42 while the
# real files summed to exactly 42. A ratchet that reads a developer's local runtime state is not
# measuring the repo, and its red says nothing about the code (V2-726).
_SKIP_DIRS = {".venv", "tests", "node_modules", "__pycache__", ".git", "frontend/vendor", ".meshkore",
              ".claude"}   # .claude/worktrees: another session's checkout is not this tree


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
            text = p.read_text()
        except Exception:
            continue
        n = sum(text.count(m) for m in _MIRROR_MARKS)
        if n:
            hits.append((rel, n))
    total = sum(n for _r, n in hits)
    assert total <= _MIRROR_MAX, (
        f"{total} marcas de espejo {_MIRROR_MARKS} (techo {_MIRROR_MAX}). Un espejo NUEVO está vetado: si dos "
        f"canales necesitan la misma decisión, se extrae a un módulo y ambos lo importan. Dónde están: {hits}")


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


# ── 2026-10-27, refactor2710-00: the PACKAGE ratchet ─────────────────────────────────────────────────────────
# The per-file table above caught god files but not god PACKAGES: `nucleo/flash` grew to 176 files and 37k lines
# one small, under-the-ceiling module at a time, and nothing went red. The deep refactor (V2-826) is measured
# against these totals — the same line count `python -m tests.infrastructure.import_graph --summary` prints, bucketed by its
# `package_of`. Edit DOWNWARD when a section lands (that edit is the section's exit); a new bucket is red until
# someone writes its number here on purpose.
_PACKAGE_CEILINGS: dict[str, int] = {
    "bus": 646,
    "config": 2525,
    "connectors": 20298,   # refactor2710-13: eight splits paid by folding five copies of the OAuth flow; refactor2710-01: +10, the consequence doors (music, messaging, mesh)
    "library": 805,
    "memory": 8532,                    # refactor2710-11: 9117 → 8532 (splits by concern, orphans out; recall timing event)
    "nucleo (top)": 7438,      # refactor2710-10: the worker CLIs → nucleo/cli/, energy → nucleo/energy/, the pulse → nucleo/pulse/; refactor2710-02: circuit, request_row, spec, harness, verify, deliverable_gate moved to their packages; refactor2710-11: processor moved to memory_agent; refactor2710-01: `consequence.py` (the door registry, each door an event), `dispatch_soon.py` (moved)
    "nucleo/actionmap": 761,   # refactor2710-04: its canvas writes cross nucleo.acts.canvas.apply
    "nucleo/acts": 3814,         # refactor2710-04b: the close, show-under-close, reopen and size licences are the door's; refactor2710-05: the tool catalogue (T-01) + what frontend.py decided about a card (T-05); refactor2710-04: the one canvas door, the arbiter and the turn it reads; refactor2710-05: the tool catalogue (T-01) + what frontend.py decided about a card (T-05); refactor2710-06: the search, memory (vault), media (player) and message doors, from nucleo/flash
    "nucleo/agentes": 795,   # refactor2710-04: its canvas writes cross nucleo.acts.canvas.apply
    "nucleo/batch": 884,        # refactor2710-01: +2, its step runs the typed turn (cli/turn)
    "nucleo/circuit": 2597,     # refactor2710-02: born (moves + verdict.py); 02b: the row half of request.model.settle MOVED in as circuit.settle, flash/write_outcome MOVED in (compose.py)
    "nucleo/context_packs": 568,
    "nucleo/dispatch": 2448,   # refactor2710-09 T-01: moved from top and split; target 1 200
    "nucleo/energy": 2269,       # refactor2710-10: born — meter, lease, tariffs, limits, routing, account, egress, keys MOVED from the top
    "nucleo/pulse": 2783,        # refactor2710-10: born — loop split into loop/workers/flows/due/signals (same beat); scheduler, sparks, homeostasis, wake, cron_api, rehydrate, notices, webpush, notice_today MOVED
    "nucleo/errands": 2548,
    "nucleo/cli": 2900,         # refactor2710-10: the worker CLIs MOVED in (nav, mesh, widget, mem, git, report, bridge, worker_api/policy, sandbox, usage); 01: born
    "nucleo/flash": 21362,      # refactor2710-02: the model client MOVED to nucleo/llm/; refactor2710-03: the word gates over our own reply went; refactor2710-05: the arms and the card decisions → nucleo/acts; refactor2710-04: the text channel's canvas mirrors went; refactor2710-02: the model client (7 files) MOVED to nucleo/llm/; refactor2710-03: the word gates over our own reply went; refactor2710-02: the model client MOVED to nucleo/llm/; refactor2710-03: the word gates over our own reply went; refactor2710-05: the arms and the card decisions → nucleo/acts; refactor2710-02: the model client (7 files) MOVED to nucleo/llm/; refactor2710-03: the word gates over our own reply went; refactor2710-06: search_turn, search_routing, listing_turn folded into acts/search; vault_carrier, vault_flow, vault_rules into acts/memory; player_control, player_outcome into acts/media; the wait lines of reminder_guards into nucleo/turn; the reminder rails (reminder_guards, reminder_fact, reminder_year, reminder_promise) went
    "nucleo/input": 739,        # refactor2710-01: born — the STT accumulator and the typed order, MOVED from nucleo/flash
    "nucleo/jev": 759,          # refactor2710-07: born — jev.py split into the client, select and decide (dead calls out)
    "nucleo/llm": 2077,         # refactor2710-02: born — fast_client, provider_chain and the rest of the model client, MOVED
    "nucleo/memory_agent": 3090,       # refactor2710-11: 1949 + processor moved in from top (1520), 3123 → 3088 (write events); refactor2710-01: +2, the memory.ingest door
    "nucleo/request": 954,     # refactor2710-02: born — request_row (model), errand_kind/title, dedup+continuity (append), stop_decision MOVED in
    "nucleo/susurro": 1386,
    "nucleo/turn": 3473,        # refactor2710-03: `reply.py` + `reply_receipts.py` (the mouth); refactor2710-07: `brief.py` + `verdicts.py` (moved from nucleo/flash); refactor2710-04: its canvas writes cross nucleo.acts.canvas.apply; refactor2710-03: `reply.py` + `reply_receipts.py`, the mouth that speaks the verdict (paid by nucleo/flash); refactor2710-03: `reply.py` + `reply_receipts.py`, the mouth that speaks the verdict (paid by nucleo/flash); refactor2710-06: `wait_lines.py`, the holding/mute/follow-up lines from flash/reminder_guards
    "nucleo/workers": 7168,            # refactor2710-10: source_outcomes MOVED in from the top; refactor2710-09: + research (590) as workers/brief*, providers and session split; target 4 500
    "nucleo/workflows": 315,
    "observability": 1005,
    "rules": 1211,              # refactor2710-01: +3, the rules.write door
    "search": 5474,
    "server": 5746,   # refactor2710-04: its canvas writes cross nucleo.acts.canvas.apply, /api/canvas/reconcile (V2-825 F5); refactor2710-13: lifespan in one file, routers ≤ 300, three dead routes gone
    "voice": 10092,             # refactor2710-01: +3, `typed_turn.py` (the typed front door) and the lent speaker
    "voice/engine/llm": 3850,   # refactor2710-04: its canvas writes cross nucleo.acts.canvas.apply; refactor2710-01: +64, a failed turn keeps his words; the vault is a door
    "widgets": 38383,           # refactor2710-01 +42 (payload_digest, sheet.rebuild); refactor2710-12 split and condensed; refactor2710-06: `agenda/notice.py`, the notice's consequence bounds read off its slots
}

#: A new file under `nucleo/` is born small. 300 lines, not the tree-wide 900 above: the refactor splits the brain
#: into doors and mechanisms, and a 400-line file there is a second concern waiting to be named. The files that were
#: already over it on 2026-10-27 are grandfathered BY NAME and the list only shrinks — when one drops under the
#: line, it leaves the list in the same commit.
_NUCLEO_NEW_FILE_MAX = 300
_NUCLEO_GRANDFATHERED: frozenset[str] = frozenset({
    "nucleo/actionmap/executor.py",
    "nucleo/batch/runner.py",
    "nucleo/circuit/__init__.py",   # MOVED from nucleo/circuit.py (refactor2710-02 T-00)
    "nucleo/consent.py",
    "nucleo/danger.py",
    "nucleo/dispatch/confirm.py",
    "nucleo/dispatch/prepare.py",
    "nucleo/dispatch_prompts.py",
    "nucleo/energy/lease.py",
    "nucleo/energy/meter.py",
    "nucleo/errands/__init__.py",
    "nucleo/errands/book.py",
    "nucleo/errands/wake.py",
    "nucleo/errands/watch.py",
    "nucleo/flash/act_repair.py",
    "nucleo/flash/answer_guards.py",
    "nucleo/flash/canvas_license.py",
    "nucleo/flash/card_close.py",
    "nucleo/flash/card_commission.py",
    "nucleo/flash/data_ops.py",
    "nucleo/flash/dialog.py",
    "nucleo/flash/direct_action.py",
    "nucleo/flash/escalation_guard.py",
    "nucleo/llm/fast_client.py",
    "nucleo/flash/live_blocks.py",
    "nucleo/flash/payload_fill.py",
    "nucleo/flash/post_stream_lanes.py",
    "nucleo/flash/post_stream_acts.py",
    "nucleo/flash/prompt.py",
    "nucleo/llm/provider_chain.py",
    "nucleo/flash/router.py",
    "nucleo/flash/router_catalog.py",
    "nucleo/flash/router_guards.py",
    "nucleo/flash/second_pass.py",
    "nucleo/flash/segmenter.py",
    "nucleo/flash/show_target.py",
    "nucleo/flash/site_catalog.py",
    "nucleo/flash/task_block.py",
    "nucleo/flash/tool_executor_calls.py",
    "nucleo/flash/tool_executor_widget_calls.py",
    "nucleo/flash/tool_selection.py",
    "nucleo/flash/widget_read.py",
    "nucleo/pulse/homeostasis.py",
    "nucleo/input/stt.py",   # the phrase accumulator, MOVED from nucleo/flash/accumulator.py (refactor2710-01)
    "nucleo/jev/__init__.py",
    "nucleo/memory_agent/gates.py",
    "nucleo/mesh_agents.py",
    "nucleo/cli/nav.py",
    "nucleo/pulse/notices.py",
    "nucleo/runstate.py",
    "nucleo/pulse/scheduler.py",
    "nucleo/sheets.py",
    "nucleo/circuit/spec.py",
    "nucleo/susurro/apply.py",
    "nucleo/susurro/engine.py",
    "nucleo/circuit/ledger.py",
    "nucleo/turn/promise_kept.py",
    "nucleo/cli/worker_api.py",
})


def _package_totals() -> dict[str, int]:
    from tests.infrastructure.import_graph import package_of, product_modules

    totals: dict[str, int] = {}
    for _name, (path, src) in product_modules().items():
        bucket = package_of(path)
        totals[bucket] = totals.get(bucket, 0) + src.count("\n") + 1
    return totals


#: The sum of every package. A package ceiling is set to what was measured only in the PR that MOVES code between
#: packages or introduces a declared mechanism, with the cause beside it — and with this total lower (refactor2710-01:
#: 178503 → 173251, with refactor2710-11 and -13 merged; → 172847 with -01 and -12; -02 and -03: → 171441; the rest of -02: → 171300; -02b: → 171265; -09: → 171151; refactor2710-07: → 170777). Never for growth in place.
_TOTAL_MAX = 169695


def test_the_total_only_shrinks():
    total = sum(_package_totals().values())
    assert total <= _TOTAL_MAX, f"the product grew to {total} lines (ceiling {_TOTAL_MAX}) — the refactor only removes"
    assert _TOTAL_MAX - total <= 200, f"the total ceiling is slack ({_TOTAL_MAX} over {total}): lower it to what landed"


def test_a_package_only_shrinks():
    totals = _package_totals()
    over = [f"{pkg}: {n} > {_PACKAGE_CEILINGS[pkg]}" for pkg, n in sorted(totals.items())
            if pkg in _PACKAGE_CEILINGS and n > _PACKAGE_CEILINGS[pkg]]
    born = sorted(set(totals) - set(_PACKAGE_CEILINGS))
    assert not over, "a package GREW — the refactor only removes lines:\n  " + "\n  ".join(over)
    assert not born, f"a new package bucket has no ceiling yet — write its number in _PACKAGE_CEILINGS: {born}"


def test_a_new_nucleo_file_is_born_small():
    over, shrunk = [], []
    for rel, p in _engine_py_files():
        if not rel.startswith("nucleo/"):
            continue
        n = _loc(p)
        if rel in _NUCLEO_GRANDFATHERED:
            if n <= _NUCLEO_NEW_FILE_MAX:
                shrunk.append(rel)
        elif n > _NUCLEO_NEW_FILE_MAX:
            over.append(f"{rel}: {n} LOC")
    missing = sorted(f for f in _NUCLEO_GRANDFATHERED if not (ENGINE / f).exists())
    assert not over, (f"a nucleo file is over {_NUCLEO_NEW_FILE_MAX} lines — split it by concern:\n  "
                      + "\n  ".join(over))
    assert not shrunk and not missing, (
        "a grandfathered file is now under the line or gone — take it off _NUCLEO_GRANDFATHERED: "
        f"{shrunk + missing}")
