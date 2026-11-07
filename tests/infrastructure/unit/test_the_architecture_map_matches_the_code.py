"""The architecture map is the code's portrait, and it may not drift (operator, 2026-11-07).

`.meshkore/docs/architecture/zaelar-architecture-map.json` is the ONE representation of the agent's pieces that the
others are aligned to (the web's Technology pages, the session player, the pieces events declare). The code is its
source; this test is what keeps it true:

  · every path a piece or an external names EXISTS;
  · every root package of the engine is drawn somewhere or listed in `not_drawn` with its reason;
  · every model id the model table (`config/models.default.json`) can call is on an external box, and every model id
    a box claims is one the table (or the Jev client) really uses;
  · ids are unique and every flow joins two pieces that are in the map.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MAP = json.loads((ROOT / ".meshkore/docs/architecture/zaelar-architecture-map.json").read_text(encoding="utf-8"))
BOXES = MAP["pieces"] + MAP["external"]


def _table_models() -> set[str]:
    table = json.loads((ROOT / "config/models.default.json").read_text(encoding="utf-8"))
    out: set[str] = set()
    for svc in table["services"].values():
        for seat in ("titular", "failover"):
            s = svc.get(seat) or {}
            out |= {s[k] for k in ("model", "fast_model") if s.get(k)}
    return out


def test_every_path_in_the_map_exists():
    missing = [(b["id"], p) for b in BOXES for p in b.get("paths", []) + b.get("called_from", []) if not (ROOT / p).exists()]
    assert not missing, f"the map names code that is not there: {missing}"


def test_every_root_package_is_drawn_or_said_why_not():
    drawn = {p.split("/")[0] for b in BOXES for p in b.get("paths", []) + b.get("called_from", [])}
    packages = {d.name for d in ROOT.iterdir() if d.is_dir() and (d / "__init__.py").exists()}
    loose = packages - drawn - set(MAP["not_drawn"])
    assert not loose, f"root packages the map does not account for: {sorted(loose)}"


def test_the_models_are_the_ones_the_table_calls():
    claimed = {m for b in MAP["external"] for m in b.get("model_ids", [])}
    table = _table_models()
    assert table <= claimed, f"the model table calls ids no box shows: {sorted(table - claimed)}"
    jev = "".join(p.read_text(encoding="utf-8") for p in (ROOT / "nucleo/jev").glob("*.py"))
    ghosts = {m for m in claimed - table if m not in jev}
    assert not ghosts, f"boxes claim ids nothing calls: {sorted(ghosts)}"


def test_ids_are_unique_and_flows_join_pieces_of_the_map():
    ids = [b["id"] for b in BOXES]
    assert len(ids) == len(set(ids)), "an id is repeated"
    zones = {z["id"] for z in MAP["zones"]}
    assert all(b["zone"] in zones for b in BOXES)
    flow_ids = [f["id"] for f in MAP["flows"]]
    assert len(flow_ids) == len(set(flow_ids))
    loose = [f["id"] for f in MAP["flows"] if f["a"] not in ids or f["b"] not in ids]
    assert not loose, f"flows to pieces the map does not have: {loose}"
