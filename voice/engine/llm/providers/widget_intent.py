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

from nucleo.flash import canvas_visibility as _cvis   # V2-723: ONE door to present

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


def _show_target_instance(wid: str, text: str = "", last_spoken: str = "") -> dict:
    """A QUÉ tarjeta va este «enséñamelo» (V2-300) — hermana de `_close_target`, mismo fail-soft: si no se
    puede saber qué hay abierto, se muestra la base como siempre.

    `text` es el turno del operador: con varias tarjetas abiertas, «las dos» resuelve a todas en vez de
    preguntar (V2-530).

    `last_spoken` es lo ÚLTIMO que dijimos (V2-605): si ya era esta misma pregunta, no se vuelve a hacer — se
    elige y se dice cuál. La pregunta se midió repetida CINCO veces en la sesión `43b7bf79`."""
    try:
        from server.voice_api import open_instances
        from widgets import instances as _inst
        return _inst.resolve_show(wid, open_instances(), text, last_spoken)
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


def with_also_named(ids, text: str) -> list[str]:
    """The cards to close: the resolved ones plus the OTHER open cards the sentence names (V2-773 — «Close the
    map and the results» closed the map and asked which one for the rest) — minus the cards the sentence tells to
    STAY («…just keep the calendar up», `instances.kept_named`). Fail-soft to the list given."""
    out = [str(x) for x in (ids or []) if str(x or "").strip()]
    try:
        from server.voice_api import open_instances
        from widgets import instances as _inst
        _open = open_instances()
        for x in _inst.also_named(text, _open, exclude=out):
            if x not in out:
                out.append(x)
        stay = {_inst.base_of(k) for k in _inst.kept_named(text, _open)}
        out = [x for x in out if _inst.base_of(x) not in stay]
    except Exception:  # noqa: BLE001
        pass
    return out


def _canvas_order(brief) -> str:
    """The canvas verb the turn's verdict SURELY reads — "show", "close", or "" (neither, unsure, absent).

    V2-807 T-07: the fallback used to decide with a verb-stem table (`pon`, `cierr`…) plus a catalogue-noun match,
    and «put the web in the signature too» opened the messaging card because «firma»/«mensaje» are its nouns, on a
    turn whose verdict said `canvas=neither` at 0.96. The verdict is the order; the words only name the card."""
    try:
        from nucleo.flash import turn_brief as _tb
        verb, info = _tb.read(brief, _tb.CANVAS_KEY, "")
        if not (isinstance(info, dict) and info.get("used")):
            return ""
        v = str(verb or "")
        return v if v in ("show", "close") else ""
    except Exception as e:  # noqa: BLE001
        logger.debug(f"widget fallback: canvas verdict unreadable — {e}")
        return ""


def _widget_fallback(text: str, emit, ask=None, last_spoken: str = "", brief=None) -> bool:
    """The model SAID it would open/close a card and emitted nothing: emit it for it — ONLY on the turn's own sure
    canvas verdict (V2-807 T-07). Returns True if it ACTED (so the caller marks acted["widget"] and the login
    fallback does not steal the turn — V2-023).

    What it acts on is the verdict, never a verb table: with `canvas=neither`, unsure or absent, it does nothing
    and the model's own calls stand. A show needs a card his words NAME (`_identify_named`, never «by context»);
    a close that names no card closes the cards he is not using (`bulk_close.close_all`, V2-807 T-08 — the draft
    he was correcting closed with everything else on «close what you don't need»).

    `ask` is where a question goes (V2-259 F3). Asking IS acting: the turn resolves with the question."""
    n = _norm_nfkd(text)
    if _action_is_negated(n):   # "no necesito que abras nada" → no dispares ningún widget
        return False
    if _is_meta_widget_question(n):   # "¿por qué abriste X?" es una PREGUNTA, no una orden
        return False
    order = _canvas_order(brief)
    if not order:
        return False
    try:
        if order == "close":
            wid = _identify_named(text)
            if not wid:
                from nucleo.flash import bulk_close as _bulk
                _bulk.close_all(emit, src="flash", text=text, brief=brief)
                return True
            _t = _close_target(wid, text)
            if _t["ask"]:
                if ask:
                    ask(_t["ask"])
                    emit("brain", "❓ cerrar: varias tarjetas abiertas", text=wid, role="system",
                         extra={"options": _t["options"]})
                    return True
                return False        # sin canal para preguntar, mejor no cerrar a ciegas
            from nucleo.acts import canvas_turn
            from nucleo.acts import canvas
            req = canvas_turn.request_of(brief, text)
            done = [canvas.apply("close", _cid, src="flash", emit=emit, request=req)
                    for _cid in (_t.get("ids") or [_t["id"] or wid])]
            return any(done)
        wid = _identify_named(text)
        if wid:
            # V2-605 F2 — the instance, as the close branch resolves it: «Enséñame el navegador» with four cards
            # on the canvas opened the bare base.
            _t = _show_target_instance(wid, text, last_spoken)
            if _t["ask"]:
                if ask:
                    ask(_t["ask"])
                    emit("brain", "❓ mostrar: varias tarjetas abiertas", text=wid, role="system",
                         extra={"options": _t["options"]})
                    return True
                # No channel to ask through: SHOW the base, exactly as before. Staying silent here would
                # turn a slightly-wrong card into a turn where nothing happens at all.
                _cvis.present(wid, reason="turn-order", src="flash", emit=emit, text=text, brief=brief)
                return True
            _cvis.present(str(_t.get("id") or wid), reason="turn-order", src="flash", emit=emit, text=text, brief=brief)
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
    # V2-666 — A SENTENCE THAT NAMES ITS WIDGET IS NEVER DEICTIC. Measured live (session 53de97d4, 10:59:10):
    # «Mírame, ábreme la agenda inmediatamente» opened the SEARCH card. The article «la» is a bare deictic token
    # for `looks_like_bare_ref` (it is right about «cancélala»), so one article made the whole sentence
    # «muéstramelo»-shaped, the noun he actually said was thrown away, and the fallback below — «the previous
    # route was a web search» — chose for him. The name wins first; the antecedent hunt only runs when he named
    # nothing.
    named = _identify_named(text)
    if named:
        return named
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
    # V2-666 — and with no name and no antecedent, a SHOW never lands on a card «by context». `_identify` would
    # return the only open card here (`runtime.identify`'s data-op nuance); for an OPEN decision that is a blind
    # open of whatever happens to be on screen — measured 10:33:27, «ponme un gráfico del Bitcoin» → youtube.
    return None


def _identify_named(text: str) -> str | None:
    """The widget the sentence NAMES (alias/name only, context breaks ties, never a by-context fallback) —
    `widgets.runtime.identify_named` with the same state narrowing `_identify` uses. V2-666."""
    try:
        from widgets import runtime
        try:
            from memory import api as _memapi
            _st = _memapi.state() or {}
            _open = _st.get("open_widgets") or []
            _recent = _st.get("recent_widgets") or []
        except Exception:
            _open, _recent = [], []
        return runtime.identify_named(text, open_ids=_open, recent_ids=_recent)
    except Exception:
        return None


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


def _identify_system(text: str) -> str | None:
    """The SYSTEM surface the phrase names (`identify()["system"]`), or None — the half `_identify` drops."""
    try:
        from widgets import runtime
        return (runtime.identify(text) or {}).get("system")
    except Exception:
        return None


def _identify_is_widget(wid: str) -> bool:
    """¿`wid` es un id EXACTO del catálogo? (para decidir si hay que resolverlo flojito antes de borrar)."""
    try:
        from widgets import runtime
        return runtime.get(wid) is not None
    except Exception:
        return False
