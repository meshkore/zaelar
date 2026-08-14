#
# Snake backend. The game is 100% client-side: all state lives in widget.js (snake position, food, score; the
# record lives in browser localStorage). This widget is passive and autonomous: no server mutations, no fetch, no
# background cycle, therefore no apply_action and no tick. view_data only returns static game configuration so the
# client can start. Never raises.
#


def view_data(q: str = "") -> dict:
    return {
        "title": "Serpiente (Snake)",
        "cols": 18,
        "rows": 18,
        "tick_ms": 130,
        "controls": "Flechas del teclado (← ↑ ↓ →).",
        "hint": "Come para crecer; game over al chocar con la pared o contigo mismo.",
    }
