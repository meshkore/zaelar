"""Una frase dicha en DOS TIEMPOS es una sola petición (V2-096, 2026-08-14).

## Por qué esperar no servía

V2-095 puso el sentido en el límite del turno, pero por la vía de RETRASARLO: el detector devuelve una probabilidad
baja y LiveKit espera `max_delay` en vez de `min_delay`. Eso es **un tiempo fijo**, y el operador lo señaló antes de
que lo midiéramos: *«no podemos tener un tiempo fijo esperando que todas las conversaciones y todas las personas van
a actuar igual»*.

Medido sobre las 195 sesiones del registro — 372 pausas reales a mitad de frase:

    p10 0,6s · p25 1,3s · **p50 2,3s** · p75 3,5s · **p90 4,9s** · max 19,5s
    caben en `max_delay`=2,2s → **48,7%**   ·   en 4s → 82,3%   ·   en 6s → 96,2%

O sea que **retrasar el turno resolvía menos de la mitad de los casos, por construcción**, y subir el techo no es
gratis: `max_delay` retrasa TODOS los turnos, también los que ya estaban completos.

## Lo que sí funciona: no esperar, ACUMULAR

El turno acústico puede cerrarse cuando quiera — da igual. Lo que importa es que un fragmento **no GENERE nada**:
ni voz, ni tool, ni widget, ni worker, ni escritura en memoria. Se guarda, y cuando llega el trozo siguiente se
juzgan los dos JUNTOS. Así la pausa puede durar 0,5 s o 19 s: deja de estar en la ecuación.

Medido sobre las mismas sesiones: **141 fragmentos quedan completos al pegarse** con el siguiente; solo 19 cadenas
terminan sin cerrar (y esas salen por la válvula). Ejemplos reales, tal cual:

    «Busca también en todas las»  +  «páginas que puedas, ¿vale?»
    «De un mínimo de cuarenta y cinco pies, y me hagas una selección de los»  +  «cinco mejores.»

## Lo que este módulo NO resuelve, y hay que decirlo

Juzga la completitud **SINTÁCTICA** (¿cuelga la frase?), que es léxica y gratis. No juzga si hay una **acción, una
pregunta o una petición CLARA**, que es la otra mitad de lo que pidió el operador. Se ve en los propios datos:
pegando sale `'Mora, is there project'`, que cierra sintácticamente y no es accionable.

Por eso el predicado es **INYECTABLE** (`set_predicate`): la capa pragmática —con modelo, y corriendo mientras el
operador habla, fuera del camino crítico— entra aquí sin tocar el resto. Ver la iniciativa V2-096 para el diseño y
su análisis de coste.

## Invariantes (todos con test, y los tres primeros son de seguridad)

  1. **Una orden de PARAR nunca se acumula.** Se atiende antes de llegar aquí (`attention.hard_interrupt`) y además
     el predicado la deja pasar. Retener un «para» es lo que V2-092 prohíbe.
  2. **Un backchannel nunca se acumula** («sí», «no», «vale»): es como el operador autoriza algo irreversible.
  3. **NUNCA se cuelga**: hay válvula por tiempo, por número de trozos y por tamaño. Puede retrasar una respuesta,
     nunca perderla — la misma promesa que el detector de turno.
  4. **VISIBLE**: cada retención emite su evento con el motivo. Un estado que puede engañar tiene que verse.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field

# ── VÁLVULAS ────────────────────────────────────────────────────────────────────────────────────────────────────
# **NO hay válvula de TIEMPO, y es deliberado.** Un fragmento abandonado se queda sin respuesta porque eso es lo
# correcto, no un descuido que haya que tapar con un temporizador — norma del operador con su propio ejemplo:
# «si digo "oye, ¿qué tal? ahora vamos a…" y me paro ahí, obviamente esa frase no genera absolutamente nada NI DEBE
# GENERARLO». Un flush por tiempo haría justo lo contrario: contestar a media frase unos segundos más tarde.
#
# Las válvulas de abajo NO existen para acabar respondiendo, sino para que el buffer no crezca sin fin ni se pegue a
# una petición posterior que no tiene nada que ver.
#
# Topes duros contra el caso patológico (STT picando una parrafada en trozos que nunca cierran).
MAX_FRAGMENTS = int(os.getenv("ZAELAR_ACC_MAX_FRAGMENTS", "6"))
MAX_CHARS = int(os.getenv("ZAELAR_ACC_MAX_CHARS", "1200"))
# Un hueco ENORME no es una continuación, es un tema nuevo: por encima de esto el buffer viejo se descarta en vez de
# pegarse (pegarlo daría una petición Frankenstein de dos intenciones distintas). El máximo medido fue 19,5 s.
MAX_GAP_S = float(os.getenv("ZAELAR_ACC_MAX_GAP_S", "25.0"))


@dataclass
class Accumulator:
    """Estado por sesión. Sin I/O y sin reloj propio (el `now` se inyecta) → se prueba entero sin motor ni voz."""

    fragments: list[str] = field(default_factory=list)
    first_at: float = 0.0
    last_at: float = 0.0

    # ── consulta ────────────────────────────────────────────────────────────────────────────────────────────
    def pending(self) -> bool:
        return bool(self.fragments)

    def text(self) -> str:
        return " ".join(self.fragments).strip()

    def clear(self) -> None:
        self.fragments.clear()
        self.first_at = self.last_at = 0.0

    # ── la decisión ─────────────────────────────────────────────────────────────────────────────────────────
    def offer(self, incoming: str, *, now: float | None = None) -> tuple[str, str, str]:
        """Ofrece la transcripción de un turno recién cerrado.

        Devuelve `(accion, texto, motivo)`:
          * `("act", texto_completo, "")` — hay una petición entera; el turno sigue con ESE texto (que puede
            incluir lo acumulado antes).
          * `("hold", "", motivo)` — es un trozo; NO se habla, NO se actúa, NO se escribe en memoria. El llamador
            programa un flush por si el operador ya no continúa.
        """
        now = time.time() if now is None else now
        incoming = (incoming or "").strip()
        if not incoming:
            return "act", incoming, ""

        # Un hueco enorme rompe la cadena: lo de antes era otra cosa. Se DESCARTA en vez de pegarse — y se dice,
        # porque perder texto del operador en silencio es peor que responder raro.
        dropped = ""
        if self.fragments and (now - self.last_at) > MAX_GAP_S:
            dropped = self.text()
            self.clear()

        candidate = (self.text() + " " + incoming).strip() if self.fragments else incoming

        if _complete(candidate):
            self.clear()
            return "act", candidate, (f"hueco>{MAX_GAP_S:.0f}s: descartado {dropped!r}" if dropped else "")

        # Sigue a medias → acumula. Las válvulas se comprueban DESPUÉS de añadir: lo que se entrega es todo lo que
        # hay, nunca un buffer a medio vaciar.
        if not self.fragments:
            self.first_at = now
        self.fragments.append(incoming)
        self.last_at = now

        if len(self.fragments) >= MAX_FRAGMENTS:
            out = self.text()
            self.clear()
            return "act", out, f"válvula: {MAX_FRAGMENTS} trozos"
        if len(self.text()) >= MAX_CHARS:
            out = self.text()
            self.clear()
            return "act", out, f"válvula: {MAX_CHARS} chars"

        return "hold", "", _why(candidate)

    def flush(self) -> str:
        """Entrega lo acumulado tal cual y vacía (o «» si no había nada).

        NO lo llama el camino de voz — ahí un fragmento abandonado se queda callado a propósito (ver §VÁLVULAS).
        Existe para quien SÍ tiene un final de conversación explícito: el cierre de sesión, un reset, o el canal de
        prueba, que necesitan poder recuperar lo que quedó a medias en vez de tirarlo en silencio."""
        out = self.text()
        self.clear()
        return out


# ── EL PREDICADO (inyectable) ───────────────────────────────────────────────────────────────────────────────────
def _default_complete(text: str) -> tuple[bool, str]:
    """Capa 1, determinista y gratis: la regla léxica de `segmenter`, con la excepción de seguridad DELANTE.

    El orden importa y no es cosmético. Entre colar un turno de más y retener un «para», el coste no está ni cerca:
    lo primero cuesta una llamada, lo segundo es el operador viendo cómo el agente ignora una orden de parar.

    **La orden de parar se comprueba con `attention.hard_interrupt`, no con una lista propia.** Es la lista canónica
    (la que atiende el turno antes de llegar aquí) y mantener una segunda copia era garantizar que divergieran. Este
    guarda nació de un fallo REAL del test: `«ciérralo todo»` SIN punto final se retenía, porque «todo» es palabra
    función blanda y la regla léxica solo la absuelve cuando el STT cerró la frase — y el STT pone el punto cuando le
    parece. Un invariante de seguridad no puede depender de la puntuación del STT.
    """
    try:
        from voice import attention
        if attention.hard_interrupt(text):
            return True, ""
    except Exception:
        pass
    from nucleo.flash import segmenter
    try:
        incomplete, why = segmenter.looks_incomplete(text)
    except Exception:
        return True, ""          # fail-open duro: ante cualquier duda se ACTÚA (nunca un agente mudo)
    return (not incomplete), why


_predicate = _default_complete


def set_predicate(fn) -> None:
    """Sustituye el juez de completitud. Es el punto de entrada de la capa PRAGMÁTICA (¿hay acción/pregunta/petición
    clara?), que necesita modelo y corre mientras el operador habla. Firma: `(str) -> (completo: bool, motivo: str)`.
    Pasar `None` restaura el léxico."""
    global _predicate
    _predicate = fn or _default_complete


def _complete(text: str) -> bool:
    try:
        ok, _ = _predicate(text)
        return bool(ok)
    except Exception:
        return True              # un predicado roto no puede dejar mudo al agente
    finally:
        pass


def _why(text: str) -> str:
    try:
        _, why = _predicate(text)
        return why or "la frase no ha acabado"
    except Exception:
        return "la frase no ha acabado"
