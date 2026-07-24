# notes — juego-serpiente-snake

- 2026-07-17 (creación): juego clásico de la serpiente (Snake) TOTALMENTE JUGABLE, pedido explícito del operador:
  rejilla, la serpiente CRECE al comer, GAME OVER al chocar (pared o contra sí misma), MARCADOR de puntos, control
  por FLECHAS del teclado. Debe ser AUTÓNOMO y PASIVO. Restricciones de implementación (no regresar):
  - Todo el juego corre en el CLIENTE (widget.js): estado en memoria + récord en localStorage (`hb-snake-best`).
    Sin red, sin store de servidor, sin apply_action, sin tick/background (nada cambia off-screen).
  - Rejilla DOM (no canvas) a propósito: el cambio de tema ☾/☀ re-pinta al instante vía CSS, sin JS.
  - Control por flechas capturado con foco PROPIO del widget (`tabIndex`+listener en `el`), NO en document →
    no secuestra las flechas de la página; también acepta WASD. No permite giro de 180°.
  - Colores por variables `--hb-*` (serpiente=accent, cabeza=accent2, comida=risk). Nunca hex temático hardcodeado.
  - `el._snkStop()` limpia intervalo + listener antes de un re-render → sin fugas de bucles.
