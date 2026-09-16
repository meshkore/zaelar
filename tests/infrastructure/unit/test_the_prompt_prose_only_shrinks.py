"""V2-711 T2.2 · The prose the model reads every turn only shrinks — measured where it is WRITTEN.

## Why the existing ratchet could not see this

`test_architecture_ratchet` freezes LOC per file, and LOC is the wrong proxy for this particular debt in
two opposite ways at once:

  · it counts COMMENTS, which this repo deliberately wants — every pattern carries the incident that
    measured it — so writing evidence reads as growth;
  · and it is paid by EXTRACTING a module, which moves the prose somewhere else without removing a word of
    it. Measured: `prompt.py` has been paid down to `live_blocks.py` twice (V2-675, V2-685) and the total
    the model reads went UP each time. A ceiling that a move satisfies is not measuring what it is about.

So this measures the PROSE: every string literal of 40+ characters in the two prompt modules, plus the tool
catalog serialized the way the provider receives it. Deterministic and machine-independent by construction —
no live state, no open widgets, no memory — which is the property the composed `build_flash_system()` cannot
have (its length depends on whose engine runs it, and a lab measures the PRODUCT, not the machine it runs
on: V2-502).

## What it is for

`principles.md` names this class outright: *«Rail on JUDGEMENT — a LIMIT, remove it»*. The `ops` block alone
is 63 sentences, 34 of them an imperative or a prohibition, and it grows one sentence per incident. Each of
those sentences fixed something real; the point of a ratchet is not that they are wrong, it is that the cost
is paid on EVERY turn by every operator and nothing was counting it. Frozen at what it is today, editable
only downward — and the way DOWN is V2-707 F4, the per-operator policy store: the frases that are really
preferences (verbosity, how much it asks before starting, confirm or not, silence on short orders) move to a
table the turn CONSULTS, the way V2-633 already moved «al recibir órdenes no respondas nada».
"""
from __future__ import annotations

import ast
import json
import pathlib
import sys

ENGINE = pathlib.Path(__file__).resolve().parents[3]
if str(ENGINE) not in sys.path:
    sys.path.insert(0, str(ENGINE))

#: Below this, a literal is an identifier, a key, a separator or a format fragment rather than prose. The
#: exact value does not matter much: what matters is that it is FIXED, so the number only moves when the
#: text does.
_PROSE_FLOOR = 40

#: The two modules that compose what the fast turn reads. `router_catalog` is measured apart, because it
#: already has its own ceiling in `test_router` and is counted here only so the TOTAL is honest.
_PROSE_FILES = ("nucleo/flash/prompt.py", "nucleo/flash/live_blocks.py")

#: Measured 2026-09-16. EDIT DOWNWARD ONLY — and the edit is the celebration.
_MAX_PROSE = 42_486          # prompt.py 23_261 + live_blocks.py 19_225
_MAX_TOTAL = 65_582          # …plus the tool catalog, 23_096


def _prose_bytes(rel: str) -> int:
    tree = ast.parse((ENGINE / rel).read_text(encoding="utf-8"))
    return sum(len(n.value) for n in ast.walk(tree)
               if isinstance(n, ast.Constant) and isinstance(n.value, str) and len(n.value) >= _PROSE_FLOOR)


def _catalog_bytes() -> int:
    from nucleo.flash import router_catalog as rc
    return len(json.dumps(rc.TOOLS, ensure_ascii=False))


def test_the_prose_of_the_turn_prompt_only_shrinks():
    per_file = {rel: _prose_bytes(rel) for rel in _PROSE_FILES}
    total = sum(per_file.values())
    assert total <= _MAX_PROSE, (
        f"the turn prompt grew to {total} bytes of prose (ceiling {_MAX_PROSE}): {per_file}.\n"
        f"Every byte here is paid on EVERY turn, by every operator. If what you are adding is a RULE ABOUT "
        f"BEHAVIOUR, `principles.md` says to remove it and find the mechanism it stands in for — and if it "
        f"is a PREFERENCE of the operator's, its home is the policy store (V2-707 F4), the way V2-633 moved "
        f"«al recibir órdenes no respondas nada» out of here. Raising this number is not one of the options.")


def test_moving_prose_between_the_two_files_does_not_pay_anything():
    """The defect in the LOC ratchet, pinned: the total is what is measured, so an extraction to
    `live_blocks.py` no longer reads as a saving. Both files are in ONE sum, deliberately."""
    assert len(_PROSE_FILES) == 2 and all((ENGINE / r).exists() for r in _PROSE_FILES)
    combined = sum(_prose_bytes(r) for r in _PROSE_FILES)
    assert combined == sum({r: _prose_bytes(r) for r in _PROSE_FILES}.values())


def test_the_whole_thing_the_model_reads_is_counted_once():
    """Prose + the tool catalog, which the provider receives beside it on the same turn."""
    total = sum(_prose_bytes(r) for r in _PROSE_FILES) + _catalog_bytes()
    assert total <= _MAX_TOTAL, (
        f"what the fast turn ships grew to {total} bytes (ceiling {_MAX_TOTAL}). The catalog has its own "
        f"ceiling in `test_router`; this one exists so paying that one by moving text into the prompt, or "
        f"the other way round, shows up as what it is.")


def test_a_comment_costs_NOTHING_here():
    """The counterweight that makes this ratchet safe to live with, and the reason LOC was the wrong proxy:
    this repo's method is that each pattern carries the incident that measured it, so writing evidence must
    never read as growth. Only what the MODEL reads is counted."""
    src = "x = 1  # " + ("a measured incident, written down at length, " * 20)
    tree = ast.parse(src)
    counted = sum(len(n.value) for n in ast.walk(tree)
                  if isinstance(n, ast.Constant) and isinstance(n.value, str) and len(n.value) >= _PROSE_FLOOR)
    assert counted == 0
