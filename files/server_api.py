#
# files/server_api.py — COMPATIBILITY SHIM (V2-003 · T55). The upload router now lives in
# `server/memory_routes.py` (memory absorbed files/; the ROUTER moved to the server layer
# in the 2026-08-23 audit — it was transport, not memory). It is re-exported here ONLY in case an external importer
# still does `from files.server_api import router`. The [SYSTEM] path note was removed: the file summary
# is already in memory and the retriever finds it, without Hermes file tools.
#
from server.memory_routes import router  # noqa: F401
