"""A widget's observability event survives a refactor of the file that emits it (V2-826 §2b, refactor2710-12).

Splitting `data.py`, `owner.py` or `tasks.py` moves their `emit(...)` / `_emit(...)` calls; dropping one by accident
fails nowhere — the timeline and the Master just show less. This freezes every call under `widgets/` whose first
argument is a literal (with its second argument when that is a literal too, `None` when it is computed): a call may
move between files, never vanish. One added later passes; one retired on purpose leaves this set in the same commit.

Measured 2026-10-28 on main before the split: 85 calls. The widgets' client code (`widget.js` and `js/`) emits
nothing — the host does — so only Python is read.
"""
from __future__ import annotations

import ast
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[4]
_NAMES = ("emit", "_emit", "publish")

FROZEN = {
    ('_emit', 'click', None),
    ('_emit', 'closed_window', 'ventana cerrada (sesión guardada)'),
    ('_emit', 'cmd_error', None),
    ('_emit', 'confirm', None),
    ('_emit', 'confirm-cancel', None),
    ('_emit', 'crash', None),
    ('_emit', 'disabled', None),
    ('_emit', 'dismiss_overlay', 'cmp-accept'),
    ('_emit', 'dismiss_overlay', 'fallback'),
    ('_emit', 'dropped', None),
    ('_emit', 'error', None),
    ('_emit', 'import_error', None),
    ('_emit', 'launched', None),
    ('_emit', 'nav_error', None),
    ('_emit', 'navigate', None),
    ('_emit', 'no_tick', None),
    ('_emit', 'ready', 'navegador listo (Chromium se lanza al primer uso)'),
    ('_emit', 'remote_port', None),
    ('_emit', 'screenshot', None),
    ('_emit', 'skip', None),
    ('_emit', 'start', None),
    ('_emit', 'stopped', None),
    ('_emit', 'tab_open', None),
    ('_emit', 'task_done', None),
    ('_emit', 'task_error', None),
    ('_emit', 'task_giveup', 'sin progreso ni con visión'),
    ('_emit', 'task_giveup', None),
    ('_emit', 'task_need_login', None),
    ('_emit', 'task_need_vision', None),
    ('_emit', 'task_refine', None),
    ('_emit', 'task_start', None),
    ('_emit', 'task_step', None),
    ('_emit', 'task_stuck', None),
    ('_emit', 'task_upgrade', None),
    ('_emit', 'tick', None),
    ('_emit', 'widget', 'action'),
    ('_emit', 'widget', 'action_refused'),
    ('_emit', 'widget', 'gate_ask'),
    ('_emit', 'widget', 'gate_shadow'),
    ('_emit', 'widget', '🩹 payload con sinónimos → renombrado al manifiesto'),
    ('_emit', 'widget', None),
    ('_emit', 'youtube', None),
    ('_emit', 'yt_search', None),
    ('emit', 'backed', None),
    ('emit', 'background', None),
    ('emit', 'brain', '✅ acción irreversible confirmada (botón)'),
    ('emit', 'flow', 'end'),
    ('emit', 'navegador', '🏁 hito'),
    ('emit', 'navegador', None),
    ('emit', 'panel', 'open'),
    ('emit', 'widget', "✉️ a held message's text goes to its row, not to a copy"),
    ('emit', 'widget', 'alias'),
    ('emit', 'widget', 'blank'),
    ('emit', 'widget', 'data'),
    ('emit', 'widget', 'exclusive'),
    ('emit', 'widget', 'form_facts: note not sent'),
    ('emit', 'widget', 'sent'),
    ('emit', 'widget', 'show'),
    ('emit', 'widget', 'wallpaper'),
    ('emit', 'widget', '🎨 presentación: calidad de los datos'),
    ('emit', 'widget', '🚫 off-category rows filed as rejected'),
    ('emit', 'widget', '🛑 buy click held: he asked about a row, not to buy'),
    ('emit', 'widget', '🩹 lo que el agente acababa de empezar no ocurrió — se dice'),
    ('emit', 'widget', None),
}


def _calls() -> set:
    found = set()
    for p in (ENGINE / "widgets").rglob("*.py"):
        if "/_user/" in p.as_posix() or "/_data/" in p.as_posix():
            continue
        for n in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
            if not isinstance(n, ast.Call) or not n.args or not isinstance(n.args[0], ast.Constant):
                continue
            name = n.func.attr if isinstance(n.func, ast.Attribute) else getattr(n.func, "id", "")
            if name == "apply":   # the canvas door (`nucleo.acts.canvas.apply("<op>", …)`) emits ("widget", "<op>")
                found.add(("emit", "widget", n.args[0].value))
            elif name in _NAMES:
                second = n.args[1].value if len(n.args) > 1 and isinstance(n.args[1], ast.Constant) else None
                found.add((name, n.args[0].value, second))
    return found


def test_no_frozen_widget_event_vanishes():
    missing = sorted(FROZEN - _calls(), key=str)
    assert not missing, f"an event stopped being emitted under widgets/: {missing}"


def test_disarm_a_dropped_event_is_named():
    gone = ("emit", "widget", "data")
    assert gone in FROZEN and sorted(FROZEN - (_calls() - {gone}), key=str) == [gone]
