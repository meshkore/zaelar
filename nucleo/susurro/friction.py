"""Detector DETERMINISTA de fricción (V2-053 F1) — funciones puras, es/en, sin LLM.

La fricción es la señal de disparo BARATA del Susurro: el LLM potente solo se paga cuando hay motivo. Doctrina
del proyecto (V2-046): esto NO es routing por tabla de palabras — no decide qué HACER con el turno (eso sigue
siendo del modelo); solo decide si merece la pena AUDITAR el tramo. Precisión > recall: un disparo de más cuesta
céntimos; uno de menos se recupera con la siguiente queja o con el pulso.
"""
from __future__ import annotations

import re
import unicodedata


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s.lower()).strip()


# Señales FUERTES: el operador está corrigiendo/quejándose de zaelar de forma inequívoca. Una basta.
_STRONG = [
    r"\bte lo (?:he |habia |había )?(?:dicho|pedido|preguntado|repetido)\b",
    r"\bte lo estoy (?:pidiendo|preguntando|diciendo|repitiendo)\b",   # presente continuo: frustración de repetir
    r"\bte (?:he|habia|había) (?:dicho|pedido|preguntado)\b",
    r"\b(?:ya )?te dije\b",
    r"\bno (?:era|es) eso\b",
    r"\beso no (?:era|es) lo que\b",
    r"\bno me (?:referia|refería|refiero)\b",
    r"\bte (?:has|estas|estás) equivocando\b|\bte has equivocado\b",
    r"\bno me (?:estas|estás) (?:escuchando|entendiendo|haciendo caso)\b",
    r"\bme (?:estas|estás) (?:escuchando|oyendo)\?",
    r"\bno me (?:has |)(?:respondido|contestado|hecho caso)\b",
    r"\bsigues sin\b",
    r"\b(?:todavia|todavía|aun|aún) no (?:lo )?has\b",
    r"\bhace (?:un montón de |mucho |un buen |)rato que\b",
    r"\bllevas (?:un rato|mucho|media hora|horas)\b",
    r"\botra vez (?:mal|no|te (?:has|vuelves)|lo mismo)\b",
    r"\bque no,?\s",                     # "que no, la otra" — corrección enfática
    # en
    r"\bi (?:already )?told you\b",
    r"\bthat'?s not what i\b",
    r"\byou'?re not listening\b",
    r"\byou (?:did it |got it |were )?wrong\b",
    r"\byou still haven'?t\b",
    r"\bi asked you (?:for|to)\b.{0,30}\b(?:ago|already|again)\b",
]
_STRONG_RE = [re.compile(p, re.I) for p in _STRONG]

# Señales DÉBILES: sugieren fricción pero tienen usos legítimos ("otra vez" en "ponla otra vez"). Hacen falta 2.
_WEAK = [
    r"\botra vez\b",
    r"\bde nuevo\b",
    r"\bno,?\s+(?:asi|así) no\b",
    r"\bno es asi\b",                    # "no es así" (corrección; débil: puede ser neutro en frase larga)
    r"\beso esta mal\b|\beso está mal\b",
    r"\bmal\b[\s.!?]*$",
    r"\bagain\b",
    r"\bnot (?:that|this) one\b",
]
_WEAK_RE = [re.compile(p, re.I) for p in _WEAK]


def complaint_signals(text: str) -> list[str]:
    """Patrones de queja/corrección que matchean en el turno (normalizado sin acentos)."""
    t = _norm(text)
    if not t:
        return []
    hits = [p.pattern for p in _STRONG_RE if p.search(t)]
    weak = [p.pattern for p in _WEAK_RE if p.search(t)]
    if hits:
        return hits + weak
    return weak if len(weak) >= 2 else []


def is_complaint(text: str) -> bool:
    return bool(complaint_signals(text))


def repeated_request(text: str, prev_user_turns: list[str], thr: float = 0.7) -> bool:
    """La MISMA petición re-dicha (≥thr Jaccard con alguno de los turnos previos del operador). Reutiliza la
    costura compartida de estabilidad (nucleo/flash/dialog.similar) — misma métrica que el anti-eco del turno."""
    t = (text or "").strip()
    if len(t) < 12:                       # "sí", "vale", "no" — nunca son una petición repetida
        return False
    try:
        from nucleo.flash.dialog import similar
    except Exception:
        return False
    return any(similar(t, p, thr=thr) for p in prev_user_turns if p and len(p.strip()) >= 12)


# RIESGO en la DECISIÓN del turno (V2-061): el cerebro rápido hizo una acción CONSECUENTE de widget (cambió datos /
# borró) SIN escalar → pudo tratar como simple tweak local algo que era una acción del MUNDO REAL (cancelar una
# cita/baja/pedido) y decir «hecho» en falso. Es la señal BARATA que le da a Susurro la OPORTUNIDAD de intervenir
# ANTES de que el operador se queje (lo que faltaba en el caso ITV). NO decide qué hacer —eso es del modelo potente,
# por comprensión—; solo marca el turno como digno de AUDITAR. No es una tabla de verbos.
def risky_decision(decision: dict | None) -> str:
    """Motivo si la DECISIÓN del turno es de riesgo (acción consecuente de widget sin escalar); '' si no."""
    d = decision if isinstance(decision, dict) else {}
    if d.get("escalated"):
        return ""       # ya tomó el camino pesado correcto — no es el patrón de riesgo
    if d.get("confirm_opened"):
        # BUG real (2026-07-25, sesión viva de Manolo): pedir "manda un mensaje a Zalo" ABRE el confirm-gate de la
        # data-op `send` (widget_acted=true PERO confirm_opened=true) — la acción NO se ejecutó, está ESPERANDO el
        # Sí/No del operador. Susurro lo leía como "acción consecuente sin escalar/no ejecutada" y lanzaba un
        # worker_action que iba al GENERADOR de código y se ponía a MODIFICAR el widget para "enviar el mensaje".
        # Un confirm-gate ABIERTO es justo lo contrario del patrón de riesgo V2-061 (reflejar en local algo real sin
        # ejecutarlo y decir «hecho»): aquí no se dijo «hecho», se PREGUNTÓ, y se ejecutará al confirmar. No auditar.
        return ""
    if d.get("widget_acted") or d.get("data_done"):
        return "acción de widget sin escalar (¿reflejo local de una acción real no ejecutada?)"
    return ""


# CONFABULACIÓN de data-op (V2-078, 2026-07-31): el ESPEJO de risky_decision. Ahí el rápido ACTUÓ sin escalar;
# aquí NO actuó (turno de charla, cero tools/tags) PERO su RESPUESTA CLAMA que hizo/está haciendo algo («ya la
# estoy añadiendo a la agenda», «sigo con ello», «hecho») sobre un widget del catálogo que el operador NOMBRÓ. Es
# la data-op FANTASMA que el A/B destapó: con el widget CERRADO el no-razonador dice que actúa sin llamar
# widget_data → mentira. Señal BARATA (regex de la RESPUESTA, es/en, no una tabla de verbos por widget) que le da a
# Susurro la oportunidad de RE-RUTEAR (worker_action) y ejecutar de verdad, OFF-hot-path. El MODELO decide si de
# verdad quedó algo sin hacer; esto solo abre la puerta. Doctrina V2-046/V2-075: la decisión es del modelo.
_CLAIM = [
    # es — pretérito/gerundio/presente que AFIRMA una mutación hecha o en curso
    r"\b(?:hecho|listo|ya (?:esta|está)|queda (?:hecho|anotad|apuntad|añadid|agregad|guardad|reservad|marcad|cread))\b",
    r"\b(?:lo|la|los|las|te) (?:he |)(?:anotad|apuntad|añadid|agregad|guardad|actualizad|reservad|marcad|puest|cread|cancelad|borrad|program)",
    r"\b(?:lo |la |los |las |)(?:añado|agrego|apunto|anoto|guardo|actualizo|reservo|marco|pongo|creo|cancelo|borro|programo)\b",
    r"\b(?:estoy|voy a) (?:añad|agreg|apunt|anot|guard|actualiz|reserv|marc|pon|cre|cancel|borr|program)",
    r"\b(?:sigo|me pongo) con ello\b|\bva en ello\b|\bahora mismo (?:lo|la|te)\b",
    # en
    r"\b(?:done|on it)\b",
    r"\b(?:i'?ve|i have|i'?ll|i will|i'?m|i am) (?:added|updated|booked|scheduled|noted|saved|marked|set|created|cancel|put|adding|updating|booking)\b",
    r"\b(?:adding|updating|booking|scheduling|noting|saving|marking|creating|cancelling|canceling) (?:it|the|your|a )\b",
]
_CLAIM_RE = [re.compile(p, re.I) for p in _CLAIM]


def claims_action(reply: str) -> bool:
    """¿La RESPUESTA de zaelar afirma haber hecho / estar haciendo una mutación? (es/en, acento-insensible).
    Es el rastro de la confabulación cuando el turno NO llamó a ninguna tool."""
    t = _norm(reply)
    return bool(t) and any(p.search(t) for p in _CLAIM_RE)


def _nothing_acted(decision: dict | None) -> bool:
    """True si el turno NO ejecutó NADA consecuente — robusto a las dos formas de `decision` (voz vs probe).
    Voz: banderas escalated/searched/widget_acted/worker_acted/data_done/confirm_opened/clarify/shown_ids.
    Probe: action=='chat' + sin tool_calls + sin tags."""
    d = decision if isinstance(decision, dict) else {}
    if "action" in d:                       # forma del probe
        if str(d.get("action") or "") not in ("chat", ""):
            return False
        return not (d.get("tool_calls") or d.get("tags"))
    # forma del provider de voz
    return not any(d.get(k) for k in ("escalated", "searched", "widget_acted", "worker_acted",
                                      "data_done", "confirm_opened", "clarify", "shown_ids"))


def phantom_dataop(user: str, decision: dict | None) -> str:
    """Motivo si el turno es una data-op FANTASMA (charló y clamó una acción sobre un widget nombrado, sin
    ejecutarla); '' si no. `decision` debe llevar la RESPUESTA en `reply`. Gate en TRES capas de precisión:
    (1) nada actuó · (2) la respuesta clama acción · (3) el turno resuelve a un widget con acciones DECLARADAS
    (data-driven del manifest, no una tabla de verbos). El modelo potente decide luego si de verdad quedó algo
    sin hacer y re-rutea; esto solo abre la puerta, barato."""
    d = decision if isinstance(decision, dict) else {}
    if not _nothing_acted(d):
        return ""
    if not claims_action(str(d.get("reply") or "")):
        return ""
    u = (user or "").strip()
    if len(u) < 8:                          # "vale", "gracias" — nunca una data-op
        return ""
    try:                                    # ¿el turno apunta a un widget REAL con acciones que cambian datos?
        from widgets import runtime
        from memory import api as _mem
        st = _mem.state() or {}
        m = (runtime.identify(u, open_ids=st.get("open_widgets") or [],
                              recent_ids=st.get("recent_widgets") or []) or {}).get("match")
        if not m:
            return ""
        w = runtime.get(m) or {}
        if not (isinstance(w.get("actions"), dict) and w.get("actions")):
            return ""                       # widget sin data-ops (solo display) → no era una data-op
    except Exception:
        return ""
    return "data-op fantasma (charló y dijo que actuaba sobre un widget, sin ejecutar la tool)"


# Eventos del sistema que son fricción por sí mismos (los emite quien ya vigila cada pieza; aquí solo se mapean
# a un motivo legible). kind/label del observer o topic del bus → motivo.
def system_friction(kind: str, label: str = "", topic: str = "") -> str:
    if topic == "worker.stuck":
        return "worker encallado (sin eventos)"
    if topic == "worker.budget_kill":
        return "worker matado por presupuesto (no entregó a tiempo)"
    if kind == "alert":
        return "turno degradado (cerebro rápido caído)"
    if kind == "rail" and "fail" in (label or "").lower():
        return "rail sin_resolver"
    return ""
