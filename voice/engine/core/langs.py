"""Supported-language catalog — the single source of truth for multilingual zaelar.

zaelar is multilingual with **English as the default**; the operator switches
language from the ⚙ panel or by voice, and EVERYTHING moves together and stays
perfectly aligned: STT recognition language + prompt, TTS voice (a native voice
per language) and lang code, and the brain's reply language. A language is only
in the catalog if we have a native, verified voice for it — so the voice can never
mismatch the language.

Live, not frozen: ``current_language()`` reads ``ZAELAR_LANGUAGE`` from the
environment (the ⚙ writes it there live and persists it to settings.json), so a
language change applies on the next voice session (reconnect) — the same contract
as the voice picker. ``SETTINGS.language`` is only the import-time default.

Adding a language = one ``LangSpec`` entry with a verified native Kokoro voice
(and Cartesia handles it via the ``cartesia`` param for the remote profile). Kokoro
lang codes: a=US English, b=UK English, e=Spanish, f=French, i=Italian, p=BR
Portuguese, h=Hindi, j=Japanese, z=Chinese.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class LangSpec:
    code: str                      # our language code (es, en, …) — Whisper/Voxtral/Deepgram/Cartesia language
    name: str                      # English name (logs/UI)
    native: str                    # native name (UI)
    kokoro_lang: str               # Kokoro lang_code (a/e/…)
    whisper_prompt: str            # Whisper initial_prompt in this language (anti-hallucination + accents)
    reply_directive: str           # instruction appended to the brain so it replies in this language
    warm: str                      # short warm phrase for the Metal TTS model
    filler_holding: str            # neutral "I'm on it" line — used when the fast brain escalates to Hermes
                                    # with no spoken content of its own (see duo.py's escalate_to_hermes tool)
    mission: str = ""              # MISIÓN/identidad de zaelar (3-4 frases) EN EL IDIOMA DEL OPERADOR — la sección A
                                    # del ESTADO compuesto (memory.compose_state). Vive aquí (single source de idioma)
                                    # y se SIEMBRA en la memoria (state.mission) al arrancar; el prompt NUNCA la
                                    # hardcodea en inglés. La usan AMBOS cerebros como parte del estado compartido.
    show_ack: str = "Aquí lo tienes."  # short "here you go" when opening a widget with no spoken content of its own
    # V2-206: the SAME act over a surface with nothing in it. «Aquí lo tienes» asserts a delivery, and
    # opening a card is not one — measured on `book-hotel-night-known__es` (2026-08-20 13:49), where the
    # judge called it «alucinación de éxito» over a browser task that had brought nothing back.
    show_ack_empty: str = "Te lo abro, pero de momento no hay nada dentro: sigo con ello."
    data_ack: str = "Hecho."       # short "done" when a widget data-op ran with no spoken content of its own (V2-026)
    # variantes del ack de data-op (V2-038, test post-P1/P2): dos data-ops seguidas con el MISMO "Hecho." disparaban
    # el loop-detector (LOOP×2) → un funcional consecutivo se dice distinto. El provider elige una que NO repita la
    # anterior. Copy localizado (vive en el catálogo de idioma, no es dato de un test).
    data_acks: tuple = ("Hecho.", "Listo.", "Ya está.", "Vale, hecho.", "Apuntado.")
    filler_still_working: str = "Sigo con ello; te aviso en cuanto lo tenga."  # V2-029: variación cuando YA había
                                    # una tarea de fondo en curso al empezar el turno — NO repetir el mismo
                                    # filler_holding turno a turno (el operador insiste mientras el SlowBrain trabaja)
    # V2-189: el mismo tratamiento que `data_acks`, que existe desde V2-038 porque dos «Hecho.» seguidos
    # disparaban el detector de bucles — y que al relleno de espera nunca se le aplicó. Medido en
    # `cheapest-monitor` (2026-08-20 01:21): «Vale, dame un momento que lo miro.» CUATRO veces palabra por
    # palabra, con el operador contestando «vale, quedo atento» cada vez. El juez lo marcó grave en dos casos
    # distintos. Ninguna de estas afirma un PASO — esa es la línea que V2-133 dejó dicha y no se cruza.
    holding_lines: tuple = ("Vale, dame un momento que lo miro.", "Sigo con ello; te aviso en cuanto lo tenga.",
                            "Sigue en marcha; en cuanto tenga algo te lo digo.")
    # Y a partir de la tercera espera seguida, el único hecho honesto que hay: cuánto lleva. Sin inventar en qué
    # punto va, y con una salida — que es lo que el operador puede hacer con ese dato.
    filler_waited: str = ("Lleva {min} min y todavía no me ha dado nada. ¿La dejo seguir o la paro y "
                          "probamos de otra forma?")
    # ENTREGA PROACTIVA (hallazgo 2026-07-23: nucleo/loop.py, nucleo/sparks.py y connectors/messaging/notify.py
    # hablaban con f-strings en español fijo, sin pasar por este catálogo — sordos a un cambio de idioma). Son
    # frases HABLADAS por iniciativa PROPIA de zaelar (el operador no las pidió en este turno): preguntas de un
    # worker, timeouts de presupuesto, chispas espontáneas, avisos de mensajería. Placeholders con `.format(...)`.
    worker_ask_named: str = "Oye, el proceso «{goal}» pregunta: {question}"
    worker_ask_generic: str = "Oye, uno de los procesos en marcha pregunta: {question}"
    worker_budget_killed: str = ("He parado «{goal}»: agotó su tiempo. Te dejo en la tarjeta lo que ha "
                                 "encontrado hasta ahora.")
    worker_timeout_running: str = "El proceso «{goal}» lleva ya {minutes} minutos. ¿Quieres que lo pare o que siga?"
    # CONFIRMATION TIMEOUT (2026-08-16): a pending irreversible-action confirmation the operator never answered
    # (`widgets/confirm.py`'s 90s TTL) must not just vanish — the task stays undone and the operator has no way
    # to know unless told. Spoken/chatted once by `nucleo/loop.py::_supervise_confirms`, same proactive rails as
    # a stuck/timed-out worker above.
    confirm_expired: str = ("Dejé de esperar tu confirmación sobre: {question} Dímelo otra vez si quieres que lo "
                            "haga.")
    spark_pending: str = "Sigo con una cosa pendiente: {title}. ¿Lo retomamos?"
    generic_task: str = "la tarea"        # fallback de {goal} cuando el worker no tiene título propio
    someone: str = "alguien"              # fallback de {sender} cuando el conector no trae remitente
    msg_notice_single: str = "Tienes un mensaje en {platform} de {sender}."
    msg_notice_single_urgent: str = "Tienes un mensaje urgente en {platform} de {sender}."
    msg_notice_multi: str = "Tienes {count} mensajes en {platform} que quizá quieras ver, de {sender} entre otros."
    # LEAD-IN FILLERS (2026-07-19): sonidos de PENSAR neutros y variados para rellenar el silencio del TTFT (~1.1s
    # medido) SOLO cuando el turno tarda de verdad (timer, `pick_filler`). NUNCA comprometen ni contradicen la
    # respuesta real (son neutros, no "hecho/vale"): la locución real los continúa. Naturalidad, no relleno de todo.
    fillers: tuple = (
        "A ver…", "Mmm…", "Veamos…", "Déjame ver…", "Un segundo…", "Espera…",
        "Vale, a ver…", "Pues…", "A ver qué tenemos…", "Déjame que mire…", "Un momentito…",
    )
    # BÓVEDA DE SECRETOS (V2-060) — líneas HABLADAS deterministas. El valor del secreto se inserta OUT-OF-BAND
    # (nunca pasa por el modelo): `secret_reveal.format(label=…, value=…)`. Las demás no llevan el valor.
    secret_reveal: str = "Tu {label}: {value}"           # (F2: lectura por voz con redacción de logs)
    secret_shown: str = "Aquí tienes tu {label}, te lo muestro en pantalla."   # F1b: valor por la UI, no por voz
    secret_locked: str = ("Necesito tu contraseña de la bóveda para dártelo. Ponla y te lo muestro.")
    secret_no_vault: str = ("Todavía no tienes una bóveda de secretos. ¿Quieres que la creemos para guardar tus "
                            "contraseñas cifradas?")
    secret_not_found: str = "No tengo guardado ese secreto."
    secret_screen_only: str = "Por seguridad no lo digo en voz alta; te lo muestro en pantalla."
    secret_saved: str = "Hecho, la he guardado cifrada en tu bóveda de secretos."   # tras cifrar un secreto nuevo
    secret_need_vault: str = ("Puedo guardártela cifrada, pero primero necesito que crees una contraseña maestra "
                              "para tu bóveda. Te la abro.")                        # querer guardar sin bóveda aún
    energy_exhausted: str = ("Se ha agotado tu Energía. Paga una cuota o compra más para seguir usando tu "
                             "agente.")                                             # 2026-08-09, solo cuentas reales
    # SPLIT-FRAGMENT ACCUMULATOR (V2-096, fix 2026-08-15): two SPOKEN lines, delivered out of band
    # (`voice/proactive.speaker()`, same channel as V2-093's lead-in filler), that only exist because staying
    # completely silent left the operator with no way to tell "still listening" from "hung".
    acc_fragment_dropped: str = ("Perdona, no cogí bien lo que dijiste antes de la pausa. ¿Me lo repites?")
    #   spoken ONCE when a mid-chain fragment gets discarded by the gap valve (> MAX_GAP_S, 25s) — the reply that
    #   follows never proceeds as if those words never existed.
    acc_still_listening: str = "Sigo aquí, cuando quieras sigue."
    #   spoken ONCE if a hold drags on longer than usual (ZAELAR_ACC_NUDGE_S, def 8s — above the real-world p90
    #   pause, 4.9s) — a reassurance, not an action: it never touches the buffer or forces the turn.
    kokoro_voices: list = field(default_factory=list)  # [{label, voice, gender}] native to this language
    kokoro_default: str = ""       # the reliable default voice for this language


# Kokoro voices are language-specific; only verified-native ones are listed so a
# voice can never be sent through the wrong-language pipeline. Cartesia (remote)
# voices are multilingual (one voice speaks any catalog language) and live in
# voices.VOICES_BY_PROVIDER["cartesia"]; here we only pass the language param.
LANGUAGES: dict[str, LangSpec] = {
    "es": LangSpec(
        code="es", name="Spanish", native="Español", kokoro_lang="e",
        whisper_prompt="Conversación natural en español.",
        reply_directive="Responde SIEMPRE en español (castellano), en frases habladas cortas y naturales, "
                         "sin markdown ni emojis.",
        warm="Hola.",
        filler_holding="Vale, dame un momento que lo miro.",
        mission=(
            "Eres Zaelar, el asistente personal por voz del operador, siempre a su lado. "
            "Atiendes lo que te pide guiándote por el ESTADO de abajo (quién es, qué tiene delante y de qué "
            "íbais hablando) y por tus recursos. "
            "Resuelves al momento lo que puedes; lo que lleva trabajo de verdad lo ARRANCAS DE VERDAD con tus "
            "recursos —LLAMANDO a la herramienta que toca (escalar, buscar, abrir/operar un widget)—, nunca te "
            "limitas a DECIR que lo harás: la frase que digas ACOMPAÑA a la acción, jamás la sustituye — pero lo que "
            "de verdad importa es LLAMAR a la herramienta, no la frase en sí. Si el operador tiene una REGLA que "
            "pide silencio/brevedad en las acciones ('hazlo y cállate', 'sin confirmaciones'), esa regla GANA "
            "sobre esta costumbre: llama a la herramienta y di como mucho una palabra ('vale') o nada — nunca una "
            "frase larga ni una narración de lo que vas a hacer. Al hablar de "
            "ello, para el operador eres UNA sola cosa: NUNCA le mencionas \"cerebros\", \"cerebro lento/rápido\", "
            "\"escalar\" ni piezas internas — le dices con naturalidad que te pones con ello y que tardará un poco, "
            "o que lo verá actualizarse en su widget (pero eso es CÓMO lo cuentas, después de haberlo lanzado). "
            "Tu memoria es tuya de siempre: hablas como un humano cercano, nunca de \"bases de datos\" ni de "
            "\"memoria de corto o largo plazo\"."
        ),
        show_ack="Aquí lo tienes.",
        kokoro_voices=[
            {"label": "Dora (es, f)",  "voice": "ef_dora",  "gender": "f"},
            {"label": "Alex (es, m)",  "voice": "em_alex",  "gender": "m"},
            {"label": "Santa (es, m)", "voice": "em_santa", "gender": "m"},
        ],
        kokoro_default="ef_dora",
    ),
    "en": LangSpec(
        code="en", name="English", native="English", kokoro_lang="a",
        whisper_prompt="Natural conversation in English.",
        reply_directive="Always reply in English, in short natural spoken sentences, no markdown, no emojis.",
        warm="Hello.",
        filler_holding="Alright, give me a moment to look into that.",
        filler_still_working="Still on it; I'll let you know as soon as I have it.",
        holding_lines=("Alright, give me a moment to look into that.",
                       "Still on it; I'll let you know as soon as I have it.",
                       "It's still running; I'll tell you the moment I have something."),
        filler_waited=("It's been {min} min and it still hasn't given me anything. Shall I let it run, or "
                       "stop it and try another way?"),
        worker_ask_named="Hey, the «{goal}» process is asking: {question}",
        worker_ask_generic="Hey, one of the running processes is asking: {question}",
        worker_budget_killed=("I stopped «{goal}»: it ran out of time. I've left what it found so far on the "
                              "card."),
        worker_timeout_running=("The «{goal}» process has been running for {minutes} minutes now. Want me to "
                                "stop it or keep going?"),
        confirm_expired=("I stopped waiting for your confirmation on: {question} Just tell me again if you still "
                         "want me to do it."),
        spark_pending="I've still got something pending: {title}. Should we pick it back up?",
        generic_task="the task",
        someone="someone",
        msg_notice_single="You have a message on {platform} from {sender}.",
        msg_notice_single_urgent="You have an urgent message on {platform} from {sender}.",
        msg_notice_multi=("You have {count} messages on {platform} you might want to check, from {sender} "
                          "among others."),
        fillers=(
            "Let's see…", "Hmm…", "Let me see…", "One sec…", "Hold on…", "Let me check…",
            "Right, let's see…", "Okay…", "Let me have a look…", "Just a moment…",
        ),
        mission=(
            "You are Zaelar, the operator's always-on personal voice assistant. "
            "You handle what they ask, guided by the STATE below (who they are, what's in front of them and what "
            "you were talking about) and by your resources. "
            "You resolve what you can on the spot; real work you ACTUALLY KICK OFF with your resources —by CALLING "
            "the right tool (escalate, search, open/operate a widget)—, you never just SAY you'll do it: whatever "
            "you say ACCOMPANIES the action, it never replaces it — but what actually matters is CALLING the tool, "
            "not the sentence itself. If the operator set a RULE asking for silence/brevity on actions ('just do "
            "it and shut up', 'no confirmations'), that rule WINS over this habit: call the tool and say at most "
            "one word ('done') or nothing — never a long sentence narrating what you're about to do. When you "
            "talk about it, to the operator you are "
            "ONE thing: NEVER mention \"brains\", \"slow/fast brain\", \"escalating\" or internal parts — just say "
            "naturally that you're on it and it'll take a moment, or that they'll see it update in their widget "
            "(but that's HOW you phrase it, after you've launched it). "
            "Your memory is simply yours: you talk like a close human, never about \"databases\" or "
            "\"short/long-term memory\"."
        ),
        show_ack="Here you go.",
        show_ack_empty="I've opened it, but there's nothing in it yet — still on it.",
        data_ack="Done.",
        data_acks=("Done.", "There you go.", "All set.", "Got it.", "Noted."),
        secret_reveal="Your {label}: {value}",
        secret_shown="Here's your {label}, showing it on screen.",
        secret_locked="I need your vault passphrase to give you that. Enter it and I'll show you.",
        secret_no_vault=("You don't have a secrets vault yet. Want me to create one so I can keep your passwords "
                         "encrypted?"),
        secret_not_found="I don't have that secret saved.",
        secret_screen_only="For safety I won't say it out loud; I'll show it on screen.",
        secret_saved="Done, I've saved it encrypted in your vault.",
        secret_need_vault=("I can keep it encrypted, but first you need to create a master passphrase for your "
                           "vault. Opening it now."),
        energy_exhausted="You're out of Energy. Pay for a plan or buy more to keep using your agent.",
        acc_fragment_dropped="Sorry, I didn't catch what you said before the pause — can you say that again?",
        acc_still_listening="Still here, go ahead whenever you're ready.",
        kokoro_voices=[
            {"label": "Bella (en, f)",   "voice": "af_bella",   "gender": "f"},
            {"label": "Nicole (en, f)",  "voice": "af_nicole",  "gender": "f"},
            {"label": "Michael (en, m)", "voice": "am_michael", "gender": "m"},
            {"label": "Adam (en, m)",    "voice": "am_adam",    "gender": "m"},
        ],
        kokoro_default="af_bella",
    ),
}

# El DEFECTO del producto es INGLÉS (norma del operador 2026-08-09; antes era castellano). Un zaelar recién
# instalado, sin idioma elegido, arranca en inglés — igual que el frontend (`store.lang()` ya caía a "en") y que
# el manifiesto de i18n. Deja de haber una instalación limpia con la UI en inglés y la VOZ en castellano.
# Esto NO es "zaelar habla inglés": es solo el punto de partida hasta que la AUTODETECCIÓN de la primera frase
# fija el idioma real del operador (`i18n/init/detect.py`) o hasta que este lo elija en ⚙. Ninguna instalación
# existente cambia: en cuanto hay `stt_language` persistido, este valor no se mira.
DEFAULT_LANG = "en"


def _default_code() -> str:
    """Import-time default: SETTINGS.language if it's a catalog language, else the product default (English)."""
    from .config import SETTINGS
    return SETTINGS.language if SETTINGS.language in LANGUAGES else DEFAULT_LANG


def first_run_auto() -> bool:
    """¿Seguimos en primera ejecución, SIN idioma elegido todavía? Entonces el STT debe transcribir en AUTO en vez
    de fijar un idioma: es lo único que permite que un operador árabe o chino sea transcrito CORRECTAMENTE en su
    primera frase — y ese texto limpio es justo lo que `i18n.init.detect` clasifica para fijar el idioma.

    Vive AQUÍ (una sola respuesta para los tres backends de STT) porque si no cada adaptador se inventa la suya:
    `whisper_local` ya lo hacía por su cuenta y los REMOTOS (deepgram/voxtral) no — o sea que en el perfil de nube,
    que es el de producción, la autodetección arrancaba con el STT clavado al idioma por defecto y no podía
    funcionar. Defensivo a propósito (fail-closed): si i18n no está disponible, se comporta como siempre.

    Cada backend traduce esto a SU forma de decir «auto» — no hay un token común: Whisper quiere `language=None`,
    Voxtral quiere que se OMITA el parámetro, y Deepgram necesita `"multi"` explícito (omitirlo cae a en-US en el
    servidor, que NO es auto)."""
    try:
        from i18n.init import detect as _detect
        return bool(_detect.should_detect())
    except Exception:
        return False


def current_code() -> str:
    """The ACTIVE language code, read LIVE from the env (⚙ writes ZAELAR_LANGUAGE),
    validated against the catalog so an unsupported value can't break alignment."""
    env = (os.getenv("ZAELAR_LANGUAGE") or "").strip().lower()
    if env in LANGUAGES:
        return env
    return _default_code()


def current_language() -> LangSpec:
    return LANGUAGES[current_code()]


def spec(code: str | None = None) -> LangSpec:
    if code and code.lower() in LANGUAGES:
        return LANGUAGES[code.lower()]
    return current_language()


def supported() -> list[LangSpec]:
    """Catalog for the ⚙ UI, Spanish first."""
    return [LANGUAGES[c] for c in sorted(LANGUAGES, key=lambda c: (c != DEFAULT_LANG, c))]


def kokoro_voices(code: str | None = None) -> list[dict]:
    return spec(code).kokoro_voices


import random as _random  # noqa: E402


def _generated_fillers(code: str) -> list[str]:
    """The per-language GENERATED filler pool (`i18n/generated/<code>.fillers.json`, V2-122) — a stable lookup
    path a component can always check FIRST, whether or not this language ever gets a real pack generated for
    it. Today nothing generates one (deliberately scoped out, see `i18n/init/fillers.py`'s docstring), so this
    always returns [] and `pick_filler` falls through to the hardcoded es/en pool — behavior is unchanged for
    both preset languages; only the LOOKUP ORDER changed, so a future generated pack needs no further wiring."""
    try:
        from i18n.init import fillers as _fillers_store
        return _fillers_store.read(code)
    except Exception:
        return []


def pick_filler(last: str = "", code: str | None = None) -> str:
    """Un sonido de PENSAR neutro y variado (lead-in) en el idioma activo, distinto del último (anti-repetición).
    Determinista-agnóstico: si no hay pool, cadena vacía → el caller no dice nada."""
    pool = _generated_fillers(code or current_code())
    if not pool:
        pool = list(getattr(spec(code), "fillers", ()) or ())
    if not pool:
        return ""
    choices = [p for p in pool if p != last] or pool
    return _random.choice(choices)


__all__ = ["LangSpec", "LANGUAGES", "DEFAULT_LANG", "current_code", "current_language",
           "spec", "supported", "kokoro_voices", "pick_filler"]
