"""voice/engine/llm/providers/widget_intent.py — is this sentence a widget order, and WHICH card?

Extracted from the voice provider on 2026-09-02 by the architecture ratchet (V2-556 landed on a file that sat
exactly at its ceiling), and the boundary was already drawn: these nine functions are DETERMINISTIC readers of
the operator's own words — negation, meta-question, which card «enséñamelo» points at, which one to close —
with no knowledge of a turn, a stream or a tool. They take `emit`/`ask` as parameters precisely because they do
not own a channel. Same pattern as `vault_intercept.py`, `promise_backstop.py` and `probe_scheduling.py`.

The rules they encode are load-bearing and were each paid for: V2-023 (a negated order must not fire),
V2-199/V2-530 (every close path goes through ONE decision, which returns a LIST so «both» is expressible) and
V2-300 (a deictic «muéstramelo» resolves against the real catalogue, never a topic table). `nucleo.py`
re-exports them, so both the call sites and the tests that reach for `nucleo._widget_fallback` keep working.
"""
from __future__ import annotations

from loguru import logger

def _action_is_negated(n: str) -> bool:
    """True si la frase NIEGA la acción de widget ("no necesito que abras nada", "no me muestres", "no cierres
    nada", "don't open") — para que el fallback NO dispare un show/close cuando el operador dice EXPLÍCITAMENTE que
    no lo haga (bug V2-023: "no necesito que abras nada" contenía "abras" → abría mensajería igual). Ventana corta
    (≤18 chars entre la negación y el verbo) para no pisar compuestos legítimos tipo "no quiero la agenda,
    muéstrame el reloj"."""
    import re as _re
    return bool(_re.search(
        r"(?:\b(?:no|sin|tampoco|nunca|ni)\b|don'?t|do not|no need|without)[^.?!¿]{0,18}\b"
        r"(?:abr|muestr|ensen|pon|saca|sube|cierr|cerr|quit|elimin|escond|ocult|close|hide|open|show)", n))


def _norm_nfkd(s: str) -> str:
    """Minúsculas sin acentos (para los guards deterministas de canvas)."""
    import unicodedata as _ud
    return "".join(c for c in _ud.normalize("NFKD", s or "") if not _ud.combining(c)).lower()


def _is_meta_widget_question(n: str) -> bool:
    """True si la frase PREGUNTA/COMENTA sobre una acción de widget YA ocurrida ("¿por qué has abierto el widget de
    proyectos?", "¿por qué se abrió eso?", "no deberías haber abierto nada") en vez de ORDENAR una — para que NUNCA
    se dispare un show/close por mencionar un widget en una queja o pregunta META (bug de la sesión 2026-07-12: el
    operador preguntando "¿por qué abriste X?" hacía que zaelar ABRIERA X). `n` ya viene normalizado (sin acentos).
    NO pisa una orden educada tipo "¿me muestras la agenda?" (no lleva 'por qué' ni verbo en pasado)."""
    import re as _re
    # "por qué" + verbo de canvas → pregunta sobre el porqué de una acción, no una orden
    if _re.search(r"\bpor ?que\b|porque\b", n) and _re.search(
            r"\b(abr|abri|abrio|abierto|mostr|ensen|saca|cerr|cerro|abriste|se abrio)", n):
        return True
    # verbo de canvas en PASADO/participio (acción ya ejecutada, se habla DE ella)
    return bool(_re.search(
        r"\b(abriste|abrio|abrido|abierto|has abierto|habias abierto|deberias haber (abierto|mostrado)|"
        r"mostraste|ensenaste|cerraste|cerro|se abrio|se cerro|has mostrado|has cerrado|se ha abierto)\b", n))


def _show_target_instance(wid: str, text: str = "") -> dict:
    """A QUÉ tarjeta va este «enséñamelo» (V2-300) — hermana de `_close_target`, mismo fail-soft: si no se
    puede saber qué hay abierto, se muestra la base como siempre.

    `text` es el turno del operador: con varias tarjetas abiertas, «las dos» resuelve a todas en vez de
    preguntar (V2-530)."""
    try:
        from server.voice_api import open_instances
        from widgets import instances as _inst
        return _inst.resolve_show(wid, open_instances(), text)
    except Exception:  # noqa: BLE001
        return {"id": wid, "ids": [wid], "ask": "", "options": []}


def _close_target(wid: str, text: str = "") -> dict:
    """A QUÉ tarjeta va este cierre (V2-259 F3). Una sola decisión para los TRES puntos de este fichero que
    emiten `widget/close` con id — escribir la regla tres veces es cómo se llega a que falte en uno.

    Fail-soft hacia el comportamiento de SIEMPRE: si no se puede saber qué hay abierto, cierra como antes. Una
    pregunta espuria en cada cierre sería peor que el fallo que esto quita.
    """
    try:
        from server.voice_api import open_instances
        from widgets import instances as _inst
        return _inst.resolve_close(wid, open_instances(), text)
    except Exception:  # noqa: BLE001
        return {"id": wid, "ids": [wid], "ask": "", "options": []}


def _widget_fallback(text: str, emit, ask=None) -> bool:
    """Si la frase es una orden clara de mostrar/cerrar un widget conocido y el modelo no emitió la tag, la
    emitimos nosotros (idempotente). Reutiliza el identificador de `widgets/runtime`. Devuelve True si ACTUÓ
    (para que el llamante marque acted["widget"] y el login-fallback no robe el turno — V2-023).

    `ask` es por dónde se PREGUNTA (V2-259 F3). Preguntar TAMBIÉN es haber actuado: el turno se resuelve con la
    pregunta, y devolver False aquí dejaría que el login-fallback se llevara el turno como si nadie hubiera
    hecho nada — que es el fallo que el comentario de arriba existe para evitar."""
    import re as _re
    import unicodedata as _ud
    n = "".join(c for c in _ud.normalize("NFKD", text or "") if not _ud.combining(c)).lower()
    if _action_is_negated(n):   # "no necesito que abras nada" → no dispares ningún widget
        return False
    if _is_meta_widget_question(n):   # "¿por qué abriste X?" es una PREGUNTA, no una orden
        return False
    try:
        if _re.search(r"\b(quit|cierr|cerr|elimin|escond|ocult|limpi|despej|close|hide|clear)", n):
            if _re.search(r"\b(todo|todos|todas|all|widgets|tarjetas|la pantalla|el escritorio)", n):
                emit("widget", "close", extra={"src": "flash"})
                return True
            wid = _identify(text)
            if wid:
                _t = _close_target(wid, text)
                if _t["ask"]:
                    if ask:
                        ask(_t["ask"])
                        emit("brain", "❓ cerrar: varias tarjetas abiertas", text=wid, role="system",
                             extra={"options": _t["options"]})
                        return True
                    return False        # sin canal para preguntar, mejor no cerrar a ciegas
                for _cid in (_t.get("ids") or [_t["id"] or wid]):
                    emit("widget", "close", extra={"id": _cid, "src": "flash"})
                return True
        elif _re.search(r"\b(abr|muestr|ensen|pon|saca|sube)|quiero ver|ver mi", n):
            wid = _identify(text)
            if wid:
                emit("widget", "show", extra={"id": wid, "src": "flash"})
                return True
    except Exception as e:  # noqa: BLE001
        logger.warning(f"widget fallback skipped: {e}")
    return False


def _show_guard_target(text: str, context: list[dict] | None = None, last_action: str = "") -> str | None:
    """Si la frase es una orden clara de MOSTRAR un widget EXISTENTE y NO pide crear uno nuevo, devuelve su id;
    si no, None. Guard DETERMINISTA (V2-023, no depende del LLM) para que una escalada ERRÓNEA de "muéstrame el de
    mensajería" nunca genere un widget basura — espejo del guard de LOGIN. Con verbo de crear ("créame otro reloj")
    devuelve None → deja escalar a un CREATE legítimo."""
    import re as _re
    import unicodedata as _ud
    n = "".join(c for c in _ud.normalize("NFKD", text or "") if not _ud.combining(c)).lower()
    if _action_is_negated(n):   # "no necesito que abras nada" → no es una orden de mostrar
        return None
    if _re.search(r"\b(crea|crear|cree|haz|hacer|genera|generar|nuev|construy|dise|monta|make|create|build|new)", n):
        return None
    if not _re.search(r"\b(abr|muestr|ensen|pon|saca|sube)|quiero ver|ver mi|ense", n):
        return None
    # Pronouns such as "muéstramelo" deliberately omit the widget noun. Resolve their most recent topical
    # antecedent through the real catalogue; this preserves human continuity without a weather/agenda/etc table.
    try:
        from nucleo.flash import router as _router
        tail = (text or "").strip().lower().strip("¿?¡!.,;:")
        deictic = (bool(_re.search(r"\b(?:muestr|ensen|abre|saca)\w*(?:lo|la|los|las)\b", n))
                    or any(_router.looks_like_bare_ref(token) for token in tail.split() if token))
        if deictic:
            for message in reversed(context or []):
                if message.get("role") != "user":
                    continue
                prior = str(message.get("content") or "").strip()
                if prior:
                    match = _identify(prior)
                    if match:
                        return match
                    break
            if last_action == "search":
                try:
                    from widgets import runtime
                    if runtime.get("search") is not None:
                        return "search"
                except Exception:
                    pass
    except Exception:
        pass
    return _identify(text)


def _identify(text: str) -> str | None:
    """Resuelve una frase a un id de widget. V2-078: pasa el CONTEXTO (abiertos + usados hace poco) para que, ante
    un empate, gane el que el operador tiene DELANTE o tocó hace nada — no un homónimo del catálogo. Lectura µs del
    estado (sin retriever); best-effort (si el estado no está, resuelve sin contexto, como antes)."""
    try:
        from widgets import runtime
        try:
            from memory import api as _memapi
            _st = _memapi.state() or {}
            _open = _st.get("open_widgets") or []
            _recent = _st.get("recent_widgets") or []
        except Exception:
            _open, _recent = [], []
        return (runtime.identify(text, open_ids=_open, recent_ids=_recent) or {}).get("match")
    except Exception:
        return None


def _identify_is_widget(wid: str) -> bool:
    """¿`wid` es un id EXACTO del catálogo? (para decidir si hay que resolverlo flojito antes de borrar)."""
    try:
        from widgets import runtime
        return runtime.get(wid) is not None
    except Exception:
        return False
