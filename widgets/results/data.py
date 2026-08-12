#
# results widget — backend. INTENTIONALLY does no searching of its own: it is the GENERIC PRESENTATION SURFACE of
# zaelar. Whoever DID the work (a Brain Worker that searched the web, the navegador, the FlashBrain) hands it a
# finished result set and this widget just PERSISTS and RENDERS it. Works the same for pools, cars, holidays,
# open-source projects, emails, files — it never knows nor cares what the items are about.
#
# HOW IT GETS FILLED (the only way; there is no other channel):
#   a Brain Worker →  python -m nucleo.widget_cli data results present '{"title": "...", "items": [...]}'
#   the FlashBrain →  tool widget_data(widget_id="results", action="present", payload={...})
# Both land on apply_action() below → store.save() → the single SSE "this widget changed" event → the open card
# re-fetches view_data() and re-renders. Because the payload is PERSISTED (not ephemeral), it survives the
# re-render, a reconnect and a server restart — the operator does not lose a report he already paid for.
#
# HISTORY (2026-08-02): view_data() used to return a hardcoded demo list of the operator's projects
# (Pricewaterhouse / Mage Core / MeshKore…). Showing the widget for a pool search therefore painted "Proyectos" —
# which is exactly what the operator saw and reported ("solo veo el widget de proyectos abierto, que no tiene
# nada que ver"). A generic presentation surface has NO content of its own: with nothing pushed it is an EMPTY
# SHEET, never someone else's data.
#
# HISTORY (2026-08-09): a result was strictly FLAT — one card = one thing. That cannot express what a real
# research answer looks like: the operator asked for holiday PROPOSALS, and a proposal is a BUNDLE (this hotel +
# that ferry crossing + maybe a restaurant), each piece with its own price, photo, link and times. Flattening a
# bundle into free text loses the structure the operator wants to compare on. So an item may now carry `parts`
# (the pieces it is made of) plus, for the DRILL-DOWN, `images`/`facts` (a photo gallery and the label→value
# sheet: check-in, port, cancellation policy…). And `view`/`focus` give the sheet a SECOND PAGE: "enséñame en
# detalle la propuesta 1" switches this same widget to the full dossier of one item instead of the compact grid.
#
# HISTORY (2026-08-12) — LA HOJA TIENE CUATRO PESTAÑAS, no solo la lista. Norma del operador: esta superficie se va
# a usar de forma genérica para MUCHAS búsquedas complejas, y una búsqueda compleja no es solo su resultado. Es
# también CÓMO va, CON QUÉ criterio y DE DÓNDE salen los datos. Hasta hoy las tres últimas cosas solo existían de
# palabra —había que preguntárselas al agente— y por tanto no se podían comprobar:
#
#   · RESULTADOS (la importante) — las fichas, y el expediente de una al abrirla.
#   · SUMARIO    — estado del trabajo + cuántos candidatos ha explorado, cuántos quedan en pantalla, qué ha hecho.
#   · FUENTES    — en qué webs ha entrado y QUÉ PASÓ en cada una: entró, no pudo por autenticación, le limitaron
#                  a 50 resultados, dio error. Es lo que convierte «no encontré nada» en un dato auditable.
#   · CRITERIOS  — el encargo tal y como se está ejecutando (duros/blandos/asumidos/baremo) MÁS las correcciones
#                  que el operador va soltando por voz («que sean de 42 a 49 pies»). Se siembran solos desde el
#                  BRIEF (`nucleo/research.py`), así que no dependen de que el worker se acuerde de escribirlos.
#
# Las cuatro viven en el MISMO payload persistido que la lista, y la pestaña activa (`tab`) también — igual que
# `view`/`focus`: así «enséñame de dónde has sacado esto» es una orden de voz que mueve la pantalla, y el estado
# sobrevive al re-render, a reconectar y a reiniciar. Cero protocolo nuevo: todo entra por acciones DECLARADAS.
#
# Y la FICHA es DINÁMICA (`blocks`): cada tipo de resultado necesita enseñarse distinto — un barco no se lee como
# un paper ni como un correo. En vez de un esquema fijo (que obliga a disolver lo que no encaje en prosa) o de HTML
# crudo del worker (que es una inyección esperando a ocurrir: este payload viene de la web abierta), un item puede
# traer una LISTA DE BLOQUES de un vocabulario cerrado —texto, ficha de datos, etiquetas, galería, medidor,
# tabla, enlace, sección— que la superficie pinta con `textContent`. Es la misma libertad de composición sin
# ceder la superficie a un tercero.
#
from .. import store

WIDGET_ID = "results"

# Fields an item may carry. Anything else pushed is dropped — the payload comes from a worker that read the open
# web, so we never let arbitrary keys through to the renderer (widget.js paints with textContent only, but the
# schema is the contract and it stays closed).
_ITEM_FIELDS = ("title", "subtitle", "price", "badge", "url", "image", "primary", "lines",
                "parts", "images", "facts", "score", "blocks")
# A PART is one piece of a composite item (the hotel inside a holiday plan, the ferry, the restaurant). Same
# closed-schema discipline; `kind` is the piece's role ("Hotel", "Ferry", "Restaurante") so the card can label it.
_PART_FIELDS = ("kind", "title", "subtitle", "price", "url", "image", "lines", "facts")

# ── FICHA DINÁMICA: vocabulario CERRADO de bloques ────────────────────────────────────────────────────────────
# Un tipo de resultado distinto necesita una ficha distinta, y el esquema fijo obligaba a disolver en prosa todo
# lo que no encajara. Esto lo resuelve SIN aceptar HTML del worker: son piezas de composición que la superficie
# pinta con textContent. Cualquier `kind` fuera de esta lista se descarta entero (no se degrada a texto: un bloque
# que el operador no verá es mejor que uno que se ve donde no debe).
_BLOCK_KINDS = ("text", "facts", "chips", "gallery", "meter", "table", "link", "section")
_MAX_BLOCKS = 14         # una ficha, no un documento
_MAX_CHIPS = 14
_MAX_TABLE_ROWS = 24
_MAX_TABLE_COLS = 6
_MAX_CELL_CHARS = 90

_MAX_ITEMS = 60          # a report the operator can actually read; widget.js renders the first 24 and says how many more
# `lines` used to cap at 4 — fine for a spec-sheet bullet list, but a real request ("show me the lyrics to X") needs
# a whole song's worth of text in ONE item's body (2026-08-03). Raised so a full block of text fits; still bounded
# so a worker can't paste an entire scraped page into a card.
_MAX_LINES = 80
_MAX_LINE_CHARS = 300
_MAX_PARTS = 6           # a plan is a handful of pieces (hotel+ferry+restaurante), never a list in disguise
_MAX_PART_LINES = 20
_MAX_IMAGES = 12         # the detail page's photo gallery
_MAX_FACTS = 30          # label→value sheet (check-in, puerto, política de cancelación…)
_MAX_FACT_CHARS = 200

# ── LAS OTRAS TRES PESTAÑAS ────────────────────────────────────────────────────────────────────────────────────
_TABS = ("results", "summary", "sources", "criteria")

# Una FUENTE es una web/origen que se ha intentado, con lo que PASÓ ahí. El estado es un vocabulario cerrado
# porque de él depende el color y, sobre todo, la lectura: «no pude entrar» y «entré pero me cortó a 50» son
# resultados MUY distintos y hasta hoy los dos se contaban como «nada».
_SOURCE_FIELDS = ("name", "url", "status", "detail", "found")
_SOURCE_STATUS = ("ok", "partial", "auth", "blocked", "error", "pending")
_MAX_SOURCES = 40
_MAX_DETAIL_CHARS = 200

# El SUMARIO: estado global + recuentos + lo que se ha ido haciendo. `explored`/`selected`/`discarded` los REPORTA
# quien trabaja (solo él sabe cuántos candidatos miró de verdad); lo que se puede derivar se deriva y se etiqueta
# como derivado, nunca se confunden (ver `_counts`).
_SUMMARY_NUMS = ("explored", "selected", "discarded", "round")
_SUMMARY_TEXT = ("state", "note")
_MAX_STEPS = 24          # bitácora de lo hecho: los hitos, no cada clic
_MAX_STEP_CHARS = 160

# Los CRITERIOS con los que se está ejecutando el encargo. Mismos nombres que el brief de `nucleo/research.py`
# (de ahí se siembran) + `changes`: las correcciones que el operador va soltando MIENTRAS se busca, que son
# justo las que hasta ahora se perdían en la conversación.
_CRIT_LISTS = ("hard", "soft", "assumed", "enrichments", "quality_bar", "changes")
_MAX_CRIT = 14
_MAX_CRIT_CHARS = 220


# ── CONTROL DE CALIDAD DE PRESENTACIÓN (2026-08-10) ───────────────────────────────────────────────────────────────
# Los presupuestos de campo y las reglas viven en `widgets/presentation.py` (compartidas por TODA superficie en
# blanco); aquí solo se aplican. Dos cosas cambian respecto a antes:
#   · el recorte va por frontera de PALABRA y se marca. El `[:200]` de antes cortó un aviso real del worker
#     («⚠️ Llevar tu cadena…») dejándolo en «⚠️ Llevar tu c»: una salvedad amputada engaña más que su ausencia.
#   · un payload que rompe la tarjeta deja RASTRO. Un prompt es una petición, no una garantía: si el título trae
#     tres ideas dentro, se registra y vuelve en la respuesta de la acción, así el worker puede corregirlo.
def _clip(text, key: str) -> str:
    try:
        from widgets import presentation
        return presentation.clip(text, presentation.contract(WIDGET_ID)[key])[0]
    except Exception:
        return "" if text is None else str(text)[:220]


def _audit(payload: dict) -> list[str]:
    try:
        from widgets import presentation
        issues = presentation.audit(WIDGET_ID, payload)
    except Exception:
        return []
    if issues:
        try:
            from voice.observer import emit
            emit("widget", "🎨 presentación: el payload rompe la tarjeta", text=" · ".join(issues)[:400],
                 role="system", extra={"id": WIDGET_ID, "n": len(issues), "issues": issues[:12]})
        except Exception:
            pass
    return issues


def _clean_facts(raw) -> list[dict]:
    """`facts` is the STRUCTURED half of a result — the part the operator asks precise questions about later
    ("¿a qué hora es el check-in?", "¿lleva desayuno?"). Written naturally as {label: value} by whoever found it,
    but STORED as an ordered list so the order the researcher chose survives the round-trip (and so a label can
    repeat, which a dict silently swallows). A list of pairs or of {label,value} dicts is accepted too — the
    payload comes from an LLM and all three shapes are things it plausibly emits."""
    out: list[dict] = []
    items = []
    if isinstance(raw, dict):
        items = list(raw.items())
    elif isinstance(raw, (list, tuple)):
        for entry in raw:
            if isinstance(entry, dict):
                items.append((entry.get("label") or entry.get("k") or entry.get("name"),
                              entry.get("value") if entry.get("value") is not None else entry.get("v")))
            elif isinstance(entry, (list, tuple)) and len(entry) >= 2:
                items.append((entry[0], entry[1]))
    for label, value in items:
        if label in (None, "") or value in (None, ""):
            continue
        out.append({"label": str(label)[:80], "value": str(value)[:_MAX_FACT_CHARS]})
        if len(out) >= _MAX_FACTS:
            break
    return out


def _clean_lines(raw, cap: int) -> list[str]:
    if isinstance(raw, (list, tuple)):
        return [str(x)[:_MAX_LINE_CHARS] for x in raw if x not in (None, "")][:cap]
    if raw:
        return [str(raw)[:_MAX_LINE_CHARS]]
    return []


def _clean_images(raw) -> list[str]:
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, (list, tuple)):
        return []
    return [str(x)[:500] for x in raw if x not in (None, "")][:_MAX_IMAGES]


def _num(raw, default=None):
    if isinstance(raw, bool) or raw in (None, ""):
        return default
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return default
    if v != v or v in (float("inf"), float("-inf")):     # NaN/inf: un número que no se puede pintar ni comparar
        return default
    return int(v) if float(v).is_integer() else round(v, 2)


def _clean_score(raw) -> dict | None:
    """LA VALORACIÓN. El operador la pidió explícitamente en la ficha de detalle, y estaba en el esquema desde
    hace meses SIN pintarse en ningún sitio — se guardaba y se perdía.

    Se acepta como número suelto (`8.7`), como texto («8,7/10») o como objeto `{value,max,label,why}`. El `why`
    es lo que la hace útil de verdad: una nota sin el porqué no se puede discutir ni corregir."""
    if raw in (None, ""):
        return None
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        v = _num(raw)
        return None if v is None else {"value": v, "max": 10 if v <= 10 else 100}
    if isinstance(raw, str):
        s = raw.strip()[:60]
        if not s:
            return None
        body, _, mx = s.partition("/")
        v = _num(body.replace(",", "."))
        if v is None:
            return {"label": s}                          # «Excelente», «A+»: vale como etiqueta, no como número
        out = {"value": v, "max": _num(mx) or (10 if v <= 10 else 100)}
        return out
    if isinstance(raw, dict):
        out: dict = {}
        v = _num(raw.get("value") if raw.get("value") is not None else raw.get("score"))
        if v is not None:
            out["value"] = v
            out["max"] = _num(raw.get("max")) or (10 if v <= 10 else 100)
        for k in ("label", "why"):
            if raw.get(k):
                out[k] = str(raw[k])[:_MAX_FACT_CHARS]
        return out or None
    return None


def _clean_block(raw, depth: int = 0) -> dict | None:
    """UN bloque de una ficha dinámica. Vocabulario cerrado: un `kind` desconocido no se degrada a texto, se cae."""
    if not isinstance(raw, dict):
        return None
    kind = str(raw.get("kind") or "").strip().lower()
    if kind not in _BLOCK_KINDS:
        return None
    b: dict = {"kind": kind}
    if raw.get("title"):
        b["title"] = str(raw["title"])[:120]

    if kind == "text":
        lines = _clean_lines(raw.get("lines") if raw.get("lines") is not None else raw.get("text"), _MAX_LINES)
        if not lines:
            return None
        b["lines"] = lines
        if str(raw.get("tone") or "").lower() in ("muted", "strong", "warn"):
            b["tone"] = str(raw["tone"]).lower()
    elif kind == "facts":
        f = _clean_facts(raw.get("facts") if raw.get("facts") is not None else raw.get("items"))
        if not f:
            return None
        b["facts"] = f
    elif kind == "chips":
        src = raw.get("chips") if raw.get("chips") is not None else raw.get("items")
        chips = [str(c)[:60] for c in src if c not in (None, "")][:_MAX_CHIPS] if isinstance(src, (list, tuple)) else []
        if not chips:
            return None
        b["chips"] = chips
    elif kind == "gallery":
        img = _clean_images(raw.get("images") if raw.get("images") is not None else raw.get("items"))
        if not img:
            return None
        b["images"] = img
    elif kind == "meter":
        v = _num(raw.get("value"))
        if v is None:
            return None
        b["value"] = v
        b["max"] = _num(raw.get("max")) or (10 if v <= 10 else 100)
        if raw.get("caption"):
            b["caption"] = str(raw["caption"])[:_MAX_FACT_CHARS]
    elif kind == "table":
        rows_raw = raw.get("rows")
        if not isinstance(rows_raw, (list, tuple)):
            return None
        cols = [str(c)[:40] for c in raw.get("columns") or [] if c not in (None, "")][:_MAX_TABLE_COLS]
        rows = []
        for r in rows_raw:
            if not isinstance(r, (list, tuple)):
                continue
            cells = [("" if c is None else str(c))[:_MAX_CELL_CHARS] for c in r][:_MAX_TABLE_COLS or 6]
            if any(c for c in cells):
                rows.append(cells)
            if len(rows) >= _MAX_TABLE_ROWS:
                break
        if not rows:
            return None
        if cols:
            b["columns"] = cols
        b["rows"] = rows
    elif kind == "link":
        url = str(raw.get("url") or "").strip()[:500]
        if not url:
            return None
        b["url"] = url
        b["label"] = str(raw.get("label") or url)[:120]
    elif kind == "section":
        if depth:                                        # UN nivel de anidamiento: una ficha, no un árbol
            return None
        inner = _clean_blocks(raw.get("blocks"), depth + 1)
        if not inner:
            return None
        b["blocks"] = inner
    return b


def _clean_blocks(raw, depth: int = 0) -> list[dict]:
    if not isinstance(raw, (list, tuple)):
        return []
    out = []
    for r in raw:
        b = _clean_block(r, depth)
        if b:
            out.append(b)
        if len(out) >= _MAX_BLOCKS:
            break
    return out


def _clean_part(raw: dict) -> dict | None:
    if not isinstance(raw, dict):
        return None
    p: dict = {}
    for k in _PART_FIELDS:
        v = raw.get(k)
        if v is None or v == "":
            continue
        if k == "lines":
            p[k] = _clean_lines(v, _MAX_PART_LINES)
        elif k == "facts":
            f = _clean_facts(v)
            if f:
                p[k] = f
        else:
            p[k] = str(v)[:300]
    return p if p.get("title") else None      # a piece with no name can't be shown or talked about


def _clean_parts(raw) -> list[dict]:
    if not isinstance(raw, (list, tuple)):
        return []
    out = []
    for r in raw:
        p = _clean_part(r)
        if p:
            out.append(p)
    return out[:_MAX_PARTS]


def _clean_item(raw: dict) -> dict | None:
    if not isinstance(raw, dict):
        return None
    it: dict = {}
    for k in _ITEM_FIELDS:
        v = raw.get(k)
        if v is None or v == "":
            continue
        if k == "primary":
            it[k] = bool(v)
        elif k == "lines":
            it[k] = _clean_lines(v, _MAX_LINES)
        elif k == "parts":
            p = _clean_parts(v)
            if p:
                it[k] = p
        elif k == "images":
            img = _clean_images(v)
            if img:
                it[k] = img
        elif k == "facts":
            f = _clean_facts(v)
            if f:
                it[k] = f
        elif k == "blocks":
            b = _clean_blocks(v)
            if b:
                it[k] = b
        elif k == "score":
            s = _clean_score(v)
            if s:
                it[k] = s
        else:
            it[k] = str(v)[:300]
    return it if it.get("title") else None       # a card with no title is not a result, it is noise


def _clean_items(raw) -> list[dict]:
    if not isinstance(raw, (list, tuple)):
        return []
    out = []
    for r in raw:
        it = _clean_item(r)
        if it:
            out.append(it)
    return out[:_MAX_ITEMS]


def _clean_source(raw) -> dict | None:
    if not isinstance(raw, dict):
        return None
    s: dict = {}
    for k in _SOURCE_FIELDS:
        v = raw.get(k)
        if v is None or v == "":
            continue
        if k == "found":
            n = _num(v)
            if n is not None:
                s[k] = int(n)
        elif k == "status":
            st = str(v).strip().lower()
            s[k] = st if st in _SOURCE_STATUS else "ok"
        elif k == "detail":
            s[k] = _clip(v, "source_detail") or str(v)[:_MAX_DETAIL_CHARS]
        else:
            s[k] = str(v)[:300]
    if not s.get("name") and s.get("url"):
        s["name"] = s["url"].split("//")[-1].split("/")[0]      # sin nombre, el dominio ya identifica la fuente
    if not s.get("name"):
        return None                              # una fuente que no se puede nombrar no se puede leer ni auditar
    s.setdefault("status", "ok")
    return s


def _clean_sources(raw) -> list[dict]:
    if isinstance(raw, dict):
        raw = [raw]
    if not isinstance(raw, (list, tuple)):
        return []
    out = []
    for r in raw:
        s = _clean_source(r)
        if s:
            out.append(s)
    return out[:_MAX_SOURCES]


def _clean_summary(raw) -> dict:
    if not isinstance(raw, dict):
        return {}
    out: dict = {}
    for k in _SUMMARY_NUMS:
        n = _num(raw.get(k))
        if n is not None and n >= 0:
            out[k] = int(n)
    for k in _SUMMARY_TEXT:
        if raw.get(k):
            out[k] = _clip(raw[k], "sheet_subtitle") or str(raw[k])[:220]
    steps = raw.get("steps")
    if isinstance(steps, str):
        steps = [steps]
    if isinstance(steps, (list, tuple)):
        clean = [str(x)[:_MAX_STEP_CHARS] for x in steps if x not in (None, "")][:_MAX_STEPS]
        if clean:
            out["steps"] = clean
    return out


def _clean_criteria(raw) -> dict:
    if not isinstance(raw, dict):
        return {}
    out: dict = {}
    for k in ("goal", "domain"):
        if raw.get(k):
            out[k] = str(raw[k])[:400]
    for k in _CRIT_LISTS:
        v = raw.get(k)
        if isinstance(v, str):
            v = [v]
        if isinstance(v, (list, tuple)):
            clean = [str(x)[:_MAX_CRIT_CHARS] for x in v if x not in (None, "")][:_MAX_CRIT]
            if clean:
                out[k] = clean
    n = _num(raw.get("min_candidates"))
    if n is not None and n > 0:
        out["min_candidates"] = int(n)
    n = _num(raw.get("n_final"))
    if n is not None and n > 0:
        out["n_final"] = int(n)
    return out


def _empty() -> dict:
    return {"title": "Resultados", "subtitle": "", "items": []}


def _counts(data: dict) -> dict:
    """Recuentos DERIVADOS, separados de los reportados a propósito. «Cuántos ha explorado» solo lo sabe quien
    trabajó (lo reporta en el sumario); «cuántos hay en pantalla» y «cuántas fuentes» los sabe la hoja. Mezclarlos
    en un solo número sería inventarse la mitad: si nadie reportó amplitud, el sumario lo DICE en vez de enseñar
    el número de tarjetas como si fuera lo explorado."""
    items = data.get("items") or []
    sources = data.get("sources") or []
    summary = data.get("summary") or {}
    ok = [s for s in sources if s.get("status") in ("ok", "partial")]
    got = sum(int(s.get("found") or 0) for s in sources)
    return {
        "shown": len(items),
        "sources": len(sources),
        "sources_ok": len(ok),
        "sources_failed": len([s for s in sources if s.get("status") in ("auth", "blocked", "error")]),
        "from_sources": got,                     # candidatos vistos SEGÚN las fuentes reportadas
        "explored": summary.get("explored"),     # lo que el trabajador declara haber evaluado de verdad
        "selected": summary.get("selected", len(items) or None),
    }


def view_data(q: str = "") -> dict:
    """The LAST result set pushed here, verbatim. Nothing pushed yet → an empty sheet (never invented content)."""
    db = store.load(WIDGET_ID, _empty())
    if not isinstance(db, dict):
        db = _empty()
    data = dict(db)
    data.setdefault("title", "Resultados")
    data["items"] = _clean_items(data.get("items"))
    data["sources"] = _clean_sources(data.get("sources"))
    data["summary"] = _clean_summary(data.get("summary"))
    data["criteria"] = _clean_criteria(data.get("criteria"))
    if data.get("tab") not in _TABS:
        data.pop("tab", None)                    # sin pestaña válida manda la de resultados (el widget decide)
    if not data["items"]:
        data.setdefault("note", "Sin resultados todavía.")
        data.pop("view", None)                   # no items ⇒ there is nothing to be showing the detail OF
        data.pop("focus", None)
    data["counts"] = _counts(data)
    return data


def _save(data: dict) -> None:
    """Persistir SIN los campos derivados: `counts` se recalcula al leer, y guardarlo lo dejaría rancio en cuanto
    cambie cualquier otra cosa (un número viejo en pantalla es peor que ninguno)."""
    d = dict(data)
    d.pop("counts", None)
    for k in ("sources", "summary", "criteria"):
        if not d.get(k):
            d.pop(k, None)                       # secciones vacías fuera: la hoja en blanco sigue siendo blanca
    store.save(WIDGET_ID, d)


def _find(items: list[dict], title: str = "", index=None) -> dict | None:
    """Resolve WHICH item the operator means. By exact title, else by a forgiving contains-match, else by ordinal.
    The ordinal matters because this arrives from VOICE: "enséñame la propuesta número uno" is far more likely to
    survive STT intact than a hotel's full commercial name, so the caller may pass index=1 instead of a title."""
    if isinstance(index, (int, float)) and not isinstance(index, bool):
        i = int(index)
        if 1 <= i <= len(items):                 # 1-based: the operator counts from one, not from zero
            return items[i - 1]
    t = (title or "").strip().lower()
    if not t:
        return None
    for it in items:
        if (it.get("title") or "").strip().lower() == t:
            return it
    for it in items:
        if t in (it.get("title") or "").strip().lower():
            return it
    return None


def ref_index() -> list[dict]:
    """The items currently ON SCREEN, so the brain can (a) let the operator pick one by talking about it ("quédate
    con la del beach club") and (b) — just as important — SEE that the sheet is empty. Before this, an open but
    blank results card was indistinguishable from a card that simply doesn't publish its items, and the brain
    answered "aquí lo tienes" over an empty screen (real session, 12:57:57).

    The hint leads with the ORDINAL because that is how the operator refers to a proposal out loud ("la número
    dos"); without it the brain had to guess which card "the second one" was."""
    out = []
    for n, it in enumerate(view_data().get("items", []), 1):
        bits = [f"#{n}"]
        if it.get("price"):
            bits.append(it["price"])
        if it.get("parts"):
            bits.append(" + ".join(p.get("kind") or p.get("title") or "" for p in it["parts"]))
        elif it.get("subtitle"):
            bits.append(it["subtitle"])
        out.append({"id": it["title"], "label": it["title"], "field": "title",
                    "hint": " · ".join(b for b in bits if b)})
    return out


_STATUS_ES = {"ok": "entró", "partial": "entró con límite", "auth": "pedía autenticación",
              "blocked": "bloqueó el acceso", "error": "dio error", "pending": "pendiente"}


def _digest_head(data: dict) -> str:
    """Las TRES pestañas que no son la lista, comprimidas para el prompt. Es lo que permite responder «¿por qué no
    sale nada de esa web?» o «¿con qué criterio has descartado?» SIN volver a buscar: el dato ya está en pantalla,
    solo faltaba que el cerebro lo tuviera delante. Muy acotado: el detalle vive en la propia tarjeta."""
    L: list[str] = []
    tab = data.get("tab") or "results"
    if tab != "results":
        L.append(f"[el operador está viendo la pestaña «{tab}»]")
    s, c = data.get("summary") or {}, data.get("counts") or {}
    # Solo lo REPORTADO abre la línea de sumario. Cuántas tarjetas hay en pantalla ya se ve en la lista que viene
    # justo debajo: anunciarlo aparte engordaba el prompt de CADA turno con la hoja abierta sin decir nada nuevo.
    bits = []
    if s.get("state"):
        bits.append(str(s["state"]))
    if s.get("explored"):
        bits.append(f"{s['explored']} explorados")
    if s.get("discarded"):
        bits.append(f"{s['discarded']} descartados")
    if bits:
        if c.get("shown"):
            bits.append(f"{c['shown']} en pantalla")
        L.append("SUMARIO: " + " · ".join(bits))
    if s.get("note"):
        L.append(f"  {s['note']}")
    crit = data.get("criteria") or {}
    if crit.get("goal"):
        L.append(f"CRITERIOS · objetivo: {crit['goal']}")
    for key, label in (("hard", "duros"), ("changes", "correcciones del operador")):
        if crit.get(key):
            L.append(f"  {label}: " + " · ".join(crit[key][:6]))
    src = data.get("sources") or []
    if src:
        L.append(f"FUENTES ({len(src)}):")
        for s0 in src[:8]:
            bit = f"  · {s0.get('name','')}: {_STATUS_ES.get(s0.get('status'), s0.get('status', ''))}"
            if s0.get("found"):
                bit += f", {s0['found']} resultados"
            if s0.get("detail"):
                bit += f" — {s0['detail']}"
            L.append(bit)
        if len(src) > 8:
            L.append(f"  (+{len(src) - 8} fuentes más)")
    return "\n".join(L)


def prompt_digest() -> str:
    """What is ACTUALLY on screen, compact enough to ride in every prompt while this widget is open.

    Why this exists: `ref_index()` only publishes title+hint, so the brain could name the items but knew nothing
    about them. Asked "¿el hotel de la propuesta 2 tiene wifi?" — about a result already on screen, whose own
    card says so — it had to either guess or escalate a whole new search for a fact it was already holding. That
    is the difference between a screen the agent can SEE and one it merely painted. Bounded on purpose: this is
    a digest for reasoning over, not the full dossier (that lives in the detail view)."""
    data = view_data()
    items = data.get("items") or []
    head = _digest_head(data)
    if not items:
        return (head + "\n" if head else "") + "hoja VACÍA — no hay ningún resultado en pantalla todavía"
    lines = []
    if head:
        lines.append(head)
    if data.get("view") == "detail" and data.get("focus"):
        lines.append(f"[viendo el DETALLE de «{data['focus']}»]")
    for n, it in enumerate(items[:12], 1):
        head = f"#{n} {it.get('title','')}"
        if it.get("price"):
            head += f" — {it['price']}"
        if it.get("badge"):
            head += f" [{it['badge']}]"
        lines.append(head)
        if it.get("subtitle"):
            lines.append(f"   {it['subtitle']}")
        for p in (it.get("parts") or []):
            bit = f"   · {p.get('kind') or 'pieza'}: {p.get('title','')}"
            if p.get("price"):
                bit += f" ({p['price']})"
            lines.append(bit)
            for f in (p.get("facts") or [])[:6]:
                lines.append(f"     - {f['label']}: {f['value']}")
        for f in (it.get("facts") or [])[:8]:
            lines.append(f"   - {f['label']}: {f['value']}")
        for ln in (it.get("lines") or [])[:3]:
            lines.append(f"   {ln}")
    if len(items) > 12:
        lines.append(f"(+{len(items) - 12} resultados más en la hoja)")
    return "\n".join(lines)


# La pestaña llega por VOZ («enséñame las fuentes», «¿cómo va?»), así que el nombre viene en el idioma del
# operador y a través del STT. No es una tabla de intención —eso lo decide el modelo— sino la normalización del
# argumento que ya eligió: el mismo papel que juega el ordinal en `detail`.
_TAB_ALIASES = {
    "resultados": "results", "resultado": "results", "lista": "results", "fichas": "results",
    "sumario": "summary", "resumen": "summary", "estado": "summary", "progreso": "summary",
    "fuentes": "sources", "fuente": "sources", "webs": "sources", "paginas": "sources", "páginas": "sources",
    "criterios": "criteria", "criterio": "criteria", "brief": "criteria", "encargo": "criteria",
}


def _merge_sections(data: dict, payload: dict) -> None:
    """`sources`/`summary`/`criteria` entregadas DE PASO dentro de un present/append. Se mezclan sobre lo que ya
    había: quien entrega resultados no siempre tiene delante lo que reportó hace cinco minutos."""
    src = _clean_sources(payload.get("sources"))
    if src:
        cur = list(data.get("sources") or [])
        for s in src:
            key = (s.get("url") or "").strip().lower() or (s.get("name") or "").strip().lower()
            hit = next((c for c in cur
                        if ((c.get("url") or "").strip().lower() or (c.get("name") or "").strip().lower()) == key),
                       None)
            if hit:
                hit.update(s)
            else:
                cur.append(s)
        data["sources"] = cur[:_MAX_SOURCES]
    summ = _clean_summary(payload.get("summary"))
    if summ:
        cur = dict(data.get("summary") or {})
        steps = list(cur.get("steps") or []) + [s for s in summ.pop("steps", []) if s not in (cur.get("steps") or [])]
        cur.update(summ)
        if steps:
            cur["steps"] = steps[-_MAX_STEPS:]
        data["summary"] = cur
    crit = _clean_criteria(payload.get("criteria"))
    if crit:
        cur = dict(data.get("criteria") or {})
        cur.update(crit)
        data["criteria"] = cur


# present/append/clear = how the result set is delivered. `choose` lets the operator PICK one of the shown items
# (e.g. "quiero esa"); unlike before it now PERSISTS the pick, because the list itself is persisted — the old
# comment about avoiding store.save() described the ephemeral-push era and no longer applies.
# `detail`/`list` flip this same sheet between the compact grid and ONE item's full dossier. The view lives in
# the persisted payload (not in the browser) so the operator's voice drives it: the widget has no state of its own.
def apply_action(action: str, payload: dict | None = None) -> dict:
    payload = payload or {}

    if action == "present":
        issues = _audit(payload)
        items = _clean_items(payload.get("items"))
        prev = view_data()
        data = {
            "title": _clip(payload.get("title") or "Resultados", "sheet_title"),
            "subtitle": _clip(payload.get("subtitle"), "sheet_subtitle"),
            "items": items,
        }
        # Las OTRAS pestañas SOBREVIVEN a un `present`. Durante un trabajo largo hay varios `present` (provisional
        # → final) y borrar en cada uno las fuentes y el sumario que ya se habían reportado sería perder datos que
        # costaron minutos de navegación. Quien las vacía es `clear`, o el arranque de una investigación NUEVA
        # (un `criteria` con otro objetivo) — dos momentos explícitos, no un efecto colateral.
        for k in ("sources", "summary", "criteria"):
            if prev.get(k):
                data[k] = prev[k]
        if prev.get("tab") in _TABS:
            data["tab"] = prev["tab"]
        # `columns` se conserva como TOPE (la superficie decide el reparto por la forma del contenido, ver
        # widget.js::columnsFor), nunca como orden — un 2 adivinado dejaba 3 tarjetas ricas con una huérfana.
        cols = payload.get("columns")
        if isinstance(cols, int) and 1 <= cols <= 3:
            data["columns"] = cols
        if payload.get("choosable"):
            data["choosable"] = True
        if not items:
            data["note"] = _clip(payload.get("note") or "Sin resultados.", "sheet_subtitle")
        # Un `present` puede traer de paso las otras secciones (entregar todo de una vez es un viaje menos para
        # quien trabaja). Se MEZCLAN sobre lo que hubiera, no lo reemplazan a ciegas.
        _merge_sections(data, payload)
        _save(data)
        return {"ok": True, "shown": len(items), "presentation": issues}

    if action == "append":
        issues = _audit(payload)
        add = _clean_items(payload.get("items"))
        if not add:
            return {"ok": False, "error": "append sin items válidos (cada item necesita al menos title)"}
        data = view_data()
        data.pop("note", None)
        seen = {(i.get("title"), i.get("url")) for i in data["items"]}
        for it in add:
            key = (it.get("title"), it.get("url"))
            if key not in seen:               # same title+url twice = the same finding, not a second result
                seen.add(key)
                data["items"].append(it)
        data["items"] = data["items"][:_MAX_ITEMS]
        if payload.get("title"):
            data["title"] = _clip(payload["title"], "sheet_title")
        if payload.get("subtitle"):
            data["subtitle"] = _clip(payload["subtitle"], "sheet_subtitle")
        _merge_sections(data, payload)
        _save(data)
        return {"ok": True, "shown": len(data["items"]), "presentation": issues}

    if action == "clear":
        store.save(WIDGET_ID, _empty())
        return {"ok": True, "shown": 0}

    if action == "choose":
        title = str(payload.get("title", "")).strip()
        if not title:
            return {"ok": False, "error": "choose necesita el title EXACTO del item"}
        data = view_data()
        data["chosen"] = title
        _save(data)
        return {"ok": True, "chosen": title}

    if action == "detail":
        data = view_data()
        it = _find(data.get("items") or [], str(payload.get("title", "")), payload.get("index"))
        if not it:
            return {"ok": False, "error": "no encuentro ese resultado en la hoja (pasa el title o index 1-based)"}
        data["view"] = "detail"
        data["focus"] = it["title"]
        data["tab"] = "results"                  # abrir un expediente es volver a la lista, no quedarse en fuentes
        _save(data)
        return {"ok": True, "detail": it["title"]}

    if action == "list":
        data = view_data()
        data.pop("view", None)
        data.pop("focus", None)
        _save(data)
        return {"ok": True, "view": "list"}

    # ── LAS OTRAS TRES PESTAÑAS ────────────────────────────────────────────────────────────────────────────────
    if action == "tab":
        tab = str(payload.get("tab") or payload.get("name") or "").strip().lower()
        tab = _TAB_ALIASES.get(tab, tab)
        if tab not in _TABS:
            return {"ok": False, "error": f"pestaña «{tab}» desconocida (results · summary · sources · criteria)"}
        data = view_data()
        data["tab"] = tab
        if tab != "results":
            data.pop("view", None)               # el detalle es una página de RESULTADOS: irse de pestaña la cierra
            data.pop("focus", None)
        _save(data)
        return {"ok": True, "tab": tab}

    if action == "sources":
        add = _clean_sources(payload.get("sources") if payload.get("sources") is not None else payload)
        if not add:
            return {"ok": False, "error": "sources necesita al menos {name|url} por fuente"}
        data = view_data()
        cur = data.get("sources") or []
        for s in add:
            # UPSERT: una fuente se reporta varias veces durante el trabajo («entrando…» → «50 resultados, me
            # cortó ahí»). Si cada reporte creara una fila, la pestaña sería un log y no un estado.
            key = (s.get("url") or "").strip().lower() or (s.get("name") or "").strip().lower()
            hit = next((c for c in cur
                        if ((c.get("url") or "").strip().lower() or (c.get("name") or "").strip().lower()) == key),
                       None)
            if hit:
                hit.update(s)
            else:
                cur.append(s)
        data["sources"] = cur[:_MAX_SOURCES]
        _save(data)
        return {"ok": True, "sources": len(data["sources"])}

    if action == "progress":
        upd = _clean_summary(payload.get("summary") if isinstance(payload.get("summary"), dict) else payload)
        if not upd:
            return {"ok": False, "error": "progress necesita al menos state, explored, selected, note o steps"}
        data = view_data()
        cur = dict(data.get("summary") or {})
        steps = list(cur.get("steps") or [])
        new_steps = upd.pop("steps", [])
        for st in new_steps:
            if not steps or steps[-1] != st:     # el mismo hito repetido no es progreso
                steps.append(st)
        cur.update(upd)
        if steps:
            cur["steps"] = steps[-_MAX_STEPS:]
        data["summary"] = cur
        _save(data)
        return {"ok": True, "summary": cur}

    if action == "criteria":
        upd = _clean_criteria(payload.get("criteria") if isinstance(payload.get("criteria"), dict) else payload)
        if not upd:
            return {"ok": False, "error": "criteria necesita goal y/o listas hard/soft/assumed/quality_bar/changes"}
        data = view_data()
        cur = dict(data.get("criteria") or {})
        # ¿Es OTRA investigación? El objetivo es la firma del encargo: si cambia, lo que hay en pantalla es de la
        # búsqueda anterior y engaña (el operador ya se comió una hoja rancia una vez). Una RONDA 2 conserva el
        # objetivo, así que «sigue buscando» no borra nada. `reset:false` lo desactiva para correcciones finas.
        new_goal = (upd.get("goal") or "").strip().lower()
        old_goal = (cur.get("goal") or "").strip().lower()
        fresh = bool(new_goal and old_goal and new_goal != old_goal)
        if payload.get("reset") is not None:
            fresh = bool(payload.get("reset"))
        if fresh:
            data = _empty()
            # RECORTADO: el `goal` del brief es un párrafo autocontenido («…y reportar el estado de cada fuente
            # consultada»), no un titular. Puesto crudo como título de la hoja ocupaba cinco líneas antes de
            # empezar a enseñar nada. El texto íntegro sigue completo en la pestaña CRITERIOS, que es su sitio.
            data["title"] = _clip(upd.get("goal") or "Resultados", "sheet_title") or "Resultados"
            cur = {}
        cur.update(upd)
        for k in _CRIT_LISTS:                    # las listas se REEMPLAZAN salvo `changes`, que se acumula
            if k == "changes":
                continue
            if k in upd:
                cur[k] = upd[k]
        if "changes" in upd:
            acc = list((data.get("criteria") or {}).get("changes") or []) if not fresh else []
            for ch in upd["changes"]:
                if ch not in acc:
                    acc.append(ch)
            cur["changes"] = acc[-_MAX_CRIT:]
        data["criteria"] = cur
        _save(data)
        return {"ok": True, "criteria": cur, "reset": fresh}

    return {"ok": False, "error": f"acción «{action}» no soportada (present · append · clear · choose · detail · "
                                  f"list · tab · sources · progress · criteria)"}
