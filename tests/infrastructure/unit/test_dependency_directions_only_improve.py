"""Cross-domain imports go through the front door — and reaching into the motor only shrinks (V2-569).

The size ratchet (7.22) keeps any one file from growing into a god file. This is its sibling for the OTHER axis
the operator asked to guard as the tree grows: not how big each piece is, but WHO is allowed to touch WHOM.
`zaelar-modularity.md` §2 has declared the facades since July — and says in as many words that `voice/engine/`
is the MOTOR (LiveKit) and its internals are not a facade. Nothing measured it until 2026-09-03. Measured:

  * **42 (file → module) pairs reach `voice.engine.*` from outside `voice/`.** Thirty of them import ONE
    module — `voice.engine.core.langs`, the language helper — and almost all do it lazily, inside a function,
    which is this codebase's documented way of papering over an import cycle. The debt has a name: `langs` is
    a shared utility that happens to LIVE inside the motor, and its honest fix is a home in a low layer with a
    re-export shim, as `text_norm.py` and `errors.brief` were before it. Until that extraction happens, the
    inventory below freezes the reach so it can only shrink.
  * **Exactly ONE private name crosses a domain boundary** in the whole engine. That number is worth a guard
    precisely because it is 1 and not 40: the convention is real, so a second offender is a decision, not noise.

`voice.observer`, `voice.proactive`, `voice.tag_protocol` are NOT in scope: §2 blesses them as the brain's
contract surface. This file guards the declared boundary, it does not invent a stricter one.

Same mechanism as everything else in this suite that works: the tables are MEASUREMENTS, edited DOWNWARD when
a coupling is retired (that edit is the celebration), never upward. A new pair means: use the facade, or
extract the shared thing to a lower layer — not «add my line to the list».
"""
from __future__ import annotations

import ast
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[3]

_SKIP = {".venv", "tests", "node_modules", "__pycache__", ".git", "TMP"}


def _packages() -> set[str]:
    return {d.name for d in ENGINE.iterdir()
            if d.is_dir() and (d / "__init__.py").exists() and d.name not in _SKIP}


def _walk_imports():
    """Yields (rel_path, top_package, ImportFrom node) for every absolute from-import in the engine tree."""
    pkgs = _packages()
    for p in sorted(ENGINE.rglob("*.py")):
        rel = p.relative_to(ENGINE).as_posix()
        parts = rel.split("/")
        if any(x in _SKIP for x in parts):
            continue
        top = parts[0] if len(parts) > 1 else ""
        if top not in pkgs:
            continue
        try:
            tree = ast.parse(p.read_text())
        except Exception:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and not node.level and node.module:
                yield rel, top, node


# ── 1 · the motor's internals are not a facade ──────────────────────────────────────────────────────────────
# Frozen 2026-09-03. One row per (importing file → voice.engine module). Deleting a row is the celebration;
# a row whose file no longer imports the module MUST be deleted, or the ratchet stops ratcheting.
_MOTOR_REACH: set[tuple[str, str]] = {
    ("config/doctor.py", "voice.engine.core"),
    ("config/settings.py", "voice.engine.core.config"),
    ("config/settings.py", "voice.engine.core.langs"),
    ("config/settings.py", "voice.engine.speech.stt"),
    ("config/settings.py", "voice.engine.speech.tts"),
    ("config/settings.py", "voice.engine.speech.voices"),
    ("connectors/messaging/notify.py", "voice.engine.core"),
    ("connectors/music/__init__.py", "voice.engine.core"),
    ("connectors/music/youtube_audio.py", "voice.engine.core"),
    ("connectors/spotify/provider.py", "voice.engine.core"),
    ("i18n/runtime.py", "voice.engine.core"),
    ("memory/state.py", "voice.engine.core"),
    ("nucleo/actionmap/store.py", "voice.engine.core"),
    ("nucleo/agentes/web.py", "voice.engine.core"),
    ("nucleo/agentes/web_cc.py", "voice.engine.core"),
    ("nucleo/browser_search.py", "voice.engine.core"),
    ("nucleo/dispatch_prompts.py", "voice.engine.core"),
    ("nucleo/flash/delivery.py", "voice.engine.core"),
    ("nucleo/flash/image_turn.py", "voice.engine.core"),
    ("nucleo/flash/listing_turn.py", "voice.engine.core"),
    ("nucleo/flash/memory_cache.py", "voice.engine.core"),
    ("nucleo/flash/music_flow.py", "voice.engine.core"),
    ("nucleo/flash/probe.py", "voice.engine.core"),
    ("nucleo/flash/prompt.py", "voice.engine.core"),
    ("nucleo/flash/reminder_guards.py", "voice.engine.core"),
    ("nucleo/flash/vault_rules.py", "voice.engine.core"),
    ("nucleo/flash/video_turn.py", "voice.engine.core"),
    ("nucleo/flash/widget_data_turn.py", "voice.engine.core"),
    ("nucleo/homeostasis.py", "voice.engine.pipeline.agent"),
    ("nucleo/loop.py", "voice.engine.core"),
    ("nucleo/mem_processor.py", "voice.engine.core"),
    ("nucleo/memllm.py", "voice.engine.core"),
    ("nucleo/sparks.py", "voice.engine.core"),
    ("nucleo/turn/vault_gate.py", "voice.engine.core"),
    ("nucleo/websearch.py", "voice.engine.core"),
    ("server/__init__.py", "voice.engine.pipeline.agent"),
    ("server/livekit_api.py", "voice.engine.core"),
    ("server/livekit_api.py", "voice.engine.core.config"),
    ("server/voice_api.py", "voice.engine.core.config"),
    ("server/voice_api.py", "voice.engine.speech.voices"),
    ("widgets/agenda/data.py", "voice.engine.core"),
    ("widgets/navegador/launch_env.py", "voice.engine.core"),
}


def _measured_motor_reach() -> set[tuple[str, str]]:
    return {(rel, node.module) for rel, top, node in _walk_imports()
            if top != "voice" and node.module.startswith("voice.engine")}


def test_no_new_reach_into_the_motors_internals():
    got = _measured_motor_reach()
    new = got - _MOTOR_REACH
    assert not new, (
        "a file outside voice/ reaches NEW internals of the motor — the modularity doc's facade table (§2) is "
        "the front door; if what you need is genuinely shared (like `langs` is), extract it to a low layer "
        "instead of adding a row here:\n  " + "\n  ".join(f"{f} → {m}" for f, m in sorted(new)))


def test_a_retired_reach_leaves_the_table():
    got = _measured_motor_reach()
    stale = _MOTOR_REACH - got
    assert not stale, (
        "these rows no longer import the motor — delete them (the edit IS the celebration, and a stale row is "
        "headroom a future coupling can hide in):\n  " + "\n  ".join(f"{f} → {m}" for f, m in sorted(stale)))


# ── 2 · a private name never crosses a domain boundary ──────────────────────────────────────────────────────
# The one offender, frozen: dispatch's findings reader borrows the browser's handed-over marker. Retiring it
# means act_api exporting a public accessor — then this set goes empty and stays empty.
_PRIVATE_CROSSINGS: set[tuple[str, str, str]] = {
    ("nucleo/workers/findings.py", "widgets.navegador.act_api", "_HANDED"),
}


def test_cross_domain_imports_use_public_names():
    """An underscore name is a promise that nobody outside the module depends on it — a promise the ratchet
    (7.22) leans on every time it moves code «byte for byte» behind aliases. A cross-DOMAIN import of one makes
    that refactor a silent break. Measured 2026-09-03: the whole engine had exactly one, so a second is a
    decision someone should have to defend, not a drift nobody saw."""
    pkgs = _packages()
    got = set()
    for rel, top, node in _walk_imports():
        mtop = node.module.split(".")[0]
        if mtop in pkgs and mtop != top:
            for a in node.names:
                if a.name.startswith("_"):
                    got.add((rel, node.module, a.name))
    new = got - _PRIVATE_CROSSINGS
    assert not new, (
        "a private name is imported across a domain boundary — export a public accessor from the owning module "
        "instead:\n  " + "\n  ".join(f"{f}: from {m} import {n}" for f, m, n in sorted(new)))
    stale = _PRIVATE_CROSSINGS - got
    assert not stale, ("retired crossings must leave the allowlist:\n  "
                       + "\n  ".join(f"{f}: from {m} import {n}" for f, m, n in sorted(stale)))
