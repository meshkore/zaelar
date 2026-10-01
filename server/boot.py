"""The server's START: everything the lifespan brings up before the app serves — identity, bus and its SSE
bridges, memory, the orchestrator loop and the Brain Workers, widgets, connectors, homeostasis (V2-778 F1,
2026-10-01).

Moved out of `server/__init__.py::_lifespan` (511 lines) with no behaviour change; the shutdown half stays there.
Every name the block read from `server` is read through it (`_srv.<name>`), so a patch on `server` still governs
it. `start_the_engine` returns the handles the shutdown half needs, only when bound.
"""
from __future__ import annotations

import server as _srv


async def start_the_engine(*, app) -> dict:
    # V2-778 F1 — the first half of the start (identity, bus, memory, loop, workers) lives in
    # `server/boot_halves.py`.
    _blk = await _boot_halves.identity_bus_memory_and_workers(
        app=app,
    )
    if '_bus_log' in _blk:
        _bus_log = _blk['_bus_log']
    if '_first_lifespan_entry' in _blk:
        _first_lifespan_entry = _blk['_first_lifespan_entry']
    if '_identity' in _blk:
        _identity = _blk['_identity']
    if '_loop_on' in _blk:
        _loop_on = _blk['_loop_on']
    if '_mem_sse_sub' in _blk:
        _mem_sse_sub = _blk['_mem_sse_sub']
    if '_mem_sse_task' in _blk:
        _mem_sse_task = _blk['_mem_sse_task']
    if '_memory_on' in _blk:
        _memory_on = _blk['_memory_on']
    if '_pulse_sse_sub' in _blk:
        _pulse_sse_sub = _blk['_pulse_sse_sub']
    if '_pulse_sse_task' in _blk:
        _pulse_sse_task = _blk['_pulse_sse_task']
    if '_slow_on' in _blk:
        _slow_on = _blk['_slow_on']
    if 'active_brain' in _blk:
        active_brain = _blk['active_brain']
    if 'asyncio' in _blk:
        asyncio = _blk['asyncio']
    if 'bus' in _blk:
        bus = _blk['bus']
    if 'memapi' in _blk:
        memapi = _blk['memapi']
    if 'meshkore' in _blk:
        meshkore = _blk['meshkore']
    if 'nucleo_dispatch' in _blk:
        nucleo_dispatch = _blk['nucleo_dispatch']
    if 'nucleo_loop' in _blk:
        nucleo_loop = _blk['nucleo_loop']
    # «Susurro» (V2-053): off-hot-path conversational auditor. It plugs in ONLY through the bus (turn.completed +
    # friction signals) — zero coupling with the voice provider. First-class kill switch: config §susurro.enabled
    # (UI) + ZAELAR_SUSURRO. Fail-open: its failure never touches voice.
    # V2-778 F1 — the second half of the start (widgets, connectors, voice wiring, homeostasis) lives in
    # `server/boot_halves.py`.
    _blk = await _boot_halves.connectors_voice_and_health(
        _first_lifespan_entry=_first_lifespan_entry,
        _identity=locals().get('_identity'),
        active_brain=active_brain,
        app=app,
        asyncio=locals().get('asyncio'),
    )
    if '_lk' in _blk:
        _lk = _blk['_lk']
    if '_susurro_on' in _blk:
        _susurro_on = _blk['_susurro_on']
    if 'browser_search' in _blk:
        browser_search = _blk['browser_search']
    if 'homeostasis' in _blk:
        homeostasis = _blk['homeostasis']
    if 'nucleo_susurro' in _blk:
        nucleo_susurro = _blk['nucleo_susurro']
    if 'supervisor' in _blk:
        supervisor = _blk['supervisor']
    if 'widget_background' in _blk:
        widget_background = _blk['widget_background']
    if 'widget_supervisor' in _blk:
        widget_supervisor = _blk['widget_supervisor']
    _out = locals()
    return {k: _out[k] for k in ('_bus_log', '_lk', '_loop_on', '_mem_sse_sub', '_mem_sse_task', '_memory_on', '_pulse_sse_sub', '_pulse_sse_task', '_slow_on', '_susurro_on', 'browser_search', 'bus', 'homeostasis', 'memapi', 'meshkore', 'nucleo_dispatch', 'nucleo_loop', 'nucleo_susurro', 'supervisor', 'widget_background', 'widget_supervisor', ) if k in _out}


from server import boot_halves as _boot_halves  # noqa: E402 — V2-778 F1, reads this module back
