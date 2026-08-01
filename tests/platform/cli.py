"""Unified local/agent/CI command line for Zaelar tests."""
from __future__ import annotations

import argparse
import json
import os
import shlex
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
import webbrowser
from pathlib import Path

from .catalog import SUITES, build_suite_catalog, deterministic_paths, find_case, suite_nodes, suite_rows
from .events import EventWriter, read_events

ENGINE = Path(__file__).resolve().parents[2]
RUNS = ENGINE / "tests" / "runs"
DEFAULT_PORT = 8765


def _free_port(preferred: int) -> int:
    if preferred:
        return preferred
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _stop_existing_dashboard(port: int) -> None:
    """Stop our previous dashboard before reusing the stable local port."""
    url = f"http://127.0.0.1:{port}"
    try:
        with urllib.request.urlopen(f"{url}/api/meta", timeout=0.35) as response:
            meta = json.loads(response.read() or b"{}")
        if "run_id" not in meta:
            raise RuntimeError(f"El puerto {port} está ocupado por un servicio que no es Test Observatory")
        request = urllib.request.Request(f"{url}/api/shutdown", data=b"{}", method="POST",
                                         headers={"Content-Type": "application/json"})
        urllib.request.urlopen(request, timeout=1).read()
    except urllib.error.URLError:
        return
    for _ in range(50):
        with socket.socket() as sock:
            if sock.connect_ex(("127.0.0.1", port)) != 0:
                return
        time.sleep(0.05)
    raise RuntimeError(f"El dashboard anterior no liberó el puerto {port}")


def _dashboard(run_dir: Path, port: int, *, open_browser: bool) -> str:
    port = _free_port(port)
    _stop_existing_dashboard(port)
    log = (run_dir / "dashboard.log").open("ab")
    subprocess.Popen(
        [sys.executable, "-m", "tests.platform.server", "--run-dir", str(run_dir), "--port", str(port)],
        cwd=ENGINE,
        stdin=subprocess.DEVNULL,
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
        close_fds=True,
    )
    log.close()
    url = f"http://127.0.0.1:{port}"
    ready = False
    for _ in range(40):
        try:
            urllib.request.urlopen(f"{url}/api/meta", timeout=0.2).read()
            ready = True
            break
        except Exception:
            time.sleep(0.05)
    if not ready:
        raise RuntimeError(f"El dashboard local no pudo arrancar en {url}; revisa {run_dir / 'dashboard.log'}")
    if open_browser:
        webbrowser.open(url)
    return url


def _stream(command: list[str], writer: EventWriter, env: dict[str, str], *, label: str) -> int:
    writer.emit("process.started", label=label, command=command, suite=env.get("ZAELAR_TEST_SUITE"))
    process = subprocess.Popen(
        command,
        cwd=ENGINE,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    assert process.stdout is not None
    for line in process.stdout:
        print(line, end="", flush=True)
        writer.emit("process.output", label=label, text=line.rstrip(), suite=env.get("ZAELAR_TEST_SUITE"))
    code = process.wait()
    writer.emit("process.finished", label=label, status="passed" if code == 0 else "failed", exit_code=code,
                suite=env.get("ZAELAR_TEST_SUITE"))
    return code


def _new_run(suite: str) -> tuple[str, Path]:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    run_id = f"{stamp}-{suite}-{uuid.uuid4().hex[:6]}"
    run_dir = RUNS / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    (run_dir / "artifacts").mkdir()
    return run_id, run_dir


def _resolve_case(suite: str, case_id: str) -> dict:
    paths = deterministic_paths(suite)
    if paths:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "--collect-only", "-q", *paths],
            cwd=ENGINE, capture_output=True, text=True, timeout=120,
        )
        tests = [line.strip() for line in result.stdout.splitlines()
                 if "::" in line and not line.startswith("<")]
    else:
        tests = []
    case = find_case(build_suite_catalog(suite, tests), case_id)
    if not case or not case.get("execution"):
        raise ValueError(f"El caso {case_id!r} no pertenece al catálogo ejecutable de {suite}")
    return case


def _run(args: argparse.Namespace) -> int:
    requested_case = args.case
    if not requested_case and args.suite != "all" and not (args.live or args.live_step or args.node):
        requested_case = SUITES[args.suite].primary_case or None
    if args.memory_case and not requested_case:  # backwards compatibility with schema v1 URLs/scripts
        corpus, _, selector = args.memory_case.partition(":")
        if selector.isdigit():
            requested_case = f"memory::{corpus}::{int(selector):04d}"
    if requested_case and (args.live or args.live_step or args.node):
        raise ValueError("--case no puede combinarse con --live, --live-step o --node")
    case = _resolve_case(args.suite, requested_case) if requested_case else None
    run_id, run_dir = _new_run(args.suite)
    meta = {"schema": 1, "run_id": run_id, "suite": args.suite, "created_at": time.time(), "status": "running"}
    (run_dir / "run.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    writer = EventWriter(run_dir, run_id=run_id)
    live_node = None
    if args.live_step:
        live_node = next((node for node in suite_nodes(args.suite)
                          if node["id"] == args.live_step and node.get("live") and node.get("cmd")), None)
        if live_node is None:
            print(f"El paso live {args.live_step!r} no existe en {args.suite}", file=sys.stderr)
            return 2
    mode = "case" if case else "live-step" if live_node else "live" if args.live else "deterministic"
    writer.emit("run.started", suite=args.suite, mode=mode)
    url = _dashboard(run_dir, args.port, open_browser=not args.no_open and not os.getenv("CI"))
    print(f"\nZaelar Test Observatory: {url}")
    print(f"Run: {run_id}\n")

    env = os.environ.copy()
    env.update({
        "ZAELAR_TEST_RUN_DIR": str(run_dir),
        "ZAELAR_TEST_RUN_ID": run_id,
        "ZAELAR_TEST_SUITE": args.suite,
        "ZAELAR_TEST_EXTERNAL_DASHBOARD": "1",
        "ZAELAR_TEST_DASHBOARD_URL": url,
    })
    if case:
        action = case["execution"]
        if action.get("kind") == "pytest":
            nodeids = list(action.get("nodeids") or [action["nodeid"]])
            command = [sys.executable, "-m", "pytest", "-q", "-p", "tests.platform.pytest_plugin",
                       *nodeids, *args.pytest_arg]
            code = _stream(command, writer, env, label=f"case · {case['id']}")
        elif action.get("kind") == "command":
            command = [sys.executable if part == "{python}" else str(part) for part in action.get("argv", ())]
            if not command:
                raise ValueError(f"El caso {case['id']} no declara argv")
            nested = bool(action.get("nested_events"))
            if not nested:
                writer.emit("test.discovered", test_id=case["id"], suite=args.suite, label=case["title"],
                            index=1, total=1, case=case)
                writer.emit("collection.finished", suite=args.suite, total=1)
                writer.emit("test.started", test_id=case["id"], suite=args.suite, label=case["title"])
                writer.emit("interaction.input", test_id=case["id"], suite=args.suite,
                            input=case.get("input"), expectation=case.get("expected"),
                            verification=case.get("verification"))
            started = time.perf_counter()
            code = _stream(command, writer, env, label=f"case · {case['id']}")
            if not nested:
                writer.emit("test.finished", test_id=case["id"], suite=args.suite, label=case["title"],
                            status="passed" if code == 0 else "failed",
                            duration_ms=round((time.perf_counter() - started) * 1000, 2))
        else:
            raise ValueError(f"Tipo de ejecución no soportado: {action.get('kind')!r}")
    elif live_node:
        nested_events = bool(live_node.get("nested_events"))
        test_id = f"live::{live_node['id']}"
        if not nested_events:
            writer.emit("test.discovered", test_id=test_id, suite=args.suite, label=live_node["title"], index=1, total=1)
            writer.emit("collection.finished", total=1)
            writer.emit("test.started", test_id=test_id, suite=args.suite, label=live_node["title"])
        command = shlex.split(live_node["cmd"])
        if command and command[0].endswith("python"):
            command[0] = sys.executable
        started = time.perf_counter()
        code = _stream(command, writer, env, label=f"live {live_node['id']} · {live_node['title']}")
        if not nested_events:
            writer.emit("test.finished", test_id=test_id, suite=args.suite, label=live_node["title"],
                        status="passed" if code == 0 else "failed",
                        duration_ms=round((time.perf_counter() - started) * 1000, 2))
    else:
        paths = args.node or deterministic_paths(args.suite)
        command = [sys.executable, "-m", "pytest", "-q", "-p", "tests.platform.pytest_plugin", *paths,
                   *args.pytest_arg]
        code = _stream(command, writer, env, label=f"pytest · {args.suite}")

    if args.live and not live_node and args.suite != "all":
        for live in SUITES[args.suite].live_commands:
            live_code = _stream([sys.executable, *live], writer, env, label=f"live · {args.suite}")
            code = code or live_code
    status = "passed" if code == 0 else "failed"
    writer.emit("run.finished", suite=args.suite, status=status, exit_code=code)
    events = read_events(run_dir)
    tests = [e for e in events if e.get("type") == "test.finished"]
    meta.update({
        "status": status,
        "finished_at": time.time(),
        "exit_code": code,
        "tests": len(tests),
        "passed": sum(e.get("status") == "passed" for e in tests),
        "failed": sum(e.get("status") == "failed" for e in tests),
        "dashboard": url,
    })
    (run_dir / "run.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"\n{status.upper()} · {len(tests)} tests · visor: {url}")
    print(f"Registro durable: {run_dir.relative_to(ENGINE)}")
    return code


def _list() -> int:
    print("Zaelar test suites\n")
    for row in suite_rows():
        live = " + live" if row["has_live"] else ""
        amount = (f"{row['case_count']} cases" if row["case_count"] else
                  f"{row['deterministic_files']} files")
        print(f"  {row['id']:<20} {amount:>9}{live:<7}  {row['description']}")
    print("\n  all                  toda la batería determinista")
    return 0


def _replay(args: argparse.Namespace) -> int:
    run_dir = RUNS / args.run_id
    if not (run_dir / "events.jsonl").exists():
        print(f"No existe el run {args.run_id}", file=sys.stderr)
        return 2
    url = _dashboard(run_dir, args.port, open_browser=not args.no_open)
    print(f"Replay: {url}")
    return 0


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="python -m tests", description="Zaelar unified test platform")
    sub = root.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="listar suites")
    run = sub.add_parser("run", help="ejecutar una suite y abrir observabilidad realtime")
    run.add_argument("suite", choices=["all", *SUITES], nargs="?", default="all")
    run.add_argument("--live", action="store_true", help="añadir el E2E vivo declarado por la suite")
    run.add_argument("--live-step", default="", help="ejecutar únicamente un paso live N.M del catálogo")
    run.add_argument("--case", default="", help="ID estable de cualquier caso del catálogo")
    run.add_argument("--memory-case", default="", help=argparse.SUPPRESS)
    run.add_argument("--no-open", action="store_true", help="no abrir navegador (CI/headless)")
    run.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"puerto local estable (default: {DEFAULT_PORT})")
    run.add_argument("--node", action="append", default=[], help="ruta/nodeid pytest concreto (repetible)")
    run.add_argument("--pytest-arg", action="append", default=[], help="argumento adicional para pytest (repetible)")
    replay = sub.add_parser("replay", help="reabrir una ejecución durable")
    replay.add_argument("run_id")
    replay.add_argument("--port", type=int, default=DEFAULT_PORT)
    replay.add_argument("--no-open", action="store_true")
    return root


def main() -> int:
    args = parser().parse_args()
    if args.command == "list":
        return _list()
    if args.command == "replay":
        return _replay(args)
    return _run(args)
