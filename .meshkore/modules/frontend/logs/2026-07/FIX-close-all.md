---
id: FIX-close-all
title: "Bug: «close widgets» cerraba solo uno — chat no-final + ALL_RE sin plural genérico"
status: done
priority: medium
owner: ricart
initiative: INI-006
created: 2026-07-03
updated: 2026-07-03
---

# Fix — "close widgets" cerraba un solo widget

## Síntoma (reportado por el operador)

Tecleó **"close widgets"** en el chat wall y solo se cerró **un** widget (quedaron meteo + reloj).

## Causa raíz (dos bugs que se combinan)

1. **El fast-path de cierre nunca disparaba desde el chat.** `handleWidgetVoice` (voiceCommands.js) gatea CLOSE
   con `if(!isFinal) return` (nunca cerrar sobre un interim revisable). En `sse.js`, `isFinal` se calculaba como
   `d.label === "transcript"`. El texto tecleado emite label `"text-injected (chat/paste)"` (voice/turn_control.py)
   → se trataba como **interim** → el CLOSE fast-path retornaba sin hacer nada. El cierre quedaba 100% en manos
   del brain, que ante "close widgets" emitió un `[[close:id]]` (uno), no `[[close]]` (todos).
2. **`ALL_RE` no reconocía el plural genérico.** `close widgets` (sin "all"/"todo") no matcheaba
   `ALL_RE`, así que ni por voz se habría tratado como cerrar-todo; habría caído a identify → last-opened → uno.

## Fix (`frontend/app/`)

- `services/sse.js`: `isFinal = d.label === "transcript" || d.label.startsWith("text-injected")` — el texto
  tecleado/pegado es definitivamente final, así el CLOSE fast-path dispara desde el chat.
- `services/voiceCommands.js`: `ALL_RE` añade `everything|widgets|tarjetas|cards`. Se mantienen en **plural** a
  propósito: "close widgets"/"cierra las tarjetas" → `closeAll()`, pero "cierra el widget del tiempo" (singular,
  con nombre) sigue cayendo a `identify()` y cierra solo ese.

## Verificación

`scratchpad/test_closeall.mjs` (node): 8 frases de cerrar-todo (es/en, "close widgets", "cierra los widgets",
"close everything", "cierra todo", "limpia la pantalla"…) → all-scope; 2 singulares con nombre → NO all-scope;
`isFinal` correcto para `transcript`/`interim`/`text-injected`. Ambos módulos parsean como ES module; el
servidor vivo ya sirve los ficheros corregidos (`no-cache` → basta recargar la página, sin reiniciar).
