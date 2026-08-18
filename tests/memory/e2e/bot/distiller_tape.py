"""tests/memory/e2e/bot/distiller_tape.py — RECORD and REPLAY the write-path CORE (V2-114 F1).

**The problem it solves.** The only serious measurement of memory (`scale_eval --fresh`) repopulates the corpus
by calling the REAL distiller hundreds of times: hours and API money per hypothesis. On that cycle ideas cannot
be tried, only confirmed once in a while. The 2026-08-18 audit named this the real iteration bottleneck — ahead
of any architectural reorganization.

**The idea.** `nucleo/mem_processor.process()` is a narrow, well-defined seam: a sentence goes in, pills come
out. Record ONCE what the LLM decided and replay it indefinitely. The fixture freezes **the model's decision**,
not what memory did with it — so a `--replay` run exercises MEMORY (writer, supersede, retriever, graph, REM)
and not the distiller. That is exactly the boundary we want to be able to change fast.

**Why a SEQUENTIAL tape and not a text->pills dict.** `memory_agent` retries once when `process()` returns
`None` (V2-103: a network blip in the write-path core), so one sentence can produce TWO calls. A per-text dict
cannot represent that; a tape in call order can, and on replay the retry fires exactly where it fired while
recording. Faithful reproduction, including the degradation path to the heuristic.

The three return values keep their semantics (this matters: they are distinct branches in the caller):
  `None` = the model was unavailable -> the caller falls back to the heuristic
  `[]`   = it ran and decided nothing is worth remembering (a legitimate DISCARD)
  `[...]`= curated pills

**What it actually costs, measured (2026-08-18) — this corrects the "seconds" this header used to promise.**
Recording the full fixture: **2 h 07 min**. Replaying it: **~29 min**. That is **4.4x**, not three orders of
magnitude. The breakdown matters because it names the NEXT bottleneck:
  · repopulating the corpus: 2 h 03 -> **24 min** (5.1x) — this is what the tape fixes, and what cost money
  · evaluating the 262 queries: **4.5 min in BOTH runs** — it never went through the distiller, so the tape
    does not touch it and never could; that is 262 x ~570 ms, and half of those 570 ms is the reranker
The remaining 24 min are NOT network: they are the WRITE path (452 inserts with their exact + semantic dedup)
plus the sleep cycle (consolidation/REM/eviction) across 1,032 cases. To go below that, THAT is the place to
look — not the distiller, which is now solved.

**And a second network dependency the tape does NOT close** (learned the hard way, via one stalled run): the
distiller is not the only thing calling a model during repopulation. `connectors/meshkore/mem_ingest`
synthesizes its cluster observation through a LOCAL model, so with Ollama saturated the replay sits BLOCKED on
its socket — 1.4% CPU, making no progress — looking slow when it is really just queued. For a genuinely
hermetic replay, make it fail FAST instead of waiting out its timeout:
`MESHKORE_MEMORY_URL=http://127.0.0.1:9/v1` (connection refused instantly -> deterministic merge, which is
exactly the branch the recording took). Do NOT use `MESHKORE_MEMORY=0` for this: it disables the whole ingest
and leaves 4 rows MISSING from the corpus (3 cluster syntheses plus their concept node), which is a REAL corpus
difference and contaminates the comparison — measured, it is precisely what moved recall@1 by +1.1pp.

Usage:
    with tape.record("fixtures/corpus-v1.jsonl"):
        await runner.run_range(0, 10_000, fresh=True)     # ~2 h, ONCE, with API cost

    with tape.replay("fixtures/corpus-v1.jsonl") as t:
        await runner.run_range(0, 10_000, fresh=True)     # ~29 min, no network, no cost
        print(t.stats())
"""
from __future__ import annotations

import contextlib
import json
import pathlib
import threading


class _Tape:
    """Shared state for one recording or replay session. Locked because, while the distiller is serial by
    design (a semaphore in `mem_processor`), the runner may invoke it from different threads via `to_thread`."""

    def __init__(self, path: str | pathlib.Path):
        self.path = pathlib.Path(path)
        self.entries: list[dict] = []
        self.pos = 0
        self.hits = 0
        self.misses = 0
        self.out_of_order = 0
        self._lock = threading.Lock()

    # ── recording ──────────────────────────────────────────────────────────────────────────────────────
    def append(self, text: str, atoms: list[dict] | None) -> None:
        with self._lock:
            self.entries.append({"i": len(self.entries), "text": text, "atoms": atoms})

    def flush(self) -> int:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as fh:
            for e in self.entries:
                fh.write(json.dumps(e, ensure_ascii=False, default=str) + "\n")
        return len(self.entries)

    # ── replay ─────────────────────────────────────────────────────────────────────────────────────────
    def load(self) -> int:
        self.entries = [json.loads(ln) for ln in
                        self.path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        return len(self.entries)

    def next_for(self, text: str) -> tuple[bool, list[dict] | None]:
        """Returns `(found, atoms)` for the next call. Strict order while the text matches; if it does not
        (a SUBRANGE is being replayed, or the corpus changed), search forward for the next entry with that text
        and count it as out-of-order — degrading beats lying with another sentence's pills."""
        with self._lock:
            if self.pos < len(self.entries) and self.entries[self.pos]["text"] == text:
                e = self.entries[self.pos]
                self.pos += 1
                self.hits += 1
                return True, e["atoms"]
            for j in range(self.pos, len(self.entries)):
                if self.entries[j]["text"] == text:
                    e = self.entries[j]
                    self.pos = j + 1
                    self.hits += 1
                    self.out_of_order += 1
                    return True, e["atoms"]
            self.misses += 1
            return False, None

    def stats(self) -> dict:
        return {"entries": len(self.entries), "hits": self.hits, "misses": self.misses,
                "out_of_order": self.out_of_order,
                "coverage": round(self.hits / (self.hits + self.misses), 4) if (self.hits + self.misses) else 0.0}


@contextlib.contextmanager
def record(path: str | pathlib.Path):
    """Wraps `mem_processor.process` to record every REAL call. Behavior is unchanged: it delegates to the
    original and stores what came back, so the recorded run is also a valid run."""
    from nucleo import mem_processor

    t = _Tape(path)
    original = mem_processor.process

    async def _recording(text: str, *, state: dict | None = None):
        atoms = await original(text, state=state)
        t.append(text, atoms)
        return atoms

    mem_processor.process = _recording          # type: ignore[assignment]
    try:
        yield t
    finally:
        mem_processor.process = original        # type: ignore[assignment]
        n = t.flush()
        print(f"⏺  distiller tape recorded: {n} calls → {t.path}")


@contextlib.contextmanager
def replay(path: str | pathlib.Path, *, strict: bool = False):
    """Swaps `mem_processor.process` for the tape: zero network, zero cost, deterministic.

    It also forces `enabled()` to True — the caller consults it to decide whether to retry after a `None`
    (`memory_agent.py:1096`), and without this a recorded `None` entry would not reproduce the retry that DID
    happen while recording. `strict=True` raises on a sentence missing from the tape instead of degrading to the
    heuristic; useful for a test that demands full fixture coverage."""
    from nucleo import mem_processor

    t = _Tape(path)
    n = t.load()
    original = mem_processor.process
    original_enabled = mem_processor.enabled

    async def _replaying(text: str, *, state: dict | None = None):
        found, atoms = t.next_for(text)
        if not found:
            if strict:
                raise AssertionError(f"no tape entry for {text[:80]!r} (incomplete fixture coverage)")
            return None                          # caller falls back to the heuristic, as with the core down
        return atoms

    mem_processor.process = _replaying          # type: ignore[assignment]
    mem_processor.enabled = lambda: True        # type: ignore[assignment]
    print(f"▶  replaying distiller tape: {n} calls from {t.path} (no network)")
    try:
        yield t
    finally:
        mem_processor.process = original        # type: ignore[assignment]
        mem_processor.enabled = original_enabled  # type: ignore[assignment]
