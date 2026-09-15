"""V2-704 — a QUESTION about a person is answered from the RECORD, not from the first page of a summary.

Measured live, session 76270f41 of 2026-09-15. «Contact Kryptonite… you've got my Telegram contact for them.»
The brain called `read_widget` FOUR times and got, all four, the same 910-character block — `prompt_digest`,
which for a directory of 2 686 people is its first fifteen rows plus «… y 2671 entradas más», and which
publishes PLATFORMS without handles by design (V2-683: a handle is personal data and has no business riding
every turn's prompt). It answered:

    «I found "Cryptonite" in your contacts — it's saved with Telegram as the preferred channel, but there's no
     Telegram handle or phone number stored.»

The row held `{"platform":"telegram","handle":"@cryptonite_fund","chatId":"7477656357"}`, and
`directory.resolve("Kryptonite")` — misspelt exactly as he said it — returned it on the first try. Nothing
hallucinated: the model read a block built never to contain the answer, whose own first line orders the reader
to treat an absence in it as authoritative («lo que no esté aquí NO está guardado»).

Two seams, and both matter more than this one widget:
  · `read_query(question)` on any widget's `data.py` — the generic door `nucleo/flash/widget_read.lookup`
    calls. Nothing there names contacts; the agenda answers through the same seam.
  · the answer comes from `widgets/directory.resolve`, the SAME door the sending side uses. What the brain says
    about who somebody is and what the message door does with that person can no longer be two answers.
"""
from __future__ import annotations

import pytest

from widgets import store
from widgets.contactos import data as contactos


@pytest.fixture(autouse=True)
def _a_directory_of_his_own(tmp_path, monkeypatch):
    """A real-shaped store: the one contact he actually has, plus enough neighbours that a question cannot be
    answered by the digest's first page. Never the operator's own file."""
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    store._last_hash.clear()
    people = [{
        "id": "c1", "kind": "person", "name": "Cryptonite", "phone": "", "email": "", "notes": "",
        "groups": [], "favorite": False, "preferred": "telegram",
        "channels": [{"platform": "telegram", "handle": "@cryptonite_fund", "chatId": "7477656357"}],
    }]
    # …and 200 others AFTER him, so anything that reads only a first page still sees him, while anything that
    # reads only a first page will NOT see the one at the end.
    people += [{"id": f"c{i}", "kind": "person", "name": f"Relleno Número {i}", "phone": f"+3460000{i:04d}",
                "channels": [], "groups": [], "favorite": False} for i in range(2, 202)]
    people.append({"id": "c999", "kind": "person", "name": "Ultima Persona", "phone": "+34999888777",
                   "email": "ultima@x.test", "channels": [], "groups": [], "favorite": False})
    store.save("contactos", {"_v": 1, "contacts": people, "next_id": 1000})
    yield


# ── the incident ──────────────────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("question", [
    'What is the contact info for "Kryptonite" (phone number, email, and preferred channel)?',
    "Is there a contact named Kryptonite, and do they have a Telegram contact? What is it?",
    "Kryptonite — contact details, name, channel",
    "What channels/contact info do we have for Kryptonite (Telegram username or phone number)?",
])
def test_the_four_questions_he_actually_asked_now_reach_the_handle(question):
    """Verbatim, from the four `read_widget` calls in the failed session."""
    out = contactos.read_query(question)
    assert "@cryptonite_fund" in out, f"la pregunta sigue sin llegar al handle: {out!r}"
    assert "Cryptonite" in out


def test_the_handle_is_the_thing_the_SUMMARY_deliberately_withholds():
    """The two seams disagree ON PURPOSE, and this pins the difference so neither drifts into the other: the
    digest rides every turn and must not carry personal identifiers; the answer to a direct question must."""
    digest = contactos.prompt_digest()
    assert "Cryptonite" in digest, "the summary still names him"
    assert "@cryptonite_fund" not in digest, "un identificador personal no viaja en el prompt de cada turno"
    assert "@cryptonite_fund" in contactos.read_query("¿cuál es el Telegram de Cryptonite?")


def test_the_spelling_he_SAYS_resolves_to_the_row_he_HAS():
    """Through `directory.resolve`, so the reader and the sending door survive the same STT garble (V2-698)."""
    assert "@cryptonite_fund" in contactos.read_query("Kryptonite")


def test_somebody_past_the_first_page_is_found_too():
    """The structural half. A directory is not fifteen people, and a lookup that only ever sees a first page is
    a confident «no lo tienes» for everybody else — which after the Google import was 2 671 of his 2 686."""
    out = contactos.read_query("¿tienes el teléfono de Ultima Persona?")
    assert "+34999888777" in out, out


# ── and it refuses rather than guesses ────────────────────────────────────────────────────────────────────

def test_a_question_that_names_nobody_answers_NOTHING():
    """"" falls through to the digest, and `compose_system` then tells the model it is looking at a summary.
    Answering something here would be worse than the defect being fixed: it would be a guess presented as a
    record."""
    assert contactos.read_query("¿cuántos contactos tengo guardados?") == ""
    assert contactos.read_query("show me the contacts widget") == ""
    assert contactos.read_query("") == ""


def test_a_common_word_does_not_drag_the_directory_into_the_answer():
    """«Número» appears inside two hundred names here. A span that matches that many is not a name, and reading
    twenty rows aloud answers nothing — so it is dropped, not truncated."""
    out = contactos.read_query("dime el número de Relleno Número 7")
    assert "Relleno Número 7" in out
    assert out.count("\n") <= 3, f"la respuesta se ha llenado de homónimos:\n{out}"


def test_two_people_who_match_are_a_QUESTION_not_a_choice(tmp_path, monkeypatch):
    """Writing to the wrong person does not undo. When the name is ambiguous the block says so and tells the
    model to ask — the same refusal `directory.resolve` makes on the sending side."""
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    store._last_hash.clear()
    store.save("contactos", {"_v": 1, "next_id": 3, "contacts": [
        {"id": "c1", "name": "Javi Moreno", "phone": "+34600000001", "channels": [], "groups": []},
        {"id": "c2", "name": "Javi Ruiz", "phone": "+34600000002", "channels": [], "groups": []},
    ]})
    out = contactos.read_query("¿cuál es el teléfono de Javi?")
    assert "Javi Moreno" in out and "Javi Ruiz" in out
    assert "PREGÚNTALE" in out, "un nombre ambiguo tiene que PEDIR que se elija, no elegir"


# ── the seam is generic ───────────────────────────────────────────────────────────────────────────────────

def test_the_reader_finds_this_door_by_CONTRACT_and_names_no_widget():
    """`nucleo/flash/widget_read` must reach it through the optional `read_query` seam — the same shape as
    `prompt_digest`. A reader with a list of special-cased widget ids is a reader that is wrong for the next
    widget, and the agenda already joined through this same door with no change there."""
    import ast
    import pathlib

    from nucleo.flash import widget_read
    text = pathlib.Path("nucleo/flash/widget_read.py").read_text(encoding="utf-8")
    assert "read_query" in text, "el lector ya no busca la costura"
    # Prose may name widgets (the docstrings cite which ones publish a digest); CODE may not. Read the string
    # and name literals out of the AST rather than grepping, so a comment can keep explaining itself.
    tree = ast.parse(text)
    # Docstrings are prose: collect them BY NODE, because `ast.get_docstring` hands back a dedented copy that no
    # longer compares equal to the literal in the tree (it silently subtracted nothing the first time).
    docs = set()
    for n in ast.walk(tree):
        if isinstance(n, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            first = (n.body or [None])[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) \
                    and isinstance(first.value.value, str):
                docs.add(id(first.value))
    literals = [n.value for n in ast.walk(tree)
                if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docs]
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    for wid in ("contactos", "agenda", "mensajeria", "results", "fotos"):
        assert not any(wid in s for s in literals), f"el lector nombra «{wid}» en código"
        assert wid not in names
    assert "@cryptonite_fund" in widget_read.lookup("contactos", "what is Kryptonite's telegram?")
    assert widget_read.lookup("contactos", "") == ""
    assert widget_read.lookup("", "anything") == ""


def test_a_widget_without_the_seam_costs_nothing():
    from nucleo.flash import widget_read
    assert widget_read.lookup("clock", "what time is it") == ""
    assert widget_read.lookup("no-such-widget", "anything") == ""


# ── the WIRING, which is the thing that was actually broken ───────────────────────────────────────────────
# `read_widget.prepare` had a `question` argument and called `read(wid)` with only the widget id: the parameter
# was decorative, and every test in the file above could be green while the chain that uses them dropped the
# lookup on the floor. A disarm proved it — setting `direct = ""` in `prepare` failed nothing at all. So the
# assertion is on the SECOND PASS'S PROMPT: whatever the plumbing looks like, the handle has to be in what the
# model is handed, and the block has to be labelled as the record rather than hedged as a first page.

def test_the_question_reaches_the_model_through_prepare():
    import asyncio

    from nucleo.flash import widget_read

    seen = []
    sysp = asyncio.run(widget_read.prepare(
        {"widget_id": "contactos", "question": "what is Kryptonite's telegram handle?"},
        "contact Kryptonite for me", "LOCK",
        lambda *a, **k: seen.append(k.get("extra") or {})))
    assert "@cryptonite_fund" in sysp, "el handle no llega al prompt de la segunda pasada"
    assert "EL REGISTRO" in sysp and "RESUMEN" not in sysp, \
        "una ficha resuelta no puede entregarse con la advertencia de resumen"
    assert seen and seen[0].get("answered") is True, "la observabilidad no dice que se resolvió"


def test_a_question_nobody_can_answer_is_handed_over_AS_A_SUMMARY():
    """The other half, and the one that stops the false denial: with no lookup the model still gets the digest,
    but is told what it is — so an absence becomes «no lo he podido ver», never «no está guardado»."""
    import asyncio

    from nucleo.flash import widget_read

    seen = []
    sysp = asyncio.run(widget_read.prepare(
        {"widget_id": "contactos", "question": "how many people do I have saved?"},
        "how many contacts do I have?", "LOCK",
        lambda *a, **k: seen.append(k.get("extra") or {})))
    assert "RESUMEN" in sysp and "NUNCA" in sysp
    assert seen and seen[0].get("answered") is False
