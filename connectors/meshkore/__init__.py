#
# MeshKore connector — zaelar's native link to MeshKore clusters (a THIRD input/output channel next to voice
# and chat). Pure I/O + a brain-agnostic bridge: the brain does all the thinking; this module only carries
# messages in/out and wakes the brain on cluster events. See .meshkore/docs and connectors/meshkore/bridge.py.
#
# Wiring (server/__init__.py at startup):
#     from connectors import meshkore
#     meshkore.init(brain)                  # brain = the FlashBrain engine, off the voice pipeline (untrusted profile)
#     meshkore.get_bridge().start_heartbeat()
#
# NOTE: the accessors are get_manager()/get_bridge(), NOT manager()/bridge() — the package also has manager.py
# and bridge.py submodules, and importing a submodule rebinds the same attribute on the package, which would
# shadow a like-named function. Distinct names avoid that collision.
#
from connectors.meshkore.manager import MeshKoreManager

_manager: MeshKoreManager | None = None
_bridge = None


def get_manager() -> MeshKoreManager:
    """The process-wide connection hub (created on first use). Transport works even without a brain wired."""
    global _manager
    if _manager is None:
        _manager = MeshKoreManager()
    return _manager


def get_bridge():
    """The connector↔brain bridge, or None if init() hasn't run (e.g. transport-only / tests)."""
    return _bridge


def init(brain):
    """Wire the bridge with the FlashBrain engine (untrusted profile) and route all inbound cluster frames into it."""
    global _bridge
    from connectors.meshkore.bridge import ClusterBridge
    m = get_manager()
    _bridge = ClusterBridge(m, brain)
    m.set_sink(_bridge.on_event)
    return _bridge


async def dispatch_tag(action: str, extra: dict):
    """Route a [[cluster.*]] tag emitted by the brain (from any turn — voice OR cluster). No-op if not wired."""
    b = _bridge
    if b is not None:
        await b.dispatch(action, extra)


async def shutdown():
    global _bridge
    if _bridge is not None:
        await _bridge.stop()
    if _manager is not None:
        await _manager.shutdown()
    _bridge = None
