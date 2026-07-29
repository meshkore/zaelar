---
id: FIX-json-leak
title: "Fix: JSON crudo hablado por el cerebro rápido (duo) al preguntar por el catálogo de widgets"
status: done
priority: medium
owner: ricart
initiative: INI-008
created: 2026-07-05
updated: 2026-07-05
---

# Fix — JSON crudo filtrándose a la voz

## Síntoma (evaluación de logs de la sesión 20260705-214902, pedida por el operador)

Al preguntar "muéstrame los widgets disponibles" en modo `BRAIN=duo`, zaelar respondió hablando JSON crudo:

> *"Claro, te muestro los widgets que tenemos disponibles. {"title":"Available widgets","items":[{"title":"agenda"}...]}"*

## Causa raíz

El brief de widgets (`widgets/brief.py`) enseña al cerebro el patrón `[[push:results]]{json}[[/push]]` para
volcar RESULTADOS DE BÚSQUEDA, pero no cubre la pregunta meta "¿qué widgets hay?" (el cerebro ya tiene la lista
en su propio contexto — es una pregunta de charla, no una búsqueda). Gemini flash-lite, sin ejemplo claro, mezcló
ambos casos: emitió un `[[show]]` vacío y además volcó el catálogo como JSON suelto en el texto hablado — algo
que `strip_tags` no tenía forma de detectar (no está dentro de ninguna tag reconocida).

## Qué se hizo

1. **Prompt** (`brains/duo/prompt.py`): regla explícita — preguntas sobre el catálogo se responden DESCRIBIENDO
   en 1-2 frases (el cerebro ya tiene la lista), nunca como JSON/`{ }`. Regla general añadida a REGLAS DE VOZ:
   fuera de una tag `[[...]]`, nunca `{ }`.
2. **Red de seguridad compartida** (`voice/tag_protocol.py`, brain-agnóstico — protege a Hermes también):
   `JSON_LEAK_RE` detecta la apertura de un objeto JSON con clave entre comillas (`{"clave":`) fuera de cualquier
   tag reconocida. En streaming, se RETIENE desde ahí (nunca se habla token a token); en el flush final, se CORTA
   entero y se registra como evento `json_leak_dropped` en el timeline (visible para depurar, nunca hablado).

## Ficheros

`brains/duo/prompt.py` · `voice/tag_protocol.py`.

## Verificación

Tests dirigidos contra la fuga real capturada: (1) la fuga real se corta y el evento se registra; (2) streaming
con la fuga repartida en 5 trozos nunca habla ni un fragmento de `{`; (3) uso legítimo de `[[push:results]]`
sigue intacto; (4) frase normal con `{x}` sin comillas+dos puntos no dispara falso positivo. Suite completa
(64 tests: 55 previos + 9 del proveedor Architect) + endpointing (9/9) + widgets (7/7) en verde tras el merge con
el commit v0.12.0 (INI-010, Architect provider).
