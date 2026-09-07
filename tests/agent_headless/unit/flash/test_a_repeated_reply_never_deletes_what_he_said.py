"""V2-605 F4 — the anti-degeneration pruner was deleting the OPERATOR's sentences.

Measured on session `43b7bf79` (2026-09-07). Across the failing stretch the conversation window collapsed
**10 → 8 → 6 → 4 → 2 messages in four turns**, so by the time he was saying «te he dicho que quiero un navegador
en MI ordenador para que yo te confirme el captcha» the model was answering with two messages of history. His own
diagnosis — *«me da la sensación de que al modelo le falta lo que estamos haciendo en este momento»* — was right,
and this is why.

`prune_window` collapses near-identical ASSISTANT replies, which is correct and is V2-032's job. What it also did
was delete the USER turn sitting in front of the twin it removed — and its own docstring has promised «conserva …
los turnos de usuario intactos» since the day it was written. The code contradicted its own contract.

The consequence is worse than the loss: the repeated reply was **ours**, a deterministic clarify question he never
provoked, so every repetition of our canned sentence ate one of his. Four of his sentences went into the window
and ONE came out — «¿no has entendido lo que te he dicho?», the least informative of the four. The mechanism put
there to stop degeneration was amplifying it: each repetition left the model with less to escape the loop with.

What repeats is the reply. What he says never repeats, and it is exactly what is needed to understand him.
"""
from nucleo.flash import dialog

#: The canned question that was spoken five times, verbatim.
ASK = "Tienes 2 abiertas: ¿cuál te enseño, «t1» o «navegador»?"

#: His four sentences from the incident, in order. All different, all informative.
SAID = [
    "o me abres el navegador para que yo lo vea y te confirme el captcha",
    "pues uno está vacío y el otro tiene la web del Tenedor",
    "te he dicho que si quieres abrirme un navegador en mi ordenador",
    "¿no has entendido lo que te he dicho?",
]


def _incident():
    w = []
    for said in SAID:
        w.append({"role": "user", "content": said})
        w.append({"role": "assistant", "content": ASK})
    return w


def test_every_sentence_the_operator_said_survives_the_pruner():
    kept = [m["content"] for m in dialog.prune_window(_incident()) if m["role"] == "user"]
    assert kept == SAID, f"la poda se comió lo que dijo el operador: quedaron {len(kept)} de {len(SAID)}"


def test_the_twin_replies_are_still_collapsed():
    """The pruner keeps doing its job — this is not a loosening, it is a narrowing to what it was FOR."""
    out = dialog.prune_window(_incident())
    assert sum(1 for m in out if m["role"] == "assistant") == 1


def test_the_window_does_not_collapse_to_nothing():
    """The measured symptom, stated as a number: 8 messages in, and the model saw 2."""
    assert len(dialog.prune_window(_incident())) >= len(SAID)


def test_different_replies_are_all_kept():
    w = [{"role": "user", "content": f"u{i}"} for i in range(3)]
    w = [x for i in range(3) for x in ({"role": "user", "content": f"u{i}"},
                                       {"role": "assistant", "content": f"respuesta distinta número {i}"})]
    assert len(dialog.prune_window(w)) == 6


def test_a_window_of_only_repeated_replies_still_collapses():
    """No user turns to protect — the old behaviour is unchanged where it was never wrong."""
    w = [{"role": "assistant", "content": ASK} for _ in range(4)]
    assert len(dialog.prune_window(w)) == 1


def test_the_original_window_is_not_mutated():
    w = _incident()
    before = len(w)
    dialog.prune_window(w)
    assert len(w) == before
