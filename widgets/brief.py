#
# brief.py — THE BRIDGE the widget layer exposes TO THE BOT (HANDOFF: "el código de interface entre el canvas y
# el bot, para que se adapte y los prompts lo tengan en cuenta"). It renders, from the live catalog, a compact
# text the assistant gets so it KNOWS which widgets exist and HOW to surface them — plus a snapshot of any widget
# that offers coach context (the agenda). The brain stays decoupled from rendering: it only learns capabilities
# and emits silent tags; the desktop does the drawing.
#
import json

from . import runtime

# Silent control tags the assistant emits in its reply; stripped before speech, turned into desktop actions.
# COMPACT on purpose: this brief lands in the conversation and is re-sent to the model on EVERY turn, so verbose
# prose = tokens + € on every request. Keep it to the tag syntax + one example + the voice→action map. Full
# rationale lives once in the persona, not here.
#
# TWO-SPEED BRAIN (v2 «Colmena»): this brief is read by the FAST layer (FlashBrain). V2-025 — the fast layer owns
# show/close/move AND every DECLARED data action of a widget (its `apply_action` vocabulary): it executes them
# itself, instantly, NEVER escalating a data mutation to a code agent. The only thing it ESCALATES is CREATING or
# MODIFYING a widget's CODE (the SlowBrain writes code). Some data actions are marked (confirmar) — irreversible,
# so the fast layer still does them but asks first; the rest are (directa). The provider
# (`voice/engine/llm/providers/nucleo.py`) enforces this in code (see widgets/actions.py for the FAST/CONFIRM/
# ESCALATE semantics): a [[create]]/[[modify]]/[[push]] tag auto-escalates; a declared data-op never does.
TAG_PROTOCOL = (
    "CANVAS = la única pantalla; zaelar enseña TODO ahí y NUNCA abre el navegador/apps del sistema para mostrar "
    "algo. Emite las tags SILENCIOSAS (jamás las digas; habla 1 frase natural ANTES).\n"
    "LO QUE HACES TÚ, al instante:\n"
    "  [[show:ID]] · [[close:ID]] o [[close]] (todos) · [[move:ID:izquierda|derecha|centro|arriba|abajo]] · "
    "[[fullscreen:ID]] (pantalla completa DE VERDAD, alterna: si ya está, la quita) — "
    "abrir/cerrar/recolocar/ampliar un widget. Usa el ID EXACTO de 'Available widgets'; nunca inventes uno. "
    "Si no existe una tag/tool para lo que piden (p.ej. cambiar el COLOR o el DISEÑO de un widget), NO digas que "
    "lo has hecho — o lo escalas (es CÓDIGO) o dices con naturalidad que eso no lo puedes hacer tú solo.\n"
    "  TRABAJAR con los datos de un widget (añadir una cita, marcar una tarea, aplazar/quitar algo) → llama a la "
    "tool `widget_data(widget_id, action, item, payload)`. TODAS las acciones que el widget declara en ACCIONES "
    "POR WIDGET las haces TÚ con esta tool, al momento — NUNCA las escalas. Para actuar sobre un item que ya existe "
    "(una tarea, un proyecto), NO inventes su id: descríbelo en `item` en lenguaje natural ('la tarea del daemon') "
    "mirando 'items ahora'. Las acciones (confirmar) son irreversibles: llámala igual, zaelar pedirá el sí/no; las "
    "(directa) van sin preguntar.\n"
    "  BORRAR un widget lo haces TÚ pero SIEMPRE con confirmación: llama a `delete_widget` (aparece un «¿Borrar? "
    "Sí/No» en la tarjeta) + pregunta en voz ('¿seguro que borro el de X?'); cuando responda, `confirm_widget_delete"
    "(confirmed)`. Borrar ≠ cerrar ([[close]] se reabre; borrar es para siempre). NUNCA borres sin preguntar.\n"
    "LO ÚNICO QUE ESCALAS a `escalate_to_slowbrain` (di UNA frase breve tipo 'vale, te lo preparo, te aviso al "
    "terminar'; NUNCA digas que 'no puedes') es cambiar el CÓDIGO de un widget:\n"
    "  · CREAR un widget nuevo bajo demanda (una tarjeta para algo que no está en el catálogo).\n"
    "  · MODIFICAR un widget existente (su aspecto, sus columnas, su lógica).\n"
    "  · O volcar/entregar datos que hay que BUSCAR primero.\n"
    "Eso lo programa un agente de código headless (~1-2 min): NO digas 'hecho' ni te inventes un id — te llegará "
    "una nota [SISTEMA] con el resultado real. Reutiliza un widget existente antes de pedir uno nuevo. Cambiar los "
    "DATOS de un widget que ya existe NO es modificarlo: es una data-op, la haces tú.\n"
    "Voz→acción: 'abre la agenda'→[[show:agenda]] · 'cierra todo'→[[close]] · 'añade una cita mañana a las 5'→"
    "widget_data(widget_id='agenda', action='add_meeting', payload={'title':'…','date':'mañana','startTime':'17:00'}) · "
    "'marca hecha lo del daemon'→widget_data(widget_id='agenda', action='done', item='la tarea del daemon') · "
    "'hazme un widget para X' o 'ponle otra columna a la agenda'→frase breve + escalate_to_slowbrain (es CÓDIGO)."
)


def _actions_brief() -> str:
    """Per-widget action vocabulary for [[widget.data:ID]], read from each manifest's `actions` field
    (declarative: {name: {desc, payload[, confirm]}}) PLUS an optional `usage` one-liner (how to drive the widget).
    Only widgets that declare `actions` appear — a widget with no `actions` is display-only from the brain's side
    (its data only changes via its own UI, or isn't mutable). Each action is tagged (directa)/(confirmar)/(escala)
    by the canonical resolver `widgets/actions.py` — the SAME classification the gate enforces."""
    from . import actions as wactions, refs
    lines = []
    for w in runtime.catalog():
        acts = w.get("actions")
        if not isinstance(acts, dict) or not acts:
            continue
        parts = []
        for name, spec in acts.items():
            spec = spec if isinstance(spec, dict) else {}
            desc = spec.get("desc", "")
            payload = spec.get("payload")
            shape = (" " + json.dumps(payload, ensure_ascii=False)) if isinstance(payload, dict) else ""
            tag = wactions.label(wactions.classify(spec, name))
            label = f'"{name}"{shape} — {desc} {tag}' if desc else f'"{name}"{shape} {tag}'
            parts.append(label)
        head = f"- {w.get('id')}"
        usage = str(w.get("usage") or "").strip()
        if usage:
            head += f" [{usage}]"
        block = head + ": " + " · ".join(parts)
        # V2-026: items VIVOS del widget (para que el modelo sepa QUÉ existe y lo referencie por lenguaje natural
        # en `widget_data(item=…)`, sin inventar ids). Best-effort: si el widget no expone `ref_index`, no aparece.
        try:
            items = refs.items_line(w.get("id"))
            if items:
                block += "\n    " + items
        except Exception:
            pass
        lines.append(block)
    return "\n".join(lines)


def for_prompt(open_ids=None, recent_ids=None) -> str:
    """TERSE widget view for the FlashBrain turn prompt (V2-027 — prompt de ~30 líneas). Data-driven from the live
    catalog, deliberately small: the old `for_brain()` dumped, on EVERY turn, the tag protocol + full payload JSON +
    usage prose + live items + agenda coach for ALL widgets (~40+ lines). This trims to what routing actually needs:

      1. **Catalog** (ALL widgets): `id — one-line mission`. Lets the model pick the right `[[show]]`/widget_id.
      2. **Action NAMES** (ALL widgets that declare actions): `id: act1 · act2 · act3(confirmar)`. The tool
         `widget_data` points here for valid action names; names are cheap, payload SHAPES are NOT dumped (the tool
         description carries the generic payload example, and `agenda.data`/`refs` normalise natural values, V2-026).
      3. **Live items** — ONLY for OPEN widgets (`open_ids`): the `item` reference in natural language matters for
         what's ON SCREEN; dumping every widget's items each turn was the biggest cost.
      4. **Coach context** — ONLY if that widget (today: agenda) is OPEN.

    ACOTACIÓN POR PRIORIDAD (V2-078, idea del operador — genérica, no hardcodea widgets): el catálogo se ORDENA y
    ANOTA en tres capas para que el modelo elija bien sin tabla de casos — **EN PANTALLA** (abiertos ahora) primero,
    **usado hace poco** (MRU `recent_ids`, aunque ya no esté abierto) después, y el resto del catálogo al final. Con
    100 widgets, "añade una cita" cae en la agenda que tiene delante o tocó hace nada, no en un homónimo. El nombre
    inequívoco ("el del tiempo") sigue valiendo esté donde esté — esto es una PISTA de prioridad, no una restricción.

    `open_ids`/`recent_ids` = ids de `memory.state().open_widgets` / `.recent_widgets`. None/empty = sin acotar.
    Best-effort: never raises (a broken widget can't break the turn)."""
    from . import actions as wactions, refs
    opened = {str(w).strip().lower() for w in (open_ids or []) if str(w).strip()}
    recent = [str(w).strip().lower() for w in (recent_ids or []) if str(w).strip() and str(w).strip().lower() not in opened]

    cat = list(runtime.catalog())
    # Ordena por capa de prioridad: abiertos (en orden de open_ids) → recientes (en orden del MRU) → resto (catálogo).
    def _rank(w):
        wid = str(w.get("id") or "").strip().lower()
        if wid in opened:
            return (0, 0)
        if wid in recent:
            return (1, recent.index(wid))
        return (2, 0)
    cat = sorted(cat, key=lambda w: (_rank(w), str(w.get("id") or "")))

    lines = ["Widgets del canvas (id — para qué; acciones = data-ops que haces TÚ con widget_data, nunca escalas). "
             "Para una orden de widget cuyo objetivo NO sea inequívoco, prefiere «EN PANTALLA», luego «usado hace "
             "poco»:"]
    for w in cat:
        wid = w.get("id")
        widl = str(wid or "").strip().lower()
        purpose = str(w.get("whenToUse") or w.get("title") or "").strip().replace("\n", " ")
        tag = "  ◀ EN PANTALLA" if widl in opened else ("  · usado hace poco" if widl in recent else "")
        row = f"- {wid} — {purpose[:80]}{tag}"
        # Acciones DECLARADAS (SOLO los nombres, inline): el vocabulario que la tool widget_data referencia. Los
        # payload SHAPES no van (el modelo los infiere del ejemplo de la tool; agenda.data/refs normalizan, V2-026).
        acts = w.get("actions")
        if isinstance(acts, dict) and acts:
            names = []
            for name, spec in acts.items():
                spec = spec if isinstance(spec, dict) else {}
                mark = "(confirmar)" if wactions.classify(spec, name) == wactions.CONFIRM else ""
                names.append(f"{name}{mark}")
            row += "  · datos: " + ", ".join(names)
        lines.append(row)
        # USAGE (V2-027 tersening había quitado esto del todo — bug real 2026-07-23: "no oigo nada" con youtube
        # ABIERTO no llevaba el aviso "empieza en silencio, usa unmute/volume_up" → el modelo pequeño no tenía cómo
        # deducir cuál de mute/unmute/volume_up resuelve "no suena" y acabó escalando a regenerar el widget. Solo
        # para widgets ABIERTOS (mismo criterio que items/coach) — coste de prompt nulo si no está en pantalla.
        if widl in opened:
            usage = str(w.get("usage") or "").strip()
            if usage:
                lines.append(f"  [{wid}] {usage}")

    # Items VIVOS + coach — SOLO de los widgets ABIERTOS (referir un item existente por lenguaje natural en `item`).
    item_lines: list[str] = []
    for w in cat:
        wid = str(w.get("id") or "").strip().lower()
        if wid not in opened:
            continue
        try:
            items = refs.items_line(w.get("id"))
            if items:
                item_lines.append(f"- {w.get('id')}: {items}")
        except Exception:
            pass
    if item_lines:
        lines.append("")
        lines.append("items ahora (de lo ABIERTO — referéncialos por lenguaje natural en `item`, no inventes ids):")
        lines += item_lines

    if "agenda" in opened:
        try:
            from .agenda import data as agenda
            ctx = agenda.coach_context()
            if ctx:
                lines += ["", "AGENDA (abierta) — contexto de coaching:", ctx]
        except Exception:
            pass

    return "\n".join(lines)


def for_brain() -> str:
    """Compact capabilities brief injected into the assistant on connect (and persisted intent in MEMORY.md).

    LEGACY (V2-027): the FlashBrain turn prompt now uses the terser `for_prompt(open_ids)`. This fuller view still
    feeds the kickoff brief of the OTHER brains (`voice/engine/pipeline/agent.py`, duo/hermes path)."""
    lines = [TAG_PROTOCOL, "", "Available widgets:"]
    for w in runtime.catalog():
        lines.append(f"- {w.get('id')}: {w.get('title','')} — {w.get('whenToUse','')}")
    actions_brief = _actions_brief()
    if actions_brief:
        lines += ["", "ACCIONES POR WIDGET (para la tool `widget_data` — usa widget_id + action EXACTOS; TODAS las "
                  "haces TÚ: (directa)=al instante · (confirmar)=hazla pero pregunta primero. [entre corchetes] = "
                  "cómo conducir el widget · 'items ahora' = qué existe, referéncialo por lenguaje en `item`):",
                  actions_brief]
    # Live snapshot from any widget that exposes coach context (today: the agenda) so the bot can coach on it.
    try:
        from .agenda import data as agenda
        ctx = agenda.coach_context()
        if ctx:
            lines += ["", "AGENDA CONTEXT (for coaching, if the user goes there):", ctx]
    except Exception:
        pass
    return "\n".join(lines)
