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

## Layer 2, the LLM judge (V2-102, 2026-08-16) — never again "incomplete" by a lexical rule's final word

Layer 1 (`_predicate`) judges **SYNTACTIC** completeness (does the sentence dangle?), which is lexical, free,
and only covers es/en. A REAL bug exposed it: "dame los datos personales que conoces de mi" (give me the
personal data you know about me) got held THREE times without ever generating a reply — unaccented "mi" is
phonetically «mí» (the pronoun, a COMPLETE sentence) but the lexical rule reads it as the possessive ("mi
coche", incomplete), and this module has NO time-based flush, by design: a bad lexical read meant a real
request was lost FOREVER, not just late.

When layer 1 says incomplete, `offer()` now `await`s layer 2 (`_judge`, a real model, any language — no
per-language word tables) for a second opinion: `"complete"` (act on it), `"ask"` (speak a clarifying
question RIGHT NOW instead of waiting in silence for something that may never come), or `"incomplete"`
(layer 1 was right, keep accumulating). The gap valve (§VALVES) also consults the judge before discarding —
see `_speak_acc_drop` in `voice/engine/llm/providers/nucleo.py`. With this, **no fragment ever ends in
silence without an intelligent decision**: it ends in ACTING, ASKING, or an acknowledged discard the judge
confirmed truly has nothing actionable in it — never "got no reply and nobody knows why".

Injectable (`set_judge`), same as layer 1 (`set_predicate`) — see the V2-102 initiative for the design and
why the bounded layer-1 wait was kept instead of always resolving on the first judgment.

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
# una petición posterior que no tiene nada que ver. There is still no TIMER that fires `offer()` on its own — the
# gap valve stays reactive, evaluated on the NEXT call, never on a clock of its own. What DOES change (V2-102):
# before a discard turns into a generic "lost it" notice, the caller (`_speak_acc_drop`) gives the JUDGE one
# last look — see the module docstring, §layer 2.
#
# Topes duros contra el caso patológico (STT picando una parrafada en trozos que nunca cierran).
MAX_FRAGMENTS = int(os.getenv("ZAELAR_ACC_MAX_FRAGMENTS", "6"))
MAX_CHARS = int(os.getenv("ZAELAR_ACC_MAX_CHARS", "1200"))
# Un hueco ENORME no es una continuación, es un tema nuevo: por encima de esto el buffer viejo se descarta en vez de
# pegarse (pegarlo daría una petición Frankenstein de dos intenciones distintas). El máximo medido fue 19,5 s.
MAX_GAP_S = float(os.getenv("ZAELAR_ACC_MAX_GAP_S", "25.0"))


def _norm_text(s: str) -> str:
    return " ".join((s or "").lower().split())


def _grows(prev: str, cur: str) -> bool:
    """True if `cur` is the SAME utterance as `prev`, only longer (2026-08-15 finding, session `d4b2bc35`).

    The acoustic layer can keep a turn open across several STT finals while its own turn-detector — the SAME
    lexical predicate this module uses (`segmenter.looks_incomplete`, wired into `SemanticTurnDetector`) — keeps
    vetoing closure. When it does, `incoming` on the NEXT `offer()` call is the whole utterance so far, not a
    fresh delta: LiveKit's `ChatContext` already grew it. Blindly appending on top would double-count the shared
    prefix. Reproduced verbatim on that session: fragment 1 `"Me refería a mi información,"`, fragment 2
    `"Me refería a mi información, personal, dónde vivo, en qué trabajo,"` (already the full turn) — appended
    naively, `text()` became `"Me refería a mi información, Me refería a mi información, personal…"`. Structural,
    not semantic — mirrors `_extends()` in `voice/engine/llm/providers/nucleo.py`, which detects the identical
    pattern one layer up (a stale in-flight turn superseded by a longer one)."""
    p, c = _norm_text(prev), _norm_text(cur)
    return bool(p) and len(c) > len(p) and c.startswith(p)


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
    async def offer(self, incoming: str, *, now: float | None = None) -> tuple[str, str, str, str]:
        """Offers the transcript of a turn that just closed.

        Returns `(action, text, reason, dropped)`:
          * `("act", full_text, "", dropped)` — there's a whole request; the turn continues with THAT text
            (which may include what was accumulated before).
          * `("ask", accumulated_text, question, dropped)` — (V2-102) looks like a request but is missing
            something concrete; `question` is what needs to be SAID right now (out of band) instead of
            waiting in silence. NOT written to memory nor dispatched to the FlashBrain for this turn — the
            question IS the response.
          * `("hold", "", reason, dropped)` — it's a fragment; nothing is spoken, acted on, or written to
            memory. The caller schedules a flush in case the operator never continues it.

        `descartado` (2026-08-15 fix): non-empty in EITHER branch, it carries whatever this call's gap valve
        (> MAX_GAP_S) just discarded. It used to travel embedded in the "act" branch's `motivo` only, so a call
        that landed on "hold" instead — the common case: the fragment that triggers a drop is usually itself
        incomplete — lost it with no trace at all. A field of its own, independent of the hold reason, so the
        caller can ALWAYS surface a discard without having to parse a sentence to find it.

        Async since V2-102: layer 1 (`_complete`, lexical, sync) still decides the FAST path alone — this only
        awaits the layer-2 JUDGE (`_judge`, real LLM, any language) when layer 1 says incomplete. A misjudged
        "incomplete" from layer 1 alone used to mean a real request held FOREVER (`accumulator.py` has no
        time-based flush, by design) — the judge is what makes that never literally true anymore: either it
        upgrades the verdict here, or the gap valve (see the caller's `_speak_acc_drop`) gets one more chance
        at it before anything is actually discarded.
        """
        now = time.time() if now is None else now
        incoming = (incoming or "").strip()
        if not incoming:
            return "act", incoming, "", ""

        # Un hueco enorme rompe la cadena: lo de antes era otra cosa. Se DESCARTA en vez de pegarse — y se dice,
        # porque perder texto del operador en silencio es peor que responder raro.
        dropped = ""
        if self.fragments and (now - self.last_at) > MAX_GAP_S:
            dropped = self.text()
            self.clear()

        # See `_grows`: if what just arrived already CONTAINS what's buffered as a prefix, it's the SAME sentence
        # the acoustic layer handed back longer — REPLACE, don't append on top (or it gets double-counted).
        grows = bool(self.fragments) and _grows(self.text(), incoming)
        if grows or not self.fragments:
            candidate = incoming
        else:
            candidate = (self.text() + " " + incoming).strip()

        if _complete(candidate):
            self.clear()
            return "act", candidate, "", dropped

        # LAYER 2 (V2-102): layer 1 says incomplete — don't just trust a word list. `segmenter.judge` (the
        # default `_judge`) is already internally fail-open, but `set_judge` accepts ANY injected callable
        # (tests, a future alternate judge) — the invariant has to hold here too, the same way `_complete()`
        # wraps `_predicate()`, or a broken injected judge could turn "hold briefly" into "hang the turn".
        try:
            verdict, extra = await _judge(candidate)
        except Exception:
            verdict, extra = "incomplete", ""
        if verdict == "complete":
            self.clear()
            return "act", candidate, "", dropped
        if verdict == "ask" and extra:
            self.clear()
            return "ask", candidate, extra, dropped

        # Sigue a medias → acumula. Las válvulas se comprueban DESPUÉS de añadir: lo que se entrega es todo lo que
        # hay, nunca un buffer a medio vaciar.
        if not self.fragments:
            self.first_at = now
        if grows:
            self.fragments[:] = [incoming]     # replaces the whole growing tail, doesn't double it up
        else:
            self.fragments.append(incoming)
        self.last_at = now

        if len(self.fragments) >= MAX_FRAGMENTS:
            out = self.text()
            self.clear()
            return "act", out, f"válvula: {MAX_FRAGMENTS} trozos", dropped
        if len(self.text()) >= MAX_CHARS:
            out = self.text()
            self.clear()
            return "act", out, f"válvula: {MAX_CHARS} chars", dropped

        return "hold", "", _why(candidate), dropped

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
    """Replaces layer 1's completeness judge (lexical, sync, free). Signature: `(str) -> (complete: bool,
    reason: str)`. Passing `None` restores the default lexical judge.

    ⚠️ No longer the pragmatic layer's entry point (this docstring used to say that, back when the hook was
    declared but unimplemented) — that layer now lives in `_judge`/`set_judge`, is ASYNC, and has three
    verdicts, not two. This predicate remains the FAST filter that decides whether calling the model is
    needed at all."""
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


# ── EL JUEZ, capa 2 (inyectable, ASÍNCRONO) — V2-102 ───────────────────────────────────────────────────────────
async def _default_judge(text: str) -> tuple[str, str]:
    from nucleo.flash import segmenter
    return await segmenter.judge(text)


_judge = _default_judge


def set_judge(fn) -> None:
    """Replaces layer 2's judge (a real LLM, any language). Signature: `async (str) -> (verdict, extra)` with
    verdict in `"complete"|"ask"|"incomplete"`. Only called when layer 1 says incomplete — injectable for
    tests (avoids a real network/model call) and for an alternate judge if ever needed. `None` restores
    `segmenter.judge`."""
    global _judge
    _judge = fn or _default_judge
