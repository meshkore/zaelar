"""nucleo/flash/show_guard.py — qué puede EJECUTAR un «abre/muéstrame X» puro.

Extraído de `router_guards.py` en V2-713 R1. El motivo es el de siempre en este repo: el trinquete de
arquitectura se paga EXTRAYENDO un módulo, nunca subiendo un techo — y el guarda del show es un concepto
entero (tres clases de verbo, la decisión, su sombra) viviendo dentro de un cajón de sastre que además
mezclaba dinero, login y cierre. `router_guards` sigue re-exportando los nombres, así que ningún llamante
cambia.

## De qué va

Un «abre la agenda» NO puede ejecutar una mutación que el operador no pidió: el incidente fundacional es un
`add_meeting` alucinado, con título y fecha inventados, sobre una orden que solo decía «abre».

Lo que costó una segunda vuelta fue CÓMO reconocerlo. La primera versión preguntaba «¿es una acción de
vista?», y eso veta de más: medido el 2026-09-16, «abre música y sigue con la pista» se lee como show puro —
«sigue» está deliberadamente fuera de la tabla de activación porque el stem choca con «el siguiente» — así
que un `resume` bien elegido se descartaba y el operador se quedaba mirando una tarjeta quieta.

La salida NO era ampliar la tabla de verbos: es el movimiento que V2-712 acaba de retirar del
consentimiento, crece un incidente cada vez y la frase siguiente se escribe de otra forma. Así que **lo
declara el widget**: `"activation": true` significa «esto cambia lo que el widget está HACIENDO, no lo que
guarda ni lo que muestra». Sin declarar = bloqueado, que es exactamente el comportamiento de hoy: el defecto
por defecto es el seguro y un widget que nadie ha tocado se comporta igual que ayer.

Dos heurísticas intentadas antes NO sobrevivieron, las dos cazadas por tests antes de commitear, y se dejan
escritas porque marcan dónde está la frontera: «sin payload = inofensivo» (`agenda:clear_all` tampoco lleva
payload y vacía la agenda entera) y «sin payload y no destructiva = inofensivo» (`navegador:open` carga una
URL e `imagenes:clear` vacía el visor, y la pregunta «¿quita algo?» dice que no a las dos). Una heurística en
la frontera de un raíl sigue encontrando el caso que no pensó; una declaración no.
"""
from __future__ import annotations

import re as _re

from .text_norm import _norm_txt

_SHOW_VERB_RE = _re.compile(r"\b(muestra|muestrame|ensena|ensename|abre|abreme|abrir|mostrar|ensenar|ver|"
                            r"visualiza|saca|pon(?:me)? en pantalla)\b")
# Match by STEM (without a final \b): 'anad' covers añade/añadir, 'apunt' covers apunta/apuntar, etc. (after
# accent-stripping by _norm_txt).
_CHANGE_VERB_RE = _re.compile(r"\b(anad|apunt|agreg|marca|quita|borr|elimin|cambi|aplaz|silenci|crea|edit|modific|"
                              r"met[ae]|programa|reserv|pon(?!(?:me|nos|te)?\s*en\s*pantalla)|añad)")
# Verbs that set something RUNNING. Neither showing nor changing data, so `_CHANGE_VERB_RE` never covered them —
# and it should not: nothing here mutates a record. Kept SHORT and stem-based on purpose (`inici` is out: it also
# matches the noun «el inicio», and a false positive here disarms a guard that exists to catch a hallucinated
# `add_meeting`). `pon`/`ponlo` already belong to the change list, with its «en pantalla» carve-out.
# `reanud` IS in: resuming playback is the same order as starting it, and its noun collision («la reanudación»,
# sportscast vocabulary) is far rarer than `inici`'s «el inicio». `resum` is OUT for the same reason `inici` is:
# «el resumen» and «la versión resumida» ride along with genuine show orders all the time.
_ACTIVATE_VERB_RE = _re.compile(r"\b(arranc|reproduc|empiez|empez|reanud|play|start)")


def is_pure_show_request(text: str) -> bool:
    """True if the turn is purely about OPENING/SHOWING a widget (with no intent to CHANGE data or to SET
    something RUNNING). Execution GUARD for widget_data: "abre/muéstrame el widget X" must NEVER execute a
    data-op (the model sometimes slips in an invented 'unhide' action or HALLUCINATES an add_meeting) →
    redirect it to showing the card. Deterministic, Spanish.

    The third class is the fix (V2-595): «muéstrame el primero, ARRÁNCALO» carries a show verb and no *change*
    verb — nothing in this list is about changing data, correctly — so it read as a pure show and the guard
    discarded the `play_item` the model had chosen right. Measured live in session `abe9942b`: the card stayed
    on «No hay ningún vídeo cargado» while the turn said «Aquí lo tienes». Starting playback is neither showing
    a card nor mutating a record: it is ACTIVATION, and an order that names it is not a pure show.
    """
    n = _norm_txt(text)
    if not _SHOW_VERB_RE.search(n):
        return False
    return not (_CHANGE_VERB_RE.search(n) or _ACTIVATE_VERB_RE.search(n))


# Words that ride along with EVERY «abre la mensajería» and name no object of their own: articles,
# possessives, clitics, prepositions and courtesy. They are dropped before asking WHAT the show verb points at.
def _shadow(wid: str, action: str, text: str, rule: str) -> None:
    """Cada descarte de este guarda, a SOMBRA — para poder retirarlo con un número (V2-713 R1).

    Un guarda que veta la elección del modelo no se juzga leyendo el código: hace falta saber cuántas veces
    tiró algo que estaba bien. V2-711 dejó el lector (`/api/observability/shadow`) y este guarda no emitía
    nada, así que su coste era invisible. Best-effort: contar un veto nunca puede tumbar un turno.
    """
    try:
        from voice.observer import emit as _emit
        _emit("widget", "gate_shadow", text=(text or "")[:160],
              extra={"id": wid, "action": action, "rule": rule, "gate": "pure-show"})
    except Exception:  # noqa: BLE001
        pass


def show_request_blocks_data_action(text: str, wid: str, action: str, payload=None) -> bool:
    """True when a PURE show order must be answered by showing the CARD instead of running the data-op the
    model chose (V2-545).

    `is_pure_show_request` says «this is a show order with no intent to change anything». It cannot say what
    the show order POINTS AT, and it never could: «ábreme la mensajería» (the card), «ábreme el Telegram» (a
    lens inside it) and «abre el mensaje de Francisco» (an element inside it) are the same shape. The first
    attempt (V2-544) tried to read the object out of the words, matching them against the widget's manifest
    aliases — and mensajeria's aliases ARE its lens names, so «ábreme el Telegram» classified as the card and
    the card, already on screen, did nothing (measured live 2026-09-01).

    So the question moved off the text and onto the ACTION: the widget declares which of its actions are
    display-only (`"view": true`, see `widgets/actions.py::is_view`). A pure show order may run one of those
    and nothing else. Any other data-op on a pure show is the failure this guard was written for — «abre la
    agenda» hallucinating an `add_meeting` — and still gets redirected to showing the card.

    The caller does not choose between showing and applying: on a view action it does BOTH (bring the card up,
    then apply the view), which is what «ábreme el Telegram» means and dissolves the card-vs-inside ambiguity
    instead of guessing it.

    Fails CLOSED (True = only show) if the catalog cannot be read: a show that does nothing is a smaller
    failure than an invented mutation.
    """
    if not is_pure_show_request(text):
        return False
    try:
        from widgets import runtime as _rt
        if _rt.get(wid) is None:
            return False                      # not a known widget — this guard has nothing to say about it
        from nucleo.flash import frontend as _fe
        from widgets import runtime as _rt2
        if _fe.action_is_view(wid, action):
            return False
        spec = ((_rt2.get(wid) or {}).get("actions") or {}).get(action) or {}
        if spec.get("activation") is True:
            return False
        # V2-713 R1 — ACTIVATION IS NOT AN INVENTED MUTATION, and this guard could not tell them apart.
        # Measured 2026-09-16: «abre música y sigue con la pista» reads as a pure show (no change verb, and
        # «sigue» is deliberately NOT in `_ACTIVATE_VERB_RE` — the stem collides with «el siguiente»), so a
        # correctly chosen `resume` was discarded and the operator got a card that did nothing.
        #
        # Widening the verb list is the move this repo just retired from consent (V2-712): it grows one
        # incident at a time and the next sentence spells it differently. So the widget DECLARES it, with
        # `"activation": true` — «esto cambia lo que el widget está HACIENDO, no lo que guarda ni lo que
        # muestra». Undeclared means blocked, which is exactly today's behaviour: the default is the safe one
        # and nothing changes for a widget nobody has touched.
        #
        # ⚠️ Two attempts that did NOT survive contact, both caught by tests before shipping:
        #   · «sin payload = inofensivo» — `agenda:clear_all` carries no payload either and empties the
        #     agenda;
        #   · «sin payload y no destructiva = inofensivo» — `navegador:open` loads a URL and `imagenes:clear`
        #     empties the viewer, and `contract.is_destructive` says no to both because it answers «¿quita
        #     algo?», which is a different question. A heuristic that guesses at the boundary of a rail keeps
        #     finding the case it did not think of; a declaration does not.
        _shadow(wid, action, text, "not-declared-activation")
        return True
    except Exception:  # noqa: BLE001
        return True
