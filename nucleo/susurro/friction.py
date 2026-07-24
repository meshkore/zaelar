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
    if d.get("widget_acted") or d.get("data_done"):
        return "acción de widget sin escalar (¿reflejo local de una acción real no ejecutada?)"
    return ""


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
