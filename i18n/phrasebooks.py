"""i18n/phrasebooks.py — the es/en SMALLTALK tables (V2-674), moved out of `langs.py` byte for byte.

The architecture ratchet fired on 2026-09-16: `langs.py` crossed the 900-line floor for an unlisted module
while V2-707 F6 moved the confirm gate's sentences into it. The ratchet's instruction is to EXTRACT, and a
PHRASEBOOK is pure DATA read at exactly one place (`langs.smalltalk_book`), so it is the same cut
`router_catalog.py` already is for the tool catalog — not a slice of convenience.

Nothing here imports anything: the dependency runs one way, `langs` reads these two names and the specs it
builds are unchanged. `langs` re-exports them under their historical names so any reader that reached for
`langs._SMALLTALK_ES` still finds it.
"""
from __future__ import annotations

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
