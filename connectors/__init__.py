#
# connectors — conectores externos de zaelar (3er I/O junto a voz + chat): mensajería personal (whatsapp/telegram/
# email sobre la capa compartida messaging), música (spotify), canal de cluster (meshkore) y proveedor de código
# (architect). Paquete regular (no namespace) para que `connectors.email` sea nuestro subpaquete y NO colisione con
# el módulo `email` de la stdlib al recolectar tests. Ver .meshkore/docs/modules/zaelar-modules.md §Connectors.
#
