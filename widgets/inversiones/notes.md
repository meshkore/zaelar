# Inversiones — notas de diseño

## Origen (2026-08-10)
- El operador pedía mejorar un "dashboard de investments/tokens" con disco/donut + cajitas
  de texto. **No existía ningún widget de inversiones en el sistema** (verificado en `widgets/`,
  `results`, `navegador` y memoria). Se construye desde cero ya con las mejoras pedidas.
- Datos de **ejemplo** (sample=true): BTC/ETH/SOL/ADA. Pendiente que el operador pase sus
  posiciones reales → action `set_holdings`.

## Decisiones de diseño (lo que pidió el operador — NO regresar)
- **Disco grande con márgenes equilibrados:** el panel del donut lleva `padding-left` ==
  `padding-bottom` (26==26). El donut es generoso (r=80, stroke 34, ~212px). No volver a un
  donut pequeño ni a márgenes asimétricos.
- **Texto desplazado a la derecha dentro de las cajitas:** cada tarjeta tiene barra de color
  a la izquierda + `padding-left` amplio (20px). El contenido arranca separado del borde izq.
- **4 datos como 2 filas × 2, NO 4 columnas:** cada posición es SU tarjeta (fondo + borde),
  en rejilla 2×2 con `gap` generoso (13px). Dentro de la tarjeta, nombre+valor van agrupados
  (misma unidad); entre tarjetas, separación clara → imposible confundir el valor de un token
  con el nombre del siguiente.
- **Recursos gráficos:** glifos por ticker (₿ Ξ ◎ ₳ …), barra de color = segmento del donut,
  tipografía monoespaciada para cifras, variación ▲/▼ verde/rojo, swatch-icono circular.

## Estructura
- `view_data()` lee de `store` (siembra ejemplo si vacío). `apply_action("set_holdings")`
  reemplaza la cartera entera (carga de datos reales). Passive, foreground-only.
- Colores: `COLORS` = accent / accent2 / violeta #8B5CF6 / ámbar #F59E0B (+ extras). Legibles
  en tema claro y oscuro.
