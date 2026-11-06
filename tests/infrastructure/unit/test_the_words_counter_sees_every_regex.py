"""The words ratchet (node 7.73) counts every regex the code WRITES (node 2.1623, V2-857 review).

It used to count only `re.compile` spelled `re`: 83 compiles through an alias (`import re as _re`) and 314 inline
`re.search/sub/…` patterns were invisible, so removing or adding a word rail through either moved nothing.
"""
from __future__ import annotations

import ast

from tests.infrastructure.unit.test_words_never_fix_a_case import _regexes


def test_the_counter_sees_every_regex_the_code_writes():
    """An alias (`import re as _re`) and an inline pattern are regexes too; a pattern read from a name is not counted
    twice (its `compile` already was), and a word-free call on a non-`re` object is not a regex."""
    tree = ast.parse(
        "import re\nimport re as _re\n"
        "A = re.compile(r'a')\nB = _re.compile('b')\n"
        "def f(x):\n    return re.search(r'c', x) or _re.sub(f'{x}d', '', x) or re.match(A, x) or x.split('e')\n")
    assert _regexes(tree) == 4
