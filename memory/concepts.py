# concepts.py — central-memory CONCEPT VOCABULARY (V2-013 T126). Shared substrate:
#   • the WRITER (nucleo/memory_agent._derive_concepts) uses it as deterministic backstop for LLM labeling,
#   • the VIEWER (memory/api.map) uses it to derive the SHORT-TERM CONCEPT MAP on the fly (short-term has no
#     persisted concept edges — those are ephemeral pills; long-term does have them in `edges`).
# One place for the taxonomy -> zero divergence between how organization is WRITTEN and DRAWN.
import re

# (concept, keyword regex) — stable order (defines priority when trimming to 3).
CONCEPT_MAP: list[tuple[str, str]] = [
    ("trabajo", r"trabaj|curro|jef[ae]|oficina|empresa|ascend|becari|compañer|n[oó]mina|despid|contrat|reuni[oó]n|colega|carrera profesional|proyecto empresarial|negocio|emprend|startup|cliente"),
    ("salud", r"salud|m[eé]dic|enferm|al[eé]rg|operaci[oó]n|\boperad[oa]\b|\boperaron\b|cirug[íi]a|quir[úu]rg|dolor|tensi[oó]n|hospital|anal[ií]tica|dentista|pastilla|lesi[oó]n|coraz[oó]n|s[ií]ntoma|receta m[eé]dica|fisio|rehabilit|espalda|vacuna|cita m[eé]dica|h[aá]bito saludable|descanso|dormir"),
    ("finanzas", r"dinero|euro|banco|hipoteca|ahorr|invers|fondo|factura|deuda|impuesto|sueldo|renta|pagar|préstamo|prestamo|nómina|cripto|bitcoin"),
    ("familia", r"familia|madre|padre|mam[aá]|pap[aá]|herman[oa]|sobrin|prim[oa]|t[íi][oa]|abuel|hij[oa]|pareja|mujer|marido|novi[oa]|boda|cuñad"),
    ("deporte", r"deporte|p[aá]del|f[uú]tbol|gimnasio|correr|tenis|baloncesto|entrena|partido|marat[oó]n|nadar|bici|yoga|buceo|escalada|surf"),
    ("vivienda", r"\bcasa\b|piso|mudan|mudad|direcci[oó]n|\bcalle\b|barrio|reforma|mueble|alquiler|casero|vecin"),
    ("viajes", r"viaj|vuelo|hotel|maleta|turism|vacacion|escapada|excursi[oó]n|refugio|destino"),
    ("estudios", r"estudi|examen|universidad|\bcurso\b|m[aá]ster|máster|aprend|idioma|jap[oó]n[eé]s|ingl[eé]s|derecho|formaci[oó]n|certificad"),
    ("ocio", r"pel[ií]cula|serie|concierto|m[uú]sica|\blibro\b|leer|vinilo|hobby|afici|jazz|techno|guitarra|videojueg|ocio"),
    ("comida", r"restaurante|\bcena\b|\bcenar\b|cocina|vegetarian|vegano|dieta|receta|desayun|t[aá]per|"
               r"comida familiar|cel[íi]ac|gluten|intoleran|lactosa|alimentari|\bcomer\b|alcohol|\bbeb[eo]"),
    ("tecnología", r"python|c[oó]digo|programa|ordenador|m[oó]vil|\bapp\b|software|widget|script|servidor|ia\b|modelo"),
    ("mascotas", r"perro|gato|mascota"),
    ("objetivos", r"objetivo|\bmeta\b|sue[ñn]o de|prop[oó]sito|aspiraci[oó]n|quiero lograr|me gustar[íi]a llegar|a[ñn]o que viene|a futuro|ilusi[oó]n"),
    ("mensajes", r"whatsapp|telegram|mensaje|chat|escrib[ií]|me ha dicho|contact[oó]"),
    ("agenda", r"agenda|cita|reuni[oó]n|recu[eé]rda|recordatorio|calendario|ma[ñn]ana a las|cron|programad"),
]
CONCEPT_RES = [(c, re.compile(p, re.I)) for c, p in CONCEPT_MAP]


def derive_concepts(text: str, cap: int = 3) -> list[str]:
    """Derive 1..cap concepts from text by keywords (deterministic, cheap). Backstop for LLM labeling on WRITE and
    engine for the SHORT-term concept map in the VIEWER."""
    t = text or ""
    out = [c for c, rx in CONCEPT_RES if rx.search(t)]
    return out[:cap]


# ── V2-858 T549 · one hub per meaning ────────────────────────────────────────────────────────────────────────
# The distiller labels concepts in the memory's language, and that language moved: the live store ended with 71
# hubs in two languages, the car alone spread over ten (car/cars/coche/coches/vehicle/vehicles/transport/…), so a
# category question reached a tenth of what the operator had said. Neither a word table (they only shrink here)
# nor the embedding of a bare word can fold them: measured on the live names, real translations score BELOW
# unrelated pairs (salud~health 0.53 < car~home 0.55). The grouping is a model's call, made in sleep (an LLM may
# write, never read); what this module owns is the deterministic part — apply a fold, keep it, never lose an edge.

import logging

_log = logging.getLogger(__name__)

FOLD_MARKER_KEY = "concepts_fold_sig"


def hubs(db) -> list[dict]:
    """The valid concept hubs: id, name, aliases already folded into it, and how many pills point at it."""
    rows = db.query(
        "SELECT m.id, m.text, m.meta, (SELECT COUNT(*) FROM edges e WHERE e.to_id=m.id) AS n "
        "FROM memories m WHERE m.kind='concept' AND m.valid=1 ORDER BY n DESC, m.id")
    out = []
    for r in rows:
        meta = _meta(r["meta"])
        out.append({"id": int(r["id"]), "name": r["text"], "aliases": list(meta.get("aliases") or []),
                    "edges": int(r["n"])})
    return out


def _meta(raw) -> dict:
    import json
    try:
        m = json.loads(raw or "{}")
    except ValueError as e:
        _log.warning("concepts: a hub's meta is not JSON (%s) — read as empty", e)
        m = None
    return m if isinstance(m, dict) else {}


def fts_text(name: str, aliases: list[str]) -> str:
    """What a hub's FTS row indexes: its name and every name folded into it (a query in either language hits)."""
    return " ".join([name, *[a for a in aliases if a and a != name]])


def plan_fold(hub_rows: list[dict], groups: list[list[str]]) -> dict[str, str]:
    """`{alias_name: canonical_name}` from the model's GROUPS. The model only says which names mean the same; the
    canonical is chosen here, deterministically: the hub most pills already point at (ties → lowest id). Names the
    model invented, groups of one and a name claimed by two groups are dropped — fail-closed, never a guess."""
    by_name = {h["name"]: h for h in hub_rows}
    seen: set = set()
    plan: dict[str, str] = {}
    for g in groups or []:
        if not isinstance(g, (list, tuple)):
            continue
        names = []
        for x in g:
            n = str(x or "").strip().lower()
            if n in by_name and n not in names:
                names.append(n)
        if len(names) < 2 or seen & set(names):
            continue
        seen |= set(names)
        canon = max(names, key=lambda n: (by_name[n]["edges"], -by_name[n]["id"]))
        for n in names:
            if n != canon:
                plan[n] = canon
    return plan


def fold(db, plan: dict[str, str], now: int) -> dict:
    """Apply `{alias: canonical}`: every edge of the alias hub moves to the canonical (none is lost, duplicates
    merge), the alias hub is invalidated pointing at its canonical (history kept) and leaves the indexes, and the
    canonical records the alias so the writer keeps resolving it and its FTS row answers in both languages."""
    import json
    by_name = {h["name"]: h for h in hubs(db)}
    folded = moved = 0
    for alias, canon in plan.items():
        a, c = by_name.get(alias), by_name.get(canon)
        if not a or not c or a["id"] == c["id"]:
            continue
        aid, cid = a["id"], c["id"]
        aliases = [x for x in dict.fromkeys([*c["aliases"], alias, *a["aliases"]]) if x != canon]
        with db.cursor() as cur:
            for col, other in (("to_id", "from_id"), ("from_id", "to_id")):
                for e in cur.execute(f"SELECT {other} AS o, type, weight FROM edges WHERE {col}=?",
                                     (aid,)).fetchall():
                    o = e[0]
                    if o == cid:
                        continue
                    pair = (o, cid) if col == "to_id" else (cid, o)
                    cur.execute("INSERT OR IGNORE INTO edges (from_id, to_id, type, weight) VALUES (?, ?, ?, ?)",
                                (*pair, e[1], e[2]))
                    moved += 1
            cur.execute("DELETE FROM edges WHERE from_id=? OR to_id=?", (aid, aid))
            ameta = _meta(cur.execute("SELECT meta FROM memories WHERE id=?", (aid,)).fetchone()[0])
            if getattr(db, "fts_available", False):
                try:
                    cur.execute("INSERT INTO fts_memories(fts_memories, rowid, text) VALUES ('delete', ?, ?)",
                                (aid, fts_text(alias, a["aliases"])))
                    cur.execute("INSERT INTO fts_memories(fts_memories, rowid, text) VALUES ('delete', ?, ?)",
                                (cid, fts_text(canon, c["aliases"])))
                    cur.execute("INSERT INTO fts_memories (rowid, text) VALUES (?, ?)",
                                (cid, fts_text(canon, aliases)))
                except Exception as e:  # noqa: BLE001 — a hub without an FTS row must not stop the fold
                    _log.warning("concepts: FTS re-index of hub %s → %s failed (%s)", aid, cid, e)
            if getattr(db, "vec_available", False):
                try:
                    cur.execute("DELETE FROM vec_memories WHERE memory_id=?", (aid,))
                except Exception as e:  # noqa: BLE001
                    _log.warning("concepts: could not drop the vector of folded hub %s (%s)", aid, e)
            ameta.update({"pruned": 1, "folded_into": cid})          # already de-indexed: prune must not redo it
            cur.execute("UPDATE memories SET valid=0, superseded_by=?, updated=?, invalidated_at=?, meta=? "
                        "WHERE id=?", (cid, now, now, json.dumps(ameta, ensure_ascii=False), aid))
            cmeta = _meta(cur.execute("SELECT meta FROM memories WHERE id=?", (cid,)).fetchone()[0])
            cmeta["aliases"] = aliases
            cur.execute("UPDATE memories SET meta=?, updated=? WHERE id=?",
                        (json.dumps(cmeta, ensure_ascii=False), now, cid))
        c["aliases"] = aliases
        folded += 1
    return {"folded": folded, "edges_moved": moved}


def fold_pass(db, group_fn, now: int, kv_get=None, kv_set=None) -> dict:
    """REM's phase: ask `group_fn(names) -> [[name, …], …]` which hubs mean the same, plan, fold. Skipped (no model
    call) when the hub set is the one already folded — the marker is the sorted names after the last pass."""
    hs = hubs(db)
    names = sorted(h["name"] for h in hs)
    sig = "|".join(names)
    if len(names) < 2:
        return {"hubs": len(names), "folded": 0, "skipped": "few"}
    if kv_get is not None and kv_get(FOLD_MARKER_KEY) == sig:
        return {"hubs": len(names), "folded": 0, "skipped": "unchanged"}
    try:
        groups = group_fn(names) if group_fn else None
    except Exception:  # noqa: BLE001 — a model failure folds nothing and leaves the marker for the next sleep
        groups = None
    if groups is None:
        return {"hubs": len(names), "folded": 0, "skipped": "no_model"}
    rep = fold(db, plan_fold(hs, groups), now)
    if kv_set is not None:
        kv_set(FOLD_MARKER_KEY, "|".join(sorted(h["name"] for h in hubs(db))))
    return {"hubs": len(names), **rep}
