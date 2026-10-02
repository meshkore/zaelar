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
_PROSE_FILES = ("nucleo/flash/prompt.py", "nucleo/flash/live_blocks.py",
                "nucleo/flash/live_blocks_nav.py")   # V2-778 F1: live_blocks' browser lines moved there, same sum

#: Measured 2026-09-16. EDIT DOWNWARD ONLY — and the edit is the celebration.
_MAX_PROSE = 24_929          # prompt.py 16_417 + live_blocks.py 3_395 + live_blocks_nav.py 5_117 — DOCSTRINGS OUT
#: ⚠️ V2-778 (2026-10-02) — RE-MEASURED, not raised: the count used to include every DOCSTRING of the three modules,
#: 19_141 of its 44_070 bytes, which the model never reads. A docstring is a comment to the model, and this file's
#: own last test says a comment costs nothing here — so writing down why a function exists was being charged as
#: prompt prose (F0 had raised the ceiling 42_376 → 44_070 partly on that). Now only strings the model can read
#: count, the ceiling is that exact number, and it is STRICTER than before: one new sentence in the prompt fails
#: this test, where the old ceiling had ~19 k of documentation to hide it in. EDIT DOWNWARD ONLY.
_MAX_TOTAL = 48_721          # the prose above 24_929 + the tool catalog 23_594 + the POLICY lines below, 198
#: V2-778 (2026-10-02) — re-measured with the docstrings out, as `_MAX_PROSE` (was 67_862 counting them).

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


def _docstrings(tree) -> set:
    """The docstring nodes of a module, its classes and its functions — documentation, never sent to a model."""
    out = set()
    for n in ast.walk(tree):
        if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and n.body \
                and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant) \
                and isinstance(n.body[0].value.value, str):
            out.add(id(n.body[0].value))
    return out


def _prose_bytes(rel: str) -> int:
    tree = ast.parse((ENGINE / rel).read_text(encoding="utf-8"))
    docs = _docstrings(tree)
    return sum(len(n.value) for n in ast.walk(tree)
               if isinstance(n, ast.Constant) and isinstance(n.value, str) and len(n.value) >= _PROSE_FLOOR
               and id(n) not in docs)


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
    # three since V2-778 F1: live_blocks' browser lines moved to live_blocks_nav.py, and stay in the same sum
    assert len(_PROSE_FILES) == 3 and all((ENGINE / r).exists() for r in _PROSE_FILES)
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
    #
    # V2-778 F0: the floor is now per LINE, because genesis legitimately turns one of them off. Since b97815e4
    # (2026-09-29) `confirm_short_actions` is ON by default, so `prompt_line()` composes nothing on purpose and
    # the sum fell to ~200 — a deliberate product change that this floor read as «the policy was emptied». So:
    # the line genesis keeps ON must arrive, and the line it keeps OFF must still arrive the moment the operator
    # turns it on. A falsified `_policy_bytes()` still fails the first floor.
    from nucleo import style_policy as sp
    sp._reset_for_tests()
    assert len(sp.shape_line()) >= 150, (
        f"`shape_line()` only composes {len(sp.shape_line())} bytes: the shape of the turn stopped reaching it.")
    real = sp.confirm_short_actions
    sp.confirm_short_actions = lambda: False
    try:
        assert len(sp.prompt_line()) >= 300, "silent-orders on must put its line into the turn"
    finally:
        sp.confirm_short_actions = real
        sp._reset_for_tests()
    assert n >= len(sp.shape_line()), f"the policy measures {n} bytes, less than the line it always emits"


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


def test_a_docstring_costs_NOTHING_here_either():
    """V2-778: a docstring is documentation — the model never reads it — so it is not prompt prose. A string the
    code RETURNS is, however long it is and wherever it sits."""
    src = ('def f():\n    """' + "why this exists, measured, " * 10 + '"""\n    return "' + "x" * 50 + '"\n')
    tree = ast.parse(src)
    docs = _docstrings(tree)
    counted = sum(len(n.value) for n in ast.walk(tree) if isinstance(n, ast.Constant)
                  and isinstance(n.value, str) and len(n.value) >= _PROSE_FLOOR and id(n) not in docs)
    assert counted == 50
