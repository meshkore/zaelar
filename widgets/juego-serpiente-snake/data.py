#
# Serpiente (Snake) — backend. El juego es 100% CLIENTE (todo el estado vive en widget.js: posición de la
# serpiente, comida, puntos; el récord en localStorage del navegador). Este widget es PASIVO y AUTÓNOMO: no
# hay mutaciones de servidor, ni fetch, ni fondo → no hay apply_action ni tick. view_data solo entrega la
# configuración estática de la partida para que el cliente arranque. Nunca lanza excepción.
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
