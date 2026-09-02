"""nucleo/flash/dialog.py — ESTABILIDAD CONVERSACIONAL del FlashBrain (V2-032).

El modelo pequeño no-razonador (Grok-fast) DEGENERA cuando se le reinyecta su propio historial repetitivo: repite
la MISMA frase turno a turno ("No tengo acceso…" ×5), empalma plantillas ("Déjame comprobar Déjame comprobar") y
pierde el hilo. Fue el bloqueante #1 del informe del 2026-07-12. Estas son tres defensas DETERMINISTAS (sin LLM,
agnósticas de idioma es/en) que COMPARTEN el turno de VOZ (`nucleo.py::_run`) y el canal de PRUEBA headless
(`probe.py`) — así lo que se arregla aquí se valida por el probe y corre igual en voz:

  1. `loop_nudge(window)` — BREAK-LOOP: si las últimas respuestas del asistente se repiten, devuelve una
     instrucción de sistema que OBLIGA a cambiar de estrategia (reformular / admitir el límite / preguntar otra
     cosa). Es la defensa principal — actúa ANTES de generar, no después.
  2. `prune_window(window)` — colapsa turnos de asistente casi idénticos antes de reinyectarlos, para que el
     modelo deje de VER el patrón y de continuarlo.
  3. `sanitize_reply(text)` — ANTI-DEGENERACIÓN del texto de salida: colapsa palabras/frases duplicadas y
     empalmes de plantilla. Se aplica a lo que se GUARDA en la ventana (corta el bucle de realimentación) y a lo
     que evalúa el probe.
"""
from __future__ import annotations

import re
import unicodedata


def _norm(s: str) -> str:
    n = unicodedata.normalize("NFKD", s or "")
    n = "".join(c for c in n if not unicodedata.combining(c)).lower()
    return re.sub(r"[^0-9a-z ]+", " ", n).strip()


def _words(s: str) -> list[str]:
    return _norm(s).split()


def similar(a: str, b: str, thr: float = 0.8) -> bool:
    """True si dos respuestas son casi la misma (Jaccard de palabras ≥thr, acento/puntuación-insensible). Cadenas
    muy cortas se comparan exactas (normalizadas) para no fusionar "sí"/"no"."""
    wa, wb = set(_words(a)), set(_words(b))
    if not wa or not wb:
        return _norm(a) == _norm(b)
    if min(len(wa), len(wb)) <= 2:
        return _norm(a) == _norm(b)
    return len(wa & wb) / len(wa | wb) >= thr


# ── 1) BREAK-LOOP ────────────────────────────────────────────────────────────────────────────────────────
def repeated_replies(window: list[dict], look: int = 3) -> int:
    """Cuántas de las últimas `look` respuestas del asistente son casi idénticas entre sí (la racha desde el
    final). ≥2 = el cerebro está en un bucle de repetición."""
    replies = [m.get("content", "") for m in window if m.get("role") == "assistant"][-look:]
    if len(replies) < 2:
        return 0
    last = replies[-1]
    run = 1
    for prev in reversed(replies[:-1]):
        if similar(prev, last):
            run += 1
        else:
            break
    return run


# A LOOP THAT NEVER REPEATS A SENTENCE (V2-143). `repeated_replies` compares SURFACE FORM, and a model asking
# for the same missing datum five turns running rephrases it every time — politely, apologising, from a new
# angle. Measured on `renew-gym-membership__es`: five replies all asking for «el nombre del gimnasio o la
# ciudad», pairwise Jaccard 0.094 / 0.197 / 0.155 / 0.349 against a 0.80 threshold, so `repeated_replies`
# returned 1 and the anti-loop nudge never fired. The live watchdog — an LLM — called it a loop on sight. The
# deterministic detector structurally cannot see it by wording, so it looks at SHAPE instead: a run of turns
# where zaelar only ASKS and nothing moves.
#
# Asking for a missing datum is CORRECT behaviour and this suite scores it as such (V2-082), so one question is
# never a loop and two are not either. Three rounds in which the operator answered and zaelar still only asked
# is not "asking" any more — and the nudge only tells the model to change strategy, it never blocks a turn.
_ASK_RE = re.compile(r"[?¿]")


def consecutive_questions(window: list[dict], look: int = 5) -> int:
    """Run of assistant replies, counted back from the end, that are QUESTIONS — regardless of wording."""
    replies = [m.get("content", "") for m in window if m.get("role") == "assistant"][-look:]
    run = 0
    for reply in reversed(replies):
        if not _ASK_RE.search(reply or ""):
            break
        run += 1
    return run


def loop_nudge(window: list[dict]) -> str:
    """Instrucción de sistema anti-bucle si el asistente lleva ≥2 respuestas casi idénticas, o ≥3 turnos seguidos
    limitándose a PREGUNTAR (V2-143: el bucle real se reformula, no se repite). Vacío si no hay bucle. Se AÑADE
    al system prompt del turno → el modelo cambia de estrategia en vez de repetir."""
    if repeated_replies(window) >= 2 or consecutive_questions(window) >= 3:
        return (
            "\n\n── ROMPE EL BUCLE (OBLIGATORIO) ──\n"
            "Llevas VARIOS turnos diciendo casi lo MISMO. PROHIBIDO repetir esa frase otra vez. Cambia de "
            "estrategia AHORA: (a) reformula el enfoque con otras palabras o pasos, (b) admite con naturalidad el "
            "límite ('esto no lo puedo hacer ahora mismo, pero puedo…') y ofrece UNA alternativa concreta, o "
            "(c) pregunta algo distinto para desatascar. Una sola frase, nueva, útil.\n"
        )
    return ""


# ── 1b) LO QUE EL OPERADOR DIJO NO SE PIERDE ─────────────────────────────────────────────────────────────
def push_user(window: list[dict], text: str) -> None:
    """Registra en la ventana lo que dijo el operador, INCLUSO si su turno se canceló por solape.

    Incidente 2026-08-02: el operador describió lo que quería en una frase larga ("estamos buscando una PISCINA en
    Tarragona… que sea especial… pública o de pago… con toboganes… me da igual hotel o camping…"). El STT la partió
    en 6 trozos y cada trozo abrió un turno que PISABA al anterior; el `raise` del CancelledError saltaba el append
    a la ventana, así que las 5 primeras frases NUNCA entraron en el historial. El turno que sí llegó al modelo fue
    el último trozo suelto —"es de unas instalaciones de un pueblo, dime qué encuentras cerca de Tarragona"— con la
    ventana VACÍA de todo lo anterior: el cerebro preguntó "¿qué instalaciones: una nave, un local, un terreno?"
    porque literalmente jamás vio la palabra piscina. No fue el modelo entendiendo mal, fue el sistema borrándole
    el contexto. Lo que el operador dijo OCURRIÓ; cancelar la RESPUESTA no borra la FRASE.

    COALESCE por prefijo: el STT reemite acumulando ("A," → "A, B" → "A, B, C"), así que si el texto nuevo extiende
    al último turno de usuario se SUSTITUYE en vez de duplicarse — si no, la ventana se llenaría de prefijos y el
    modelo vería la misma frase cinco veces (que es justo lo que degrada al modelo pequeño, V2-032)."""
    t = (text or "").strip()
    if not t:
        return
    if window and window[-1].get("role") == "user":
        prev = (window[-1].get("content") or "").strip()
        pn, tn = _norm(prev), _norm(t)
        if pn and tn:
            if tn.startswith(pn):            # el nuevo CONTIENE al anterior → es su versión completa
                window[-1] = {"role": "user", "content": t}
                return
            if pn.startswith(tn):            # llegó un trozo más corto de lo ya registrado → nada nuevo
                return
    window.append({"role": "user", "content": t})


# ── 2) PODA DE HISTORIAL ─────────────────────────────────────────────────────────────────────────────────
def prune_window(window: list[dict]) -> list[dict]:
    """Colapsa respuestas del asistente casi idénticas para no reforzar el patrón. Conserva el orden y los turnos
    de usuario intactos; de una racha de respuestas gemelas deja solo la última (con su turno de usuario). No
    muta la lista original."""
    out: list[dict] = []
    for m in window:
        if m.get("role") == "assistant":
            # ¿ya hay una respuesta gemela reciente (dentro de los últimos 4 mensajes)? entonces esta racha ya
            # está representada — deja la más nueva quitando la vieja gemela y su turno de usuario acompañante.
            for j in range(len(out) - 1, max(-1, len(out) - 5), -1):
                if out[j].get("role") == "assistant" and similar(out[j].get("content", ""), m.get("content", "")):
                    # quita la respuesta gemela vieja y (si lo hay) el turno de usuario inmediatamente anterior
                    del out[j]
                    if j - 1 >= 0 and j - 1 < len(out) and out[j - 1].get("role") == "user":
                        del out[j - 1]
                    break
        out.append(m)
    return out


# ── 3) ANTI-DEGENERACIÓN DEL OUTPUT ──────────────────────────────────────────────────────────────────────
def _collapse_repeated_phrase(text: str, max_block: int = 10) -> str:
    """Colapsa un BLOQUE de palabras repetido contiguo ("Déjame comprobar Déjame comprobar" → "Déjame comprobar";
    "hola hola hola" → "hola"). Recorre de bloque grande a pequeño; itera hasta punto fijo."""
    for _ in range(4):
        toks = text.split()
        n = len(toks)
        out: list[str] = []
        i = 0
        changed = False
        while i < n:
            hit = False
            for L in range(min(max_block, (n - i) // 2), 0, -1):
                a = [w.lower() for w in toks[i:i + L]]
                b = [w.lower() for w in toks[i + L:i + 2 * L]]
                if a == b:
                    out.extend(toks[i:i + L])
                    i += 2 * L
                    hit = True
                    changed = True
                    break
            if not hit:
                out.append(toks[i])
                i += 1
        text = " ".join(out)
        if not changed:
            break
    return text


def sanitize_reply(text: str) -> str:
    """Anti-degeneración DETERMINISTA de la respuesta hablada del FlashBrain: colapsa palabras/frases duplicadas y
    empalmes de plantilla que produce el modelo pequeño bajo repetición. Idempotente; conserva texto normal."""
    if not text or not text.strip():
        return text
    t = text.strip()
    # frases duplicadas inmediatas ("Hola. Hola." → "Hola.")
    parts = re.split(r"(?<=[.!?…])\s+", t)
    dedup: list[str] = []
    for p in parts:
        if dedup and _norm(p) and _norm(p) == _norm(dedup[-1]):
            continue
        dedup.append(p)
    t = " ".join(dedup)
    # bloques de palabras repetidos contiguos (sin puntuación de por medio)
    t = _collapse_repeated_phrase(t)
    return re.sub(r"\s+", " ", t).strip()


def looks_degenerate(text: str) -> bool:
    """Heurística: ¿la respuesta parece degenerada (empalme/repetición) ANTES de sanear? Para observabilidad."""
    return bool(text) and sanitize_reply(text) != text.strip()


# Extraído de `probe.py` en la pasada del trinquete (2026-09-02): escribe en la VENTANA, que es de este
# módulo. `cap` se pasa porque el tope es del canal, no del diálogo.
def remember_what_was_said(sess, text: str, cap: int) -> None:
    """Record the operator's line in the window NOW, before anything remaining in the turn can fail.

    V2-167/V2-176, measured on `restaurant-tonight-madrid` and again on `book-hotel-night-known__es`: the window
    was only written at the very END of the turn (step (f)), so every early exit lost the sentence that had just
    been said. When the provider call failed, the turn returned `ok: False` — no reply at all — and the request
    went with it. Five turns later the operator asked how the booking was going and zaelar answered about the
    PREVIOUS errand it still remembered, then said «no tengo constancia de ese encargo en mi estado — no me
    had asked me to reserve a table». The judge called that hallucination and gaslighting; it was neither.
    It was TRUE, and it was our doing.

    `push_user` (right here) already carries this exact principle for the voice channel — «lo que el operador dijo
    HAPPENED; cancelling the RESPONSE does not erase the SENTENCE» — and the text channel called the very same function at the
    only point where it could not help. Calling it early also leaves the right shape behind: a user line with no
    assistant answer after it, which reads as «that one went unanswered», which is what happened.

    Idempotent: `push_user` coalesces an identical trailing line in place, so step (f) can still call it.
    """
    push_user(sess.window, text)
    del sess.window[:-cap]
