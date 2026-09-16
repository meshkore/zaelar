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

## Sensitivity is DECLARED DATA, layered like `style_policy` (V2-633)

The layering is not invented here — `nucleo/style_policy.py` already ships it and this module deliberately
mirrors it file for file: factory defaults in `nucleo/genesis.json`, per-install overrides in
`<workspace>/config/consent.json`, written the moment the operator says so and read per use, so a rule he
states governs the very next turn and survives a restart.

A widget declares `"security": "standard"` (every shipped widget today, exactly as he asked); an action may
declare its own `"sensitivity"`. Today's `confirm:true` is READ as `sensitive` rather than deleted — so no
behaviour changes by accident, only what V2-712 says changes.

⚠️ `critical` is the one level that asks even with a clear order and complete data: **money leaving his
accounts**. That is a rail on the consequence, it is the class the V2-705 contract was born from, and it is
not negotiable by convenience.
"""
from __future__ import annotations

import json
import re
import time
import unicodedata
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

_GENESIS_PATH = Path(__file__).resolve().parent / "genesis.json"
_cache: dict = {"path": None, "mtime": None, "data": {}}
_genesis_cache: dict | None = None


def _rank(level: str) -> int:
    try:
        return LEVELS.index(str(level or "").strip().lower())
    except ValueError:
        return LEVELS.index("standard")


# ── The layered store (same shape as style_policy) ──────────────────────────────────────────────────────

def _overrides_path() -> Path:
    from nucleo import workspace as _ws
    return _ws.root() / "config" / "consent.json"


def _genesis() -> dict:
    global _genesis_cache
    if _genesis_cache is None:
        try:
            _genesis_cache = dict(json.loads(_GENESIS_PATH.read_text()).get("consent") or {})
        except Exception:  # noqa: BLE001 — a broken genesis must not stop the engine booting
            _genesis_cache = {}
    return json.loads(json.dumps(_genesis_cache))     # deep copy: `classes` is a nested dict


def _overrides() -> dict:
    p = _overrides_path()
    try:
        mtime = p.stat().st_mtime_ns
    except OSError:
        if _cache["path"] == str(p):
            _cache.update(mtime=None, data={})
        return {}
    if _cache["path"] == str(p) and _cache["mtime"] == mtime:
        return _cache["data"]
    try:
        data = json.loads(p.read_text())
        data = data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001
        data = {}
    _cache.update(path=str(p), mtime=mtime, data=data)
    return data


def _write_overrides(data: dict) -> None:
    p = _overrides_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    _cache.update(path=None, mtime=None, data={})


def policy() -> dict:
    """genesis ⊕ overrides. `classes` merges KEY BY KEY: an operator who changed one standing rule must not
    silently lose the other factory ones, which a whole-dict replace would do."""
    eff = _genesis()
    ov = _overrides()
    classes = dict(eff.get("classes") or {})
    classes.update({k: v for k, v in (ov.get("classes") or {}).items() if isinstance(k, str)})
    for k, v in ov.items():
        if k in eff and k != "classes":
            eff[k] = v
    eff["classes"] = classes
    return eff


def ask_at() -> str:
    """The lowest level that asks for consent EVEN WHEN the order is clear, the target resolved and the data
    complete. Genesis says `critical` — the single knob that answers «estoy hasta los huevos de confirmar»."""
    lvl = str(policy().get("ask_at", "critical")).strip().lower()
    return lvl if lvl in LEVELS else "critical"


def class_policy(key: str) -> str:
    """A standing rule of the operator's for a named class: 'never' | 'ask' | 'allow' | '' (unset).

    His own example is the one that ships: `messaging.autorespond: "never"` — PRESET, not hardcoded. «Contesta
    tú los correos de logística» flips it, and the next decision of that class reads the new value.
    """
    v = str((policy().get("classes") or {}).get(str(key or "").strip(), "")).strip().lower()
    return v if v in ("never", "ask", "allow") else ""


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


# ── THE RULE ────────────────────────────────────────────────────────────────────────────────────────────

def decide(*, level: str = "standard", missing=(), candidates=(), radius: int | None = 1,
           bounded: bool = True, policy_key: str = "") -> dict:
    """Act, or ask — and if asking, WHICH of the three useful questions it is.

    Every argument is something another layer already measured; nothing here reads text or guesses intent.

      · `missing`   — facts the action needs and the engine does not have (names, not values).
      · `candidates`— labels of the things that matched, when more than one did.
      · `radius`    — how many things this will touch, when it is known. `None` means «not counted».
      · `bounded`   — whether the call names WHAT it hits at all. A sweep with no selector is unbounded, and
                      that is the V2-707 rail: «vacía la agenda» is not «borra la cita del dentista».
      · `policy_key`— the class this belongs to, for the operator's standing rules (`messaging.autorespond`).

    Returns `{verdict, why, needs, candidates, n, level}` — data for the caller to phrase in its own words.
    This module never writes a sentence the operator hears: that would be a rail on judgement.
    """
    missing = [str(m) for m in (missing or []) if str(m).strip()]
    cands = [str(c) for c in (candidates or []) if str(c).strip()]
    lvl = str(level or "standard").strip().lower()
    lvl = lvl if lvl in LEVELS else "standard"
    out = {"verdict": RUN, "why": "", "needs": missing, "candidates": cands, "n": radius, "level": lvl}

    # 1 · a missing datum is not a permission question
    if missing:
        return {**out, "verdict": ASK_FACT, "why": "faltan datos para ejecutar"}

    # 2 · doubt about WHAT
    if len(cands) > 1:
        return {**out, "verdict": ASK_WHICH, "why": "más de uno encaja"}

    # 3 · a standing rule of his own decides the class before anything else about it
    pol = class_policy(policy_key)
    if pol == "never":
        return {**out, "verdict": REFUSE, "why": f"regla del operador: «{policy_key}» nunca"}
    if pol == "ask":
        return {**out, "verdict": ASK_CONSENT, "why": f"regla del operador: «{policy_key}» preguntar"}

    # 4 · the radius rail (V2-707). An unbounded call, or one that will touch more than one thing, is a
    #     different act from the one he named — and `allow` is a standing rule that does not cover a sweep.
    if bool(policy().get("unbounded_asks", True)) and (not bounded or (radius is not None and radius > 1)):
        return {**out, "verdict": ASK_CONSENT,
                "why": "alcance mayor que lo que nombró" if bounded else "no nombra sobre qué actúa"}

    # 5 · `allow` clears the class rail below, never the radius rail above
    if pol == "allow":
        return out

    # 6 · the class itself
    if _rank(lvl) >= _rank(ask_at()):
        return {**out, "verdict": ASK_CONSENT, "why": f"clase «{lvl}»"}
    return out


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


# ── Spoken overrides (sibling of style_policy.apply_directive) ──────────────────────────────────────────
# Coarse ON PURPOSE, and for the same reason as its sibling: only concepts that can be matched without
# understanding may flip a stored flag. Everything else still reaches the model as a rule in `state.rules` —
# nothing the operator says is lost, it just does not silently rewrite a policy nobody can audit.

def _norm(text: str) -> str:
    t = unicodedata.normalize("NFKD", (text or "").lower())
    return " ".join("".join(c for c in t if not unicodedata.combining(c)).split())


_LESS_FRICTION_RE = re.compile(
    r"\b(?:no (?:me )?pregunt\w+|deja de pregunt\w+|sin pregunt\w+|no (?:me )?pidas (?:permiso|confirmacion)|"
    r"no (?:hace falta|necesito) confirmar|hazlo (?:y ya|sin mas|directamente)|ejecuta sin parar|"
    r"stop asking|don'?t ask (?:me )?(?:again|for confirmation)|just do it)\b")
_MORE_FRICTION_RE = re.compile(
    r"\b(?:pregunt\w+ (?:siempre|antes)|pideme (?:permiso|confirmacion)|confirma (?:siempre|antes de)|"
    r"always ask|ask (?:me )?(?:first|before)|check with me)\b")


def _flags_for(text: str) -> dict:
    n = _norm(text)
    if _LESS_FRICTION_RE.search(n):
        return {"ask_at": "critical"}
    if _MORE_FRICTION_RE.search(n):
        return {"ask_at": "sensitive"}
    return {}


def apply_directive(text: str) -> dict:
    """Persist what a spoken directive names, effective on the next decision. `{}` = it named nothing this
    store can act on, which is not a failure: the model still receives the sentence as a rule."""
    flags = _flags_for(text)
    if not flags:
        return {}
    data = dict(_overrides())
    data.update(flags)
    data["_set_at"] = int(time.time())
    _write_overrides(data)
    return flags


def set_class(key: str, value: str) -> dict:
    """Set one standing class rule ('never'|'ask'|'allow'). This is the half `principles.md` calls the known
    gap: the operator's ANSWER becoming the default the next decision of the same class reads."""
    key = str(key or "").strip()
    value = str(value or "").strip().lower()
    if not key or value not in ("never", "ask", "allow"):
        return {}
    data = dict(_overrides())
    classes = dict(data.get("classes") or {})
    classes[key] = value
    data["classes"] = classes
    data["_set_at"] = int(time.time())
    _write_overrides(data)
    return {key: value}


_TOPIC_RE = re.compile(r"\bpregunt\w*|confirm\w*|permiso|friccion|ask\b")


def retract_directive(text: str) -> dict:
    """Release the override a retired rule had set — back to genesis."""
    if not _TOPIC_RE.search(_norm(text)):
        return {}
    data = dict(_overrides())
    released = {k: data.pop(k) for k in ("ask_at",) if k in data}
    if released:
        _write_overrides(data)
    return released


def _reset_for_tests() -> None:
    global _genesis_cache
    _genesis_cache = None
    _cache.update(path=None, mtime=None, data={})
