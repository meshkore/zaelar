"""Every observability event names the architecture piece it comes from (`piece`), by construction.

The canonical map (`.meshkore/docs/architecture/zaelar-architecture-map.json`) is what the web, the session player
and the event stream are aligned to. An event names its piece from the module that emitted it (read once from the
stack against the map's `paths` + `emitters`), or from an explicit `piece=` where one module hosts several.

  · every kind the map lists under a piece's `emits` is emitted, somewhere in the code, by a call site that resolves
    to THAT piece — a claim on the map that no code makes is a box the player would never light;
  · `observer.emit` stamps the derived piece on the event (and the explicit one when passed);
  · an event from a module the map does not draw says `piece="unmapped"` and its path — never a guess;
  · a hand-built dict published on the bus is stamped too, and the event log stores the piece as a column;
  · the emitters table names only pieces that exist and paths that exist.
"""
from __future__ import annotations

import ast
import json
import os
from pathlib import Path

import pytest

from observability import pieces

ROOT = Path(pieces.ROOT)
MAP = json.loads(Path(pieces.MAP_PATH).read_text(encoding="utf-8"))
PIECE_IDS = {p["id"] for p in MAP["pieces"]}

# A bus topic the observer stream re-publishes as one kind (server/boot/nervous_system.py::memory_sse_bridge).
TOPIC_AS_KIND = {"memory.updated": "memory"}

_SKIP_DIRS = {".venv", "tests", ".git", "node_modules", "__pycache__", ".meshkore"}


def _engine_files():
    for d, dirs, files in os.walk(ROOT):
        dirs[:] = [x for x in dirs if x not in _SKIP_DIRS and not x.startswith(".")]
        for f in files:
            if f.endswith(".py"):
                yield Path(d, f)


_MAP_FILES = sorted({x for p in MAP["pieces"] for x in p.get("paths") or []}
                    | {k for k in MAP["emitters"] if not k.startswith("_")})


def _pattern_pieces(fn: ast.FunctionDef) -> list[str]:
    """A helper that names the piece by a path pattern — `pieces.piece_for(f"connectors/{platform}/…", kind)`:
    every piece the map draws for a path that matches it."""
    import re
    out = []
    for n in ast.walk(fn):
        if (isinstance(n, ast.Call) and getattr(n.func, "attr", getattr(n.func, "id", "")) == "piece_for"
                and n.args and isinstance(n.args[0], ast.JoinedStr)):
            rx = "".join(re.escape(v.value) if isinstance(v, ast.Constant) else "[^/]+" for v in n.args[0].values)
            kind = n.args[1].value if len(n.args) > 1 and isinstance(n.args[1], ast.Constant) else ""
            out += [pieces.piece_for(f, kind) for f in _MAP_FILES if re.fullmatch(rx, f)]
    return out


def _module_constants(tree: ast.Module) -> tuple[dict, dict]:
    """Top-level `NAME = "str"` and `NAME = {"k": "str", …}` — a kind or a piece table named once."""
    strs, tables = {}, {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name, v = node.targets[0].id, node.value
            if isinstance(v, ast.Constant) and isinstance(v.value, str):
                strs[name] = v.value
            elif isinstance(v, ast.Dict) and all(isinstance(x, ast.Constant) for x in v.values):
                tables[name] = [x.value for x in v.values]
        elif isinstance(node, ast.FunctionDef):
            got = _pattern_pieces(node)
            if got:
                tables[node.name] = got
    return strs, tables


def _override(call: ast.Call, tables: dict) -> list[str] | None:
    for kw in call.keywords:
        if kw.arg != "piece":
            continue
        v = kw.value
        if isinstance(v, ast.Constant) and isinstance(v.value, str):
            return [v.value]
        # `piece=TABLE.get(x, default)` / `piece=TABLE[x]`: any value of a module-level table, plus the default
        if isinstance(v, ast.Call) and isinstance(v.func, ast.Name) and v.func.id in tables:
            return list(tables[v.func.id])          # a helper of this module that names it by a path pattern
        if isinstance(v, ast.Call) and isinstance(v.func, ast.Attribute) and isinstance(v.func.value, ast.Name):
            out = list(tables.get(v.func.value.id, []))
            out += [a.value for a in v.args[1:] if isinstance(a, ast.Constant)]
            return out or None
        if isinstance(v, ast.Subscript) and isinstance(v.value, ast.Name):
            return list(tables.get(v.value.id, [])) or None
    return None


def emit_sites() -> dict[str, set[str]]:
    """kind → the pieces its literal call sites resolve to (derived, or the explicit `piece=`)."""
    sites: dict[str, set[str]] = {}
    for path in _engine_files():
        rel = path.relative_to(ROOT).as_posix()
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        strs, tables = _module_constants(tree)
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and node.args):
                continue
            fn = node.func
            name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")
            if "emit" not in name:
                continue
            a0 = node.args[0]
            kind = (a0.value if isinstance(a0, ast.Constant) and isinstance(a0.value, str)
                    else strs.get(a0.id) if isinstance(a0, ast.Name) else None)
            if not kind:
                continue
            kind = TOPIC_AS_KIND.get(kind, kind)
            got = _override(node, tables) or [pieces.piece_for(rel, kind)]
            sites.setdefault(kind, set()).update(got)
    return sites


def test_every_kind_a_piece_emits_is_emitted_with_that_piece():
    sites = emit_sites()
    missing = [f"{p['id']} · {k} (call sites resolve to {sorted(sites.get(k, ())) or 'nothing'})"
               for p in MAP["pieces"] for k in p.get("emits") or [] if p["id"] not in sites.get(k, set())]
    assert not missing, ("the map says these pieces emit these kinds, and no call site does it as that piece — "
                         "route the emitting module in `emitters`, pass piece= where one module hosts several, "
                         "or drop the claim:\n  " + "\n  ".join(missing))


def test_the_emitters_table_names_real_pieces_and_real_paths():
    bad = []
    for path, val in MAP["emitters"].items():
        if path.startswith("_"):
            continue
        if not (ROOT / path).exists():
            bad.append(f"{path}: no such path")
        for pid in ([val] if isinstance(val, str) else list(val.values())):
            if pid not in PIECE_IDS:
                bad.append(f"{path}: {pid} is not a piece")
    assert not bad, bad


def _emit_from(rel: str, src: str, **ns):
    """Run `src` as if it were code of engine module `rel` (its frames carry that file name)."""
    code = compile(src, str(ROOT / rel), "exec")
    scope = dict(ns)
    exec(code, scope)
    return scope.get("ev")


@pytest.fixture
def observer(monkeypatch):
    from voice import observer as obs
    monkeypatch.setattr(obs, "_dedup", {})
    return obs


def test_emit_stamps_the_piece_of_the_module_that_emitted(observer):
    ev = _emit_from("nucleo/turn/pipeline_gate.py", "ev = emit('ambient', 'x')", emit=observer.emit)
    assert ev["piece"] == "f_gate"
    # one module, several pieces: the map routes by kind
    ev = _emit_from("voice/engine/pipeline/agent_events.py", "ev = emit('tts', 'say')", emit=observer.emit)
    assert ev["piece"] == "f_mouth"
    ev = _emit_from("voice/engine/pipeline/agent_events.py", "ev = emit('vad', 'start')", emit=observer.emit)
    assert ev["piece"] == "f_ear"


def test_an_explicit_piece_wins_and_an_unknown_one_says_so(observer):
    ev = _emit_from("voice/engine/pipeline/agent_events.py", "ev = emit('transcript', 't', piece='u_chat')",
                    emit=observer.emit)
    assert ev["piece"] == "u_chat"
    ev = _emit_from("nucleo/turn/pipeline_gate.py", "ev = emit('ambient', 'x', piece='no_such_box')",
                    emit=observer.emit)
    assert ev["piece"] == pieces.UNMAPPED and "no_such_box" in ev["piece_src"]


def test_an_unmapped_module_says_so_instead_of_guessing(observer):
    rel = "nucleo/request/stop.py"
    assert pieces.piece_for(rel, "brain") == pieces.UNMAPPED, "pick a module the map does not draw"
    ev = _emit_from(rel, "ev = emit('brain', 'x')", emit=observer.emit)
    assert ev["piece"] == pieces.UNMAPPED
    assert ev["piece_src"] == rel


def test_a_hand_built_dict_on_the_bus_is_stamped_too(observer):
    ev = _emit_from("nucleo/pulse/signals.py", "ev = {'kind': 'pulse', 'label': 'beat'}\nstamp(ev)",
                    stamp=observer.stamp_identity)
    assert ev["piece"] == "b_pulse"


def test_the_event_log_stores_the_piece_as_a_column():
    from bus import log
    names = [c[0] for c in log._COLUMNS]
    assert "piece" in names
    row = log._row({"topic": "observer", "ts_ms": 1.0, "payload": {"kind": "ambient", "piece": "f_gate"}})
    assert row[3 + names.index("piece")] == "f_gate"
    # a topic whose payload carries no piece takes the publisher's, read on the publishing thread
    # a topic whose payload carries no piece: the bus reads the publisher's path at dispatch, the writer maps it
    import bus
    got = []
    bus.add_sink(got.append)
    try:
        _emit_from("memory/queue.py", "bus.emit_sync('memory.updated', {'op': 'write'})", bus=bus)
    finally:
        bus.remove_sink(got.append)
    rec = next(r for r in got if r["topic"] == "memory.updated")
    assert log._row(rec)[3 + names.index("piece")] == "m_queue"
    assert "piece" not in rec["payload"], "the payload is shared with the subscribers: never written into"


def test_an_inbound_message_is_from_its_platforms_piece():
    from connectors.messaging import calls
    assert [calls._inbound_piece(p) for p in ("whatsapp", "telegram", "email")] == ["o_wa", "o_tg", "o_mail"]
    assert calls._inbound_piece("nowhere") == pieces.UNMAPPED
