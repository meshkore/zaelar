"""
nucleo/surfaces.py — WHERE the operator is going to see the result, decided when the errand is COMMISSIONED.

Operator, 2026-08-20: «si el worker tarda, el usuario se aburre y la experiencia es mala. Necesita ver en tiempo
real lo que está pasando». A worker can run for seven minutes; today the operator stares at nothing and the
surface where the answer will land is only chosen when the answer already exists — which is exactly too late to
open it early and stream progress into it.

So the surface becomes a FIRST-CLASS field of the errand, travelling with it from the escalation onwards.

THREE RULES, and each one is there because its opposite is a known failure:

  1. **Decided at commission time, not at delivery.** The point that decides to escalate already knows what the
     operator asked for; deciding later means nothing can be opened while the work happens.
  2. **CLOSED vocabulary.** Five values and no more. An open string drifts into a taxonomy nobody maintains, and
     then the frontend has to guess — which is how a surface contract dies.
  3. **Decided ONCE.** `set_once` never overwrites. Switching surface halfway is worse than choosing wrong: the
     operator is already looking at the first one.

The value is CHOSEN BY THE BRAIN that escalates (a `surface` argument on `escalate_to_slowbrain`), because it is
the only party that has the operator's actual sentence. `resolve()` is the backstop for every other door into
the dispatcher — auto-resume, confirm-gate re-launch, cluster peers, the Susurro — where nobody said anything.

Per `.meshkore/docs/architecture/zaelar-brain-worker-doctrine.md` this is a RESOURCE, so it must hold for any
errand: booking a table, a research report on 2nd-century-BC Greek culture, a rocket's task list, a Wallapop
search, houses in Los Angeles. Nothing here knows a single one of those domains, and nothing here may learn one.
"""
from __future__ import annotations

# ── the closed vocabulary ────────────────────────────────────────────────────────────────────────────────────
LIST = "lista"              # several things to compare/pick from  → results sheet, opened NOW
ITEM = "item"               # ONE thing with its detail            → results sheet, opened NOW
DOC = "informe"             # ONE written thing to READ at the end → documento sheet, opened NOW (V2-644)
WIDGET = "widget"           # new functionality the operator uses  → its box, with a loader
VOICE = "voz"               # it is told, there is nothing to look at → box
SILENT = "silenciosa"       # nothing to show at all               → only the activity hexagon

SURFACES = (LIST, ITEM, DOC, WIDGET, VOICE, SILENT)

#: Surfaces that open the results sheet before there is anything in it (the whole point of deciding early).
SHEET = frozenset({LIST, ITEM})

DEFAULT = VOICE

# Synonyms the model may reasonably emit. Deliberately SMALL: this maps wording to the SAME five values, it does
# not grow the vocabulary. Anything unknown falls back rather than inventing a sixth surface.
_ALIASES = {
    "list": LIST, "listado": LIST, "lista": LIST, "results": LIST, "resultados": LIST,
    "item": ITEM, "ficha": ITEM, "detalle": ITEM, "detail": ITEM, "single": ITEM,
    # V2-644 — the sixth value, not a synonym of `item`: an ITEM is a card you glance at (a product, a hotel),
    # a REPORT is a written piece you sit down and read, and it lands in the `documento` sheet, not `results`.
    "informe": DOC, "documento": DOC, "doc": DOC, "document": DOC, "report": DOC, "dossier": DOC,
    "widget": WIDGET, "app": WIDGET, "componente": WIDGET,
    "voz": VOICE, "voice": VOICE, "speech": VOICE, "chat": VOICE,
    "silenciosa": SILENT, "silencioso": SILENT, "silent": SILENT, "none": SILENT, "ninguna": SILENT,
}

# Fallback by errand kind, for the doors where nobody declared one. `code` is the widget GENERATOR, so its
# outcome really is a widget; `web` and research errands end in something to look at. Everything else is told.
_BY_KIND = {"code": WIDGET, "web": LIST, "research": LIST}


def normalize(value) -> str:
    """A declared surface → one of `SURFACES`, or "" if it is not one of ours.

    Returns "" rather than the default on purpose: the caller has to be able to tell «he said nothing» from «he
    said something we do not understand», because only the second one is worth a warning.
    """
    v = str(value or "").strip().lower()
    return _ALIASES.get(v, "")


def resolve(declared=None, kind: str = "generic") -> str:
    """The surface for an errand: what was declared if it is valid, otherwise derived from its kind."""
    return normalize(declared) or _BY_KIND.get(str(kind or "").strip().lower(), DEFAULT)


def set_once(rec, value) -> str:
    """Stamp the surface on a session record the FIRST time and never again (rule 3). Returns what stands.

    Changing surface mid-errand is not a correction, it is moving what the operator is already watching. If a
    later step disagrees, the place to fix it is the decision at commission time.
    """
    current = getattr(rec, "surface", "") or ""
    if current:
        return current
    stamped = resolve(value, getattr(rec, "kind", "generic"))
    try:
        rec.surface = stamped
    except Exception:  # noqa: BLE001
        return current or stamped
    return stamped


def opens_sheet(surface: str) -> bool:
    """Does this surface mean «open the results sheet now, before there is anything in it»?"""
    return (surface or "") in SHEET


def opens_doc(surface: str) -> bool:
    """Does this surface mean «open the DOCUMENT sheet now, with its process view» (V2-644)?

    Deliberately not part of `SHEET`: the results sheet and the document sheet are different boxes with
    different delivery contracts, and every `opens_sheet` caller (open, retitle, close, browser delivery)
    must NOT start treating a report errand as a list errand — that is the exact confusion this value exists
    to remove."""
    return (surface or "") == DOC
