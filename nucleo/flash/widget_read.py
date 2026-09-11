"""nucleo/flash/widget_read.py — a QUESTION about what a widget HOLDS is answered by READING that widget (V2-668).

Measured live, session 53de97d4 (2026-09-11, 10:58:33 → 11:00:03). «Johnny, ¿a qué hora tengo la cita con
Hacienda?» — the agenda held, in one line, `11:30–12:30 · Cita Agencia Tributaria`. The model said it had no
hour for it. Six turns later, after the operator had opened the agenda card BY HAND, it answered «hoy a las once
y media» — calling no tool. Nothing had been looked up: the content of an OPEN card rides in the prompt
(`widgets/brief.py`, `if wid in opened`), and that is the only way a widget's interior ever reached the model.

The tool catalog had three doors and none was this one: `widget_data` EXECUTES a declared action (navigate,
mutate), `recall` reads his long-term memory («no es para datos del mundo»), `web_search` reads the world. A
question about what his own widget stores had no route, so it was answered from whatever memory pill the prompt
happened to carry — a race, lost that morning («figura como algo que tienes que atender próximamente, sin
hora»). He had to show the system its own data. His own words: «si yo le tengo que explicar cómo llegar a los
datos, pierdo menos tiempo buscándolos yo».

`read_widget` is that door. It is `recall`'s sibling in shape — a LIGHT two-pass route resolved IN the turn,
no card opened, no worker — and it reads through the seams the widgets already publish for the prompt
(`refs.prompt_digest`, a `coach_context`, `refs.items_line`), so every widget that can be reasoned about while
open can now be asked about while closed. Nothing here mutates anything; the canvas does not move.

Both channels (`providers/nucleo.py` for voice, `probe.py` for text) call THIS module for the resolution, the
read and the second-pass system prompt, so the two parallel turn implementations cannot drift on this decision.
"""
from __future__ import annotations

import asyncio
import time

_MAX_BLOCK_CHARS = 1800      # the same bound `refs.prompt_digest` keeps — a summary for reasoning, not the record

TOOL_DEF = {
    "type": "function",
    "function": {
        "name": "read_widget",
        "description": (
            "CONTESTA una PREGUNTA sobre lo que un widget GUARDA (a qué hora es una cita, el teléfono de "
            "alguien, qué ficheros hay), aunque la tarjeta esté CERRADA. Vuelve en este turno, sin abrir nada. "
            "SOLO responde: ELEGIR, abrir o tocar algo de dentro es widget_data, y enseñar la tarjeta es "
            "show_widget. No es su vida (recall) ni el mundo (web_search)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "widget_id": {"type": "string", "description": "id del catálogo o su nombre natural"},
                "question": {"type": "string", "description": "qué quieres saber, autocontenido"},
            },
            "required": ["widget_id", "question"],
        },
    },
}


def resolve(widget_arg: str, text: str = "") -> str | None:
    """WHICH widget to read: the exact catalog id the model gave, else the widget its argument or the operator's
    sentence NAMES (`runtime.identify_named` — alias/name only; a read never lands «by context» either, a
    question about the agenda is about the agenda whatever card is open). `None` when nothing is named."""
    try:
        from widgets import runtime
    except Exception:
        return None
    arg = (widget_arg or "").strip()
    if arg and runtime.get(arg) is not None:
        return arg
    for probe in (arg, text or ""):
        if probe:
            wid = runtime.identify_named(probe)
            if wid and runtime.get(wid) is not None:
                return wid
    return None


def read(wid: str) -> str:
    """What the widget holds, as text the model can reason over. The seams the widgets already publish for the
    prompt, in order of richness: `prompt_digest` (the interior — agenda, contactos, archivos, results, youtube,
    fotos, documento), a `coach_context()` when `data.py` exposes one, `items_line` (labels). Bounded. Empty
    string when the widget publishes nothing readable — the caller then says so instead of inventing."""
    wid = (wid or "").strip()
    if not wid:
        return ""
    parts: list[str] = []
    try:
        from widgets import refs
        digest = str(refs.prompt_digest(wid) or "").strip()
        if digest:
            parts.append(digest)
    except Exception:
        pass
    try:
        import importlib
        mod = importlib.import_module(f"widgets.{wid}.data")
        fn = getattr(mod, "coach_context", None)
        if callable(fn):
            ctx = str(fn() or "").strip()
            if ctx and ctx not in parts:
                parts.append(ctx)
    except Exception:
        pass
    if not parts:
        try:
            from widgets import refs
            items = str(refs.items_line(wid) or "").strip()
            if items:
                parts.append(items)
        except Exception:
            pass
    block = "\n\n".join(parts).strip()
    return block[:_MAX_BLOCK_CHARS]


def title(wid: str) -> str:
    try:
        from widgets import runtime
        w = runtime.get(wid) or {}
        return str(w.get("title") or w.get("name") or wid)
    except Exception:
        return wid


def compose_system(lang_lock: str, operator_text: str, wid: str, question: str, block: str) -> str:
    """The second pass's system prompt: the widget's content is the ONLY source; an absence is stated, never
    filled. Same doctrine as `recall`'s pass and V2-210 («no des un dato inventado»)."""
    head = (lang_lock or "").rstrip()
    src = block or "(este widget no tiene nada guardado que responda a eso)"
    return (
        f"{head}\n"
        f"Necesitabas LEER lo que guarda el widget «{title(wid)}» ({wid}) para contestar; aquí está su contenido. "
        "Responde a la pregunta del operador en 1-2 frases HABLADAS y naturales usando SOLO lo que hay aquí — el "
        "dato exacto (hora, fecha, nombre) tal cual figura. Si lo que pregunta NO está, dilo con naturalidad y "
        "no lo rellenes con nada. Nunca digas «widget», «datos» ni «leer»: hablas como quien simplemente lo "
        "sabe.\n\n"
        f"PREGUNTA: {question or operator_text}\n\nPETICIÓN DEL OPERADOR: {operator_text}\n\n"
        f"LO QUE GUARDA «{title(wid)}»:\n{src}"
    )


def cover_target(args: dict, operator_text: str) -> str:
    """The card's own TITLE, for the voice channel's WORK COVER (V2-669). Resolved BEFORE the read so the
    cover can name WHERE we are looking while the read and the second pass run — the one thing the blind
    lead-in could not say. Empty string when nothing resolves: a cover with nothing to name says less than
    silence, and `langs.pick_cover` drops it."""
    try:
        wid = resolve(str(args.get("widget_id") or ""), operator_text)
        return title(wid) if wid else ""
    except Exception:                                    # noqa: BLE001 — a cover never breaks a turn
        return ""


async def prepare(args: dict, operator_text: str, lang_lock: str, emit, channel: str = "") -> str:
    """Resolve → read → observe → compose: everything BOTH channels share about a `read_widget` turn, so the two
    parallel turn implementations cannot drift on it (V2-252). Returns the second pass's system prompt; the
    caller only has to run that pass through its own mouth (voice streams it, the probe collects it).

    `emit` is injected rather than imported: this module must not reach into `voice.engine.*` (V2-569's
    direction ratchet). The read itself goes off the event loop — a widget's `view_data()` is synchronous
    stdlib code and may touch its store."""
    wid = resolve(str(args.get("widget_id") or ""), operator_text)
    question = str(args.get("question") or "")
    t0 = time.time()
    try:
        block = await asyncio.to_thread(read, wid) if wid else ""
    except Exception:                                    # noqa: BLE001 — a broken widget never breaks the turn
        block = ""
    try:
        emit("brain", "📖 lectura de widget (tool del modelo)", role="system",
             text=f"{wid or args.get('widget_id') or '?'} ← {question or operator_text[:80]}",
             extra={"cat": "flash", "widget": wid or "", "asked": str(args.get("widget_id") or ""),
                    "chars": len(block or ""), "read_ms": round((time.time() - t0) * 1000),
                    "ev": (block or "")[:600], **({"channel": channel} if channel else {})})
    except Exception:                                    # noqa: BLE001
        pass
    return compose_system(lang_lock, operator_text, wid or "", question, block)


async def probe_answer(args: dict, operator_text: str, lang_lock: str, emit, spec, collect, sanitize) -> str:
    """The TEXT channel's whole `read_widget` turn: `prepare` + one collected second pass, sanitized. Returns the
    spoken answer, or "" so the caller keeps whatever it had (the probe's own fail-soft convention)."""
    sys2 = await prepare(args, operator_text, lang_lock, emit, channel="probe")
    try:
        out = await collect(sys2, operator_text, spec, max_tokens=220)
        return sanitize(out or "").strip()
    except Exception:                                    # noqa: BLE001 — a failed compose is not a failed turn
        return ""

