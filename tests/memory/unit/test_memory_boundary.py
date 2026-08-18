"""memory/contract.py — memory's boundary, with a ratchet (V2-114 F0).

Memory has to be reimplementable without the agent noticing, and that requires knowing where the agent comes in.
Measured 2026-08-18: 84 of ~108 production imports already go through `memory.api`; the ~24 leaks live in few
files and are nearly all explainable. The risk is not today's state, it is DRIFT — that in three months there are
forty new imports of internals and nobody noticed.

These tests are the ratchet. Same pattern as `test_observer_categories.py` (CLOSED inventory: a new unclassified
`kind` breaks) and `test_roadmap_closure.py` (declared debt can only go DOWN).

⚠️ If one of these fails while adding code, the right question is NOT "how do I silence the test?" but "should
this go through the facade?". If it genuinely cannot, add it to `BLESSED_INTERNAL_IMPORTS` **with its reason**,
and the ceiling only drops when a leak is actually closed.
"""
from __future__ import annotations

import pathlib
import re

from memory import api as memapi
from memory.contract import BLESSED_INTERNAL_IMPORTS, MemoryContract

REPO = pathlib.Path(__file__).resolve().parents[3]

# Upper bound on internals leaks in PRODUCTION. It is a RATCHET: it can only go down. Measured today = 24.
MAX_INTERNAL_IMPORTS = 24

_IMPORT_RE = re.compile(r"^[ \t]*from[ \t]+memory(\.[a-z_]+)?[ \t]+import[ \t]+(.+)$", re.MULTILINE)
_SKIP_DIRS = ("/memory/", "/tests/", "/.venv/", "/TMP/", "/.meshkore/")
# The facade and this contract itself are the blessed paths by definition.
_FACADE = {"api", "contract"}


def _submodules() -> set[str]:
    """The REAL submodules of `memory/`, read from disk. Needed because the dominant form in this repo is
    `from memory import db as memdb` (the submodule travels in the NAME list, not after a dot), so telling
    "imports the facade" apart from "imports internals" requires knowing which names are modules."""
    return {p.stem for p in (REPO / "memory").glob("*.py") if p.stem != "__init__"}


def _production_files() -> list[pathlib.Path]:
    """Production .py files: excluding `memory/` (it is the implementation) and `tests/` (may touch internals)."""
    out = []
    for p in REPO.rglob("*.py"):
        s = str(p)
        if any(d in s for d in _SKIP_DIRS):
            continue
        out.append(p)
    return out


def _internal_imports() -> list[tuple[str, str]]:
    """`[(submodule, relative_file)]` for every import of `memory` internals in production.

    Covers BOTH forms that appear in the tree:
      `from memory.rem import synthesize`   → the submodule comes after the dot
      `from memory import db as memdb`      → the submodule is in the name list (the dominant form)
    """
    subs = _submodules()
    found: list[tuple[str, str]] = []
    for p in _production_files():
        try:
            src = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        rel = str(p.relative_to(REPO))
        for dotted, names in _IMPORT_RE.findall(src):
            if dotted:                                  # from memory.<sub> import …
                sub = dotted.lstrip(".")
                if sub not in _FACADE:
                    found.append((f"memory.{sub}", rel))
                continue
            # from memory import a as x, b   →  every name that is a real submodule counts
            for chunk in names.split("#")[0].split(","):
                name = chunk.strip().split(" as ")[0].strip().strip("()")
                if name in subs and name not in _FACADE:
                    found.append((f"memory.{name}", rel))
    return found


def test_the_facade_satisfies_the_contract():
    """`memory.api` must satisfy the Protocol. It is STRUCTURAL typing, so this breaks the moment somebody
    renames or removes a function the agent needs — which is exactly what a replacement would break."""
    assert isinstance(memapi, MemoryContract), (
        "memory.api no longer satisfies MemoryContract: a function the agent uses is missing or was renamed. "
        "If the change is deliberate, update the contract in the SAME commit."
    )


def test_every_contract_member_actually_exists_on_the_facade():
    """A Protocol with `...` bodies does not verify the implementation exists if the structural check is
    relaxed. Checked by hand, and it also gives a useful message (what is missing, not "does not satisfy")."""
    expected = [m for m in dir(MemoryContract) if not m.startswith("_")]
    missing = [m for m in expected if not callable(getattr(memapi, m, None))]
    assert not missing, f"the facade does not expose: {missing}"


def test_no_unblessed_internal_imports_in_production():
    """Every import of internals outside `memory/` has to be declared in BLESSED_INTERNAL_IMPORTS with its
    reason. A new submodule reached from production is an architecture decision, not an oversight."""
    intruders = {}
    for sub, fichero in _internal_imports():
        if sub not in BLESSED_INTERNAL_IMPORTS:
            intruders.setdefault(sub, []).append(fichero)
    assert not intruders, (
        "UNBLESSED imports of memory internals:\n" +
        "\n".join(f"  {s} ← {', '.join(sorted(set(f)))}" for s, f in sorted(intruders.items())) +
        "\n\nCan it go through memory.api? If it really cannot, add it to BLESSED_INTERNAL_IMPORTS with a reason."
    )


def test_internal_import_count_only_goes_down():
    """The numeric ratchet. Blessing a submodule must not become a license to import it from forty places: the
    TOTAL is bounded too."""
    n = len(_internal_imports())
    assert n <= MAX_INTERNAL_IMPORTS, (
        f"{n} imports of internals in production, ceiling {MAX_INTERNAL_IMPORTS}. The boundary is opening up: "
        f"move the new call to memory.api."
    )


def test_lowering_the_ceiling_is_noticed():
    """If somebody closes leaks and the real number drops well below the ceiling, the ceiling has to come DOWN —
    otherwise the ratchet stops biting. This warns; it is not a code failure, it is ratchet maintenance."""
    n = len(_internal_imports())
    assert n >= MAX_INTERNAL_IMPORTS - 4, (
        f"only {n} imports of internals left (ceiling {MAX_INTERNAL_IMPORTS}): lower MAX_INTERNAL_IMPORTS to {n} "
        f"so the ratchet keeps its grip."
    )


def test_blessed_list_has_no_dead_entries():
    """A blessed entry nobody uses any more is documentation debt: it makes the boundary look more porous than
    it is. It gets cleaned up."""
    used = {sub for sub, _ in _internal_imports()}
    # `vault_api`/`server_api` are mounted by chain in the server and may not appear as `from memory.x`
    exempt = {"memory.vault_api", "memory.server_api"}
    dead = [s for s in BLESSED_INTERNAL_IMPORTS if s not in used and s not in exempt]
    assert not dead, (
        f"blessed entries nobody imports any more (remove them from BLESSED_INTERNAL_IMPORTS): {sorted(dead)}"
    )
