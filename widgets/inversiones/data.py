#
# Investments: token portfolio dashboard. Donut allocation chart + 2x2 card grid, one card per token, so each
# position reads as a separate datum.
# PASSIVE: view_data() reads from store and seeds an example when empty. set_holdings replaces the whole portfolio
# with real data loaded by voice or from a worker. Stdlib only, never raises.
#
from .. import store

WID = "inversiones"

# EMPTY portfolio. It used to seed an example one — BTC/ETH/SOL/ADA adding up to about EUR 70,000 — flagged
# `sample: True` so the code knew it was fake. The screen did not: a brand-new account opened this widget and
# saw a portfolio, and the one thing a portfolio must never do is show a number that is not yours. A widget's
# data is USER data drawn as a widget; a fresh account owns nothing. Real positions arrive through
# `set_holdings` (voice or a worker), and until then the honest answer is an empty state.
_EMPTY = {
    "title": "Cartera de inversiones",
    "currency": "€",
    "sample": False,
    "holdings": [],
}


def _seed() -> dict:
    db = store.load(WID, {})
    if not db:
        db = dict(_EMPTY)
        store.save(WID, db)
    return db


def view_data(q: str = "") -> dict:
    db = _seed()
    holdings = list(db.get("holdings") or [])
    # Soft safety limit: no non-numeric values reach render.
    clean = []
    for h in holdings:
        try:
            v = float(h.get("value") or 0)
        except Exception:
            v = 0.0
        try:
            c = float(h.get("change") or 0)
        except Exception:
            c = 0.0
        clean.append({
            "name": str(h.get("name") or "—")[:40],
            "ticker": str(h.get("ticker") or "")[:12],
            "value": v,
            "change": c,
        })
    total = sum(h["value"] for h in clean)
    for h in clean:
        h["pct"] = (h["value"] / total * 100) if total > 0 else 0
    return {
        "title": db.get("title", "Cartera de inversiones"),
        "currency": db.get("currency", "€"),
        "sample": bool(db.get("sample", True)),
        "total": total,
        "holdings": clean,
    }


def apply_action(action: str, payload: dict) -> dict:
    # Replace the whole portfolio. payload: {"holdings":[{"name","ticker","value","change"}, ...]}
    # A worker or voice uses this to load the operator's real positions.
    if action == "set_holdings":
        raw = (payload or {}).get("holdings") or []
        norm = []
        for h in raw:
            try:
                v = float(h.get("value") or 0)
            except Exception:
                v = 0.0
            try:
                c = float(h.get("change") or 0)
            except Exception:
                c = 0.0
            norm.append({
                "name": str(h.get("name") or "—")[:40],
                "ticker": str(h.get("ticker") or "")[:12],
                "value": v,
                "change": c,
            })
        db = {
            "title": (payload or {}).get("title", "Cartera de inversiones"),
            "currency": (payload or {}).get("currency", "€"),
            "sample": False,
            "holdings": norm,
        }
        store.save(WID, db)
        return {"ok": True, "saved": len(norm)}
    return {"ok": False, "error": f"acción desconocida: {action}"}
