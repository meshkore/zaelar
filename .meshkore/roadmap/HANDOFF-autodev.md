# Prompt de relevo — sesión limpia de auto-mejora de zaelar (INI-013)

Copia el bloque de abajo en un Claude Code nuevo (contexto en blanco), en la carpeta
`/Users/ricartjuncadella/Documents/Prj/asimovia/zaelar`.

---

Eres el agente de auto-desarrollo de **zaelar** (asistente de voz personal, castellano). Trabajas en
`/Users/ricartjuncadella/Documents/Prj/asimovia/zaelar`, que sigue el **MeshKore Standard v27**.

## 1. Carga contexto (léelo, en este orden)
- `CLAUDE.md` (instrucciones del repo + decisiones clave + reglas duras).
- `.meshkore/roadmap/initiatives/INI-013-NOCHE-RESUMEN.md` (estado actual + qué funciona + abiertos).
- `.meshkore/roadmap/initiatives/INI-013-voice-tester.md` (el sistema de test, detallado).
- `.meshkore/docs/ops/zaelar-observability.md` (cómo depurar por los eventos, sin mirar pantallas).

## 2. Arquitectura del auto-desarrollo
- **zaelar** (el sistema bajo prueba) = el propio repo. Se arranca con `make run-duo` → LiveKit **nativo (sin Docker)**
  en :8473, worker embebido, cerebro **duo** (fast layer **DeepSeek vía AIMLAPI** + Hermes async), STT Whisper Metal,
  TTS Kokoro local. Config viva en `config/settings.json` + `.env` (FAST_* apunta a DeepSeek).
- **El tester** (interpela a zaelar, INDEPENDIENTE, 0 imports de zaelar) = carpeta `tester/`:
  `tester/interlocutor/` (voz/chat/paste + persona en castellano + traza SSE) y `tester/judge/` (juez).
  Habla a zaelar solo por LiveKit + HTTP + data-channel + SSE `/events`.
- **El juez** = `tester/judge/judge.py`: **GLM vía Z.AI** (endpoint coding-plan Anthropic) con **fallback a DeepSeek**;
  lee la traza de observabilidad (acciones de frontend + cerebro), no solo el transcript.

## 3. Credenciales + routing (NO negociar)
- Claves en `.env` (raíz, gitignored) + `.meshkore/credentials/tester.env` (gitignored). Ya están todas
  (AIMLAPI, TESTER_ZAI, Cartesia, Deepgram). El tester carga ambas.
- **Routing**: conducir el tester + fast layer de zaelar = **DeepSeek/AIMLAPI**. Juez/razonamiento = **GLM/Z.AI**
  (fallback DeepSeek). **Gemini free-tier PROHIBIDO** (429, 20/día). NO usar modelos caros de AIMLAPI (opus…).
- Tester habla por **Deepgram Aura** (`TESTER_TTS=deepgram`, voz es) porque Cartesia se quedó sin saldo (402).

## 4. Arranque
```
bash tester/guard.sh      # idempotente: levanta zaelar (:8473) + el bucle de test si están caídos
```
- `tester/overnight.sh` = bucle: rota escenarios (conversation/agenda/memory/widget/search/complex_idea/chat/paste/
  websocket) + goals creativos, escribe informes en `tester/runs/report_*.md` (.md/.json se commitean; .wav/.log no).
- Verificar un escenario a mano: `./.venv/bin/python -m tester.run --scenario <id> --no-open --hold 0`
  → mira `frontend_actions` + el veredicto del juez GLM en el informe.

## 5. El bucle test→fix→commit (tu trabajo)
Crea un **cron de sesión cada 15 min** (CronCreate, `"7,22,37,52 * * * *"`) con ESTE prompt:
> Iteración autónoma zaelar (INI-013). No preguntes; trabaja hasta el límite de uso.
> 1) `bash tester/guard.sh`. 2) Lee el informe más reciente `tester/runs/report_*.md`; elige el TOP bug de zaelar.
> 3) Arréglalo en el código, reinicia zaelar (`make run-duo`), re-verifica con `tester.run --scenario <id>` mirando
> la traza. 4) `git add -A && git commit` con mensaje que describa hallazgo+fix (incluye los informes). NO push.
> 5) Registra el fix en INI-013. Para y deja que el siguiente tick siga.

## 6. Reglas duras
- **NO push** sin confirmación del operador (commits locales sí, uno por iteración). Rama actual: `feat/livekit-migration`.
- El core de zaelar **NO usa Docker** (LiveKit nativo; `make install-livekit`). Docker solo lo puede usar el tester.
- No commitear secretos (.env/.meshkore/credentials/settings.json/tester runs → ya gitignored).
- Un modelo **razonador nunca** en el path de voz (no cierra el turno → mudo). Fast layer = no-razonador.

## 7. Estado al heredar (resumen)
zaelar **funciona** (verificado, juez GLM 5/5 en corridas limpias): voz+chat+paste en castellano, dispara widgets
`[[show/close]]`, memoria (guardar+recall en-contexto), TTS local sin mute, STT sin alucinaciones, voz siempre-encendida
en el frontend (mute por el orbe → 🚫). ~20 commits la noche del 2026-07-06/07 (crónica en `git log`).
**Único bloqueante grande abierto (decisión del operador, NO adivinar)**: la **latencia del fast layer** (DeepSeek/AIMLAPI
~2-3s, no sub-segundo) → elegir un **modelo local rápido y capaz** (qwen2.5:7b / Kimi / GLM-air). Menores: ruido
STT-sobre-STT del tester (inherente); `LLM_MODEL=zhipu/glm-5-2` en .env es razonador (solo capa deep/display).
