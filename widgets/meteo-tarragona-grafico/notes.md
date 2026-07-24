# meteo-tarragona-grafico — notas

- Objetivo: previsión GRÁFICA de temperatura en Tarragona para los próximos 14 días, mostrando los valores a las 12 h y a las 18 h.
- Dos líneas en el mismo gráfico (12 h = azul `#3D6FE0`, 18 h = teal `#16B8A6`) sobre un eje X de 14 días. Cada punto rotula su valor en grados.
- Eje X = días (dow + dd/mm), hoy resaltado. Eje Y = temperatura con rango auto-ajustado al min/max real más un pequeño margen.
- Fuente: Open-Meteo (sin clave), stdlib only, 6 s timeout; `data.py` nunca lanza.
- Render en SVG inline, sin librerías externas ni red desde `widget.js`. Todo texto del servidor inyectado con `textContent` (XSS-safe).
