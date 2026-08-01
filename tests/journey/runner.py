"""Execute the whole-system journey against one disposable Zaelar engine.

The Observatory itself remains on 127.0.0.1:8765. This runner starts a second,
headless engine on an ephemeral loopback port with ZAELAR_WORKSPACE and ZAELAR_DB
pointing at a temporary directory. Every chronological step therefore sees the
same memory/widget/task state without touching the operator's profile.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from typing import Any

from tests.journey.catalog import case_id, load_plan, serialize


ENGINE = Path(__file__).resolve().parents[2]


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _request(base: str, path: str, *, body: dict | None = None, timeout: float = 90) -> tuple[int, Any]:
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode()
    request = urllib.request.Request(base + path, data=data, method="POST" if body is not None else "GET",
                                     headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            return response.status, json.loads(raw or b"{}")
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            payload = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            payload = {"error": raw.decode("utf-8", "replace")}
        return exc.code, payload


def _wait_ready(base: str, process: subprocess.Popen, timeout: float = 35, log_path: Path | None = None) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            tail = ""
            if log_path and log_path.exists():
                tail = "\n" + "\n".join(log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-80:])
            raise RuntimeError(f"engine aislado terminó durante el arranque (exit {process.returncode}){tail}")
        try:
            status, _ = _request(base, "/api/status", timeout=1)
            if status == 200:
                return
        except Exception:
            pass
        time.sleep(0.2)
    raise TimeoutError(f"engine aislado no respondió en {base}")


def _flat(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str).lower()


def _contains_all(value: Any, needles: list[str]) -> bool:
    text = _flat(value)
    return all(str(needle).lower() in text for needle in needles)


def _contains_any(value: Any, needles: list[str]) -> bool:
    text = _flat(value)
    return not needles or any(str(needle).lower() in text for needle in needles)


def _matching(items: list[Any], needles: tuple[str, ...] = ("moto", "enduro", "wallapop")) -> list[Any]:
    """Return task-shaped records belonging to the journey's motorbike search."""
    return [item for item in items if _contains_any(item, list(needles))]


def _unique_tasks(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    values = [*(snapshot.get("sessions") or []), *(snapshot.get("history") or [])]
    unique: dict[str, dict[str, Any]] = {}
    for item in values:
        if isinstance(item, dict):
            unique[str(item.get("id") or item.get("task_id") or _flat(item))] = item
    return list(unique.values())


class Journey:
    def __init__(self, base: str, session: str) -> None:
        self.base = base
        self.session = session
        self.products: set[str] = set()
        self.outputs: dict[str, Any] = {}

    def _get(self, path: str) -> tuple[int, Any]:
        return _request(self.base, path)

    def _post(self, path: str, body: dict, timeout: float = 90) -> tuple[int, Any]:
        return _request(self.base, path, body=body, timeout=timeout)

    def _workers(self) -> dict[str, Any]:
        active = self._get("/api/tasks")[1].get("sessions", [])
        history = self._get("/api/workers/history")[1].get("history", [])
        return {"sessions": active, "history": history}

    def execute(self, case: dict[str, Any]) -> tuple[bool, str, Any]:
        missing = [item for item in case.get("consumes", []) if item not in self.products]
        if missing:
            return False, f"prerrequisitos no producidos: {missing}", {"missing": missing}
        op = case["op"]
        expected = case.get("expected", {})
        status = 200
        if op == "get":
            status, output = self._get(case["path"])
        elif op == "chat":
            before_workers = self._workers()
            status, output = self._post("/api/flash/say", {
                "text": case["input"], "session": self.session, "ingest": True,
                "prompt": bool(expected.get("must_reference_state")), "execute": bool(case.get("execute")),
            }, timeout=180)
            output["_workers_before"] = before_workers
            # Dispatch is asynchronous. Expectations about worker cardinality are a causal barrier: sample
            # until a new worker becomes observable (or a short deadline expires), then retain both snapshots.
            settle = 8 if expected.get("min_new_tasks") else (3 if expected.get("max_total_matching_tasks") else 0)
            deadline = time.monotonic() + settle
            after_workers = self._workers()
            while time.monotonic() < deadline:
                before_ids = {str(item.get("id")) for item in _unique_tasks(before_workers)}
                after_ids = {str(item.get("id")) for item in _unique_tasks(after_workers)}
                if expected.get("min_new_tasks") and len(after_ids - before_ids) >= int(expected["min_new_tasks"]):
                    break
                time.sleep(0.25)
                after_workers = self._workers()
            output["_workers_after"] = after_workers
            probes = expected.get("memory_contains") or expected.get("memory_contains_any") or []
            if probes:
                # The memory gateway is intentionally fire-and-forget from the hot voice/chat path. A later
                # chronological step must not race it: this is an explicit causal barrier, not an arbitrary sleep.
                deadline = time.monotonic() + 45
                recall = {}
                while time.monotonic() < deadline:
                    _, recall = self._post("/api/memory/recall", {"query": " ".join(probes), "k": 20})
                    ready = (_contains_all(recall, probes) if expected.get("memory_contains")
                             else _contains_any(recall, probes))
                    if ready:
                        break
                    time.sleep(0.5)
                output["_memory_recall"] = recall
        elif op == "reset_session":
            status, output = self._post("/api/flash/reset", {"session": self.session})
        elif op == "canvas":
            status, output = self._post("/api/canvas/state", case["input"])
        elif op == "widget_action":
            status, output = self._post(f"/widgets/{case['widget']}/action", case["input"])
        elif op == "tasks":
            status, output = self._get("/api/tasks")
        elif op == "debug":
            status, output = self._get("/api/debug")
        elif op == "cluster_dialogue":
            output = asyncio.run(self._cluster(case["input"]))
        elif op == "checkpoint":
            output = {
                "tasks": self._get("/api/tasks")[1], "debug": self._get("/api/debug")[1],
                "history": self._get("/api/workers/history")[1],
                "agenda": self._get("/widgets/agenda/data")[1],
                "connectors": self._get("/api/connectors")[1],
                "memory": self._post("/api/memory/recall", {
                    "query": "Nora Castellón arquitectura revisión moto enduro", "k": 30,
                })[1],
                "canvas": self.outputs.get("J010", {}),
            }
        else:
            return False, f"operación no soportada: {op}", {}
        ok, reasons = self._verify(status, output, expected)
        if ok:
            self.products.update(case.get("produces", []))
        self.outputs[case["id"]] = output
        return ok, "; ".join(reasons) if reasons else "contrato verificado", output

    async def _cluster(self, text: str) -> dict[str, Any]:
        from connectors.meshkore import security
        from connectors.meshkore.brain import _spec
        from nucleo.flash import cluster
        framed = ("[RELACIÓN con «journey-peer»] Fase: trabajo. NO te presentes. "
                  "Objetivo: revisar una búsqueda de motos de enduro.\n\n"
                  "[cluster:meshcore · message from agent 'journey-peer']\n"
                  + security.fence_untrusted(text))
        reply = await cluster.respond(framed, spec=_spec(), timeout=90)
        return {"reply": reply, "machinery": bool(reply.strip()),
                "identity_safe": not any(word in reply.lower() for word in ("nora", "castellón", "valencia")),
                "no_reintro": not any(word in reply.lower() for word in ("soy zaelar", "me presento"))}

    def _verify(self, status: int, output: Any, expected: dict[str, Any]) -> tuple[bool, list[str]]:
        failures: list[str] = []
        wanted_status = int(expected.get("http_status", 200))
        if status != wanted_status:
            failures.append(f"HTTP {status}, esperado {wanted_status}")
        if expected.get("ok") is True and not bool(output.get("ok")):
            failures.append("ok no es true")
        if expected.get("reply_nonempty") and not str(output.get("reply") or "").strip():
            failures.append("respuesta vacía")
        reply = str(output.get("reply") or "")
        if expected.get("reply_contains") and not _contains_all(reply, expected["reply_contains"]):
            failures.append(f"respuesta no contiene todo {expected['reply_contains']}")
        if expected.get("reply_contains_any") and not _contains_any(reply, expected["reply_contains_any"]):
            failures.append(f"respuesta no contiene ninguno de {expected['reply_contains_any']}")
        if expected.get("forbid_reply") and _contains_any(reply, expected["forbid_reply"]):
            failures.append("respuesta contiene formato prohibido")
        if expected.get("prompt_contains") and not _contains_all(output.get("prompt", ""), expected["prompt_contains"]):
            failures.append(f"prompt no contiene {expected['prompt_contains']}")
        for key in expected.get("keys", []):
            if not isinstance(output, dict) or key not in output:
                failures.append(f"falta clave {key}")
        for key, value in expected.get("equals", {}).items():
            if output.get(key) != value:
                failures.append(f"{key}={output.get(key)!r}, esperado {value!r}")
        if expected.get("contains") and not _contains_all(output, expected["contains"]):
            failures.append(f"salida no contiene {expected['contains']}")
        if expected.get("widget_ids"):
            ids = {str(item.get("id")) for item in output.get("widgets", [])}
            absent = set(expected["widget_ids"]) - ids
            if absent:
                failures.append(f"widgets ausentes: {sorted(absent)}")
        if expected.get("services"):
            services = {str(item.get("key")) for item in output.get("items", [])}
            absent = set(expected["services"]) - services
            if absent:
                failures.append(f"servicios ausentes: {sorted(absent)}")
        actions = [output.get("action"), *(output.get("tool_calls") or [])]
        if expected.get("actions_any") and not _contains_any(actions, expected["actions_any"]):
            failures.append(f"acción observada {actions!r} no casa con {expected['actions_any']}")
        if expected.get("tags_any") and not _contains_any(output.get("tags", []), expected["tags_any"]):
            failures.append(f"tags no contienen {expected['tags_any']}")
        memory_value = output.get("_memory_recall", output)
        if expected.get("memory_contains") and not _contains_all(memory_value, expected["memory_contains"]):
            failures.append(f"memoria no contiene {expected['memory_contains']}")
        if expected.get("memory_contains_any") and not _contains_any(memory_value, expected["memory_contains_any"]):
            failures.append(f"memoria no contiene ninguno de {expected['memory_contains_any']}")
        if expected.get("open_widgets") is not None and output.get("open_widgets") != expected["open_widgets"]:
            failures.append(f"canvas={output.get('open_widgets')!r}")
        before = _unique_tasks(output.get("_workers_before", {}))
        after = _unique_tasks(output.get("_workers_after", {}))
        if expected.get("min_new_tasks") is not None or expected.get("max_new_tasks") is not None:
            before_ids = {str(item.get("id") or item.get("task_id")) for item in before}
            new_count = sum(str(item.get("id") or item.get("task_id")) not in before_ids for item in after)
            minimum = int(expected.get("min_new_tasks", 0))
            maximum = int(expected.get("max_new_tasks", 10**9))
            if not minimum <= new_count <= maximum:
                failures.append(f"workers nuevos={new_count}, esperado {minimum}..{maximum}")
        task_records = _unique_tasks(output) if isinstance(output, dict) else []
        matching = _matching(task_records)
        if expected.get("min_matching") is not None and len(matching) < int(expected["min_matching"]):
            failures.append(f"tareas de moto visibles={len(matching)}, mínimo {expected['min_matching']}")
        if expected.get("max_matching") is not None and len(matching) > int(expected["max_matching"]):
            failures.append(f"tareas de moto visibles={len(matching)}, máximo {expected['max_matching']}")
        if expected.get("max_total_matching_tasks") is not None:
            total_matching = _matching(after)
            if len(total_matching) > int(expected["max_total_matching_tasks"]):
                failures.append(f"tareas totales de moto={len(total_matching)}")
        if expected.get("event_kinds_any"):
            kinds = {str(item.get("kind") or item.get("type") or "")
                     for item in output.get("events", []) if isinstance(item, dict)}
            if not kinds.intersection(expected["event_kinds_any"]):
                failures.append(f"eventos {sorted(kinds)} no incluyen {expected['event_kinds_any']}")
        if expected.get("machinery") and not output.get("machinery"):
            failures.append("motor cluster sin respuesta")
        if expected.get("identity_safe") and not output.get("identity_safe"):
            failures.append("cluster filtró identidad")
        if expected.get("no_reintro") and not output.get("no_reintro"):
            failures.append("cluster se volvió a presentar")
        if expected.get("memory") and not _contains_all(output.get("memory"), ["castellón"]):
            failures.append("checkpoint sin memoria corregida de Castellón")
        if expected.get("canvas") is not None:
            observed_canvas = output.get("canvas", {}).get("open_widgets")
            if observed_canvas != expected["canvas"]:
                failures.append(f"checkpoint canvas={observed_canvas!r}")
        if expected.get("agenda_contains") and not _contains_all(output.get("agenda"), [expected["agenda_contains"]]):
            failures.append(f"checkpoint agenda sin {expected['agenda_contains']!r}")
        if expected.get("max_motorbike_tasks") is not None:
            workers = {"sessions": output.get("tasks", {}).get("sessions", []),
                       "history": output.get("history", {}).get("history", [])}
            count = len(_matching(_unique_tasks(workers)))
            if count > int(expected["max_motorbike_tasks"]):
                failures.append(f"checkpoint tareas de moto={count}")
        if expected.get("traceable"):
            events = output.get("debug", {}).get("events", [])
            if not events or not _contains_any(events, ["moto", "enduro", "worker", "task"]):
                failures.append("checkpoint sin traza de búsqueda/worker")
        return not failures, failures


def _validate_plan(cases: list[dict[str, Any]]) -> None:
    ids = [case["id"] for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("IDs duplicados en journey.json")
    produced: set[str] = set()
    for case in cases:
        missing = set(case.get("consumes", [])) - produced
        if missing:
            raise ValueError(f"{case['id']} consume antes de producir: {sorted(missing)}")
        produced.update(case.get("produces", []))


# Campos que se MIRAN para decidir PASS/FAIL — el resumen de un fallo empieza por ellos, no por el volcado.
_SUMMARY_KEYS = ("ok", "status", "action", "reply", "detail", "error", "open_widgets", "tool_calls", "tags",
                 "match", "widgets", "items")


def _dump_failure(case: dict[str, Any], output: Any, artifacts: Path) -> str:
    """Guarda el output ÍNTEGRO como artefacto descargable y devuelve un resumen accionable para la terminal.

    Regla: la evidencia no se recorta, la PRESENTACIÓN sí. El fichero lleva el JSON completo (indentado, para
    poder diffearlo y grepearlo); la consola lleva tamaño, campos de veredicto y la ruta."""
    raw = json.dumps(output, ensure_ascii=False, default=str, indent=2, sort_keys=True)
    path = artifacts / f"journey-{case['id']}-output.json"
    try:
        artifacts.mkdir(parents=True, exist_ok=True)
        path.write_text(raw, encoding="utf-8")
        where = str(path)
    except OSError as exc:                                   # nunca dejar al agente sin evidencia por un fallo de I/O
        where = f"(no se pudo escribir el artefacto: {exc})"
    lines = [f"  output: {len(raw):,} chars · raw completo → {where}"]
    if isinstance(output, dict):
        for key in _SUMMARY_KEYS:
            if key not in output:
                continue
            val = output[key]
            val = val if isinstance(val, str) else json.dumps(val, ensure_ascii=False, default=str)
            lines.append(f"    {key}: {val if len(val) <= 300 else val[:300] + '…'}")
        extra = [k for k in output if k not in _SUMMARY_KEYS and not k.startswith("_")]
        if extra:
            lines.append(f"    (+{len(extra)} campos más en el artefacto: {', '.join(sorted(extra)[:10])})")
    else:
        lines.append(f"    {raw[:300]}")
    return "\n".join(lines)


def run(until: int) -> dict[str, Any]:
    cases = load_plan()["cases"]
    _validate_plan(cases)
    selected = cases[:until + 1]
    observer = None
    if os.getenv("ZAELAR_TEST_RUN_DIR"):
        from tests.platform.events import EventWriter
        observer = EventWriter(os.environ["ZAELAR_TEST_RUN_DIR"], run_id=os.getenv("ZAELAR_TEST_RUN_ID"))
        for index, case in enumerate(selected):
            observer.emit("test.discovered", test_id=case_id(index), suite="journey", label=case["title"],
                          index=index + 1, total=len(selected), case=serialize(index, case))
        observer.emit("collection.finished", suite="journey", total=len(selected))
    with tempfile.TemporaryDirectory(prefix="zaelar-journey-") as workspace:
        port = _free_port()
        base = f"http://127.0.0.1:{port}"
        env = os.environ.copy()
        env.update({
            "PORT": str(port), "HOST": "127.0.0.1", "BRAIN": "nucleo", "ZAELAR_ENGINE": "headless",
            "ZAELAR_WORKSPACE": workspace, "ZAELAR_DB": str(Path(workspace) / "memory" / "_data" / "journey.db"),
            "ZAELAR_HOMEOSTASIS": "0", "WA_ENABLED": "0", "TG_ENABLED": "0", "BROWSER_SEARCH": "1",
            "MESHKORE_AUTORECONNECT": "0", "ZAELAR_TLS_CERT_DIR": str(Path(workspace) / "no-tls"),
        })
        log_path = Path(os.getenv("ZAELAR_TEST_RUN_DIR", workspace)) / "artifacts" / "journey-engine.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("wb") as log:
            process = subprocess.Popen([sys.executable, "-m", "server"], cwd=ENGINE, env=env,
                                       stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            _wait_ready(base, process, log_path=log_path)
            journey = Journey(base, session=f"journey-{int(time.time())}")
            results = []
            for index, case in enumerate(selected):
                started = time.perf_counter()
                if observer:
                    observer.emit("test.started", test_id=case_id(index), suite="journey", label=case["title"])
                    observer.emit("interaction.input", test_id=case_id(index), suite="journey", input=case.get("input"),
                                  expectation=case.get("expected"), consumes=case.get("consumes"),
                                  phase=case["phase"], channel=case["channel"])
                try:
                    ok, detail, output = journey.execute(case)
                except Exception as exc:  # noqa: BLE001
                    ok, detail, output = False, f"{type(exc).__name__}: {exc}", {}
                elapsed = round((time.perf_counter() - started) * 1000, 2)
                result = {"id": case["id"], "ok": ok, "detail": detail, "duration_ms": elapsed}
                results.append(result)
                if observer:
                    observer.emit("interaction.output", test_id=case_id(index), suite="journey", output=output,
                                  text=detail, produces=case.get("produces"), phase=case["phase"])
                    observer.emit("test.finished", test_id=case_id(index), suite="journey", label=case["title"],
                                  status="passed" if ok else "failed", duration_ms=elapsed)
                print(f"{'✓' if ok else '×'} {case['id']} · {case['phase']} · {case['title']} · {detail}", flush=True)
                if not ok:
                    # EVIDENCIA COMPLETA, TERMINAL LEGIBLE (V2-084). Antes: `json.dumps(output)[:12000]` — un dump
                    # que a la vez inundaba la consola Y **recortaba** la prueba justo cuando más falta hacía (el
                    # peor de los dos mundos). Ahora el raw íntegro se guarda como ARTEFACTO del run y la terminal
                    # imprime el resumen accionable + la ruta. Nada se pierde; deja de ser ilegible.
                    print(_dump_failure(case, output, log_path.parent), flush=True)
                    break
        finally:
            process.terminate()
            try:
                process.wait(timeout=12)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        passed = sum(item["ok"] for item in results)
        return {"total": len(results), "passed": passed, "failed": len(results) - passed, "results": results}


def main() -> int:
    parser = argparse.ArgumentParser(description="Viaje cronológico integral de Zaelar")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--all", action="store_true")
    group.add_argument("--target", type=int)
    group.add_argument("--validate", action="store_true")
    args = parser.parse_args()
    cases = load_plan()["cases"]
    _validate_plan(cases)
    if args.validate:
        print(f"Plan causal válido: {len(cases)} pasos · {len({x for c in cases for x in c.get('produces', [])})} productos")
        return 0
    until = len(cases) - 1 if args.all else args.target
    if until is None or not 0 <= until < len(cases):
        parser.error(f"target fuera de rango 0..{len(cases) - 1}")
    report = run(until)
    print(f"\nViaje integral: {report['passed']}/{report['total']} pasos correctos")
    return 0 if report["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
