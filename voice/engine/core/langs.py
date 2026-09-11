"""voice/engine/core/langs.py — RE-EXPORT SHIM. The language table moved to `i18n/langs.py` (V2-676).

## Why it moved

The dependency ratchet (`tests/infrastructure/unit/test_dependency_directions_only_improve.py`) has carried
this debt with its name written on it since V2-569:

    «Thirty of them import ONE module — `voice.engine.core.langs`, the language helper… The debt has a name:
     `langs` is a shared utility that happens to LIVE inside the motor, and its honest fix is a home in a low
     layer with a re-export shim, as `text_norm.py` and `errors.brief` were before it.»

V2-676 is when it stopped being theoretical. The operator, running his agent in English, was answered by our
own canned lines in Spanish — «esta tarea no ha podido realizarse por un fallo del proveedor» — and ruled
that every text the operator can hear or read must live in ONE place that gets translated when the agent is
initialised in a language. That place is `i18n/`, next to the UI bundles, which is where the generation and
the upgrade diff already live. A language table inside the LiveKit motor made every consumer —`nucleo/`,
`widgets/`, `connectors/`— reach into the motor to say one sentence.

## Why the shim is a `sys.modules` alias and not `from … import *`

Thirty-odd files import this path, and the tests monkeypatch through it. A star-import shim would create a
SECOND module object with its own globals: patching `voice.engine.core.langs.LANGUAGES` would leave the real
table untouched and the test would measure nothing while going green. (This codebase has paid that exact
lesson once already — «mover código byte por byte cambia sus globals».) Aliasing makes both paths name the
SAME object, so every existing import, monkeypatch and `reload` keeps working unchanged.

NEW code imports `i18n.langs`. This file exists so the migration of the old callers can happen in its own
batch, measured, instead of inside the one that needed the table to move.
"""
import sys as _sys

from i18n import langs as _langs

_sys.modules[__name__] = _langs
