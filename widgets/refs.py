"""widgets/refs.py — resolución de REFERENCIAS a items en lenguaje natural (V2-026).

El operador habla en lenguaje natural ("marca hecha la tarea del daemon", "aplaza lo de Reddit"); NO conoce los
ids internos de los items de un widget, y un modelo rápido que intenta adivinarlos los INVENTA (el bug V2-026: el
FlashBrain emitió `done` con `taskId="09:00–11:00"` —el rango horario— en vez de "t_daemon"). Solución: el modelo
pasa una REFERENCIA en lenguaje natural (`item`) y AQUÍ se resuelve al id REAL contra los items VIVOS del widget.

Contrato del widget (OPCIONAL, en su `data.py`):

    def ref_index() -> list[dict]:
        '''Items referenciables por voz: [{"id","label","field"[,"hint"]}]. `field` = la clave del payload que
        identifica a ese item en las acciones del manifest (p.ej. "taskId" para una tarea, "projectId" para un
        proyecto). `label` = texto humano para casar la referencia (título de la tarea, nombre del proyecto…).
        `hint` opcional = contexto extra para el brief (estado, hora…).'''

Qué campo hay que rellenar se deduce del PROPIO manifest: el `payload` declarado de la acción ya nombra su campo
id (agenda `done`→{"taskId":…}, `drop_project`→{"projectId":…}). Se resuelve la referencia SOLO contra los items
cuyo `field` coincide con ese campo → "descarta el proyecto CryptoKnight" (`drop_project`→`projectId`) apunta al
PROYECTO, no a la tarea "Revisión de CryptoKnight". Fuzzy stdlib (solape de tokens + difflib), acento-insensible.
Devuelve una señal de AMBIGÜEDAD/NO-MATCH en vez de adivinar (mejor preguntar que actuar sobre el item equivocado).
"""
from __future__ import annotations

import difflib
import re
import unicodedata

from . import runtime


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s or ""))
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9ñ ]+", " ", s).strip()


_STOP = set("el la los las un una de del en al a y o que con para por mi tu su lo se me the a an of to my "
            "tarea tareas cita citas item proyecto la de lo eso esa ese esta este cosa asunto".split())


def _ref_index(widget_id: str) -> list[dict]:
    try:
        import importlib
        mod = importlib.import_module(f"widgets.{widget_id}.data")
        if hasattr(mod, "ref_index"):
            idx = mod.ref_index()
            return [i for i in idx if isinstance(i, dict) and i.get("id") and i.get("field")]
    except Exception:
        pass
    return []


def _exposes_ref_index(widget_id: str) -> bool:
    """¿Este widget PUBLICA sus items? (para poder distinguir «vacío» de «no publica» — ver items_line)."""
    try:
        import importlib
        return hasattr(importlib.import_module(f"widgets.{widget_id}.data"), "ref_index")
    except Exception:
        return False


def id_field_for_action(widget_id: str, action: str) -> str | None:
    """La clave del payload de esta acción que identifica a un item existente (termina en 'Id', p.ej. `taskId`,
    `projectId`, `chatId`), leída del manifest. None si la acción no actúa sobre un item preexistente (p.ej.
    `add_meeting`, que CREA uno) → no hay nada que resolver."""
    try:
        spec = ((runtime.get(widget_id) or {}).get("actions") or {}).get(action) or {}
        payload = spec.get("payload")
        if not isinstance(payload, dict):
            return None
        for k in payload:
            if str(k).lower().endswith("id"):
                return k
    except Exception:
        pass
    return None


def _score(ref_n: str, label_n: str) -> float:
    if not ref_n or not label_n:
        return 0.0
    r_tokens = [t for t in ref_n.split() if t not in _STOP and len(t) > 2]
    l_tokens = [t for t in label_n.split() if t not in _STOP]
    if not r_tokens:
        return 0.0
    hits = 0.0
    for t in r_tokens:
        if t in l_tokens or any(t in lt or lt in t for lt in l_tokens):
            hits += 1
        elif difflib.get_close_matches(t, l_tokens, n=1, cutoff=0.82):
            hits += 0.8
    token_score = hits / len(r_tokens)                       # fracción de la referencia cubierta
    ratio = difflib.SequenceMatcher(None, ref_n, label_n).ratio()
    return token_score * 2.0 + ratio                          # el solape de tokens pesa más que el ratio bruto


# Resultado de una resolución de referencia.
class RefResult:
    def __init__(self, ok, payload=None, needs=None, candidates=None):
        self.ok = ok                    # True si se resolvió (o no hacía falta resolver)
        self.payload = payload          # payload actualizado con el id real (si ok)
        self.needs = needs              # 'ref' | 'ambiguous' | 'no_match' cuando ok=False
        self.candidates = candidates or []   # etiquetas candidatas (para preguntar al operador)


def resolve(widget_id: str, action: str, ref: str, payload: dict | None = None) -> RefResult:
    """Resuelve una referencia en lenguaje natural al id real del item para `action`. Devuelve un `RefResult`:
    - ok=True + payload (con el id real relleno) si se resolvió, o si la acción no actúa sobre un item existente.
    - ok=False con `needs` ('ref'|'ambiguous'|'no_match') y `candidates` para que el llamante PREGUNTE en vez de
      inventar un id. NUNCA lanza."""
    payload = dict(payload or {})
    field = id_field_for_action(widget_id, action)
    if not field:
        return RefResult(True, payload)                       # nada que resolver (p.ej. add_meeting)

    idx = [i for i in _ref_index(widget_id) if i.get("field") == field]

    # Si el modelo YA dio un id que EXISTE de verdad, respétalo (no lo pises).
    given = str(payload.get(field) or "").strip()
    if given and any(i["id"] == given for i in idx):
        return RefResult(True, payload)

    # Texto por el que buscar: la ref explícita del modelo, o —si no la dio— lo que puso en el campo id (que suele
    # ser una descripción/valor inventado que a veces casa por texto, p.ej. el título de la tarea).
    query = _norm(ref) or _norm(given)
    if not query:
        return RefResult(False, needs="ref", candidates=[i["label"] for i in idx][:6])
    if not idx:
        return RefResult(False, needs="no_match")

    scored = sorted(((_score(query, _norm(i["label"])), i) for i in idx), key=lambda s: -s[0])
    best_score, best = scored[0]
    second = scored[1][0] if len(scored) > 1 else 0.0
    if best_score < 1.0:
        return RefResult(False, needs="no_match", candidates=[i["label"] for i in idx][:6])
    if len(scored) > 1 and (best_score - second) < 0.5:       # empate → no adivines, pregunta
        close = [i["label"] for s, i in scored if best_score - s < 0.5][:4]
        return RefResult(False, needs="ambiguous", candidates=close)
    payload[field] = best["id"]
    return RefResult(True, payload)


def label_for(widget_id: str, field: str, item_id: str) -> str:
    """Etiqueta HUMANA del item `item_id` (campo `field`) del widget — para componer un mensaje legible (p.ej. el
    texto de una confirmación) sin exponer el id interno. '' si no se encuentra. Genérico (lee `ref_index`)."""
    iid = str(item_id or "").strip()
    if not iid:
        return ""
    for i in _ref_index(widget_id):
        if i.get("field") == field and str(i.get("id")) == iid:
            return str(i.get("label") or "").strip()
    return ""


def items_line(widget_id: str) -> str:
    """Línea compacta con los items VIVOS del widget (label + hint) para el brief del cerebro, de modo que sepa
    QUÉ existe y pueda referenciarlo con naturalidad. Sin ids internos (el modelo referencia por lenguaje).

    VACÍO ≠ SIN ÍNDICE (fix 2026-08-02): un widget que expone `ref_index` pero no tiene nada dentro lo DICE. Antes
    devolvía "" en los dos casos, así que el cerebro no podía distinguir «esta tarjeta está abierta y vacía» de
    «esta tarjeta no publica sus items» — y con la hoja de resultados abierta y en blanco contestaba «aquí lo
    tienes» al operador, que no veía nada. Un widget vacío es un hecho que el cerebro tiene que ver."""
    if not _exposes_ref_index(widget_id):
        return ""
    idx = _ref_index(widget_id)
    if not idx:
        return ("items ahora: NINGUNO — la tarjeta está ABIERTA pero VACÍA: el operador no ve NADA dentro, así que "
                "no des por entregado lo que hay que poner ahí")
    bits = []
    for i in idx[:12]:
        h = str(i.get("hint") or "").strip()
        bits.append(f"«{i['label']}»" + (f" ({h})" if h else ""))
    return "items ahora: " + " · ".join(bits)
