#
# triage_agent.py — el TRIADOR del widget mensajería (V2-008). En la arquitectura v2 el triaje deja de vivir en
# los conectores y pasa a ser un AGENTE DEL WIDGET: dado un lote de mensajes entrantes (de cualquier plataforma,
# ya publicados en el bus como connector.msg), decide para cada uno si merece la atención del operador y si va
# dirigido a él. Encapsula la clasificación que antes estaba suelta en connectors/messaging (el "qwen2.5:3b
# suelto" del diseño).
#
# PRIVACIDAD (invariante DURO): el triaje corre con un modelo LOCAL por defecto (Ollama) — NADA personal sale de
# la máquina. La implementación del clasificador (prompt + few-shot + parseo defensivo) se conserva en
# connectors/messaging/triage.py como utilidad STATELESS y agnóstica de plataforma; este agente la invoca. El
# traslado físico del fichero al widget se difiere al entierro (V2-009), por strangler-fig (el camino duo/hermes
# de hoy aún lo usa). Usar un CodeAgent de NUBE (Claude Code) para triar es una decisión de producto ABIERTA que
# choca con este invariante de privacidad — ver bitácora de V2-008.
#


async def classify(messages: list[dict], operator_name: str | None = None) -> list[dict]:
    """Tría un lote. Devuelve la lista enriquecida con {importante, dirigido_a_mi, urgencia, motivo} alineada por
    índice. Best-effort: ante fallo del modelo, el clasificador marca todo como incierto (fail-open hacia el
    operador), nunca lanza."""
    from connectors.messaging import triage as _classifier
    return await _classifier.classify(messages, operator_name)
