#
# messaging — capa COMPARTIDA de mensajería personal triada (INI-015). Un solo modelo mental para CUALQUIER
# plataforma (WhatsApp, Telegram y, a futuro, email): los conectores por-plataforma (connectors/whatsapp,
# connectors/telegram) hacen el transporte + el emparejamiento; ESTA capa aporta lo que es común a todas:
#
#   · triage.py  — el clasificador LOCAL, agnóstico de plataforma (Ollama por defecto; NO pasa por el agente
#                  Hermes → privacidad + invariante ACP de voz). Promovido desde connectors/whatsapp.
#   · store.py   — el store UNIFICADO (widgets/_data/mensajeria.json): estado de vínculo por plataforma + una
#                  única lista de items de TODAS las plataformas + cola de pending_read (con su platform).
#   · notify.py  — el aviso proactivo (voz + nota [SISTEMA]) y el filtro de "qué merece atención", compartidos.
#   · brief.py   — el brief NUMERADO combinado que ve el brain (una sola lista → [[msg.read:N]] mapea bien).
#
# Frontera con Hermes (doc: .meshkore/docs/architecture/zaelar-hermes-federation.md): el clasificador es LOCAL y
# NUNCA pasa por el agente Hermes; ningún dato personal sale de la máquina.
#


async def dispatch_tag(action: str, extra: dict) -> None:
    """Enruta un [[msg.*]] emitido por el brain (voz/chat/duo — nunca turnos de cluster: operator-only).

    read:N / dismiss:N / clear → misma mutación que los botones del widget unificado (apply_action sobre el store
    unificado). La acción NO necesita saber la plataforma: el item N ya lleva su `platform`, y cada conector drena
    su parte de `pending_read` (marcado leído real en su plataforma). Nunca lanza."""
    try:
        from widgets.mensajeria import data
        name = action.split(".", 1)[1] if "." in action else action
        payload = {"n": extra.get("n")} if extra.get("n") is not None else {}
        data.apply_action(name, payload)
    except Exception:
        pass
