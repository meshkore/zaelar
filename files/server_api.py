#
# files/server_api.py — SHIM de compatibilidad (V2-003 · T55). El router de subida vive ahora en
# `server/memory_routes.py` (la memoria absorbió files/; el ROUTER se mudó a la capa de servidor
# en la auditoría del 2026-08-23 — era transporte, no memoria). Se re-exporta desde aquí SOLO por si algún importador
# externo aún hace `from files.server_api import router`. La nota [SISTEMA] de ruta se retiró: el resumen del
# archivo ya está en la memoria y lo encuentra el retriever, sin tools de fichero de Hermes.
#
from server.memory_routes import router  # noqa: F401
