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


def lookup(wid: str, question: str) -> str:
    """THE WIDGET ANSWERING THE QUESTION, or "" when it cannot (V2-704).

    The defect this exists for, measured live on 2026-09-15 (session 76270f41). «Contact Kryptonite… you've got
    my Telegram contact for them» — the model called this tool FOUR times and got, all four, the same 910-char
    block: `prompt_digest`, which for a directory of 2 686 people is its first fifteen rows plus «… y 2671
    entradas más», and which publishes PLATFORMS without handles by design (V2-683: a handle is personal data
    and has no business riding every turn's prompt). The stored row held
    `{"platform":"telegram","handle":"@cryptonite_fund","chatId":"7477656357"}`. The model answered «it's saved
    with Telegram as the preferred channel, but there's no Telegram handle stored» — not a hallucination, an
    accurate reading of a block that was built never to contain the answer, and whose own first line orders the
    reader to treat an absence in it as authoritative.
    The `question` argument existed and was never used: `read()` took only a widget id, so the same summary came
    back whatever was asked. A tool with a decorative parameter is a tool that cannot answer a question about a
    specific row of anything large, which is most of what a directory, an agenda or an inbox IS.

    The seam is OPTIONAL and generic — any widget joins by exposing it, none is named here:

        def read_query(question: str) -> str:
            '''The rows this question is about, in full. "" when it resolves to nothing.'''

    Two rules for whoever implements it, and both come from what the digest gets right:
      · it answers with the RECORD, not a summary — this is a direct question, not context riding every turn,
        so the fields the digest withholds for privacy belong here;
      · it returns "" rather than a guess: an empty answer falls through to the digest, and `compose_system`
        then tells the model it is looking at a summary, which is a different thing from "not stored".
    """
    wid, q = (wid or "").strip(), (question or "").strip()
    if not wid or not q:
        return ""
    try:
        import importlib
        fn = getattr(importlib.import_module(f"widgets.{wid}.data"), "read_query", None)
        if not callable(fn):
            return ""
        return str(fn(q) or "").strip()[:_MAX_BLOCK_CHARS]
    except Exception:                                    # noqa: BLE001 — a widget that cannot answer says nothing
        return ""


def can_answer(wid: str) -> bool:
    """Does this widget ANSWER questions about what it holds (`read_query`)? The gate for treating a commission
    that names it as a read rather than a worker's errand (V2-773): a card that only publishes a digest is not
    a record anyone can resolve a question against."""
    try:
        import importlib
        return callable(getattr(importlib.import_module(f"widgets.{str(wid or '').strip().lower()}.data"), "read_query", None))
    except Exception:  # noqa: BLE001
        return False


def read(wid: str) -> str:
    """What the widget holds, as text the model can reason over. The seams the widgets already publish for the
    prompt, in order of richness: `prompt_digest` (the interior — agenda, contactos, archivos, results, youtube,
    fotos, documento), a `coach_context()` when `data.py` exposes one, `items_line` (labels). Bounded. Empty
    string when the widget publishes nothing readable — the caller then says so instead of inventing.

    This is the SUMMARY half. What the question itself resolves to comes from `lookup()`, which runs first and
    is placed above this block so a truncation eats context, never the answer."""
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
    """The piece's name IN THE OPERATOR'S LANGUAGE.

    It used to read the manifest straight (`name` / `title`), and every manifest in this repo is written in
    Castilian — so an English session heard «Let me check Contactos…» out loud (work cover, 2026-09-15 14:29:44)
    and the second pass below was told it had read «el widget "Contactos"». The translated label has existed
    since V2-694 (`widgets.contactos.name` → "Contacts" in `en.json`); this path simply never asked for it.
    `registry.display_name` is the ONE place that resolves it, and it falls back to the manifest for a widget the
    bundles have never heard of — a generated one, a fork — so nothing loses its name.
    """
    try:
        from widgets import registry, runtime
        w = runtime.get(wid) or {}
        native = str(w.get("title") or w.get("name") or wid)
        return registry.display_name("widgets", wid, native) or native
    except Exception:
        return wid


def compose_system(lang_lock: str, operator_text: str, wid: str, question: str, block: str,
                   answered: bool = False) -> str:
    """The second pass's system prompt: the widget's content is the ONLY source; an absence is stated, never
    filled. Same doctrine as `recall`'s pass and V2-210 («no des un dato inventado»).

    `answered` says WHICH of the two things the block is, and it changes what an absence in it means — the
    distinction the whole V2-704 incident turned on:
      · True  — the widget resolved the question and handed back the ROWS. An absence here is real: the datum
                is not stored, and saying so is correct.
      · False — all we have is the always-on SUMMARY, which for anything large is a first page. An absence here
                means WE DID NOT SEE IT, and a summary's own «this is everything» line (`contactos` says
                «lo que no esté aquí NO está guardado», written when the directory had a dozen rows and true
                only while nothing is cut) must not be allowed to turn that into a denial. This is generic on
                purpose: every widget whose digest can truncate — agenda, archivos, results — had the same
                loaded gun pointed at it.
    """
    head = (lang_lock or "").rstrip()
    src = block or "(este widget no tiene nada guardado que responda a eso)"
    name = title(wid)
    doctrine = (
        "Esto es EL REGISTRO de lo que se te pregunta, resuelto contra el almacén: si un dato no figura aquí, "
        "de verdad no está guardado, y decirlo es la respuesta correcta."
        if answered else
        "⚠️ Esto es un RESUMEN, no el registro completo — de una lista larga trae solo su primera página, y "
        "algunos campos (identificadores, direcciones, teléfonos) no viajan en él por privacidad. Si lo que se "
        "pregunta NO aparece aquí, di que no lo has podido ver o consultar, NUNCA que no está guardado: no "
        "tienes delante nada que permita afirmar eso. Si el propio bloque dice que él lo es todo, ignóralo "
        "cuando también diga que hay más entradas."
    )
    return (
        f"{head}\n"
        f"Necesitabas LEER lo que guarda el widget «{name}» ({wid}) para contestar; aquí está su contenido. "
        "Responde a la pregunta del operador en 1-2 frases HABLADAS y naturales usando SOLO lo que hay aquí — el "
        "dato exacto (hora, fecha, nombre) tal cual figura. Nunca digas «widget», «datos» ni «leer»: hablas "
        f"como quien simplemente lo sabe.\n{doctrine}\n\n"
        f"PREGUNTA: {question or operator_text}\n\nPETICIÓN DEL OPERADOR: {operator_text}\n\n"
        f"LO QUE GUARDA «{name}»:\n{src}"
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
    direct = summary = ""
    try:
        # The QUESTION first. It goes above the summary so the cap below eats context and never the answer.
        direct = await asyncio.to_thread(lookup, wid, question or operator_text) if wid else ""
        summary = await asyncio.to_thread(read, wid) if wid else ""
    except Exception:                                    # noqa: BLE001 — a broken widget never breaks the turn
        pass
    block = "\n\n".join(p for p in (direct, summary) if p)[:_MAX_BLOCK_CHARS]
    try:
        emit("brain", "📖 lectura de widget (tool del modelo)", role="system",
             text=f"{wid or args.get('widget_id') or '?'} ← {question or operator_text[:80]}",
             extra={"cat": "flash", "widget": wid or "", "asked": str(args.get("widget_id") or ""),
                    "chars": len(block or ""), "read_ms": round((time.time() - t0) * 1000),
                    # `answered` is the one field an incident is read by: it says whether the model was looking
                    # at the record or at a first page, which is the difference between "not stored" and
                    # "I did not see it".
                    "answered": bool(direct), "hit_chars": len(direct),
                    "ev": (block or "")[:600], **({"channel": channel} if channel else {})})
    except Exception:                                    # noqa: BLE001
        pass
    return compose_system(lang_lock, operator_text, wid or "", question, block, answered=bool(direct))


async def probe_answer(args: dict, operator_text: str, lang_lock: str, emit, spec, collect, sanitize) -> str:
    """The TEXT channel's whole `read_widget` turn: `prepare` + one collected second pass, sanitized. Returns the
    spoken answer, or "" so the caller keeps whatever it had (the probe's own fail-soft convention)."""
    sys2 = await prepare(args, operator_text, lang_lock, emit, channel="probe")
    try:
        out = await collect(sys2, operator_text, spec, max_tokens=220)
        return sanitize(out or "").strip()
    except Exception:                                    # noqa: BLE001 — a failed compose is not a failed turn
        return ""

