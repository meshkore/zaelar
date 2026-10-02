"""The testing INCIDENTS inbox — where every red a test finds is written down for a developer (V2-780).

The operator's rule (2026-10-02): *tests diagnose and evaluate; they never fix*. A failure is marked, kept as
an incident — one task in ONE initiative — and a developer drains them one by one. So this module only WRITES
tasks; nothing here touches product code, and nothing here closes a task (closing is the developer's, after
the task's «Done when» is green).

One task per KEY (a test node id, a use case id): the first occurrence creates
`.meshkore/modules/tester/tasks/T<n>-<slug>.md`; a repeat on an OPEN task appends one dated line under
«Occurrences» instead of opening a duplicate. A key whose task is `done` and fails again gets a NEW task that
cites the old one — a regression is a new incident, not a reopened diary.

The tasks live under `.meshkore/` (gitignored on purpose: our diary is not published) — so this writes on the
maintainer's checkout and is a no-op target dir anywhere else, created on demand.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent
TASKS = ENGINE / ".meshkore" / "modules" / "tester" / "tasks"
MODULES = ENGINE / ".meshkore" / "modules"
INITIATIVE = "V2-780"

_KEY = re.compile(r"^key:\s*(.+?)\s*$", re.M)
_STATUS = re.compile(r"^status:\s*(\S+)", re.M)
_ID = re.compile(r"^T(\d+)")


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60] or "incident"


def _next_number() -> int:
    """Highest `T<n>` across EVERY module + 1 — the numbering is global (tasks of all modules share it)."""
    top = 0
    for p in MODULES.glob("*/tasks/T*.md"):
        m = _ID.match(p.name)
        if m:
            top = max(top, int(m.group(1)))
    return top + 1


def find(key: str) -> list[Path]:
    """Every task filed under `key`, oldest first."""
    out = []
    for p in sorted(TASKS.glob("T*.md")):
        m = _KEY.search(p.read_text(encoding="utf-8", errors="ignore"))
        if m and m.group(1) == key:
            out.append(p)
    return sorted(out, key=lambda p: int(_ID.match(p.name).group(1)))


def _status(p: Path) -> str:
    m = _STATUS.search(p.read_text(encoding="utf-8", errors="ignore"))
    return m.group(1) if m else ""


def file(key: str, *, title: str, kind: str, symptom: str, reproduce: str, evidence: str,
         diagnosis: str = "", done_when: str = "", priority: str = "medium") -> dict:
    """Create the incident for `key`, or append an occurrence to its open task. Returns what happened.

    `kind` is one of: `product bug`, `non-hermetic test`, `ratchet`, `environment`, `stale test`,
    `use case` (a FAIL the judge and the mechanism report agree on, not yet narrowed to a cause), `unknown`.
    Fail-soft: bookkeeping must never take down the run that produced the verdict.
    """
    try:
        stamp = time.strftime("%Y-%m-%d %H:%M", time.localtime())
        today = stamp[:10]
        TASKS.mkdir(parents=True, exist_ok=True)
        prior = find(key)
        open_ = [p for p in prior if _status(p) not in ("done", "closed")]
        if open_:
            p = open_[-1]
            body = p.read_text(encoding="utf-8").rstrip("\n")
            if "\n## Occurrences\n" not in body:
                body += "\n\n## Occurrences\n"
            body += f"\n- {stamp} — {symptom.splitlines()[0][:200] if symptom else 'again'}"
            p.write_text(body + "\n", encoding="utf-8")
            return {"task": p, "created": False}
        n = _next_number()
        p = TASKS / f"T{n}-{_slug(title)}.md"
        regression = (f"\n**Regression** — this key was fixed before in `{prior[-1].name}`.\n" if prior else "")
        p.write_text(
            f"---\nid: T{n}\ntitle: {json.dumps(title, ensure_ascii=False)}\nstatus: next\n"
            f"priority: {priority}\nowner: ricart\ncategory: tester\ninitiative: {INITIATIVE}\n"
            f"key: {key}\ndepends_on: []\ncreated: {today}\nupdated: {today}\n---\n\n"
            f"Filed by the test system ({stamp}). Tests diagnose; a developer fixes — see {INITIATIVE}.\n"
            f"{regression}\n"
            f"## Symptom\n{symptom.strip() or '—'}\n\n"
            f"## Reproduce\n{reproduce.strip() or '—'}\n\n"
            f"## Evidence\n{evidence.strip() or '—'}\n\n"
            f"## Diagnosis\n{diagnosis.strip() or 'Not narrowed yet.'}\n\n"
            f"## Kind\n{kind}\n\n"
            f"## Done when\n{done_when.strip() or 'The reproduce command above is green.'}\n",
            encoding="utf-8")
        return {"task": p, "created": True}
    except Exception as e:                               # noqa: BLE001 — see the docstring
        return {"error": str(e)}
