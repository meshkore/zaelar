"""A card read answers HIM, in the second person — never «Richard has…» (V2-831 T-19 R3).

Demo pass 8, R3: «find me five days in her vacation where i'm free» → the model read the agenda with the question
«What meetings… does Richard have between…», and the read's spoken answer echoed it: «Richard has nothing on the
calendar during Anna's vacation…». The composer's input contract names the addressee: the operator, in the second
person, whatever the model's look-up question called him.

Disarm: drop the addressee sentence from `widget_read.compose_system` → red.
"""
from __future__ import annotations


def test_the_read_composer_is_told_who_it_answers():
    from nucleo.flash import widget_read
    sys2 = widget_read.compose_system("", "find me five days in her vacation where i'm free", "agenda",
                                      "What meetings does Richard have between 2026-12-20 and 2027-01-04?",
                                      "(no entries)", answered=True)
    assert "segunda persona" in sys2 and "nunca por su nombre ni en tercera persona" in sys2
    # the contract comes BEFORE the model's question, which is where the third person came from
    assert sys2.index("segunda persona") < sys2.index("PREGUNTA:")
