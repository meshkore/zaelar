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
    mission: str = ""              # Zaelar's MISSION/identity (3-4 sentences) IN THE OPERATOR'S LANGUAGE — section A
                                    # of the composite STATE (memory.compose_state). It lives here (the single language source)
                                    # and is SEEDED into memory (state.mission) at startup; the prompt NEVER
                                    # hardcodes it in English. BOTH brains use it as part of the shared state.
    show_ack: str = "Aquí lo tienes."  # short "here you go" when opening a widget with no spoken content of its own
    # V2-209: the SAME act over a surface with nothing in it. «Aquí lo tienes» asserts a delivery, and
    # opening a card is not one — measured on `book-hotel-night-known__es` (2026-08-20 13:49), where the
    # judge called it «alucinación de éxito» over a browser task that had brought nothing back.
    # ⚠️ DOES NOT CLAIM ONGOING WORK. The first version ended with “I'm still on it,” and that was a measured
    # REGRESSION (V2-209 addendum): in `cancel-subscription-before-charge__es` —the board's only 5/5 case,
    # which succeeded precisely by asserting NOTHING— it dropped to 2/5 with the verdict “said it was still
    # canceling on the user's account without the mechanism supporting it.” I changed one false claim (“here you go”)
    # to another, smaller one and therefore one easier to sneak through. This ack only says what HAPPENED: it opened,
    # and it is empty.
    show_ack_empty: str = "Te lo abro, aunque de momento está vacío."
    # V2-210: when the turn had to consult a source and could not. Worse response, better information.
    unverified_fact: str = "No he podido comprobarlo ahora mismo, así que prefiero no darte un dato inventado."
    data_ack: str = "Hecho."       # short "done" when a widget data-op ran with no spoken content of its own (V2-026)
    # data-op ack variants (V2-038, post-P1/P2 test): two consecutive data-ops with the SAME "Done." triggered
    # the loop detector (LOOP×2) → consecutive functional responses are phrased differently. The provider chooses one
    # that does NOT repeat the previous one. Localized copy (lives in the language catalog, not test data).
    data_acks: tuple = ("Hecho.", "Listo.", "Ya está.", "Vale, hecho.", "Apuntado.")
    filler_still_working: str = "Sigo con ello; te aviso en cuanto lo tenga."  # V2-029: variation when a background task was ALREADY
                                    # a background task was already in progress when the turn began — do NOT repeat the same
                                    # filler_holding from turn to turn (the operator keeps insisting while the SlowBrain works)
    # V2-189: the same treatment as `data_acks`, which has existed since V2-038 because two consecutive «Done.» lines
    # triggered the loop detector — a treatment never applied to the waiting filler. Measured in
    # `cheapest-monitor` (2026-08-20 01:21): «Alright, give me a moment to look into that.» FOUR times word for
    # word, with the operator replying «okay, I'll wait» each time. The judge marked it serious in two different
    # cases. None of these asserts a STEP — that is the line V2-133 established and does not cross.
    holding_lines: tuple = ("Vale, dame un momento que lo miro.", "Sigo con ello; te aviso en cuanto lo tenga.",
                            "Sigue en marcha; en cuanto tenga algo te lo digo.")
    # V2-603: the SAME treatment for the OTHER half of the mute backstop — the one with no background task
    # running, which had exactly one line, «Perdona, ¿me lo repites?», and said it every single time. Measured
    # on the operator's engine (2026-09-06, session e1acdcca): four times in ninety seconds, ending in «Pero
    # ¿por qué te lo tengo que repetir?». Two faults in one string. It repeats, which `holding_lines` exists to
    # prevent on the sibling branch; and it blames the operator's SPEECH for a turn the model returned empty —
    # he had been perfectly clear, four times. These say the honest thing instead: the fault was ours.
    #: Said when every `mute_lines` variant is already in the last three turns — the operator has repeated
    #: himself three times into an engine that keeps coming back empty. Cycling a fourth apology pretends this
    #: is a hiccup; it is not, and saying so is the only useful thing left.
    mute_stuck: str = ("Algo no está funcionando bien por mi parte: llevo tres intentos sin contestarte. "
                       "Si quieres, párame y vuelve a arrancarme.")
    mute_lines: tuple = ("Perdona, se me ha ido. ¿Me lo dices otra vez?",
                         "Perdona, no te he seguido bien. ¿Qué querías que hiciera?",
                         "Se me ha cruzado algo por dentro y no te he contestado. Dime otra vez qué necesitas.")
    # And from the third consecutive wait onward, the only honest fact available: how long it has been running. Without
    # inventing what point it has reached, and with a way out — something the operator can do with that information.
    filler_waited: str = ("Lleva {min} min y todavía no me ha dado nada. ¿La dejo seguir o la paro y "
                          "probamos de otra forma?")
    # PROACTIVE DELIVERY (finding 2026-07-23: nucleo/loop.py, nucleo/sparks.py, and connectors/messaging/notify.py
    # spoke with fixed Spanish f-strings without going through this catalog — deaf to a language change). These are
    # SPOKEN phrases initiated by zaelar itself (the operator did not request them in this turn): worker questions,
    # budget timeouts, spontaneous sparks, and messaging notices. Placeholders use `.format(...)`.
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
    generic_task: str = "la tarea"        # fallback for {goal} when the worker has no title of its own
    someone: str = "alguien"              # fallback for {sender} when the connector provides no sender
    msg_notice_single: str = "Tienes un mensaje en {platform} de {sender}."
    msg_notice_single_urgent: str = "Tienes un mensaje urgente en {platform} de {sender}."
    msg_notice_multi: str = "Tienes {count} mensajes en {platform} que quizá quieras ver, de {sender} entre otros."
    # LEAD-IN FILLERS (2026-07-19): neutral, varied THINKING sounds to fill TTFT silence (~1.1s measured) ONLY when
    # the turn genuinely takes time (timer, `pick_filler`). They NEVER commit to or contradict the real response
    # (they are neutral, not "done/okay"): the actual utterance continues them. Naturalness, not filler everywhere.
    # V2-642 — the pool follows OpenAI's realtime prompting doctrine, which the operator pointed at
    # («OpenAI tiene un agente de voz que es brillante gestionando esos huecos»): a cover DESCRIBES THE
    # ACTION («I'll check that now»), never a bare thinking sound — their explicit avoid-list («Hmm…»,
    # «Let me think…», «One moment while I process…») was literally our old pool, and the 19:27 session
    # showed why: a sound that promises nothing invites «¿a ver qué?» back.
    fillers: tuple = (
        "Voy a mirarlo…", "Ahora te digo…", "Te lo miro ahora…", "Un segundo, que lo compruebo…",
        "Deja que lo mire…", "Ahora mismo lo miro…", "Vamos a verlo…", "Te lo compruebo…",
        "A ver qué tenemos…", "Dame un segundo…", "Un momento, que lo busco…", "Buena pregunta…",
        "Pues mira, te lo miro…", "Déjame que lo mire…",
    )
    # Lead-ins for a turn that is an ORDER to act (V2-572). «Déjame ver…» before closing a widget reads as
    # incomprehension — the operator's own words. These commit to nothing either: they promise motion, not a
    # result, so a turn that ends up declining («no puedo cerrar eso, hay un encargo en marcha») still
    # continues them naturally.
    fillers_action: tuple = ("Voy…", "Ahora mismo…", "Marchando…", "Voy a ello…", "Venga…",
                             "Voy con ello…", "Ahora mismo voy…", "Venga, va…", "Voy, un segundo…")
    # Lead-ins for a SOCIAL/META turn (V2-640) — the operator asks about the CONVERSATION itself or about us
    # («¿qué tal?», «¿de qué me estás hablando?», «¿qué quieres ver?»). A thinking sound here is what produced
    # the 19:27 besugos session: «Déjame ver…» answered «¿qué quieres ver?» and the operator asked what we
    # wanted to see, forever. These open an EXPLANATION or a presence, promise no looking, and the reply
    # continues them («Pues…» → «Pues te decía que…»).
    fillers_social: tuple = ("Pues…", "Verás…", "Sí, mira…", "Te cuento…", "A ver, te explico…", "Eh, pues…")
    # WORK COVERS (V2-669) — the SECOND cover, spoken at the TOOL SEAM, not before the model. A lead-in is a
    # blind guess made ~1.1 s in; by the time the router hands back a light route we KNOW what we are about to
    # do, and the measured hole is on the far side of that seam: with `deepseek-v4-pro` a web-search turn ends
    # 3.4-5.9 s AFTER the tool fires (7 real voice turns, 2026-09-04..11), and the lead-in's audio is long over.
    # These name the SOURCE, which is information the lead-in could not carry — that is what keeps them from
    # being a second stall («Voy a mirarlo…» then «Miro en agenda…» says something new). Short on purpose: a
    # cover cannot be cut mid-sentence, so its own length is latency (the operator's rule, 2026-09-11).
    covers_widget: tuple = ("Lo miro en {t}…", "Un segundo, lo miro en {t}…", "Lo compruebo en {t}…",
                            "Déjame mirarlo en {t}…")
    covers_search: tuple = ("Lo busco en internet…", "Un segundo, lo busco…", "Voy a buscarlo…",
                            "Lo miro en la web…")
    covers_recall: tuple = ("Miro lo que tengo guardado…", "Un segundo, lo busco en mis notas…",
                            "Déjame recordarlo…", "Lo miro en lo que guardé…")
    # V2-640 — the PRESENCE fast lane's spoken answers («¿sigues ahí?» must never wait 4 s for a model).
    # Two pools because the honest answer differs: idle = "I'm here, talk to me"; busy = "here, and still
    # on your task" — which is what that question really asks mid-task.
    presence_idle: tuple = ("Sí, aquí estoy. Dime.", "Aquí sigo, cuéntame.", "Te escucho, dime.",
                            "Sí, dime.", "Aquí estoy. ¿Qué necesitas?")
    presence_busy: tuple = ("Aquí estoy — sigo con lo tuyo, ahora te cuento.",
                            "Sí, sigo aquí, dándole a lo que me pediste.",
                            "Aquí sigo, trabajando en ello.")
    # V2-674 — the PHRASEBOOK: the set phrases of a relationship (a greeting, «¿qué tal?», «gracias»,
    # «adiós»), with the replies to answer them with. Same reason as `presence_*` widened to the rest of the
    # connective tissue of a conversation, and DATA rather than a regex because Zaelar is language agnostic
    # and a regex is not: a new language is a translation of this table, never a code change. Matching lives
    # in `nucleo/flash/smalltalk.py`; the shape is
    #   {"vocatives": (…), "intents": {name: {"cues": (…), "replies": (…), "bounces"?, "after_bounce"?}}}
    smalltalk: dict = field(default_factory=dict)
    # V2-642 — the HONEST closer for a turn that produced no answer after a sounded cover. The operator's
    # rule: «igual no tenía respuesta, pero igualmente hay que cerrar las conversaciones» — a conversation
    # may end without an answer, never without an ending.
    closers_no_answer: tuple = ("Pues ahora mismo no tengo una buena respuesta a eso.",
                                "Esa no te la sé contestar ahora, la verdad.",
                                "Ahí me he quedado sin respuesta — pregúntamelo de otra forma si quieres.")
    # The spoken confirmation of an already-EXECUTED direct action (the action-map fast lane). Unlike fillers
    # these DO commit — they are only ever spoken after the mutation happened, never as a lead-in.
    acks: tuple = ("Hecho.", "Vale, hecho.", "Listo.", "Ya está.")
    # SECRETS VAULT (V2-060) — deterministic SPOKEN lines. The secret's value is inserted OUT-OF-BAND
    # (it never passes through the model): `secret_reveal.format(label=…, value=…)`. The others do not contain the value.
    secret_reveal: str = "Tu {label}: {value}"           # (F2: voice reading with log redaction)
    secret_shown: str = "Aquí tienes tu {label}, te lo muestro en pantalla."   # F1b: value through the UI, not by voice
    secret_locked: str = ("Necesito tu contraseña de la bóveda para dártelo. Ponla y te lo muestro.")
    secret_no_vault: str = ("Todavía no tienes una bóveda de secretos. ¿Quieres que la creemos para guardar tus "
                            "contraseñas cifradas?")
    secret_not_found: str = "No tengo guardado ese secreto."
    secret_screen_only: str = "Por seguridad no lo digo en voz alta; te lo muestro en pantalla."
    secret_saved: str = "Hecho, la he guardado cifrada en tu bóveda de secretos."   # after encrypting a new secret
    secret_need_vault: str = ("Puedo guardártela cifrada, pero primero necesito que crees una contraseña maestra "
                              "para tu bóveda. Te la abro.")                        # attempting to save without a vault yet
    energy_exhausted: str = ("Se ha agotado tu Energía. Paga una cuota o compra más para seguir usando tu "
                             "agente.")                                             # 2026-08-09, real accounts only
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


# ── THE PHRASEBOOKS (V2-674) ────────────────────────────────────────────────────────────────────────────────
# Cues are written the way `smalltalk._norm` leaves them: lowercase, no accents, no apostrophes, no
# punctuation. They are matched WHOLE — «hola» matches, «hola, ¿me abres la agenda?» does not, because its
# second clause is not in the table. Pools are plural on purpose: the operator asked for «una especie de
# diálogo heurístico, un poco random», so the same greeting twice does not give the same sentence back.
_SMALLTALK_ES: dict = {
    # Generic forms of address. They carry no request, so a segment made only of these is skipped — which is
    # what lets «Hola, tío. ¿Qué tal?» be read as the two phrases it actually is.
    "vocatives": ("tio", "tia", "hombre", "mujer", "chaval", "colega", "maquina", "campeon", "crack",
                  "amigo", "amiga", "jefe", "jefa"),
    # Coordinating words that glue two phrases with no punctuation between them («hola y buenos días»).
    "joiners": ("y", "e"),
    "intents": {
        "greeting": {
            "cues": ("hola", "buenas", "muy buenas", "buenos dias", "buen dia", "buenas tardes",
                     "buenas noches", "hey", "ey", "holi", "que hay", "hola que hay", "hola buenas"),
            "replies": ("¡Hola! Dime.", "Hola, cuéntame.", "¡Hola! ¿En qué andamos?",
                        "Buenas. Tú dirás.", "Hola. Aquí estoy."),
        },
        "how_are_you": {
            "cues": ("que tal", "que tal estas", "como estas", "como te va", "como vas", "como andas",
                     "que tal todo", "como lo llevas", "que tal te va", "que tal andas", "todo bien"),
            "replies": ("Muy bien, gracias. ¿Y tú qué tal?", "De maravilla. ¿Tú cómo vas?",
                        "Bien, con ganas. ¿Y tú?", "Todo en orden por aquí. ¿Y tú qué tal?",
                        "Estupendamente. ¿Y tú cómo andas?"),
            "bounces": True,
        },
        "im_fine": {
            # Only ever read this way right after we handed the question back — otherwise «bien» is an answer
            # to something WE asked, and swallowing it would be V2-665's defect with the roles reversed.
            "cues": ("bien", "muy bien", "bien gracias", "muy bien gracias", "todo bien", "genial",
                     "estupendo", "de maravilla", "aqui andamos", "tirando", "no me quejo", "fenomenal"),
            "replies": ("Me alegro. ¿Qué necesitas?", "Perfecto. Tú dirás.",
                        "Me alegro mucho. ¿En qué te ayudo?", "Estupendo. Cuando quieras, dime."),
            "after_bounce": True,
        },
        "thanks": {
            "cues": ("gracias", "muchas gracias", "mil gracias", "muchisimas gracias", "te lo agradezco",
                     "gracias por todo", "muy amable", "gracias eh"),
            "replies": ("A ti.", "De nada.", "Para eso estoy.", "Un placer.", "Cuando quieras."),
        },
        "goodbye": {
            "cues": ("adios", "hasta luego", "hasta ahora", "hasta manana", "hasta pronto", "nos vemos",
                     "chao", "chau", "me voy", "me piro", "luego hablamos"),
            "replies": ("Hasta luego.", "Nos vemos. Aquí estaré.", "Hasta ahora.", "Cuídate.",
                        "Venga, hasta luego."),
        },
    },
}

_SMALLTALK_EN: dict = {
    "vocatives": ("mate", "man", "buddy", "dude", "pal", "bro", "friend", "boss", "champ", "folks"),
    "joiners": ("and",),
    "intents": {
        "greeting": {
            "cues": ("hello", "hi", "hey", "hiya", "yo", "howdy", "good morning", "morning",
                     "good afternoon", "good evening", "hello there", "hi there", "hey there",
                     "good day"),
            "replies": ("Hi! Go ahead.", "Hello — what's up?", "Hey! What can I do?",
                        "Hi there. I'm listening.", "Hello. Tell me."),
        },
        "how_are_you": {
            "cues": ("how are you", "how are you doing", "how is it going", "hows it going",
                     "how you doing", "how are things", "how do you do", "you all right", "you alright",
                     "you ok", "you okay", "how have you been", "hows everything"),
            "replies": ("Great, thanks — how about you?", "Doing well. And you?",
                        "All good here. How are you?", "Pretty good. What about you?",
                        "Very well, thanks. How's your day going?"),
            "bounces": True,
        },
        "im_fine": {
            "cues": ("fine", "im fine", "good", "im good", "very well", "great", "all good", "not bad",
                     "pretty good", "fine thanks", "good thanks", "cant complain"),
            "replies": ("Glad to hear it. What do you need?", "Good. Go ahead.",
                        "Happy to hear that. How can I help?", "Great. Tell me whenever."),
            "after_bounce": True,
        },
        "thanks": {
            "cues": ("thanks", "thank you", "thanks a lot", "thank you very much", "many thanks",
                     "cheers", "much appreciated", "appreciate it", "thanks so much"),
            "replies": ("Anytime.", "You're welcome.", "That's what I'm here for.", "My pleasure.",
                        "Sure thing."),
        },
        "goodbye": {
            "cues": ("bye", "goodbye", "see you", "see you later", "see ya", "talk later",
                     "catch you later", "im off", "good night", "later"),
            "replies": ("See you.", "Talk soon — I'll be here.", "Bye for now.", "Take care."),
        },
    },
}


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
        smalltalk=_SMALLTALK_ES,
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
        mute_stuck=("Something is wrong on my end: that's three turns without answering you. "
                    "Stop me and start me again if you like."),
        mute_lines=("Sorry, I lost that. Could you say it again?",
                    "Sorry, I didn't follow. What did you want me to do?",
                    "Something went sideways on my end and I didn't answer. Tell me again what you need."),
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
            "I'll check that now…", "Let me look that up…", "One sec, checking…", "I'll take a look…",
            "Let me pull that up…", "Give me a second, checking…", "Good question…",
            "Let me see what we have…", "I'll find out now…", "Let me check that for you…",
        ),
        fillers_action=("On it…", "Right away…", "Sure…", "Doing it…", "On it now…", "Right, doing it…"),
        fillers_social=("Well…", "So…", "Right, so…", "Let me explain…", "Okay, so…"),
        covers_widget=("Checking {t}…", "One sec, checking {t}…", "Let me check {t}…", "Looking at {t}…"),
        covers_search=("Looking it up online…", "One sec, searching…", "Let me search for that…",
                       "Checking the web…"),
        covers_recall=("Checking what I have saved…", "One sec, checking my notes…", "Let me recall that…",
                       "Checking my notes…"),
        presence_idle=("Yes, I'm here. Go ahead.", "Still here, tell me.", "I'm listening.",
                       "Right here — what do you need?"),
        presence_busy=("I'm here — still on your task, I'll tell you in a moment.",
                       "Yes, still here, working on what you asked.",
                       "Still here, on it."),
        closers_no_answer=("I don't have a good answer to that right now.",
                           "Honestly, that one's beyond me at the moment.",
                           "I came up empty there — try asking me another way."),
        acks=("Done.", "Okay, done.", "All set.", "There you go."),
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
        show_ack_empty="I've opened it, though there's nothing in it yet.",
        unverified_fact="I couldn't check that just now, so I'd rather not give you a made-up figure.",
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
        smalltalk=_SMALLTALK_EN,
        kokoro_default="af_bella",
    ),
}

# The product DEFAULT is ENGLISH (operator policy 2026-08-09; it used to be Spanish). A newly
# installed zaelar with no language selected starts in English — like the frontend (`store.lang()` already fell back to "en") and
# the i18n manifest. A clean installation therefore no longer has an English UI and Spanish VOICE.
# This does NOT mean "zaelar speaks English": it is only the starting point until AUTODETECTION of the first phrase
# sets the operator's actual language (`i18n/init/detect.py`) or until they choose it in ⚙. No existing installation
# changes: once `stt_language` is persisted, this value is not consulted.
DEFAULT_LANG = "en"


def _default_code() -> str:
    """Import-time default: SETTINGS.language if it's a catalog language, else the product default (English)."""
    from .config import SETTINGS
    return SETTINGS.language if SETTINGS.language in LANGUAGES else DEFAULT_LANG


def first_run_auto() -> bool:
    """Are we still on the first run, with NO language selected yet? Then STT must transcribe in AUTO instead
    of fixing a language: it is the only way for an Arabic- or Chinese-speaking operator to be transcribed CORRECTLY in their
    first phrase — and that clean text is exactly what `i18n.init.detect` classifies to set the language.

    It lives HERE (one answer for all three STT backends) because otherwise each adapter invents its own:
    `whisper_local` already did this on its own while the REMOTE backends (deepgram/voxtral) did not — meaning that in the cloud
    profile, which is the production one, autodetection started with STT pinned to the default language and could not
    work. Defensive by design (fail-closed): if i18n is unavailable, it behaves as before.

    Each backend translates this into ITS way of saying «auto» — there is no common token: Whisper wants `language=None`,
    Voxtral wants the parameter OMITTED, and Deepgram needs explicit `"multi"` (omitting it falls back to en-US on the
    server, which is NOT auto)."""
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
    """Catalog for the ⚙ UI, with Spanish first."""
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


def smalltalk_book(code: str | None = None) -> dict:
    """The PHRASEBOOK for a language (V2-674): the hardcoded es/en table, with a GENERATED pack layered on top.

    Same lookup order as `pick_filler`: whatever `i18n/generated/<code>.smalltalk.json` holds WINS, because a
    pack generated for that language is native and this table is not. The merge is per INTENT — a pack that
    only translated greetings still gets the rest — and a language with neither answers `{}`, which the lane
    reads as «not my business» and hands the turn to the model. Failing into the model is the right fallback:
    a wrong canned greeting is worse than a slow correct answer."""
    c = (code or current_code()).lower()
    # `spec()` answers with the ACTIVE language for anything it does not know, which is right for a filler
    # pool and wrong here: it would hand a German operator the English phrasebook, and the one intent that
    # could still match («hello») would be answered in English, deterministically and with no model to
    # correct it. An unknown language has no book until one is generated for it.
    base = dict(LANGUAGES[c].smalltalk or {}) if c in LANGUAGES else {}
    gen = {}
    try:
        from i18n.init import fillers as _fillers_store
        gen = _fillers_store.read_smalltalk(c) or {}
    except Exception:  # noqa: BLE001
        gen = {}
    if not gen:
        return base
    out = {"vocatives": tuple(gen.get("vocatives") or base.get("vocatives") or ()),
           "joiners": tuple(gen.get("joiners") or base.get("joiners") or ())}
    intents = dict(base.get("intents") or {})
    for name, spec_in in (gen.get("intents") or {}).items():
        if not isinstance(spec_in, dict):
            continue
        merged = dict(intents.get(name) or {})
        merged.update({k: v for k, v in spec_in.items() if v})
        intents[name] = merged
    out["intents"] = intents
    return out


_RECENT_FILLERS: list[str] = []   # V2-640: the anti-repetition remembers a few turns back, not one —
_RECENT_MAX = 4                   # the operator heard «A ver…» twice in three turns with depth-1 memory.


def pick_filler(last: str = "", code: str | None = None, kind: str = "neutral") -> str:
    """A varied lead-in in the active language, MATCHED to the turn's shape and not heard recently.
    Shapes (V2-572 + V2-640): `kind="action"` draws from the action pool («Voy…») — a thinking sound before
    an order to act reads as incomprehension; `kind="social"` draws from the explanation-openers («Pues…») —
    a thinking sound answering a question about the conversation itself is what turned the 19:27 session
    into a dialogue of besugos; anything else keeps the thinking pool. Anti-repetition is a small RECENT
    window (depth {n}), not just the last phrase. Deterministic-agnostic: no pool → empty string → the
    caller says nothing.""".format(n=_RECENT_MAX)
    if kind == "action":
        pool = list(getattr(spec(code), "fillers_action", ()) or ())
    elif kind == "social":
        pool = list(getattr(spec(code), "fillers_social", ()) or ())
    else:
        pool = _generated_fillers(code or current_code())
        if not pool:
            pool = list(getattr(spec(code), "fillers", ()) or ())
    if not pool:
        return ""
    avoid = set(_RECENT_FILLERS[-_RECENT_MAX:]) | ({last} if last else set())
    choices = [p for p in pool if p not in avoid] or [p for p in pool if p != last] or pool
    phrase = _random.choice(choices)
    _RECENT_FILLERS.append(phrase)
    del _RECENT_FILLERS[:-8]
    return phrase


_RECENT_COVERS: list[str] = []


def _generated_covers(code: str, kind: str) -> list[str]:
    """Same read-side seam as `_generated_fillers`, for the work covers — so a language onboarded at runtime
    (Japanese, the operator's standing example) can eventually ship its own covers from the SAME generated
    pack, without this module learning anything about generation. Empty today: nothing writes them yet."""
    try:
        from i18n.init import fillers as _fillers_store
        return _fillers_store.read_covers(code, kind)
    except Exception:
        return []


def pick_cover(kind: str, target: str = "", last: str = "", code: str | None = None) -> str:
    """The WORK COVER for the tool seam (V2-669): a short line that names WHERE we are about to look, chosen
    once the router has already decided. `kind` is "widget" | "search" | "recall"; `target` fills `{t}` for the
    widget pool (the card's own title). Varied against a recent window like `pick_filler`, and — crucially —
    against the LEAD-IN that may have just sounded (`last`), because the one thing this must never be is the
    same wait said twice. No pool, or an unknown kind, returns "" and the caller stays silent."""
    field = {"widget": "covers_widget", "search": "covers_search", "recall": "covers_recall"}.get(kind or "")
    if not field:
        return ""
    pool = _generated_covers(code or current_code(), kind) or list(getattr(spec(code), field, ()) or ())
    if not pool:
        return ""
    avoid = set(_RECENT_COVERS[-_RECENT_MAX:]) | ({last} if last else set())
    # Three rungs like `pick_filler`, and the MIDDLE one is the point: once the recent window has swallowed a
    # short pool, falling straight back to it would hand back the very phrase we must not repeat.
    choices = [p for p in pool if p not in avoid] or [p for p in pool if p != last] or pool
    phrase = _random.choice(choices)
    _RECENT_COVERS.append(phrase)
    del _RECENT_COVERS[:-8]
    if "{t}" in phrase:
        t = (target or "").strip()
        if not t:
            return ""                      # a widget cover with nothing to name says less than silence
        phrase = phrase.replace("{t}", t)
    return phrase


def pick_closer(last: str = "", code: str | None = None) -> str:
    """The honest «no answer» closer (V2-642), varied like the acks — spoken when a turn that sounded a
    cover produced nothing and even the repair pass came back empty. Empty string when no pool ships."""
    pool = list(getattr(spec(code), "closers_no_answer", ()) or ())
    if not pool:
        return ""
    choices = [p for p in pool if p != last] or pool
    return _random.choice(choices)


def pick_ack(last: str = "", code: str | None = None) -> str:
    """The spoken «done» after an EXECUTED direct action (the action-map fast lane, V2-572). Varied like the
    fillers and never the same twice in a row; empty string when the language ships no pool."""
    pool = list(getattr(spec(code), "acks", ()) or ())
    if not pool:
        return ""
    choices = [p for p in pool if p != last] or pool
    return _random.choice(choices)


__all__ = ["LangSpec", "LANGUAGES", "DEFAULT_LANG", "current_code", "current_language",
           "spec", "supported", "kokoro_voices", "pick_filler", "pick_cover", "pick_ack", "pick_closer"]
