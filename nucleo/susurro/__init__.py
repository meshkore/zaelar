"""«Susurro» (V2-053) — auto-auditoría conversacional y mejora continua, off-hot-path.

Un modelo POTENTE (fuera del camino de voz → aquí sí puede razonar) observa la conversación y los eventos del
sistema POR EL BUS (topic `turn.completed` + señales de fricción; cero acoplamiento con el provider de voz) y,
cuando detecta FRICCIÓN (queja/corrección del operador, petición repetida, turno degradado, rail `sin_resolver`,
worker encallado), audita el tramo y devuelve correcciones de un CATÁLOGO CERRADO:

  - F1 (esta fase): `repair_say` (frase de reparación → brain_notes [SISTEMA]) y `finding` (hallazgo → cola
    `.meshkore/logs/susurro/findings.jsonl` + topic `susurro.finding`, que consume el bucle de desarrollo).
  - F2/F3 (después): user_rule / worker_action / state_patch / memory_fix — ver la iniciativa V2-053.

INVARIANTES: (1) NUNCA modifica BRAIN RULES/prompt de sistema en runtime — un auto-modificador corrompido no
tiene punto fijo; la genética solo cambia por desarrollo (findings → test→fix → git). (2) Fail-open duro: sin
key/timeout/JSON inválido → no pasa nada; jamás toca la latencia del turno. (3) Observabilidad TOTAL (regla del
operador): el payload ENVIADO al LLM, la respuesta CRUDA y cada corrección con su ANTES/DESPUÉS quedan en el
timeline (eventos kind `susurro`) y en el log durable del bus. (4) Solo ve conversación del OPERADOR; el
contenido `untrusted` de cluster queda fuera (anti prompt-injection). (5) Kill-switch de 1ª clase:
config §susurro.enabled (UI) + env ZAELAR_SUSURRO.
"""
from .engine import start, status, stop  # noqa: F401

__all__ = ["start", "stop", "status"]
