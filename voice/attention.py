#
# attention.py — Gate de ATENCIÓN (zaelar v2 «Colmena», V2-015 · T134/T135/T136).
#
# Con el micro SIEMPRE abierto, zaelar oía TODO (una reunión entera) y ACTUABA sobre voz ambiente: alucinaba,
# abría widgets, escalaba tareas al SlowBrain sobre frases que no le hablaban a él. Este gate decide si un turno
# va DIRIGIDO a zaelar; si no, el turno se marca `ambient` y NO produce acción NI respuesta.
#
# Modos (`ZAELAR_ATTENTION`, gestionado por la UI en config/settings.py; env = fallback power-user):
#   - `smart`    (default): dirigido si (a) hay wake-word ("zaelar" / "oye zaelar") o (b) cae dentro de una
#                           VENTANA de conversación activa (N s tras el último turno dirigido).
#   - `wakeword` : exige wake-word SIEMPRE (sin ventana).
#   - `ptt`      : push-to-talk — dirigido solo mientras la señal PTT del frontend está activa (set_ptt()).
#   - `always`   : comportamiento antiguo (todo turno es dirigido). Sigue disponible; no es el default.
#
# Estado a nivel de PROCESO (zaelar = una sola sesión de voz viva): la ventana de conversación + el flag PTT.
# Puro y barato: `evaluate()` LEE (no muta); el llamador llama `note_directed()` cuando ATIENDE un turno para
# abrir/refrescar la ventana. `hard_interrupt()` (T136) detecta un STOP duro (cierra/para/silencio) que se
# atiende SIEMPRE, saltándose el gate. `clamp_input()` (T135) acota el turno preservando el comando explícito.
#
from __future__ import annotations

import asyncio
import json
import os
import re
import time
import unicodedata
from dataclasses import dataclass

from loguru import logger

# ── configuración (UI-managed; env = fallback) ──────────────────────────────────────────────────────────
_VALID_MODES = ("smart", "wakeword", "ptt", "always")
_DEFAULT_MODE = "always"   # robot OFF = escucha y responde siempre; el toggle de la UI pasa a wake-word
_DEFAULT_WINDOW_S = 30.0

# Wake-word: "zaelar". Ampliable por env (`ZAELAR_WAKEWORDS`, coma-separado) con variantes fonéticas que el STT
# confunda — las anteriores (harvey/arbi/jarbi…) eran mishearings específicos de "harbee" y ya no aplican.
# Se buscan como palabra completa sobre el texto normalizado (sin tildes).
_DEFAULT_WAKEWORDS = ("zaelar",)

# ── estado de proceso ───────────────────────────────────────────────────────────────────────────────────
_state = {"last_directed": 0.0, "ptt": False}


def _norm(text: str) -> str:
    """Minúsculas sin tildes (comparación robusta STT es/en)."""
    n = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in n if not unicodedata.combining(c)).lower()


def mode() -> str:
    m = (os.getenv("ZAELAR_ATTENTION") or _DEFAULT_MODE).strip().lower()
    return m if m in _VALID_MODES else _DEFAULT_MODE


def window_s() -> float:
    try:
        v = float((os.getenv("ZAELAR_ATTENTION_WINDOW") or "").strip() or _DEFAULT_WINDOW_S)
        return v if v > 0 else _DEFAULT_WINDOW_S
    except Exception:
        return _DEFAULT_WINDOW_S


def _wakewords() -> tuple[str, ...]:
    env = (os.getenv("ZAELAR_WAKEWORDS") or "").strip()
    if env:
        ws = tuple(_norm(w) for w in env.split(",") if w.strip())
        if ws:
            return ws
    return _DEFAULT_WAKEWORDS


def has_wakeword(text: str) -> bool:
    n = _norm(text)
    return any(re.search(r"\b" + re.escape(w) + r"\b", n) for w in _wakewords())


@dataclass
class Verdict:
    directed: bool
    reason: str        # 'wakeword' | 'active_window' | 'always' | 'ptt' | 'ambient'


def evaluate(text: str, *, now: float | None = None) -> Verdict:
    """¿Va este turno DIRIGIDO a zaelar? PURO — no muta estado (el llamador llama `note_directed()` si atiende)."""
    m = mode()
    if m == "always":
        return Verdict(True, "always")
    if has_wakeword(text):
        return Verdict(True, "wakeword")
    if m == "wakeword":
        return Verdict(False, "ambient")
    if m == "ptt":
        return Verdict(True, "ptt") if _state["ptt"] else Verdict(False, "ambient")
    # smart: ventana de conversación activa
    now = time.time() if now is None else now
    if _state["last_directed"] and (now - _state["last_directed"]) <= window_s():
        return Verdict(True, "active_window")
    return Verdict(False, "ambient")


# ── CONTENIDO, no solo modo (2026-08-16) ────────────────────────────────────────────────────────────────────
# `evaluate()` en modo `always` (el default: micro SIEMPRE abierto, SIN wake-word — decisión permanente del
# operador, no algo a revertir) es un no-op: TODO turno es dirigido. Con una familia real en la sala, eso hizo
# que ruido de fondo ("Mira donde tú quieras, pero dame el ya...", frases con "hija" de por medio) corriera el
# turno COMPLETO — prompt, decisión de tools, y en un caso real un `web_search` que tardó 3,3s y se completó —
# antes de descartarse como superado. Coste real, cero valor.
#
# `evaluate_content()` es la versión que SÍ juzga: sigue sin exigir wake-word (eso no cambia), pero en `always`
# consulta al modelo rápido —la única señal que queda cuando no hay palabra de activación es la NATURALEZA de
# la frase: pregunta, dato concreto, continuación de una tarea en marcha = dirigido; charla ajena/ruido = no—.
# `evaluate()` (síncrona, sin red) se queda intacta para quien no puede pagar un round-trip (tests, probe,
# accumulator, agent.py's non-hot-path uses) — el turno REAL de voz es el único llamador de esta.
_DIRECTED_SYSTEM = (
    "Eres un filtro rápido para un asistente de voz con el MICRÓFONO SIEMPRE ABIERTO — no hay palabra de "
    "activación, así que además de al operador oye conversación de fondo (familia, TV, terceros) que NO va "
    "dirigida a ti.\n\n"
    "Te doy la última frase transcrita y, si la hay, un apunte de qué se estaba haciendo. Decide si la frase va "
    "DIRIGIDA a ti: es una pregunta, da datos concretos para algo, o continúa una tarea que ya estabais "
    "haciendo. O si es AMBIENTE: conversación ajena, ruido, algo sin sentido como petición.\n\n"
    "Ante la duda, marca DIRIGIDO — dejar sin atender una petición real es peor que procesar un poco de ruido.\n\n"
    'Responde SOLO con JSON: {"directed": true} o {"directed": false}. Nada más.'
)


async def _default_directed_judge(text: str, context: str) -> bool | None:
    """True/False, o None si el juez falló (el llamador hace fail-open a directed=True). Off el hot path del
    turno real gracias a `asyncio.to_thread` — mismo patrón que `segmenter.judge()`."""
    try:
        from nucleo import memllm
        user = f"Se estaba haciendo: {context}\n\nFrase: «{text}»" if context else f"Frase: «{text}»"
        raw = await asyncio.to_thread(
            memllm.chat_sync, "directed", _DIRECTED_SYSTEM, user,
            max_tokens=20, temperature=0.0, timeout=4.0,
        )
        return _parse_directed(raw)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"attention._default_directed_judge: failed ({str(e)[:160]}) — fail-open to directed")
        return None


def _parse_directed(raw: str | None) -> bool | None:
    """Tolerante a un fence de código (mismo problema que `segmenter._parse_judge`). None si no se pudo leer."""
    if not raw:
        return None
    s = raw.strip()
    if s.startswith("```"):
        s = s.split("```", 2)[1] if s.count("```") >= 2 else s.strip("`")
        if s.lstrip().lower().startswith("json"):
            s = s.lstrip()[4:]
    i, j = s.find("{"), s.rfind("}")
    if i >= 0 and j > i:
        s = s[i:j + 1]
    try:
        d = json.loads(s)
    except Exception:
        return None
    v = d.get("directed")
    return bool(v) if isinstance(v, bool) else None


_directed_judge = _default_directed_judge


def set_directed_judge(fn) -> None:
    """Sustituye el juez de `evaluate_content()`'s modo `always`. Firma: `async (text, context) -> bool | None`.
    Inyectable para tests (evita una llamada de red real) y para un juez alternativo si hiciera falta algún día.
    `None` restaura `_default_directed_judge`."""
    global _directed_judge
    _directed_judge = fn or _default_directed_judge


async def evaluate_content(text: str, *, context: str = "", now: float | None = None) -> Verdict:
    """Como `evaluate()`, pero en modo `always` juzga el CONTENIDO en vez de dar todo por dirigido — ver el
    comentario de arriba. `smart`/`wakeword`/`ptt` no cambian (su heurístico ya discrimina sin necesitar red)."""
    m = mode()
    if m != "always":
        return evaluate(text, now=now)
    if has_wakeword(text):
        return Verdict(True, "wakeword")   # atajo gratis — no hace falta preguntarle al modelo lo obvio
    t = (text or "").strip()
    if not t:
        return Verdict(False, "ambient")
    try:
        directed = await _directed_judge(t, context)
    except Exception as e:  # noqa: BLE001 — fail-open aquí TAMBIÉN cubre un juez inyectado (set_directed_judge)
        # que reviente, no solo el default: nada que sustituya al juez puede dejar mudo al agente.
        logger.warning(f"attention.evaluate_content: juez roto ({str(e)[:160]}) — fail-open a dirigido")
        directed = None
    if directed is None:
        return Verdict(True, "always")     # fail-open: un juez roto nunca puede dejar mudo al agente
    return Verdict(directed, "always" if directed else "llm_ambient")


def note_directed(now: float | None = None) -> None:
    """Marca que se ATENDIÓ un turno dirigido → abre/refresca la ventana de conversación activa (modo smart)."""
    _state["last_directed"] = time.time() if now is None else now


def set_ptt(active: bool) -> None:
    """Estado del push-to-talk (lo fija el frontend por el topic de datos `zaelar-ptt`). Solo cuenta en modo ptt."""
    _state["ptt"] = bool(active)


def reset() -> None:
    """Cierra la ventana / limpia el PTT (nueva sesión de voz o test)."""
    _state["last_directed"] = 0.0
    _state["ptt"] = False


# ── interrupción DURA (T136): STOP siempre atendido, SALTA el gate, DETERMINISTA (no depende del LLM) ────
# PRONOMBRE ENCLÍTICO (fix 2026-08-12, fallo REAL en vivo): en castellano el imperativo se PEGA al pronombre —
# «ciérraLO todo», «páraLO todo», «quítaLOS» — y `\bcierra\b` NO casa con «cierralo» (después de 'cierra' vienen
# más caracteres de palabra, así que no hay frontera). Resultado medido (13:01:51): el operador dijo «Ciérralo todo
# y páralo todo», el detector devolvió None, la orden ACABÓ EN EL MODELO —que ese turno se atascó— y no se cerró
# nada. Justo lo que este camino determinista existe para que no pase: cerrar y parar no pueden depender del LLM.
# No es una tabla de frases: es la MORFOLOGÍA del imperativo español (hasta dos pronombres: «devuélveMeLO»), así que
# cubre cualquier verbo de la lista y los que se añadan.
_ENCLITIC = r"(?:(?:me|te|se|nos|os|lo|la|le|los|las|les){1,2})?"
# Cerrar TODO: verbo de cierre + palabra de "todo/widgets". Corto, agnóstico de idioma (es/en).
_CLOSE_VERB_RE = re.compile(
    r"\b(?:cierra|cierre|cierr|quita|elimina|esconde|oculta|limpia|despeja)" + _ENCLITIC + r"\b"
    r"|\b(?:close|hide|clear)\b")
_ALL_RE = re.compile(
    r"\b(todo|todos|todas|all|widgets|tarjetas|ventanas|pantalla|escritorio|everything)\b")
# BUG real 2026-07-23 (feature nueva de fullscreen): "quita la pantalla completa" (salir de pantalla completa de UN
# widget) coincidía con "cierra/quita la PANTALLA" (verbo de cierre + 'pantalla' de _ALL_RE) y disparaba el cierre
# de TODOS los widgets — "pantalla completa"/"full screen" es un modo de UN widget, no un sinónimo de "todo".
_FULLSCREEN_RE = re.compile(r"\bpantalla\s+completa\b|\bfull\s*screen\b", re.I)
# STOP inequívoco (dispara aunque el turno sea largo).
_STOP_HARD_RE = re.compile(
    r"\b(silencio|calla(?:te|os|d)?|basta|stop|shh+|quiet[oa]|detente|para\s+ya|para\s+de|parate|shut\s*up)\b"
    # «páralo / párala / páralos / detenlo» — con pronombre pegado ya NO es la preposición «para», así que es
    # inequívoco y entra en la regla DURA (la blanda de abajo solo existe por la ambigüedad de «para» a secas).
    r"|\b(?:para|pare|deten|detenga)(?:me|te|se|nos|os|lo|la|le|los|las|les){1,2}\b")
# STOP ambiguo ("para"/"pare"/"espera" — también preposición): solo como imperativo CORTO (evita "para la cena").
_STOP_SOFT_RE = re.compile(r"\b(para|pare|espera)\b")


def hard_interrupt(text: str) -> str | None:
    """Detecta un STOP duro que se ejecuta SIEMPRE de inmediato (salta el gate de atención):
      - 'close'  → cerrar TODOS los widgets ("cierra los widgets / cierra todo").
      - 'stop'   → callar/parar (el barge-in de LiveKit ya cortó el TTS; no se genera respuesta nueva).
    Devuelve el tipo o None. El caso 'close' fue el bug real: quedó enterrado en un turno gigante y se truncó."""
    n = _norm(text)
    if _CLOSE_VERB_RE.search(n) and _ALL_RE.search(n) and not _FULLSCREEN_RE.search(n):
        return "close"
    if _STOP_HARD_RE.search(n):
        return "stop"
    if _STOP_SOFT_RE.search(n) and len(n.split()) <= 4:
        return "stop"
    return None


# ── fin de turno acotado + preservación de comando (T135) ───────────────────────────────────────────────
# Cláusula de comando explícito (abrir/cerrar/mostrar/parar…), para que un recorte por longitud NUNCA la pierda.
_COMMAND_RE = re.compile(
    r"[^.!?\n]*\b(cierra|cierre|abre|abra|muestra|muestrame|ensena|ensename|pon|saca|sube|para|pare|stop|"
    r"silencio|calla|basta|close|open|show|hide|clear|quita|oculta|esconde|limpia|despeja)\b[^.!?\n]*")


def clamp_input(text: str, max_len: int) -> tuple[str, bool]:
    """Acota el texto del turno a `max_len` chars PRESERVANDO el comando explícito (cerrar/parar/mostrar…): si el
    turno es largo y contiene un comando, se conserva su cláusula (no se trunca a ciegas los últimos N chars, que
    era como el "cierra los widgets" acababa FUERA del recorte). Devuelve (texto, recortado?)."""
    if max_len <= 0 or len(text) <= max_len:
        return text, False
    tail = text[-max_len:]
    cmds = [m.group(0).strip() for m in _COMMAND_RE.finditer(text)]
    cmd = cmds[-1] if cmds else ""      # el último comando = lo más reciente que pidió el operador
    if cmd and cmd not in tail:
        keep = cmd[: max(0, max_len // 2)]
        room = max_len - len(keep) - 3   # " … "
        tail = keep + " … " + (tail[-room:] if room > 0 else "")
    return tail, True
