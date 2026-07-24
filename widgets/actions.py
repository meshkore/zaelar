"""widgets/actions.py — SEMÁNTICA CANÓNICA de las acciones de un widget (V2-025).

Un widget declara en su `manifest.json` un vocabulario de `actions` (la **API de DATOS** del widget: qué
mutaciones acepta su `apply_action()`, con `desc` + `payload`). Este módulo es el ÚNICO sitio que decide, a
partir de la declaración, **CÓMO se ejecuta cada acción** — y lo leen por igual el gate del FlashBrain
(`nucleo/flash/frontend.py`), la frontera forzada del provider (`voice/.../nucleo.py`) y el brief que el cerebro
ve (`widgets/brief.py`). Una sola fuente de verdad, cero divergencia.

## El fallo que corrige (el flag `safe` estaba SOBRECARGADO)

Antes, `"safe": false` mezclaba DOS preguntas ortogonales en una:
  (a) «¿puede la capa rápida ejecutar esta mutación?» y
  (b) «¿es una acción IRREVERSIBLE que exige confirmación?».
`add_meeting` («añade una cita a la agenda») estaba `safe:false` → **se auto-escalaba a un AGENTE DE CÓDIGO**
del SlowBrain que no tenía NADA que programar (solo habría llamado al mismo `apply_action`), tardaba minutos y
llegó a colgarse >6 min. Una mutación de datos trivial NO es trabajo de código.

## El modelo nuevo — TRES modos, dos ejes SEPARADOS

Toda acción DECLARADA es una **data-op**: la ejecuta el FlashBrain al instante llamando al `apply_action` del
widget (o, en un widget `backed`, encolando al owner) — **NUNCA** se escala a un agente de código. El SlowBrain
queda reservado SOLO para CREAR/MODIFICAR el CÓDIGO de un widget.

  - `FAST`     — por defecto: el FlashBrain la ejecuta ya, sin fricción.
  - `CONFIRM`  — la acción es IRREVERSIBLE (pagar/enviar/publicar/vaciar…): el FlashBrain **igualmente la
                 ejecuta** (no la escala), pero antes PIDE OK (mismo gate reutilizable que el borrado de widget,
                 `widgets/confirm.py`; hermano de `nucleo/danger.py`). Se marca con `"confirm": true`
                 (alias `"irreversible": true`) o se DEDUCE de un heurístico estrecho sobre nombre+desc.
  - `ESCALATE` — vía de escape EXPLÍCITA (`"escalate": true`) para la acción rara que de verdad necesita al
                 SlowBrain. NO es para mutaciones de datos; existe por si un widget quiere delegar algo pesado.

## Compatibilidad con los manifests existentes (flag `safe` legacy)

  - `"safe": true`  → `FAST` (idéntico a antes: directa, instantánea).
  - `"safe": false` → **ya NO escala**: es `FAST` (o `CONFIRM` si el heurístico de irreversibilidad salta).
  - ausente         → `FAST` (o `CONFIRM` por heurístico).
Un `"confirm"`/`"irreversible"`/`"escalate"` EXPLÍCITO siempre manda sobre el legacy y sobre el heurístico.
"""
from __future__ import annotations

import re

FAST = "fast"          # el FlashBrain la ejecuta al instante
CONFIRM = "confirm"    # el FlashBrain la ejecuta, pero pide OK antes (irreversible)
ESCALATE = "escalate"  # vía de escape explícita al SlowBrain (rara; no para datos)

# Heurístico ESTRECHO de irreversibilidad — hermano deliberado de `nucleo/danger.py::_DANGER_RE`, pero LOCAL al
# módulo de widgets (que no debe importar del núcleo de voz). Solo verbos de consecuencia real: pagar/comprar/
# enviar/publicar/borrar-cuenta/vaciar-todo. NO incluye quitar/descartar/silenciar/limpiar-panel (reversibles) ni
# stems ciegos (evita falsos positivos). Se aplica al NOMBRE + la `desc` de la acción, ambos en el idioma del
# manifest (es/en). Un flag `confirm`/`irreversible` explícito hace innecesario acertar aquí.
_IRREVERSIBLE_RE = re.compile(
    r"\b(pagar|paga|pago|comprar|compra|publicar|publica|enviar|envia|env[íi]o|mandar|manda|"
    r"eliminar cuenta|borrar cuenta|vaciar|borrar todo|eliminar todo|"
    r"pay|purchase|buy|publish|post\b|send|checkout|delete account|wipe|clear all|empty)\b",
    re.I,
)


def _looks_irreversible(name: str, desc: str) -> bool:
    """¿El nombre/descripción de la acción huele a irreversible? Backstop determinista para un widget generado
    que se olvidó de marcar `confirm:true` en algo con consecuencias (p. ej. `send_email`)."""
    return bool(_IRREVERSIBLE_RE.search(f"{name or ''} {desc or ''}"))


def classify(spec: dict | None, name: str = "") -> str:
    """Modo de ejecución (`FAST`/`CONFIRM`/`ESCALATE`) de UNA acción a partir de su spec del manifest.

    Precedencia: `escalate` explícito → `confirm`/`irreversible` explícito → legacy `safe` (nunca escala) →
    heurístico de irreversibilidad. Cualquier cosa malformada cae a `FAST` (una data-op declarada nunca debe
    convertirse por accidente en trabajo de código: ese ERA el bug)."""
    spec = spec if isinstance(spec, dict) else {}
    if spec.get("escalate") is True:
        return ESCALATE
    conf = spec.get("confirm")
    if conf is None:
        conf = spec.get("irreversible")
    if conf is None:
        # Ni flag nuevo ni legacy fiable → dedúcelo. (`safe:true` es una señal explícita de "trivial/reversible":
        # respétala como FAST aunque la desc mencione un verbo fuerte.)
        conf = False if spec.get("safe") is True else _looks_irreversible(name, str(spec.get("desc") or ""))
    return CONFIRM if conf else FAST


def label(mode: str) -> str:
    """Etiqueta legible para el brief del cerebro (lo que ve el FlashBrain junto a cada acción)."""
    return {FAST: "(directa)", CONFIRM: "(confirmar)", ESCALATE: "(escala)"}.get(mode, "(directa)")
