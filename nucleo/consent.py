"""nucleo/consent.py — THE ONE RULE that decides whether to act or to ask (V2-712).

## Why this exists

The operator, 2026-09-16, on what V2-711 had just shipped:

> «Estoy un poco hasta los huevos de tener que confirmar las cosas. Si le digo borra una cita de la agenda
> llamada tal, la borras y punto. A menos que haya dos que se llamen igual […]. Si te digo que reserves mesa
> en un restaurante, tú ya tienes que saber quién soy yo, cuál es mi teléfono, cuál es mi email. Y si no lo
> sabes, obviamente preguntas. Pero una vez ya lo sepas y lo tengas en el estado, no hace falta preguntar.»

And, decisively, on the SHAPE the fix must have:

> «No forzamos las preguntas de forma hardcodeada. Tiene que ser el propio sistema el que tenga una regla para
> todo el sistema […]. Cuando hagamos un widget diremos cuál es el nivel de seguridad, y pondremos de momento
> a todos por defecto nivel estándar. […] Por defecto no autorrespondemos ningún mensaje. Eso es una regla de
> usuario preseteada en el Génesis. Pero si el usuario decide cambiarla, que la cambie. No debemos hardcodear.»

He is right, and the defect was mine. V2-711 made the browser's click gate judge CONTEXT instead of the
button's label — a rail on the consequence, which keeps. But it then asked for consent whenever the form
carried IDENTITY fields, and a form asking for a name, a phone and an email is the NORMAL shape of the order
he just gave. `principles.md` names that class exactly: *«Rail on JUDGEMENT — a LIMIT, remove it»*.

## What was measured before writing this (2026-09-16, current tree)

  · **Consent was decided by the VERB.** `_apply_widget_data` → `flash/frontend.action_mode()` →
    `widgets/actions.classify()` → the manifest's `confirm:true`. Twenty actions in the catalog carry it, and
    none of those three functions knows how many items the call will touch or whether the reference resolved.
  · **Ambiguity is already resolved one step earlier, and we asked again anyway.** `widgets/refs.resolve()`
    returns `needs='ambiguous'|'no_match'|'ref'` with `candidates`, and the caller asks which one. When it
    resolves to exactly ONE, the turn proceeds — and the confirm gate then asks a second question that adds
    no information. That second question is the one he is complaining about.
  · **The right mechanism already exists, applied in exactly one place.** `widgets/rows.py::apply()` (V2-707
    F1) computes the radius BEFORE acting and asks only when n>1, naming the count and the rows. Its sentence
    is the one generalised here: **the friction is the RADIUS, not the verb.**

## The rule, in the operator's own order

Four questions, asked in this sequence. Anything that is not one of them is not asked at all.

  1. **Is a FACT missing to act with guarantees?** → `ASK_FACT`, naming the fact. Asking «what is your phone»
     is help; asking «shall I proceed» when the phone is already on file is friction.
  2. **Is there DOUBT about what will be touched?** → `ASK_WHICH`, with the count and the names.
  3. **Does the RADIUS exceed what he named?** (a sweep with no selector) → `ASK_CONSENT`. This is V2-707's
     rail and it stays: «vacía la agenda» is a different act from «borra la cita del dentista».
  4. **Is the class itself sensitive enough to ask even so?** → the DECLARED level, layered with the
     operator's own standing policy.

Nothing here is a verb table and nothing here decides intent: every input is data somebody else measured.

## Sensitivity is DECLARED DATA; his standing rules are rows of ONE scoped table (V2-806)

Factory defaults in `nucleo/genesis.json`; what he says is a user row of the `rules` table (`rules/`), scoped to
the act it governs and read through a cascade over the request's path, so a rule he states governs the very next
decision and survives a restart. The rails (a missing fact, a doubt about which, the radius) are steps of
`decide` below and no row reaches them.

A widget declares `"security": "standard"` (every shipped widget today, exactly as he asked); an action may
declare its own `"sensitivity"`. Today's `confirm:true` is READ as `sensitive` rather than deleted — so no
behaviour changes by accident, only what V2-712 says changes.

⚠️ `critical` is the one level that asks even with a clear order and complete data: **money leaving his
accounts**. That is a rail on the consequence, it is the class the V2-705 contract was born from, and it is
not negotiable by convenience.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

# ── Verdicts ────────────────────────────────────────────────────────────────────────────────────────────
RUN = "run"                  # act now; the order and the data are enough
ASK_FACT = "ask_fact"        # a datum is missing — ask for THE DATUM, never for permission
ASK_WHICH = "ask_which"      # more than one thing matches — ask which, with the names
ASK_CONSENT = "ask_consent"  # the radius or the class genuinely warrants a yes/no
REFUSE = "refuse"            # a standing policy of the operator's forbids this class outright

#: Ordered, low to high. A widget with nothing declared is `standard`, which is where every shipped widget
#: sits today — the operator's instruction, verbatim: «pondremos de momento a todos por defecto estándar».
LEVELS = ("routine", "standard", "sensitive", "critical")

def _rank(level: str) -> int:
    try:
        return LEVELS.index(str(level or "").strip().lower())
    except ValueError:
        return LEVELS.index("standard")


# ── The operator's standing rules live in ONE table (V2-806) ────────────────────────────────────────────
# Genesis `consent` is the factory layer (`rules/defaults.py` reads it: a `consent` gate per class, the global
# `ask_at` and `intent_act_at`); what he says is a `user` row of the `rules` table, scoped like the act it
# governs. `<workspace>/config/consent.json`, the override file this module used to write, is imported into the
# table once (`_migrate`) and never written again.

def _overrides_path() -> Path:
    from nucleo import workspace as _ws
    return _ws.root() / "config" / "consent.json"


def _migrate() -> None:
    """One-time import of the legacy override file into the table. Idempotent: a marker per database AND a
    deterministic id per row, so a second run (or a second process) inserts nothing."""
    import rules
    from rules import store as _rstore
    p = _overrides_path()
    marker = f"migrated:consent.json:{p}"
    if _rstore.once_done(marker):
        return
    try:
        data = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except (OSError, ValueError) as e:
        import logging
        logging.getLogger("zaelar.consent").warning(f"consent: {p} unreadable ({e}) — nothing migrated")
        data = {}
    data = data if isinstance(data, dict) else {}
    at = float(data.get("_set_at") or time.time())
    rows = [(rules.class_scope(*rules.split_key(k)), "consent", str(v).strip().lower(), k)
            for k, v in (data.get("classes") or {}).items() if str(v).strip().lower() in rules.GATE_VALUES]
    rows += [(rules.GLOBAL, knob, data[knob], knob) for knob in ("ask_at", "intent_act_at") if knob in data]
    for sc, k, v, src in rows:
        _rstore.insert_new({"id": f"m_consent_{src}", "scope": sc, "kind": "gate", "key": k, "value": v,
                            "source": "user", "created_at": at, "origin": f"consent.json:{src}"})
    _rstore.mark_done(marker)


def _anchors(policy_key: str = "", scope: dict | None = None) -> list:
    import rules
    _migrate()
    return rules.path(cls=policy_key, **{k: v for k, v in (scope or {}).items() if v})


def policy() -> dict:
    """The effective global knobs and every class genesis names, as the cascade reads them today."""
    import rules
    from rules import defaults as _rdef
    out = {k: rules.value(_anchors(), k) for k in _rdef.GATE_KNOBS}
    out["classes"] = {r["origin"].partition(":")[2]: class_policy(r["origin"].partition(":")[2])
                      for r in _rdef.rows() if r["key"] == "consent"}
    return out


def ask_at(policy_key: str = "", scope: dict | None = None) -> str:
    """The lowest level that asks for consent EVEN WHEN the order is clear, the target resolved and the data
    complete. Genesis says `critical` — the single knob that answers «estoy hasta los huevos de confirmar».
    Read through the cascade, so a narrower rule of his can move it for one place only."""
    import rules
    lvl = str(rules.value(_anchors(policy_key, scope), "ask_at", "critical") or "").strip().lower()
    return lvl if lvl in LEVELS else "critical"


def intent_act_at() -> float:
    """How sure the turn's verdict must be of an ORDER and its action to carry it out when the model held it for a
    question (2026-10-15, the operator's 70%). Genesis `intent_act_at`, overridable like every other knob here."""
    import rules
    try:
        v = float(rules.value(_anchors(), "intent_act_at", 0.7))
    except (TypeError, ValueError):
        v = 0.7
    return min(max(v, 0.5), 0.99)


def class_policy(key: str, scope: dict | None = None) -> str:
    """The standing rule for a class: 'never' | 'ask' | 'allow' | '' (no row covers it).

    His own example is the one that ships: `messaging.autorespond: "never"` — PRESET, not hardcoded. A class
    REFINED by a channel (`messaging.send_new@email`) is covered by his rule for that channel, else by the class's
    rule for every channel — a rule for one channel never reaches another (`rules/scope.py`).
    """
    import rules
    return rules.gate(_anchors(str(key or "").strip(), scope))


# ── Declared sensitivity ────────────────────────────────────────────────────────────────────────────────

def level_of(spec: dict | None, *, widget_security: str = "", action: str = "") -> str:
    """The action's level, from what is DECLARED — never from its name.

    Precedence: the action's own `sensitivity` → the legacy `confirm`/`irreversible` flag, read as
    `sensitive` → `view:true`, read as `routine` → the widget's `security` → `standard`.
    """
    spec = spec if isinstance(spec, dict) else {}
    declared = str(spec.get("sensitivity") or "").strip().lower()
    if declared in LEVELS:
        return declared
    if spec.get("confirm") is True or spec.get("irreversible") is True:
        return "sensitive"
    if spec.get("view") is True:
        return "routine"
    ws = str(widget_security or "").strip().lower()
    return ws if ws in LEVELS else "standard"


# ── Whose order was it? (V2-812 T-03) ───────────────────────────────────────────────────────────────────
# The attention gate admits a line inside an open conversation without waiting for its judge, and judges it
# beside the turn: was it addressed to the agent, and was it a clear request? `licence` is that answer for the
# line of the CURRENT turn (its trace), measured by another layer like every other input here. Nothing in this
# module reads the words.

_FROM_LINE = object()   # `decide(licensed=...)` default: read the current turn's line


def line_licence(trace: str = "") -> bool | None:
    """True: the turn's line was a clear request to the agent (or he said yes to the question it raised).
    False: judged, and it was not. None: unknown — no voice line behind this call, a wake word, a typed line,
    a verdict still on its way — and then nothing here changes."""
    try:
        from voice import attention
        return attention.licence(trace)
    except Exception as e:  # noqa: BLE001 — no attention layer (a headless caller) is «unknown», never «refused»
        import logging
        logging.getLogger("zaelar.consent").debug(f"consent: no line licence to read ({e!r}) — unknown")
        return None


# ── THE RULE ────────────────────────────────────────────────────────────────────────────────────────────

def decide(*, level: str = "standard", missing=(), candidates=(), radius: int | None = 1,
           bounded: bool = True, policy_key: str = "", his_yes: bool = False, scope: dict | None = None,
           licensed=_FROM_LINE) -> dict:
    """Act, or ask — and if asking, WHICH of the three useful questions it is.

    Every argument is something another layer already measured; nothing here reads text or guesses intent.

      · `missing`   — facts the action needs and the engine does not have (names, not values).
      · `candidates`— labels of the things that matched, when more than one did.
      · `radius`    — how many things this will touch, when it is known. `None` means «not counted».
      · `bounded`   — whether the call names WHAT it hits at all. A sweep with no selector is unbounded, and
                      that is the V2-707 rail: «vacía la agenda» is not «borra la cita del dentista».
      · `policy_key`— the class this belongs to, for the operator's standing rules (`messaging.autorespond`).
      · `scope`     — what else names the request's place for the rules cascade: `widget`, `action`, `item`
                      (V2-806). With the class, it is the request's path; the cascade reads only rows covering it.
      · `his_yes`   — his own order already IS the consent: the act delivers a row he has SEEN, held for his
                      word, and the turn's verdict surely names that act (the widget's `held_row` hook). It clears
                      the class question and nothing above it: a missing fact, a doubt, his standing «ask» rule
                      and the radius rail still stop.
      · `licensed`  — was the line this act comes from a clear request to the agent (`line_licence`, read
                      from the current turn when not given)? `False` asks first for an ACT — a declared consent
                      class, or a level from `sensitive` up — before any other question: a fact is not asked
                      for, nor a doubt resolved, about something he may not have ordered. His standing `allow`
                      and `his_yes` do not clear it: both say the act is fine when HE orders it (V2-812 T-03).

    Returns `{verdict, why, needs, candidates, n, level}` — data for the caller to phrase in its own words.
    This module never writes a sentence the operator hears: that would be a rail on judgement.
    """
    missing = [str(m) for m in (missing or []) if str(m).strip()]
    cands = [str(c) for c in (candidates or []) if str(c).strip()]
    lvl = str(level or "standard").strip().lower()
    lvl = lvl if lvl in LEVELS else "standard"
    out = {"verdict": RUN, "why": "", "needs": missing, "candidates": cands, "n": radius, "level": lvl}

    # 0 · an act from a line that was not a clear request to the agent is asked first (V2-812 T-03)
    lic = line_licence() if licensed is _FROM_LINE else licensed
    if lic is False and (str(policy_key or "").strip() or _rank(lvl) >= _rank("sensitive")):
        return {**out, "verdict": ASK_CONSENT, "why": "the line was not clearly a request to the agent",
                "unlicensed": True}

    # 1 · a missing datum is not a permission question
    if missing:
        return {**out, "verdict": ASK_FACT, "why": "faltan datos para ejecutar"}

    # 2 · doubt about WHAT
    if len(cands) > 1:
        return {**out, "verdict": ASK_WHICH, "why": "más de uno encaja"}

    # 3 · a standing rule of his own decides the class before anything else about it — the rules cascade over
    #     this request's path (V2-806): the most specific row that covers it wins
    pol = class_policy(policy_key, scope)
    if pol == "never":
        return {**out, "verdict": REFUSE, "why": f"regla del operador: «{policy_key}» nunca"}
    if pol == "ask":
        return {**out, "verdict": ASK_CONSENT, "why": f"regla del operador: «{policy_key}» preguntar"}

    # 4 · the radius rail (V2-707). An unbounded call, or one that will touch more than one thing, is a
    #     different act from the one he named — and `allow` is a standing rule that does not cover a sweep.
    #     A RAIL, not a rule: no row of the rules table reaches it (V2-806).
    if not bounded or (radius is not None and radius > 1):
        return {**out, "verdict": ASK_CONSENT,
                "why": "alcance mayor que lo que nombró" if bounded else "no nombra sobre qué actúa"}

    # 5 · `allow` — or his own explicit order over a row he has seen — clears the class rail below, never the
    #     radius rail above
    if pol == "allow" or his_yes:
        return {**out, "why": "su orden sobre lo que ya ha visto" if his_yes and pol != "allow" else ""}

    # 6 · the class itself
    if _rank(lvl) >= _rank(ask_at(policy_key, scope)):
        return {**out, "verdict": ASK_CONSENT, "why": f"clase «{lvl}»"}
    return out


def act_key(cls: str, channel: str = "") -> str:
    """The consent key of an act: its class, refined by the channel it leaves through (`<class>@email`).
    `class_policy` falls back to the bare class, so a rule for one channel never reaches another (V2-800)."""
    cls, channel = str(cls or "").strip(), str(channel or "").strip().lower()
    return f"{cls}@{channel}" if cls and channel else cls


def decide_act(cls: str, *, channel: str = "", level: str = "", his_yes: bool = False, missing=(),
               candidates=(), radius: int | None = 1, bounded: bool = True, licensed=_FROM_LINE,
               subject: str = "") -> dict:
    """THE door for an act that reaches the real world OUTSIDE a widget's data-op (V2-805): a cluster message, an
    errand's reply under its mandate, a worker's click that commits him on a website.

    A widget's action reaches `decide` through `frontend.action_verdict` (its manifest's `consent_class`, refined
    by its `consent_scope` hook); these callers have no manifest row, so they name their class and channel here
    and get the SAME rule, the same defaults and the same user rules. `his_yes` is the grant the caller holds —
    his explicit order over a row he saw, or a mandate he gave for this very conversation; it clears the class
    rail and nothing above it (a missing fact, a doubt, his standing «ask»/«never», the radius).

    `subject` is the contact id of the person the act is about, when the caller resolved exactly one (V2-857
    phase 2): his rule for that person (`subject:<id>…`) then outranks his rule for the channel.

    `level` left empty is the class's DECLARED default (`nucleo/events/vocabulary`, V2-857 phase 1): money is
    `critical` and a message `sensitive` because the event type says so, not because each caller remembered to.
    Every decision is one `consent` event on the timeline — the type, its channel, the level and where it came from,
    the verdict and its reason — so a reader sees WHY an act left or stopped without opening the code."""
    from nucleo.events import vocabulary as _evoc
    out = decide(level=level or _evoc.level_of(cls), missing=missing, candidates=candidates, radius=radius,
                 bounded=bounded, policy_key=act_key(cls, channel), his_yes=his_yes, licensed=licensed,
                 scope={"subject": subject} if subject else None)
    _observe_act(cls, channel, out, his_yes=his_yes, subject=subject,
                 level_from="caller" if level else ("declared" if _evoc.declared(cls) else "default"))
    return out


def _observe_act(cls: str, channel: str, verdict: dict, *, his_yes: bool, level_from: str, subject: str = "") -> None:
    """The one `consent` event of an act's decision (V2-857 phase 1): the event type and channel, the verdict, the
    level and where it came from (`declared` by the vocabulary · `caller` measured it · `default` for a class nobody
    declared), the winning reason and whether his own yes was the grant. Never raises."""
    try:
        from voice.observer import emit
        emit("consent", "🔐 act decided at the one door", role="system",
             text=f"{act_key(cls, channel)} → {verdict.get('verdict')} ({verdict.get('why') or verdict.get('level')})"[:200],
             extra={"cat": "consent", "event": str(cls or ""), "channel": str(channel or ""),
                    "verdict": str(verdict.get("verdict") or ""), "level": str(verdict.get("level") or ""),
                    "level_from": level_from, "why": str(verdict.get("why") or "")[:160], "his_yes": bool(his_yes),
                    "subject": str(subject or "")})
    except Exception as e:  # noqa: BLE001 — the record never decides the act
        import logging
        logging.getLogger("zaelar.consent").debug(f"consent: decision not recorded ({e!r})")


def missing_facts(requires) -> list[str]:
    """Which of the facts an action DECLARES it needs are not in the operator's state (V2-712).

    The impure half, kept apart from `decide` on purpose so the rule itself stays a pure function of its
    arguments. `requires` is a list of memory slot names an action declares — `operator.phone`,
    `operator.email` — and this answers which of them the engine cannot supply. That is the whole of «tú ya
    tienes que saber quién soy yo […]. Y si no lo sabes, obviamente preguntas»: the question is about the
    DATUM, and the engine only asks for one it genuinely does not have.

    Fails toward ASKING: a memory it cannot read is a fact it does not have, and inventing a phone number
    into somebody's real booking is the failure this whole initiative exists to avoid.
    """
    names = [str(r).strip() for r in (requires or []) if str(r).strip()]
    if not names:
        return []
    try:
        from memory import api as _mem, slots as _slots
        have = _mem.state() or {}
    except Exception:  # noqa: BLE001
        return names
    out = []
    for n in names:
        if _known(n, have, _mem, _slots):
            continue
        out.append(n)
    return out


def _known(slot: str, have: dict, _mem, _slots) -> bool:
    """Is this fact on file? Asked against the TWO surfaces a slot really lives in.

    ⚠️ Measured 2026-09-16, and it is why this is not a one-liner: a slot is reflected in `state()` only when
    `memory/slots.py` gives it a `state_field`, and the reflected name is not the slot name —
    `operator.name` is stored as `operator_name`. The other identity slots this is FOR — `operator.phone`,
    `operator.email`, `operator.address` — have NO state field at all and live as pills, so a reader that
    only looked at `state()` reported every one of them missing and would have asked him for a phone number
    he had told the system months ago. The first version of this function guessed the last path segment
    (`operator.name` → `name`), which matches nothing in either surface.

    Fails toward ASKING: an unreadable memory is a fact we do not have, and inventing a phone number into
    somebody's real booking is the failure this whole initiative exists to avoid.
    """
    if str(have.get(slot) or "").strip():
        return True
    try:
        field = _slots.state_field(slot)
    except Exception:  # noqa: BLE001
        field = None
    if field and str(have.get(field) or "").strip():
        return True
    try:
        return bool(_mem.by_slot_prefix(slot, limit=1))
    except Exception:  # noqa: BLE001
        return False


def asks(verdict: dict | str) -> bool:
    """Whether a verdict stops to talk to the operator at all. One accessor so callers do not re-derive it."""
    v = verdict.get("verdict") if isinstance(verdict, dict) else verdict
    return str(v) in (ASK_FACT, ASK_WHICH, ASK_CONSENT, REFUSE)


# ── Writes: his standing rules are rows of the rules table ──────────────────────────────────────────────
# A spoken rule is understood ONCE, when it is written, by `rules.shape` (one structured call over the declared
# vocabulary) — no word table here decides what a sentence means (V2-806). This module keeps the one door code
# uses to write a class rule: the autoresponder's switch, a «yes, and don't ask me again».

def set_class(key: str, value: str, text: str = "") -> dict:
    """Set one standing class rule ('never'|'ask'|'allow') — a user row at the class's scope, refined by its
    channel when the key names one. This is the half `principles.md` calls the known gap: the operator's ANSWER
    becoming the default the next decision of the same class reads."""
    import rules
    key = str(key or "").strip()
    value = str(value or "").strip().lower()
    if not key or value not in rules.GATE_VALUES:
        return {}
    _migrate()
    rules.add(rules.class_scope(*rules.split_key(key)), "gate", "consent", value, text=text)
    return {key: value}


def _reset_for_tests() -> None:
    import rules
    rules._reset_for_tests()
