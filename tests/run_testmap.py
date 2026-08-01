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
            "tests/memory/unit/test_db.py", "tests/memory/unit/test_journal.py",
            "tests/memory/unit/test_graph.py", "tests/memory/unit/test_state.py",
            "tests/memory/unit/test_compose_state.py"]},
        {"id": "1.2", "title": "Embeddings y recuperación (retriever+reranker)", "ch": UNIT, "paths": [
            "tests/memory/unit/test_embeddings.py", "tests/memory/unit/test_retriever.py",
            "tests/memory/integration/test_rerank.py"]},
        {"id": "1.3", "title": "Escritura / ingest / destilador", "ch": UNIT, "paths": [
            "tests/memory/integration/test_memory_agent.py", "tests/memory/integration/test_writer_queue.py",
            "tests/memory/integration/test_write_precision_v2033.py",
            "tests/memory/integration/test_write_precision_v2050.py",
            "tests/memory/integration/test_write_changes_20260712.py",
            "tests/memory/integration/test_episodic.py", "tests/memory/integration/test_episodic_bytes.py",
            "tests/memory/unit/test_consolidator.py"]},
        {"id": "1.4", "title": "Recall correcto (comportamiento, corpus)", "ch": UNIT, "live": True,
            "cmd": "./.venv/bin/python -m tests.memory.e2e.bot.runner --corpus v1 --next 10",
            "nested_events": True},
        {"id": "1.5", "title": "Sueño REM / síntesis", "ch": UNIT, "paths": ["tests/memory/unit/test_rem.py"]},
        {"id": "1.6", "title": "Bóveda y secretos", "ch": UNIT, "paths": [
            "tests/memory/unit/test_vault.py", "tests/memory/unit/test_vault_flow.py",
            "tests/memory/unit/test_vault_ingest.py", "tests/memory/unit/test_vault_rules.py",
            "tests/memory/unit/test_secrets.py", "tests/memory/unit/test_pill_slot.py",
            "tests/memory/unit/test_slots_audit.py", "tests/memory/unit/test_location_grounding.py",
            "tests/memory/unit/test_critical_health.py", "tests/memory/integration/test_seed_from_hermes.py"]},
        {"id": "1.7", "title": "API HTTP de memoria", "ch": HTTP, "paths": [
            "tests/memory/integration/test_api.py", "tests/memory/integration/test_vault_api.py",
            "tests/memory/e2e/test_server_api.py"]},
        {"id": "1.8", "title": "Contexto de UI en el estado", "ch": UNIT, "paths": [
            "tests/memory/integration/test_ui_context.py"]},
    ]},
    {"id": "2", "name": "FLASHBRAIN (nucleo)", "nodes": [
        {"id": "2.1", "title": "Enrutado / elección de tool", "ch": UNIT, "paths": [
            "tests/agent_headless/unit/flash/test_router.py", "tests/agent_headless/unit/flash/test_music_flow.py", "tests/agent_headless/unit/test_demo_routing.py"]},
        {"id": "2.2", "title": "Bucle de diálogo y anti-degeneración", "ch": UNIT, "paths": [
            "tests/agent_headless/unit/flash/test_dialog.py", "tests/agent_headless/unit/test_loop.py"]},
        {"id": "2.3", "title": "Prompt / skeleton / chispas", "ch": UNIT, "paths": [
            "tests/agent_headless/unit/flash/test_prompt.py", "tests/agent_headless/unit/test_skeleton.py", "tests/agent_headless/unit/test_sparks.py"]},
        {"id": "2.4", "title": "Cliente LLM rápido y reintento", "ch": UNIT, "paths": [
            "tests/agent_headless/unit/flash/test_fast_client.py", "tests/agent_headless/unit/flash/test_fast_client_retry.py",
            "tests/agent_headless/unit/flash/test_procs.py"]},
        {"id": "2.5", "title": "Escalado / dispatch / workers", "ch": UNIT, "paths": [
            "tests/agent_headless/unit/flash/test_escalate.py", "tests/agent_headless/unit/test_dispatch.py", "tests/agent_headless/unit/workers/test_workers.py",
            "tests/agent_headless/unit/agentes/test_agentes.py", "tests/agent_headless/unit/agentes/test_work_agents.py"]},
        {"id": "2.6", "title": "Scheduler / rails / workspace / frontend-glue", "ch": UNIT, "paths": [
            "tests/agent_headless/unit/test_scheduler.py", "tests/agent_headless/unit/test_rails.py", "tests/agent_headless/unit/test_workspace.py",
            "tests/agent_headless/unit/flash/test_frontend.py", "tests/agent_headless/unit/flash/test_memory_cache.py"]},
        {"id": "2.7", "title": "Susurro (auto-reparación)", "ch": UNIT, "paths": [
            "tests/agent_headless/unit/susurro/test_susurro.py",
            "tests/agent_headless/unit/susurro/test_phantom_dataop.py"]},
        {"id": "2.8", "title": "Búsqueda web (comportamiento)", "ch": UNIT, "live": True,
            "cmd": "./.venv/bin/python tests/agent_headless/e2e/search/bot/runner.py"},
        {"id": "2.9", "title": "Sandbox de ejecución ligero (V2-076)", "ch": UNIT, "paths": [
            "tests/agent_headless/unit/test_sandbox.py"]},
        {"id": "2.10", "title": "Puente git acotado + dev worker (V2-076)", "ch": UNIT, "paths": [
            "tests/agent_headless/unit/test_git_cli.py", "tests/agent_headless/unit/test_dev_worker.py",
            "tests/agent_headless/unit/test_dev_worker_guard.py"]},
        {"id": "2.11", "title": "Conversación sintética + juez", "ch": CHAT, "live": True,
            "cmd": "./.venv/bin/python -m tests.agent_headless.harness.run"},
    ]},
    {"id": "3", "name": "VOZ", "nodes": [
        {"id": "3.1", "title": "Atención / VAD / endpointing", "ch": VOICE, "paths": [
            "tests/voice/unit/test_attention.py", "tests/voice/unit/test_endpointing.py"]},
        {"id": "3.2", "title": "Puente voz→nucleo + trazas", "ch": VOICE, "paths": [
            "tests/voice/unit/providers/test_nucleo.py", "tests/voice/unit/providers/test_nucleo_guards.py",
            "tests/voice/unit/test_trace.py", "tests/voice/e2e/agent/interlocutor/test_trace.py"]},
        {"id": "3.3", "title": "Mic→STT (transporte WebRTC)", "ch": VOICE, "live": True,
            "cmd": "./.venv/bin/python -m tests.voice.e2e.mic.mic_selftest"},
        {"id": "3.4", "title": "Bucle de voz completo", "ch": VOICE, "live": True,
            "cmd": "./.venv/bin/python -m tests.voice.e2e.agent.smoke"},
        {"id": "3.5", "title": "Escenarios voz/chat/paste + juez", "ch": VOICE, "live": True,
            "cmd": "./.venv/bin/python -m tests.voice.e2e.agent.run --no-open --hold 0"},
    ]},
    {"id": "4", "name": "WIDGETS", "nodes": [
        {"id": "4.1", "title": "Ciclo de vida / acciones / refs / generador / background", "ch": UNIT, "paths": [
            "tests/browser/unit/widgets/test_lifecycle_confirm.py", "tests/browser/unit/widgets/test_actions.py", "tests/browser/unit/widgets/test_refs.py",
            "tests/browser/unit/widgets/test_generator_sync.py", "tests/browser/unit/widgets/test_background.py",
            "tests/browser/unit/widgets/test_aliases.py", "tests/browser/unit/widgets/test_identify_context.py",
            "tests/browser/unit/widgets/test_resolver_certainty.py", "tests/browser/unit/widgets/test_system_surfaces_sync.py"]},
        {"id": "4.2", "title": "Navegador (browser)", "ch": UNIT, "paths": [
            "tests/browser/unit/navegador/test_auth.py", "tests/browser/unit/navegador/test_tasks_dedup.py"]},
        {"id": "4.3", "title": "Widget de música", "ch": UNIT, "paths": ["tests/browser/unit/musica/test_data.py"]},
        {"id": "4.4", "title": "Widget de YouTube", "ch": UNIT, "paths": ["tests/browser/unit/youtube/test_youtube.py"]},
        {"id": "4.5", "title": "Widget de mensajería", "ch": UNIT, "paths": ["tests/browser/unit/mensajeria/test_owner_v2.py"]},
        {"id": "4.6", "title": "Agenda: contrato XSS del renderer", "ch": UNIT, "paths": [
            "tests/browser/unit/agenda/test_xss_contract.py"]},
        # V2-085 — la garantía de ESCALA: el prompt es O(K) y no O(N) por muchos widgets que haya. Nodo propio (no
        # dentro de 4.1) porque lo que prueba no es el contrato de UN widget sino el del CATÁLOGO: sintéticos de
        # 100/1.000/10.000, promoción del widget nombrado desde la cola, e índice compacto del endpoint.
        {"id": "4.7", "title": "Selección progresiva del catálogo (escala 100/1k/10k)", "ch": UNIT, "paths": [
            "tests/browser/unit/widgets/test_selection_scale.py"]},
    ]},
    {"id": "5", "name": "CONECTORES", "nodes": [
        {"id": "5.1", "title": "Email", "ch": UNIT, "paths": [
            "tests/connectors/unit/email/test_mailbox.py", "tests/connectors/unit/email/test_oauth.py",
            "tests/connectors/unit/email/test_providers.py"]},
        {"id": "5.2", "title": "Mensajería (ingest/reply)", "ch": UNIT, "paths": [
            "tests/connectors/unit/messaging/test_ingest.py", "tests/connectors/unit/messaging/test_reply.py",
            "tests/connectors/unit/messaging/test_memory_dump.py"]},
        {"id": "5.3", "title": "Música / Spotify / YouTube-audio", "ch": UNIT, "paths": [
            "tests/connectors/unit/music/test_music.py", "tests/connectors/unit/music/test_youtube_audio.py",
            "tests/connectors/unit/spotify/test_auth.py", "tests/connectors/unit/spotify/test_provider.py"]},
        {"id": "5.4", "title": "Architect", "ch": UNIT, "paths": ["tests/connectors/unit/architect/test_architect.py"]},
        {"id": "5.5", "title": "WhatsApp: normalización y allowlist", "ch": UNIT, "paths": [
            "tests/connectors/unit/whatsapp/test_allowlist_contract.py"]},
    ]},
    {"id": "6", "name": "CLUSTER (meshkore)", "nodes": [
        {"id": "6.1", "title": "Cápsula / framing (una sola mente)", "ch": PEER, "paths": [
            "tests/cluster/unit/test_capsule.py", "tests/cluster/unit/test_capsule_flow.py"]},
        {"id": "6.2", "title": "Seguridad del canal", "ch": PEER, "paths": ["tests/cluster/unit/test_security.py"]},
        {"id": "6.3", "title": "Ingesta cluster→memoria", "ch": PEER, "paths": [
            "tests/cluster/unit/test_mem_ingest.py"]},
        {"id": "6.5", "title": "Protección de recursos (balance/anti-offload, V2-071)", "ch": PEER, "paths": [
            "tests/cluster/unit/test_resource.py"]},
        {"id": "6.6", "title": "Pacto de conversación agente-agente (reglas negociadas, V2-072)", "ch": PEER, "paths": [
            "tests/cluster/unit/test_pact.py"]},
        {"id": "6.7", "title": "Criterio de conversación por INTELIGENCIA (evaluador modelo, genérico, V2-075)", "ch": PEER, "paths": [
            "tests/cluster/unit/test_pace.py"]},
        {"id": "6.8", "title": "Permisos por-cluster + contrato de catálogo (V2-076)", "ch": PEER, "paths": [
            "tests/cluster/unit/test_perms.py"]},
        {"id": "6.4", "title": "Conversación con peer (comportamiento)", "ch": PEER, "live": True,
            "cmd": "./.venv/bin/python tests/cluster/e2e/run_cluster_suite.py"},
    ]},
    {"id": "7", "name": "SERVER / OBSERVABILIDAD", "nodes": [
        {"id": "7.1", "title": "Bus de eventos y log", "ch": UNIT, "paths": [
            "tests/infrastructure/unit/test_bus.py", "tests/infrastructure/unit/test_bus_log.py",
            "tests/platform/tests/test_events.py", "tests/platform/tests/test_catalog.py",
            "tests/platform/tests/test_pytest_plugin.py"]},
        {"id": "7.2", "title": "Observer SSE", "ch": HTTP, "paths": [
            "tests/infrastructure/integration/test_sse_observer.py", "tests/infrastructure/unit/test_zai_sse.py"]},
        {"id": "7.5", "title": "Sello de versión (instancia + observabilidad, V2-074)", "ch": UNIT, "paths": [
            "tests/infrastructure/unit/test_version.py"]},
        {"id": "7.3", "title": "Chat por transporte LiveKit REAL", "ch": CHAT, "live": True,
            "cmd": "./.venv/bin/python tests/infrastructure/e2e/smoke/run_chat_over_livekit.py"},
        {"id": "7.4", "title": "Smoke INTEGRAL de salud", "ch": HTTP, "live": True,
            "cmd": "./.venv/bin/python tests/infrastructure/e2e/smoke/run_full_smoke.py"},
    ]},
    {"id": "8", "name": "ENERGÍA / CONFIG", "nodes": [
        {"id": "8.1", "title": "Medidor de energía y límites demo", "ch": UNIT, "paths": [
            "tests/infrastructure/unit/core/test_energy_meter.py", "tests/infrastructure/unit/core/test_demo_limits.py", "tests/infrastructure/unit/config/test_balances.py"]},
        {"id": "8.2", "title": "Perfiles / v2 / doctor / credenciales", "ch": UNIT, "paths": [
            "tests/infrastructure/unit/config/test_profiles.py", "tests/infrastructure/unit/config/test_v2.py",
            "tests/infrastructure/unit/config/test_doctor.py", "tests/infrastructure/unit/config/test_credentials.py"]},
    ]},
    {"id": "9", "name": "HOMEOSTASIS (latido autónomo)", "nodes": [
        {"id": "9.1", "title": "Detección/seguridad/eviction/rotación (V2-070)", "ch": UNIT, "paths": [
            "tests/infrastructure/unit/core/test_homeostasis.py"]},
        {"id": "9.2", "title": "Salud viva de la máquina", "ch": HTTP, "live": True,
            "cmd": "./.venv/bin/python tests/infrastructure/e2e/smoke/run_full_smoke.py --no-pytest"},
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
