# Bench del DESTILADOR (CORAZÓN) — calidad vs precio — 2026-08-09 14:02

34 casos · 3 pasada(s) · la latencia NO puntúa (escritor off-hot-path)

| modelo | write-compl. | precisión | capa/slot | $/1k turnos | in/out tok | p50 | muertas |
|---|---|---|---|---|---|---|---|
| gpt-4.1-mini@aimlapi | 98.9% | 100.0% | 100.0% | $1.516 | 3558/57.7 | 1678ms | 0 |
| deepseek-v4-flash | 98.5% | 100.0% | 94.4% | $0.68 | 4076/389.3 | 4083ms | 0 |
| ministral-8b@mistral | 97.8% | 73.3% | 100.0% | $0.393 | 3858/68.7 | 1046ms | 0 |
| gemini-2.5-flash | 96.7% | 100.0% | 100.0% | $1.232 | 3608/60 | 2452ms | 0 |
| gemini-2.5-flash-lite | 96.7% | 90.0% | 94.4% | $0.39 | 3608/72 | 906ms | 0 |
| deepseek-chat | 95.6% | 100.0% | 94.4% | $0.579 | 3997/69 | 1957ms | 0 |
| grok-4-fast-nonreason | 95.6% | 100.0% | 100.0% | $0.762 | 3689/48.3 | 1074ms | 0 |
| gpt-4o-mini | 80.4% | 76.7% | 81.5% | $0.571 | 3559.3/61.3 | 1203ms | 21 |
