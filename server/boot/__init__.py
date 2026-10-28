"""The engine's start, one phase per module (refactor2710-13 T-03).

`nervous_system` — identity, the bus and its durable log, central memory and its SSE bridge, the MeshKore connector.
`brain` — the orchestrator loop and its pulse, the Brain Worker dispatcher and what a restart left behind, Susurro,
the action-map and context-pack watchers.
`surfaces` — the language top-up, widgets, the embedded voice worker, the hot-path prewarm and its seams, the
energy lease, the messaging connectors and homeostasis.

`server/lifespan.py` runs the three in that order and stops what they started. Each phase returns the handles the
shutdown needs; nothing here reads `server` back.
"""
