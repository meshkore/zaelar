"""tests/memory/e2e/bot/live_rem_faithfulness.py — validación REAL del gate de fidelidad de REM (V2-104).

Norma del operador (2026-08-16): "todas las validaciones tienen que ser reales... no nos importa el coste, lo que
nos importa es verificar que todo va bien". `test_rem.py` prueba la MECÁNICA del gate con `verify_fn` mockeado a
mano — nunca invoca el modelo de verdad. Este script SÍ: llama a `nucleo.memllm.synthesize_concept_groups()` y
`verify_insight_grounded()` REALES (DeepSeek V4 Flash, el modelo de producción) contra una BD aislada.

Tres pruebas, en orden:
  1. SÍNTESIS REAL — un grupo de píldoras reales → insight generado por el modelo → ¿el gate determinista Y el
     verificador REAL lo aceptan? (caso limpio, se espera que SÍ)
  2. ADVERSARIAL — un insight fabricado A MANO (nombre y cifra que NO están en las píldoras) → ¿el verificador
     REAL lo detecta? (se espera que SÍ lo rechace — esta es la prueba que demuestra que el gate no es teatro)
  3. CICLO COMPLETO — `memory.rem.synthesize()` con ambos hooks REALES sobre la BD aislada: ¿escribe el insight,
     demota las fuentes, y el ciclo entero corre sin mocks de principio a fin?

Uso: ./.venv/bin/python -m tests.memory.e2e.bot.live_rem_faithfulness
BD aislada: ZAELAR_DB=memory/_data/zaelar.remcheck.db (gitignored, se borra y recrea en cada corrida).
"""
from __future__ import annotations

import os
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parents[4]


def _setup_env():
    os.environ["ZAELAR_DB"] = str(REPO / "memory" / "_data" / "zaelar.remcheck.db")
    os.environ.setdefault("ZAELAR_LANGUAGE", "es")
    # Norma del operador (2026-08-16): "ahora Ollama en ninguna parte... todo de pago" — el trabajo con modelos
    # LOCALES (Ollama/embeddinggemma) queda APARCADO hasta que el sistema esté validado en producción contra el
    # modelo de pago; se retomará entonces con el MISMO benchmark. `fastembed` (ONNX in-process, sin servidor, sin
    # contención con Ollama) es el backend de embeddings mientras tanto — esta prueba NO mide calidad de embedding,
    # solo necesita un vector cualquiera para que `insert_memory()` funcione; lo que se valida aquí es la síntesis
    # y verificación REALES, que ya son DeepSeek de punta a punta.
    os.environ["ZAELAR_EMBED_BACKEND"] = "fastembed"
    try:
        from dotenv import load_dotenv
        load_dotenv(REPO / ".env", override=False)
        load_dotenv(REPO / ".meshkore" / "credentials" / "zaelar.env", override=False)
    except Exception:
        pass
    db_path = pathlib.Path(os.environ["ZAELAR_DB"])
    if db_path.exists():
        db_path.unlink()


PILLS = [
    "Los domingos por la mañana sale a correr 8 kilómetros por el parque del Retiro.",
    "Entrena para la media maratón de Madrid, prevista para noviembre.",
    "Le gusta correr con música de Vetusta Morla en los auriculares.",
    "El fisio le recomendó bajar el ritmo tras una molestia en la rodilla derecha.",
    "Corre siempre antes de las nueve para evitar el calor.",
]
CONCEPT = "running"

# Insight fabricado A MANO: introduce un nombre ("Manolo") y una cifra ("21 km") que NO están en PILLS —
# fabricación clásica de resumen por LLM, la clase de error que el gate debe cazar.
FABRICATED_INSIGHT = "Manolo, su compañero de entrenamiento, le acompaña a correr 21 km cada domingo."


def main() -> int:
    _setup_env()
    from memory import db as memdb, writer as memwriter
    from memory.rem import _grounded, synthesize
    from nucleo import memllm

    memdb.get_db()
    # `_canonical_lang_native()` (nucleo/memllm.py) prefiere `state.language` sobre ZAELAR_LANGUAGE — y el
    # DEFAULT de state en una BD nueva es "en" (arranque idiomático del producto, memory/state.py:28). Sin esto
    # una BD aislada recién creada produce insights en INGLÉS aunque las píldoras estén en español — no es un
    # bug de REM, es que esta BD nunca pasó por la detección de idioma de la primera frase real del operador.
    from memory import state as memstate
    memstate.patch({"language": "es"})
    ok = True

    print("=" * 78)
    print("PRUEBA 1 — síntesis REAL (DeepSeek V4 Flash) sobre píldoras reales")
    print("=" * 78)
    ids = [memwriter.insert_memory(t, level="mid", kind="fact", weight=0.8, concepts=[CONCEPT])
           for t in PILLS]
    group = {"concept": CONCEPT, "pills": PILLS}
    # El gate es ESTRICTO y probabilístico A PROPÓSITO (fail-closed) — un insight fiel puede rechazarse por
    # ruido del juez en un intento suelto. Igual que Test 3, hasta 3 intentos reales antes de dar por perdido.
    test1_ok = False
    for attempt in range(1, 4):
        results = memllm.synthesize_concept_groups([group])
        if not results or not results[0].get("insight"):
            print(f"  [intento {attempt}/3] el modelo no devolvió insight")
            continue
        real_insight = results[0]["insight"]
        grounded = _grounded(real_insight, PILLS)
        verified = memllm.verify_insight_grounded(real_insight, PILLS)
        print(f"  [intento {attempt}/3] insight={real_insight!r}")
        print(f"               backstop={grounded}  verificación_real={verified}")
        if grounded and verified:
            test1_ok = True
            break
    if test1_ok:
        print("  ✓ al menos un intento real generó un insight aceptado por los dos gates")
    else:
        print("  ✗ FALLO: en 3 intentos reales, ninguno pasó los dos gates")
        ok = False

    print()
    print("=" * 78)
    print("PRUEBA 2 — ADVERSARIAL: ¿el verificador REAL detecta una fabricación a mano?")
    print("=" * 78)
    print(f"  insight fabricado: {FABRICATED_INSIGHT!r}")
    det = _grounded(FABRICATED_INSIGHT, PILLS)
    print(f"  backstop determinista rechaza (debe ser False): {det}")
    real_verify = memllm.verify_insight_grounded(FABRICATED_INSIGHT, PILLS)
    print(f"  verificación REAL por LLM rechaza (debe ser False): {real_verify}")
    if det or real_verify:
        print("  ✗ FALLO: alguno de los dos gates ACEPTÓ una fabricación evidente")
        ok = False
    else:
        print("  ✓ ambos gates (determinista Y modelo real) rechazaron la fabricación")

    print()
    print("=" * 78)
    print("PRUEBA 3 — ciclo completo REAL: memory.rem.synthesize() con hooks reales")
    print("=" * 78)
    before = {mid: memdb.get_db().query_one("SELECT weight FROM memories WHERE id=?", (mid,))["weight"]
              for mid in ids}

    # Transparencia total: si el ciclo rechaza, queremos VER qué generó el modelo ESTA vez (la generación es
    # estocástica — Test 1 ya demostró que el modelo SÍ puede producir un insight que pasa los dos gates; que
    # esta llamada, independiente, no lo consiga es una observación real que hay que mostrar, no ocultar).
    def _synthesize_fn_debug(groups):
        out = memllm.synthesize_concept_groups(groups)
        for r in out:
            print(f"  [debug] intento REAL de síntesis: {r}")
        return out

    def _verify_fn_debug(insight, pills):
        v = memllm.verify_insight_grounded(insight, pills)
        print(f"  [debug] verificación REAL sobre ese intento: {v}")
        return v

    # La generación es ESTOCÁSTICA y el gate es ESTRICTO a propósito (asimétrico: perder un insight legítimo
    # sale más barato que dejar pasar uno inventado) — REM real reintenta la NOCHE siguiente si un intento no
    # pasa. Aquí simulamos hasta 3 "noches" para demostrar el camino feliz de verdad, sin forzar nada.
    written = 0
    for attempt in range(1, 4):
        print(f"  --- intento {attempt}/3 ---")
        written = synthesize(_synthesize_fn_debug, min_group=4, verify_fn=_verify_fn_debug)
        if written:
            break
    print(f"  insights escritos: {written}")
    row = memdb.get_db().query_one("SELECT text, weight FROM memories WHERE slot=? AND valid=1",
                                   (f"insight:{CONCEPT}",))
    if written == 1 and row is not None:
        print(f"  insight vigente: {row['text']!r} (peso {row['weight']})")
        demoted = 0
        for mid in ids:
            after = memdb.get_db().query_one("SELECT weight FROM memories WHERE id=?", (mid,))["weight"]
            if after < before[mid]:
                demoted += 1
        print(f"  píldoras fuente demotadas: {demoted}/{len(ids)}")
        if demoted == len(ids):
            print("  ✓ ciclo completo real: sintetiza, verifica de verdad, escribe y demota")
        else:
            print("  ✗ FALLO: no todas las fuentes quedaron demotadas")
            ok = False
    else:
        print("  ✗ FALLO: no se escribió el insight en el ciclo completo (¿el verificador real lo rechazó?)")
        ok = False

    print()
    print("=" * 78)
    print("RESULTADO:", "✓ TODAS LAS PRUEBAS REALES PASARON" if ok else "✗ HUBO FALLOS — revisar arriba")
    print("=" * 78)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
