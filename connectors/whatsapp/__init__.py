#
# WhatsApp triage connector (INI-014; store unificado en INI-015) — zaelar lee el WhatsApp personal del operador y
# solo le interrumpe con lo que MERECE atención, marcando leído lo ya resumido. Read-only + mark-read.
#
# Frontera con Hermes (doc: .meshkore/docs/architecture/zaelar-hermes-federation.md): el bridge Baileys es una
# COPIA vendorizada de Hermes en connectors/whatsapp/bridge/ (parches marcados // ZAELAR-PATCH), inmune a
# `hermes update`. El clasificador es el COMPARTIDO (connectors/messaging), LOCAL por defecto (Ollama) y NO pasa
# por el agente Hermes → nada personal sale de la máquina y se preserva el invariante ACP de la voz.
#
# Módulos: bridge/ (Node, vendorizado) · bridge_proc (lifecycle+QR) · client (HTTP) · service (motor). El triaje,
# el store unificado, el aviso proactivo, el brief y el dispatch de tags viven en connectors/messaging/ (comunes a
# todas las plataformas). Config del bridge en config.py.
#
