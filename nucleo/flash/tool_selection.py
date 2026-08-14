"""Selección PROGRESIVA de tools: el turno lleva la dirección hacia la que va, no el catálogo entero (V2-096 F2).

## La petición

> «Cuando alguien dice "hola, ¿qué tal?" no le vamos a mandar todos los widgets, todas las tools. Lo primero que
> vamos a decirle es: analiza esto, este es el abanico de posibilidades por donde podemos ir… e ir encaminando la
> dirección.»

## Por qué NO es una segunda llamada al modelo

Porque eso ya se midió y perdió (2026-08-02): partir el turno en dos peticiones baja el prompt de 9.729 a 1.221
tokens pero **sube el turno de 1.938 a 6.208 ms**, porque cada ida y vuelta cuesta 1,5-4,5 s. Dos viajes en el
camino crítico del turno común están descartados.

El abanico se resuelve sin viaje extra, en tres piezas de las que **solo la última necesitaría modelo**:

  1. ¿la frase está acabada?  → léxico, gratis (V2-096 F1, `accumulator`)
  2. ¿qué tools cargo?        → **RECUPERACIÓN O(K), gratis — esto es este módulo**
  3. ¿hay petición clara?     → sí necesita modelo, y es el hueco declarado (`accumulator.set_predicate`)

## Recuperar no es comprender, y por eso hay escotilla

V2-085 fijó un invariante duro: **un GATE mira ESTADO, jamás las palabras del turno** — si no, esconderías una
capacidad que sí existe. Este módulo no es un gate: es RECUPERACIÓN, la misma que `widgets/selection.py` ya hace
para elegir widgets con la capa `named` sobre el texto del turno. La diferencia entre las dos cosas es lo que
justifica usar palabras aquí: un gate DECIDE que algo no existe; una recuperación PROPONE candidatos y tiene que
degradar bien cuando falla.

La escotilla es `need_capability`: una tool minúscula que se añade **solo cuando se ha recortado algo**, y con la que
el modelo pide la familia que le falta. Si la llama, el llamador repite con esa familia cargada. Eso convierte el
error de recuperación en **un viaje extra medible** en vez de en una capacidad negada en silencio — que es el fallo
que de verdad rompe una conversación.

## Las familias que NUNCA se recortan, y por qué

`core` (escalar y fijar estilo), `web` (`web_search`) y `memory` (`recall`) se quedan siempre. Son las que un turno
puede necesitar **sin ningún aviso previo en el estado ni en las palabras**: «¿cuánto cuesta la entrada?» o «¿cuándo
es la cita de la ITV» no anuncian nada; simplemente no se pueden contestar sin la tool. Recortarlas para ahorrar
tokens sería cambiar coste por contestar mal, que es el intercambio equivocado.
"""
from __future__ import annotations

import os
import re
import unicodedata

from nucleo.flash.router import FAMILIES

# Familias intocables (ver el docstring). El resto se recupera.
ALWAYS: frozenset[str] = frozenset({"core", "web", "memory"})

# Pistas léxicas por familia. NO son un clasificador de intención: son SEMILLAS de recuperación, y su fallo lo
# absorbe `need_capability`. Deliberadamente cortas — la lista larga de verbos que el operador rechazó
# ([[feedback_no_hardcoded_understand]]) es lo que NO se hace aquí: no se decide qué quiere el operador, solo qué
# esquemas vale la pena poner delante del modelo para que lo decida ÉL.
_HINTS: dict[str, tuple[str, ...]] = {
    "widgets": ("widget", "tarjeta", "panel", "pantalla", "ventana", "abre", "abre", "cierra", "muestra",
                "muestrame", "ensename", "borra", "alias", "llama", "lista", "agenda", "card", "screen",
                "show", "close", "open", "delete"),
    "media": ("musica", "cancion", "suena", "spotify", "video", "youtube", "pon", "reproduce", "volumen",
              "podcast", "play", "music", "song", "sube", "baja"),
    "workers": ("para", "paralo", "cancela", "cancelalo", "detente", "worker", "tarea", "proceso", "busqueda",
                "informe", "responde", "contesta", "stop", "task"),
    "cluster": ("cluster", "meshkore", "peer", "agente", "invitacion", "commons", "conecta"),
    "messaging": ("mensaje", "whatsapp", "telegram", "correo", "email", "responde", "contesta", "mail"),
}


def _norm(s: str) -> str:
    n = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in n if not unicodedata.combining(c)).lower()


def _words(s: str) -> set[str]:
    return set(re.sub(r"[^\w\s]+", " ", _norm(s)).split())


NEED_CAPABILITY = {
    "type": "function",
    "function": {
        "name": "need_capability",
        "description": (
            "Use ONLY when this turn needs a capability whose tool you cannot see. Names the family; the turn is "
            "then retried with it loaded. Families: widgets (show/close/modify a card, change its data, aliases), "
            "media (music, video, volume), workers (stop/answer a running background task), cluster (talk to "
            "another agent), messaging (reply to a message). Do NOT use it for anything you can already do."),
        "parameters": {
            "type": "object",
            "properties": {"family": {"type": "string",
                                      "enum": ["widgets", "media", "workers", "cluster", "messaging"]}},
            "required": ["family"],
        },
    },
}

_family_of: dict[str, str] = {name: fam for fam, names in FAMILIES.items() for name in names}


def enabled() -> bool:
    """Kill-switch de 1ª clase. Un cambio que toca el ENRUTADO tiene que poder apagarse sin desplegar código:
    `ZAELAR_TOOL_SELECTION=0` devuelve el comportamiento de mandar el catálogo entero."""
    return (os.getenv("ZAELAR_TOOL_SELECTION", "1") or "").strip().lower() not in ("0", "false", "no", "off")


def select(tools: list[dict], *, turn_text: str = "", open_widgets=None,
           recent_families=None, force: set[str] | None = None) -> tuple[list[dict], dict]:
    """Recorta `tools` (que YA vienen gateadas por estado, `router.tools`) a lo que este turno puede necesitar.

    Devuelve `(tools_recortadas, informe)`. El informe viaja a la observabilidad: sin él, un recorte equivocado es
    un modelo que "se olvida" de una capacidad y nadie sabe por qué.

    Capas, de más a menos derecho a estar (misma escalera que `widgets/selection.py`):
      · `ALWAYS`   — nunca se recortan
      · `state`    — lo que el operador tiene DELANTE (widgets abiertos → familia widgets)
      · `forced`   — lo que el llamador exige (p. ej. tras un `need_capability`)
      · `named`    — lo que las palabras del turno sugieren
      · `recent`   — familias usadas en los últimos turnos (MRU), para que una conversación no pierda el hilo
    """
    if not enabled() or not tools:
        return tools, {"selection": "off"}

    keep = set(ALWAYS)
    keep |= set(force or ())
    if open_widgets:
        keep.add("widgets")                      # lo que tiene delante manda, sin mirar palabras
    ws = _words(turn_text)
    named: set[str] = set()
    for fam, hints in _HINTS.items():
        if ws & set(hints):
            named.add(fam)
    keep |= named
    keep |= {f for f in (recent_families or ()) if f in FAMILIES}

    out, omitted = [], set()
    for t in tools:
        name = (t.get("function") or {}).get("name", "")
        fam = _family_of.get(name)
        if fam is None or fam in keep:
            out.append(t)
        else:
            omitted.add(fam)

    if omitted:
        out.append(NEED_CAPABILITY)              # la escotilla, solo si de verdad falta algo

    report = {"selection": "on", "kept": sorted(keep), "omitted": sorted(omitted),
              "n_before": len(tools), "n_after": len(out), "named": sorted(named)}
    return out, report


def families_used(names) -> set[str]:
    """Familias a las que pertenecen unas tools llamadas — para alimentar la capa `recent` del turno siguiente."""
    return {_family_of[n] for n in (names or ()) if n in _family_of}
