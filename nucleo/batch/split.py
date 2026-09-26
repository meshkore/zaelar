"""Split a list-shaped message into ordered, self-contained STEPS (V2-771).

Each step is written the way the operator would have said it on its own — first person, his language, every
reference resolved — because each one is then run as an ORDINARY turn (`runner.py`). That is the whole trick:
the ordinary turn already knows how to store a fact, create an appointment, set a rule or hand a search to a
worker, and it does each of those well inside its own limits. What it cannot do is twelve of them at once.

One model call (`memllm` task `batch_split`: relay chain, billed to Energy). It fails OPEN in two rungs: a
structural split on the message's own numbered sections, and below that nothing — the caller then runs the
message as today's single turn.
"""
from __future__ import annotations

import datetime as _dt
import json
import re

#: More than this is not a list somebody wrote for an assistant; it is a document. The cap bounds the cost of
#: a runaway split, never a real list (his 12-section demo splits into ~25).
MAX_STEPS = 40
#: A step is a turn: the memory distiller reads 600 chars of a turn (`mem_processor._MAX_INPUT`), so a step
#: longer than that would lose facts exactly the way the unsplit message did.
MAX_STEP_CHARS = 560

KINDS = ("identity", "memory", "preference", "rule", "agenda", "reminder", "task", "message", "question", "other")

_SYSTEM = """You turn a message that hands a personal assistant SEVERAL things to do into an ordered list of steps.
Each step will be given to the assistant ALONE, as if the user had just said it, so each step must stand on its own.

Rules:
- Write every step in the SAME LANGUAGE as the message, in the first person, the way the user would say it.
- Keep the original order. Drop nothing: every name, fact, date, time, number and plate must appear in a step.
- Resolve references: «these preferences», «that period», «him» become the explicit content. Dates carry the year.
- ONE calendar entry per step. A period of several days is ONE entry («from 20 December 2026 through 4 January 2027»).
- Facts to remember: group at most 5 closely related facts per step, starting with «Remember:» in the message's
  language. HARD LIMIT: a step is at most 450 characters — split a longer one into two steps.
- A standing instruction about how the assistant should behave («when I ask X, do Y») is its own step, starting
  «From now on» in the message's language; group closely related ones, at most 3 such steps in total.
- Instructions about how to process THIS message («do them in order», «treat each section separately») are NOT steps.
- Headings are not steps; their content is.
- kind is one of: identity (the assistant's own name/role), memory (facts about the user), preference, rule
  (standing behaviour), agenda (create/change a calendar entry), reminder (ONLY a timed alert: «remind me on Friday
  at 9 to…»; dated facts to keep in mind — «remember that the insurance renews on…» — are memory), task (research, search, booking,
  shopping, organising — work that takes time), message (contact someone), question, other.

Answer ONLY with JSON: {"steps": [{"title": "<3-6 words>", "kind": "<kind>", "say": "<the step>"}]}"""

_SECTION_RE = re.compile(r"^\s*(\d{1,2})\s*[.)]\s+", re.M)


def _today_line() -> str:
    d = _dt.date.today()
    return f"Today is {d.isoformat()} ({d.strftime('%A')})."


def _pieces(say: str) -> list[str]:
    """A step over the ceiling is split at SENTENCE boundaries, never cut: measured on his demo (2026-09-25),
    the model wrote the whole «DEFAULT BEHAVIOR» section as one 700-char step despite the rule, and a cut at
    560 dropped «do not ask me for information already stored in memory» — the one line of it that matters
    most. A single sentence longer than the ceiling is the only thing that is still cut."""
    if len(say) <= MAX_STEP_CHARS:
        return [say]
    out, cur = [], ""
    for sent in re.split(r"(?<=[.!?。！？])\s+", say):
        if cur and len(cur) + 1 + len(sent) > MAX_STEP_CHARS:
            out.append(cur)
            cur = ""
        cur = f"{cur} {sent}".strip()
    if cur:
        out.append(cur)
    return [p[:MAX_STEP_CHARS] for p in out]


def _clean(steps) -> list[dict]:
    out: list[dict] = []
    for s in steps if isinstance(steps, list) else []:
        if not isinstance(s, dict):
            continue
        say = re.sub(r"\s+", " ", str(s.get("say") or "")).strip()
        if not say:
            continue
        kind = str(s.get("kind") or "other").strip().lower()
        title = str(s.get("title") or say[:48]).strip()[:80]
        for piece in _pieces(say):
            out.append({"title": title, "kind": kind if kind in KINDS else "other", "say": piece})
    return out[:MAX_STEPS]


def parse(content: str) -> list[dict]:
    """The model's answer → clean steps. Tolerates a fenced block or prose around the JSON; [] when unusable."""
    raw = (content or "").strip()
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        return []
    try:
        data = json.loads(m.group(0))
    except Exception:  # noqa: BLE001
        return []
    return _clean(data.get("steps") if isinstance(data, dict) else None)


def by_sections(text: str) -> list[dict]:
    """The structural fallback: the message's own numbered top-level sections, one step each. A section that
    starts the message's preamble («DEMO INITIALIZATION … Execute…») is skipped because it is not numbered."""
    t = text or ""
    marks = list(_SECTION_RE.finditer(t))
    if len(marks) < 2:
        return []
    steps = []
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(t)
        body = re.sub(r"\s+", " ", t[m.end():end]).strip()
        if body:
            steps.append({"title": body[:48], "kind": "other", "say": body[:MAX_STEP_CHARS]})
    return steps[:MAX_STEPS]


def split(text: str, *, chat=None) -> tuple[list[dict], str]:
    """(steps, how). Blocking — call it in a thread. `how` is `model`, `sections` or `none`."""
    try:
        if chat is None:
            from nucleo.memllm import chat_sync as chat
        content = chat("batch_split", _SYSTEM, f"{_today_line()}\n\nMessage:\n{(text or '').strip()[:12000]}",
                       max_tokens=4000, temperature=0.1, timeout=90.0)
        steps = parse(content or "")
        if len(steps) >= 2:
            return steps, "model"
    except Exception:  # noqa: BLE001 — a split that breaks falls to the structure, then to today's turn
        pass
    steps = by_sections(text)
    return (steps, "sections") if len(steps) >= 2 else ([], "none")
