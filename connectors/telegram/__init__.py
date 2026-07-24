#
# Telegram triage connector (INI-015) — zaelar lee el Telegram PERSONAL del operador (userbot Telethon, cuenta
# enlazada por QR) y solo le interrumpe con lo que MERECE atención, marcando leído lo ya resumido. Read-only +
# mark-read (autorespondedor fuera de alcance, como en WhatsApp).
#
# Frontera con Hermes (doc: .meshkore/docs/architecture/zaelar-hermes-federation.md): Telegram es "black-box lib"
# — NO usa nada de Hermes (Hermes solo trae la Bot API, que no lee chats personales), así que NO hay bridge que
# vendorizar. Es Python puro in-process (asyncio). El clasificador es el COMPARTIDO (connectors/messaging), LOCAL
# por defecto → nada personal sale de la máquina; NO pasa por el agente Hermes (invariante ACP de voz intacto).
#
# El triaje escribe el store UNIFICADO (widgets/_data/mensajeria.json, platform="telegram"); el widget único de
# mensajería lo LEE. El control por voz ([[msg.*]]) y el brief numerado son COMPARTIDOS (connectors/messaging).
#
