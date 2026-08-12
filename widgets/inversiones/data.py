#
# Inversiones — dashboard de cartera de tokens. Disco/donut con la asignación + rejilla
# 2×2 de tarjetas (una por token) para que cada posición se lea como un dato separado.
# PASSIVE: view_data() lee de store (siembra ejemplo si está vacío). set_holdings reemplaza
# la cartera entera (carga de datos reales por voz/desde un worker). Stdlib only, nunca lanza.
#
from .. import store

WID = "inversiones"

# Cartera de EJEMPLO (marcada sample=True). El operador no ha pasado aún sus posiciones
# reales; cuando lo haga vía set_holdings, sample pasa a False.
_SAMPLE = {
    "title": "Cartera de inversiones",
    "currency": "€",
    "sample": True,
    "holdings": [
        {"name": "Bitcoin",  "ticker": "BTC", "value": 42000, "change": 2.4},
        {"name": "Ethereum", "ticker": "ETH", "value": 18500, "change": -0.8},
        {"name": "Solana",   "ticker": "SOL", "value": 6200,  "change": 5.1},
        {"name": "Cardano",  "ticker": "ADA", "value": 3300,  "change": 1.2},
    ],
}


def _seed() -> dict:
    db = store.load(WID, {})
    if not db or not db.get("holdings"):
        db = dict(_SAMPLE)
        db["sample"] = True
        store.save(WID, db)
    return db


def view_data(q: str = "") -> dict:
    db = _seed()
    holdings = list(db.get("holdings") or [])
    # Limite blando de seguridad: nada de valores no numéricos al render.
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
    # Reemplaza toda la cartera. payload: {"holdings":[{"name","ticker","value","change"}, ...]}
    # Un worker o la voz lo usan para cargar las posiciones reales del operador.
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
