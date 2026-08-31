"""A pointer in `CLAUDE.md` that leads nowhere is worse than no pointer.

`CLAUDE.md` is the entry point every agent reads, and its value is entirely in the paths it hands over: «for X,
read Y». When Y moves or is renamed, nothing fails — the next agent opens a missing file, shrugs, and works
without the context the pointer existed to give. Same shape as the drift `test_roadmap_closure.py` was written
for: documentation that decays silently.

Only `.meshkore/docs/**` **of this repo** is checked, on purpose, and the two exclusions are not oversights:

  · `.meshkore/roadmap/`, `.meshkore/modules/*/tasks/` and `.meshkore/team/` are gitignored by the «neither our
    past nor our future is published» rule, so on a fresh clone they legitimately do not exist;
  · a path written `../.meshkore/...` belongs to the workspace ROOT repo, which is private (cloud, billing,
    pricing). It is *correct* for it to be missing here.

On its first run this guard caught a real one: `CLAUDE.md` cited
`.meshkore/docs/ops/zaelar-energy-accounting.md` — a doc that lives in the PRIVATE root repo — as if it were an
engine path. The sentence already said «from the workspace ROOT»; the path did not, so anyone cloning the public
repo was sent to a file that will never be there. Now it reads `../.meshkore/...`, which is both true and
skipped by this test.
"""
import re
from pathlib import Path

import pytest

ENGINE = Path(__file__).resolve().parents[3]
CLAUDE = ENGINE / "CLAUDE.md"

# Paths as they appear in the file: inside backticks, under .meshkore/docs/, ending in .md
_CITED = re.compile(r"`(\.meshkore/docs/[^`\s]+\.md)`")


def _cited() -> list[str]:
    return sorted(set(_CITED.findall(CLAUDE.read_text(encoding="utf-8"))))


def test_there_are_pointers_at_all():
    """If this ever goes to zero, the regex stopped matching the file's shape and the guard is asleep."""
    assert len(_cited()) >= 10


@pytest.mark.parametrize("rel", _cited())
def test_every_cited_doc_exists(rel):
    assert (ENGINE / rel).is_file(), (
        f"CLAUDE.md manda leer `{rel}` y ese fichero no existe. O se movió (arregla la cita) o se borró "
        f"(quita la cita): un puntero roto deja al siguiente agente trabajando sin el contexto que lo justifica.")


def test_the_brain_worker_doctrine_is_reachable():
    """Not one pointer among many: it is the one that decides how EVERY worker-side fix is aimed (operator,
    2026-08-20 — harden the resources, keep the reasoning open). If it stops being cited from the entry point it
    stops being applied, and the next agent goes back to shaping fixes like the failing scenario."""
    body = CLAUDE.read_text(encoding="utf-8")
    assert ".meshkore/docs/architecture/zaelar-brain-worker-doctrine.md" in body
    doc = ENGINE / ".meshkore/docs/architecture/zaelar-brain-worker-doctrine.md"
    assert doc.is_file()
    text = doc.read_text(encoding="utf-8")
    # The two halves and the ban are the load-bearing content; a doc that lost them is a different doc.
    for must in ("RESOURCES", "REASONING", "Change a word in the errand"):
        assert must in text, must
