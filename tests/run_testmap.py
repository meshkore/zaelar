"""EL MAPA DE TESTS — «¿funciona todo?» respondido por DOMINIO → CASO DE USO → CANAL (2026-07-25).

Petición del operador: que el testing esté tan ordenado que a "¿funciona todo bien?" se pueda responder
"1.1 ✅, 1.2 ✅, 2.1 ✅…". Este fichero es la ÚNICA fuente de verdad de esa taxonomía: cada nodo N.M declara qué
ficheros lo cubren, por qué CANAL entran (voz / chat-sobre-livekit / peer-de-cluster / http-api / unidad-directa) y
si es DETERMINISTA (pytest, corre en CI sin servidor) o VIVO (e2e, exige `make run` + proveedores reales).

Correr:
  ./.venv/bin/python tests/run_testmap.py                # todo lo DETERMINISTA (pytest), árbol numerado + veredicto
  ./.venv/bin/python tests/run_testmap.py --domain 1     # solo el dominio 1 (MEMORIA)
  ./.venv/bin/python tests/run_testmap.py --list         # solo listar la taxonomía (no ejecuta nada)
  ./.venv/bin/python tests/run_testmap.py --live         # incluye los nodos VIVOS (los lista + su comando; no los lanza)

La narrativa (canales, huecos conocidos, duplicación) vive en tests/TESTMAP.md — este fichero es el ejecutable.
Se EXTIENDE (1000→10000 casos) añadiendo ficheros a los nodos de abajo o nodos nuevos, no reescribiendo la espina.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys

ENGINE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# ── LA TAXONOMÍA ────────────────────────────────────────────────────────────────────────────────────────────────
# Cada nodo: (id, título, canal, ["ruta/pytest", ...] | comando-vivo). `live=True` = exige servidor vivo (no en CI).
# Canales: unit=unidad-directa · http=http-api · voice=voz(livekit) · chat=chat-sobre-livekit · peer=peer-de-cluster.
UNIT = "unit"; HTTP = "http"; VOICE = "voice"; CHAT = "chat"; PEER = "peer"

DOMAINS: list[dict] = [
    {"id": "1", "name": "MEMORIA", "nodes": [
        {"id": "1.1", "title": "BD y primitivas de estado", "ch": UNIT, "paths": [
            "tests/unit/memory/test_db.py", "tests/unit/memory/test_journal.py",
            "tests/unit/memory/test_graph.py", "tests/unit/memory/test_state.py",
            "memory/test_compose_state.py"]},
        {"id": "1.2", "title": "Embeddings y recuperación (retriever+reranker)", "ch": UNIT, "paths": [
            "tests/unit/memory/test_embeddings.py", "tests/unit/memory/test_retriever.py",
            "tests/integration/memory/test_rerank.py"]},
        {"id": "1.3", "title": "Escritura / ingest / destilador", "ch": UNIT, "paths": [
            "nucleo/test_memory_agent.py", "tests/integration/memory/test_writer_queue.py",
            "tests/integration/memory/test_write_precision_v2033.py",
            "tests/integration/memory/test_write_precision_v2050.py",
            "tests/integration/memory/test_write_changes_20260712.py",
            "tests/integration/memory/test_episodic.py", "tests/integration/memory/test_episodic_bytes.py",
            "tests/unit/memory/test_consolidator.py"]},
        {"id": "1.4", "title": "Recall correcto (comportamiento, corpus)", "ch": UNIT, "live": True,
            "cmd": "./.venv/bin/python tests/e2e/memory/bot/runner.py"},
        {"id": "1.5", "title": "Sueño REM / síntesis", "ch": UNIT, "paths": ["tests/unit/memory/test_rem.py"]},
        {"id": "1.6", "title": "Bóveda y secretos", "ch": UNIT, "paths": [
            "tests/unit/memory/test_vault.py", "tests/unit/memory/test_vault_flow.py",
            "tests/unit/memory/test_vault_ingest.py", "tests/unit/memory/test_vault_rules.py",
            "tests/unit/memory/test_secrets.py", "tests/unit/memory/test_pill_slot.py",
            "tests/unit/memory/test_slots_audit.py", "tests/unit/memory/test_location_grounding.py",
            "tests/unit/memory/test_critical_health.py", "tests/integration/memory/test_seed_from_hermes.py"]},
        {"id": "1.7", "title": "API HTTP de memoria", "ch": HTTP, "paths": [
            "tests/integration/memory/test_api.py", "tests/integration/test_vault_api.py",
            "tests/e2e/memory/test_server_api.py"]},
        {"id": "1.8", "title": "Contexto de UI en el estado", "ch": UNIT, "paths": [
            "tests/integration/estado/test_ui_context.py"]},
    ]},
    {"id": "2", "name": "FLASHBRAIN (nucleo)", "nodes": [
        {"id": "2.1", "title": "Enrutado / elección de tool", "ch": UNIT, "paths": [
            "nucleo/flash/test_router.py", "nucleo/flash/test_music_flow.py", "nucleo/test_demo_routing.py"]},
        {"id": "2.2", "title": "Bucle de diálogo y anti-degeneración", "ch": UNIT, "paths": [
            "nucleo/flash/test_dialog.py", "nucleo/test_loop.py"]},
        {"id": "2.3", "title": "Prompt / skeleton / chispas", "ch": UNIT, "paths": [
            "nucleo/flash/test_prompt.py", "nucleo/test_skeleton.py", "nucleo/test_sparks.py"]},
        {"id": "2.4", "title": "Cliente LLM rápido y reintento", "ch": UNIT, "paths": [
            "nucleo/flash/test_fast_client.py", "nucleo/flash/test_fast_client_retry.py",
            "nucleo/flash/test_procs.py"]},
        {"id": "2.5", "title": "Escalado / dispatch / workers", "ch": UNIT, "paths": [
            "nucleo/flash/test_escalate.py", "nucleo/test_dispatch.py", "nucleo/workers/test_workers.py",
            "nucleo/agentes/test_agentes.py", "nucleo/agentes/test_work_agents.py"]},
        {"id": "2.6", "title": "Scheduler / rails / workspace / frontend-glue", "ch": UNIT, "paths": [
            "nucleo/test_scheduler.py", "nucleo/test_rails.py", "nucleo/test_workspace.py",
            "nucleo/flash/test_frontend.py", "nucleo/flash/test_memory_cache.py"]},
        {"id": "2.7", "title": "Susurro (auto-reparación)", "ch": UNIT, "paths": ["nucleo/susurro/test_susurro.py"]},
        {"id": "2.8", "title": "Búsqueda web (comportamiento)", "ch": UNIT, "live": True,
            "cmd": "./.venv/bin/python tests/e2e/search/bot/runner.py"},
    ]},
    {"id": "3", "name": "VOZ", "nodes": [
        {"id": "3.1", "title": "Atención / VAD / endpointing", "ch": VOICE, "paths": [
            "voice/test_attention.py", "voice/test_endpointing.py"]},
        {"id": "3.2", "title": "Puente voz→nucleo + trazas", "ch": VOICE, "paths": [
            "voice/engine/llm/providers/test_nucleo.py", "voice/engine/llm/providers/test_nucleo_guards.py",
            "voice/test_trace.py"]},
        {"id": "3.3", "title": "Mic→STT (transporte WebRTC)", "ch": VOICE, "live": True,
            "cmd": "./.venv/bin/python -m harness.mic_selftest"},
        {"id": "3.4", "title": "Bucle de voz completo", "ch": VOICE, "live": True,
            "cmd": "./.venv/bin/python -m tester.smoke"},
    ]},
    {"id": "4", "name": "WIDGETS", "nodes": [
        {"id": "4.1", "title": "Ciclo de vida / acciones / refs / generador / background", "ch": UNIT, "paths": [
            "widgets/test_lifecycle_confirm.py", "widgets/test_actions.py", "widgets/test_refs.py",
            "widgets/test_generator_sync.py", "widgets/test_background.py"]},
        {"id": "4.2", "title": "Navegador (browser)", "ch": UNIT, "paths": [
            "widgets/navegador/test_auth.py", "widgets/navegador/test_tasks_dedup.py"]},
        {"id": "4.3", "title": "Widget de música", "ch": UNIT, "paths": ["widgets/musica/test_data.py"]},
        {"id": "4.4", "title": "Widget de YouTube", "ch": UNIT, "paths": ["widgets/youtube/test_youtube.py"]},
        {"id": "4.5", "title": "Widget de mensajería", "ch": UNIT, "paths": ["widgets/mensajeria/test_owner_v2.py"]},
    ]},
    {"id": "5", "name": "CONECTORES", "nodes": [
        {"id": "5.1", "title": "Email", "ch": UNIT, "paths": [
            "connectors/email/test_mailbox.py", "connectors/email/test_oauth.py",
            "connectors/email/test_providers.py"]},
        {"id": "5.2", "title": "Mensajería (ingest/reply)", "ch": UNIT, "paths": [
            "connectors/messaging/test_ingest.py", "connectors/messaging/test_reply.py",
            "connectors/messaging/test_memory_dump.py"]},
        {"id": "5.3", "title": "Música / Spotify / YouTube-audio", "ch": UNIT, "paths": [
            "connectors/music/test_music.py", "connectors/music/test_youtube_audio.py",
            "connectors/spotify/test_auth.py", "connectors/spotify/test_provider.py"]},
        {"id": "5.4", "title": "Architect", "ch": UNIT, "paths": ["connectors/architect/test_architect.py"]},
    ]},
    {"id": "6", "name": "CLUSTER (meshkore)", "nodes": [
        {"id": "6.1", "title": "Cápsula / framing (una sola mente)", "ch": PEER, "paths": [
            "connectors/meshkore/test_capsule.py", "connectors/meshkore/test_capsule_flow.py"]},
        {"id": "6.2", "title": "Seguridad del canal", "ch": PEER, "paths": ["connectors/meshkore/test_security.py"]},
        {"id": "6.3", "title": "Ingesta cluster→memoria", "ch": PEER, "paths": [
            "connectors/meshkore/test_mem_ingest.py"]},
        {"id": "6.5", "title": "Protección de recursos (balance/anti-offload, V2-071)", "ch": PEER, "paths": [
            "connectors/meshkore/test_resource.py"]},
        {"id": "6.6", "title": "Pacto de conversación agente-agente (reglas negociadas, V2-072)", "ch": PEER, "paths": [
            "connectors/meshkore/test_pact.py"]},
        {"id": "6.7", "title": "Criterio de conversación por INTELIGENCIA (evaluador modelo, genérico, V2-075)", "ch": PEER, "paths": [
            "connectors/meshkore/test_pace.py"]},
        {"id": "6.8", "title": "Permisos por-cluster + contrato de catálogo (V2-076)", "ch": PEER, "paths": [
            "connectors/meshkore/test_perms.py"]},
        {"id": "6.4", "title": "Conversación con peer (comportamiento)", "ch": PEER, "live": True,
            "cmd": "./.venv/bin/python tests/e2e/cluster/run_cluster_suite.py"},
    ]},
    {"id": "7", "name": "SERVER / OBSERVABILIDAD", "nodes": [
        {"id": "7.1", "title": "Bus de eventos y log", "ch": UNIT, "paths": ["bus/test_bus.py", "bus/test_log.py"]},
        {"id": "7.2", "title": "Observer SSE", "ch": HTTP, "paths": ["bus/test_sse_observer.py"]},
        {"id": "7.5", "title": "Sello de versión (instancia + observabilidad, V2-074)", "ch": UNIT, "paths": [
            "tests/unit/test_version.py"]},
        {"id": "7.3", "title": "Chat por transporte LiveKit REAL", "ch": CHAT, "live": True,
            "cmd": "./.venv/bin/python tests/e2e/smoke/run_chat_over_livekit.py"},
        {"id": "7.4", "title": "Smoke INTEGRAL de salud", "ch": HTTP, "live": True,
            "cmd": "./.venv/bin/python tests/e2e/smoke/run_full_smoke.py"},
    ]},
    {"id": "8", "name": "ENERGÍA / CONFIG", "nodes": [
        {"id": "8.1", "title": "Medidor de energía y límites demo", "ch": UNIT, "paths": [
            "nucleo/test_energy_meter.py", "nucleo/test_demo_limits.py", "config/test_balances.py"]},
        {"id": "8.2", "title": "Perfiles / v2 / doctor / credenciales", "ch": UNIT, "paths": [
            "config/test_profiles.py", "config/test_v2.py", "config/test_doctor.py", "config/test_credentials.py"]},
    ]},
    {"id": "9", "name": "HOMEOSTASIS (latido autónomo)", "nodes": [
        {"id": "9.1", "title": "Detección/seguridad/eviction/rotación (V2-070)", "ch": UNIT, "paths": [
            "nucleo/test_homeostasis.py"]},
        {"id": "9.2", "title": "Salud viva de la máquina", "ch": HTTP, "live": True,
            "cmd": "./.venv/bin/python tests/e2e/smoke/run_full_smoke.py --no-pytest"},
    ]},
]

_SUMMARY = re.compile(r"(\d+) passed|(\d+) failed|(\d+) error")


def _run_node(paths: list[str]) -> tuple[bool, str]:
    existing = [p for p in paths if os.path.exists(os.path.join(ENGINE, p))]
    missing = [p for p in paths if p not in existing]
    if not existing:
        return False, "sin ficheros (¿movidos?)"
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", *existing],
                       cwd=ENGINE, capture_output=True, text=True)
    tail = [l for l in (r.stdout or r.stderr).splitlines() if l.strip()]
    summary = tail[-1] if tail else ""
    note = summary.strip("= ")
    if missing:
        note += f" · ⚠ faltan {len(missing)}"
    return r.returncode == 0, note


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--domain", help="solo este dominio (id, p.ej. 1)")
    ap.add_argument("--list", action="store_true", help="solo listar la taxonomía")
    ap.add_argument("--live", action="store_true", help="incluir los nodos VIVOS (lista su comando; no los lanza)")
    args = ap.parse_args()

    print("═" * 74 + "\nMAPA DE TESTS — zaelar · dominio → caso de uso → canal\n" + "═" * 74)
    fails: list[str] = []
    for dom in DOMAINS:
        if args.domain and dom["id"] != args.domain:
            continue
        print(f"\n{dom['id']}. {dom['name']}")
        for n in dom["nodes"]:
            live = n.get("live")
            if args.list:
                tag = f"[VIVO · {n['ch']}]" if live else f"[{n['ch']}]"
                print(f"  {n['id']} {n['title']}  {tag}")
                continue
            if live:
                if args.live:
                    print(f"  🔌 {n['id']} {n['title']} — VIVO ({n['ch']}): {n.get('cmd','')}")
                else:
                    print(f"  ⏭  {n['id']} {n['title']} — VIVO ({n['ch']}), omitido (usa --live para verlo)")
                continue
            ok, note = _run_node(n["paths"])
            print(f"  {'✅' if ok else '❌'} {n['id']} {n['title']} — {note}")
            if not ok:
                fails.append(n["id"])

    if args.list:
        return 0
    print("\n" + "═" * 74)
    if fails:
        print("❌ FALLAN:", ", ".join(fails), "\n→ el sistema NO está plenamente verde")
        return 1
    print("✅ TODO VERDE (deterministas). Los nodos VIVOS exigen `make run` — corre con --live para su lista.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
