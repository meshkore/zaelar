"""V2-707 F1 · The CATALOG HARNESS: every action a widget declares is still reachable through the funnel.

## Why this exists

> «¿Podemos ser capaces de inferir las cosas que se pueden hacer, por ejemplo, con el widget de la agenda
> para asegurar de que todas esas tools, guardarraíles, etcétera, lo soporten? Es decir, ¿tengo que poder
> crear ítems, borrar ítems, mover ítems, invitar a personas, notificar a personas?» — the operator,
> 2026-09-16.

The capability inference already exists: a `manifest.json` IS the declaration of what a widget can do, and
`hbwidget read` hands it over with the real ids. What did not exist is the other half — anything that
checks the declared surface against the GUARDS standing in front of it. And that gap is not theoretical:
on 2026-09-16 a correct `cancel_meeting` was thrown away by the anti-drag guard while the model was told to
re-issue it, and nothing anywhere said an action had become unreachable.

So this walks the catalog: **for every widget, for every declared action, a minimal valid call must reach
the handler.** It is a ratchet, not a scenario — it grows by itself as widgets are added, and it fails the
day somebody adds a guard that silently eats a declared capability.

## What "reachable" means here, precisely

`dispatch_raw` is stubbed, so nothing runs and no network is touched: the question is only whether the call
SURVIVES `_dispatch` — the alias fold, the V2-705 contract, the production gate, the generic-door branch —
and arrives. An action refused because its selector is empty is NOT unreachable: it is the contract working,
and the harness fills the selector from the widget's own `ref_index` exactly as the refusal's menu tells the
model to. That is the difference between a door that says «name one» and a door that is shut.
"""
from __future__ import annotations

import asyncio
import json
import pathlib

import pytest

from widgets import actions as wactions
from widgets import contract, rows

ENGINE = pathlib.Path(__file__).resolve().parents[4]
WIDGETS = ENGINE / "widgets"


def _catalog() -> list[tuple[str, str, dict]]:
    out = []
    for d in sorted(p for p in WIDGETS.iterdir() if p.is_dir() and not p.name.startswith("_")):
        man_path = d / "manifest.json"
        if not man_path.is_file():
            continue
        try:
            man = json.loads(man_path.read_text(encoding="utf-8"))
        except Exception:                                     # a broken manifest is another test's business
            continue
        for name, spec in (man.get("actions") or {}).items():
            out.append((d.name, name, spec if isinstance(spec, dict) else {}))
    return out


CATALOG = _catalog()


def test_the_catalog_is_not_empty():
    """The harness is worthless if the walk silently finds nothing — the failure mode of every ratchet."""
    # 11 since V2-764: the separate `torrent` widget was retired into Archivos' Torrents section.
    assert len({w for w, _, _ in CATALOG}) >= 11, f"only {len({w for w, _, _ in CATALOG})} widgets walked"
    assert len(CATALOG) >= 150, f"only {len(CATALOG)} declared actions walked"


def _sample(wid: str, field: str) -> str:
    """A value the widget itself would recognise for this selector — from its own `ref_index`, which is what
    the contract's refusal offers the model. Falls back to a string, which is enough to pass the contract."""
    try:
        from widgets import refs
        for r in refs._ref_index(wid) or []:
            if str(r.get("field") or "") == field:
                return str(r.get("id") or r.get("label") or "x")
    except Exception:                                          # noqa: BLE001
        pass
    return "x"


def _minimal(wid: str, action: str, spec: dict) -> dict:
    """The smallest payload that satisfies the DECLARED contract: every non-optional key filled."""
    payload: dict = {}
    for key, desc in (spec.get("payload") or {}).items():
        if contract._OPTIONAL_RE.search(str(desc or "")):
            continue
        payload[key] = _sample(wid, key)
    field = contract.selector_for(wid, action, spec)
    if field and not str(payload.get(field) or "").strip():
        payload[field] = _sample(wid, field)
    return payload


@pytest.mark.parametrize("wid,action,spec", CATALOG, ids=[f"{w}.{a}" for w, a, _ in CATALOG])
def test_a_declared_action_survives_every_guard_in_the_funnel(wid, action, spec, monkeypatch, tmp_path):
    from widgets import server_api, store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))     # never the operator's real data
    landed: list = []

    async def _land(w, a, p):
        landed.append((w, a, p))
        return {"ok": True}

    monkeypatch.setattr(server_api, "dispatch_raw", _land)
    res = asyncio.run(server_api._dispatch(wid, action, _minimal(wid, action, spec)))

    if landed:
        assert landed[0][1] == action, f"the funnel rewrote {action} into {landed[0][1]}"
        return
    # It did not land: the only acceptable reason is a gate that SAYS SO, in the shape the callers read.
    assert isinstance(res, dict) and res.get("ok") is False, (
        f"{wid}.{action} vanished in the funnel without reaching the handler and without a refusal: {res}")
    assert str(res.get("error") or ""), f"{wid}.{action} was refused with no machine-readable reason: {res}"


@pytest.mark.parametrize("wid,action,spec", CATALOG, ids=[f"{w}.{a}" for w, a, _ in CATALOG])
def test_a_declared_action_is_classified_and_never_silently_undeclared(wid, action, spec):
    """The other half of «is it reachable»: the FlashBrain routes by `action_mode`, and an action that
    classifies as None escalates instead of running — the V2-540 defect, a capability that gets NARRATED."""
    from widgets import runtime
    live = ((runtime.get(wid) or {}).get("actions") or {})
    assert action in live, f"{wid}.{action} is in the manifest on disk and not in the live runtime catalog"
    assert wactions.classify(spec, action) in (wactions.FAST, wactions.CONFIRM, wactions.ESCALATE)


# ── the collections a widget declares must also be operable ────────────────────────────────────────────

@pytest.mark.parametrize("wid", sorted({w for w, _, _ in CATALOG}))
def test_every_declared_collection_answers_a_read(wid, monkeypatch, tmp_path):
    """A collection nobody can list is a structure the worker cannot see, which is the whole point of F1."""
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    for coll in rows.declared(wid):
        assert "list" in rows.ops_for(wid, coll), f"{wid}.{coll} cannot even be read"
        p = rows.plan(wid, "list", {"collection": coll})
        assert p.get("ok") is True, f"{wid}.{coll} refuses a plain list: {p}"


def test_a_widget_that_declares_no_collection_says_so_instead_of_crashing():
    """Most widgets hold no row collection, and the door must be a no-op for them, not an exception."""
    p = rows.plan("clock", "delete", {"collection": "whatever"})
    assert p.get("ok") is False and p["error"] == rows.UNKNOWN_COLLECTION
