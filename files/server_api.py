#
# files/server_api.py — SHIM de compatibilidad (V2-003 · T55). El router de subida vive ahora en
# `memory/server_api.py` (la memoria absorbe files/). Se re-exporta desde aquí SOLO por si algún importador
# externo aún hace `from files.server_api import router`. La nota [SISTEMA] de ruta se retiró: el resumen del
# archivo ya está en la memoria y lo encuentra el retriever, sin tools de fichero de Hermes.
#
from memory.server_api import router  # noqa: F401
