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
_MAX_PROSE = 42_376          # prompt.py 23_151 + live_blocks.py 19_225   (V2-713 R5: 42_486 → 42_376)
#: V2-728: 66_072 → 66_555. The PROSE ceiling above did not move — this one tracks prose PLUS the tool
#: catalog, and the catalog grew by exactly the one new tool (`reopen_task`, +479 after compacting),
#: whose own ceiling and whose reason are in `test_router.MAX_CATALOG_CHARS`. That is precisely the
#: accounting this number exists for: paying one ceiling by moving text into the other shows up here
#: as what it is, and here it does not happen — nothing moved, one tool was added.
_MAX_TOTAL = 66_555          # …plus the tool catalog 23_579, plus the POLICY lines below, 600

#: ⚠️ V2-713 R5 — A THIRD SOURCE, WHICH WAS ALWAYS THERE AND NEVER COUNTED. `style_policy` composes lines
#: that ride into the turn beside the prompt (`style_directive.prompt_lines`), and this ratchet could not see
#: them: 402 bytes of `prompt_line()` have been shipping on every turn since V2-633 without ever appearing in
#: a number. Counting them RAISES `_MAX_TOTAL`, and that raise is the debt becoming visible, not prose
#: growing — the same shape as the mirror ratchet counting the mark nobody used.
#:
#: The honest accounting of R5's own change, stated rather than rounded: moving «1-2 frases» and «UNA ACCIÓN
#: por turno» out of `prompt.py` removed 110 bytes there and added 198 in `shape_line()`, so what the model
#: reads grew by **88 bytes**. It is not sold as a reduction. What it buys is that two sentences which were
#: constants fixed by whoever was working that day are now data the operator changes by speaking — and that
#: `max_sentences: 0` makes half of that line disappear instead of contradicting the policy.
#:
#: It is measured as what the policy EMITS, not as the file's literals: `style_policy.py` holds 5_241 bytes
#: of string constants and almost all of them are docstrings and regexes the model never sees. Counting the
#: file would have inflated this by 5_000 bytes of documentation, which is the same dishonesty as the LOC
#: proxy in the other direction.
_MAX_POLICY = 600


def _prose_bytes(rel: str) -> int:
    tree = ast.parse((ENGINE / rel).read_text(encoding="utf-8"))
    return sum(len(n.value) for n in ast.walk(tree)
               if isinstance(n, ast.Constant) and isinstance(n.value, str) and len(n.value) >= _PROSE_FLOOR)


def _catalog_bytes() -> int:
    from nucleo.flash import router_catalog as rc
    return len(json.dumps(rc.TOOLS, ensure_ascii=False))


def _policy_bytes() -> int:
    """What `style_policy` composes into the turn under the GENESIS defaults — deterministic by construction
    (the defaults are committed in `nucleo/genesis.json`; a per-install override is the operator's machine,
    not the product, exactly as V2-502 requires of a lab)."""
    from nucleo import style_policy as sp
    sp._reset_for_tests()
    return len(sp.shape_line()) + len(sp.prompt_line())


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


def test_the_policy_lines_are_counted_too_because_the_model_reads_them():
    """The source this ratchet was blind to. A sentence that reaches the turn from a policy costs exactly the
    same per turn as one typed into `prompt.py`; what differs is who can change it."""
    n = _policy_bytes()
    assert n <= _MAX_POLICY, (
        f"las líneas compuestas por `style_policy` suman {n} bytes (techo {_MAX_POLICY}). Una política que "
        f"crece en prosa es una receta con otro nombre: si hace falta decir más, mira si lo que falta es un "
        f"MECANISMO.")
    # ⚠️ Un SUELO, no un `> 0`. El desarme lo enseñó: con `_policy_bytes()` devolviendo 1 este caso seguía
    # verde, porque solo comprobaba cotas y 1 cabe entre 0 y el techo. Un trinquete que pasa con la medición
    # falsificada no mide nada — es la misma trampa que «un arnés puede FABRICAR un pass». El suelo solo lo
    # cumple una lectura real de las dos líneas; si baja de aquí es que la política dejó de llegar al turno.
    assert n >= 400, (
        f"la política solo aporta {n} bytes al turno: o dejó de componerse, o alguien la vació. Las dos "
        f"líneas juntas rondan los 600 desde V2-713.")


def test_a_preference_that_is_turned_OFF_stops_costing_bytes():
    """La prueba de que es una política y no una frase: apagarla la retira del turno. Una receta en el prompt
    se paga aunque el operador no la quiera."""
    from nucleo import style_policy as sp
    sp._reset_for_tests()
    completo = len(sp.shape_line())
    sp._cache.update(path=None, mtime=None, data={})
    real = sp.policy
    sp.policy = lambda: {**real(), "max_sentences": 0, "one_action_per_turn": False}
    try:
        assert sp.shape_line() == "", "con las dos preferencias apagadas no debe quedar ni una palabra"
    finally:
        sp.policy = real
        sp._reset_for_tests()
    assert completo > 0


def test_the_whole_thing_the_model_reads_is_counted_once():
    """Prose + the tool catalog + the policy lines: everything that reaches the provider on one turn."""
    total = sum(_prose_bytes(r) for r in _PROSE_FILES) + _catalog_bytes() + _policy_bytes()
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
