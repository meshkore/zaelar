"""V2-778 F0-2 — a caution rule never opens the door.

`consent._flags_for` reads a spoken directive for the ONE concept it may flip: how much friction the act-or-ask
gate applies. «sin preguntar» was a LESS-friction phrase with nothing looking at what governed it, so «nunca
envíes un correo sin preguntarme» — the operator asking for MORE caution — set `ask_at: critical`, the setting
under which the agent stops asking about almost everything. A caution rule became the key. Measured by the
self-audit of 2026-09-30.

The repair is a reading of scope, not a new vocabulary: a negation (nunca/never/no/don't) that GOVERNS
«without asking» inside its own clause is a demand to ask. A clause boundary (comma, «y», «and», «but») ends
the negation's reach, so «no me preguntes, hazlo sin preguntar» still means less friction.
"""
from __future__ import annotations

import re

import pytest

from nucleo import consent


@pytest.mark.parametrize("text", [
    "nunca envíes un correo sin preguntarme",
    "never send an email without asking me",
    "no mandes nada sin preguntarme antes",
    "don't pay anything without asking me",
])
def test_a_negated_without_asking_is_more_friction(text):
    assert consent._flags_for(text) == {"ask_at": "sensitive"}, text


@pytest.mark.parametrize("text", [
    "no me preguntes, hazlo sin preguntar",
    "hazlo sin preguntar",
    "stop asking",
    "no me pidas permiso y hazlo sin preguntar",
])
def test_less_friction_is_still_less_friction(text):
    assert consent._flags_for(text) == {"ask_at": "critical"}, text


def test_the_scope_reading_is_what_the_flags_read():
    """Disarm guard: with the governed reading turned off, the caution rule opens the door again."""
    original = consent._GOVERNED_WITHOUT_ASKING_RE
    consent._GOVERNED_WITHOUT_ASKING_RE = re.compile(r"(?!x)x")
    try:
        opened = consent._flags_for("nunca envíes un correo sin preguntarme")
    finally:
        consent._GOVERNED_WITHOUT_ASKING_RE = original
    assert opened == {"ask_at": "critical"}, "the governed reading is not the one `_flags_for` consults"
