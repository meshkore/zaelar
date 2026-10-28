"""What one act door ended in (refactor2710-06): `(request, args) → Outcome`.

`fired` says the act reached the world (or its read came back); `verdict` is a name of the one enumeration in
`nucleo/circuit/verdict.py`; `say` is the act's own sentence, when it has one; `data` is what the caller composes
with (a search's results, a sheet id).
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Outcome:
    fired: bool
    verdict: str
    say: str = ""
    data: dict = field(default_factory=dict)
