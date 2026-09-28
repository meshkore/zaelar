"""A system note glued under the turn never names a card to close (demo pass 30, I4, 2026-09-28).

«alright close the pictures» arrived with a web-search note about the monitor errand glued under it. The
canvas completion read the composed turn, `also_named` found «results» in OUR note, and the picture viewer AND
both monitor sheets were closed. `router.operator_words` — the door every backstop reads the operator through
— now cuts the notes off, whichever text it is handed.
"""
from nucleo.flash import router
from voice import brain_notes
from widgets import instances

_NOTE = ("[SISTEMA] Una búsqueda web ha devuelto esto, trabajando en «can you find me three 27 inch 4k "
         "monitors»: the results sheet has 10 models")


def _composed(said: str) -> str:
    return brain_notes.compose_turn(said, [_NOTE])


def test_operator_words_cut_the_notes_off():
    said = "alright close the pictures"
    assert router.operator_words(_composed(said), _composed(said)) == said
    assert router.operator_words("", _composed(said)) == said


def test_the_note_does_not_add_the_results_to_a_close():
    open_now = ["imagenes", "results::c29838-ls1", "results"]
    words = router.operator_words(_composed("alright close the pictures"), "")
    assert instances.also_named(words, open_now, exclude=["imagenes"]) == []
