"""Dependency-free local dashboard server for one durable test run."""
from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
ENGINE = HERE.parents[1]


def run_is_active(run_dir: Path) -> bool:
    """Return whether the displayed run is still executing.

    The UI is also a spectator surface. Refusing a handoff while a run is active
    prevents a manual click from hiding an agent-owned execution on port 8765.
    """
    try:
        meta = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return False
    return meta.get("status") == "running"


class DashboardServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, handler, run_dir: Path, idle_timeout: int) -> None:
        super().__init__(address, handler)
        self.run_dir = run_dir
        self.idle_timeout = idle_timeout
        self.last_access = time.monotonic()
        self.catalog_cache: dict[str, bytes] = {}
        self.stop_requested = False
        self.pending_launch: tuple[list[str], Path] | None = None


class Handler(BaseHTTPRequestHandler):
    server: DashboardServer

    def log_message(self, fmt: str, *args) -> None:
        return

    def _headers(self, content_type: str, length: int | None = None) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        if length is not None:
            self.send_header("Content-Length", str(length))
        self.end_headers()

    def do_GET(self) -> None:
        self.server.last_access = time.monotonic()
        if self.path in ("/", "/index.html"):
            payload = (HERE / "dashboard" / "index.html").read_bytes()
            self._headers("text/html; charset=utf-8", len(payload))
            self.wfile.write(payload)
            return
        if self.path == "/api/meta":
            meta_path = self.server.run_dir / "run.json"
            payload = meta_path.read_bytes() if meta_path.exists() else b"{}"
            self._headers("application/json", len(payload))
            self.wfile.write(payload)
            return
        if self.path == "/events":
            self._events()
            return
        if self.path.startswith("/api/catalog/"):
            self._catalog(self.path.removeprefix("/api/catalog/"))
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        self.server.last_access = time.monotonic()
        expected_origin = f"http://127.0.0.1:{self.server.server_address[1]}"
        origin = self.headers.get("Origin", "")
        if origin and origin != expected_origin:
            self.send_error(HTTPStatus.FORBIDDEN, "invalid origin")
            return
        if self.path == "/api/shutdown":
            raw = b'{"ok":true}'
            self._headers("application/json", len(raw))
            self.wfile.write(raw)
            self.server.stop_requested = True
            return
        if self.path != "/api/run":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        try:
            length = min(int(self.headers.get("Content-Length", "0")), 2048)
            payload = json.loads(self.rfile.read(length) or b"{}")
            suite = str(payload.get("suite", ""))
            node = str(payload.get("node", "")).strip()
            live = bool(payload.get("live", False))
            live_step = str(payload.get("live_step", "")).strip()
            case_id = str(payload.get("case_id", "")).strip()
            # Compatibility for Observatory tabs opened before schema v2.
            memory_case = str(payload.get("memory_case", "")).strip()
            if memory_case and not case_id:
                corpus, _, selector = memory_case.partition(":")
                if selector.isdigit():
                    case_id = f"memory::{corpus}::{int(selector):04d}"
            from tests.platform.catalog import SUITES, deterministic_paths, find_case, suite_nodes
            if suite not in {"all", *SUITES}:
                raise ValueError("suite no declarada")
            if node and node.split("::", 1)[0] not in deterministic_paths(suite):
                raise ValueError("el test no pertenece a la suite declarada")
            if live and (suite == "all" or not SUITES[suite].live_commands):
                raise ValueError("la suite no declara una ejecución live")
            if live_step and not any(item["id"] == live_step and item.get("live") and item.get("cmd")
                                     for item in suite_nodes(suite)):
                raise ValueError("el paso live no pertenece a la suite")
            if (live or live_step) and node:
                raise ValueError("live solo puede lanzarse a nivel de suite")
            if live and live_step:
                raise ValueError("elige batería live o un único paso live")
            if case_id:
                case = find_case(self._catalog_data(suite), case_id)
                if not case or not case.get("execution"):
                    raise ValueError("el caso no pertenece al catálogo ejecutable de la suite")
            if case_id and (node or live or live_step):
                raise ValueError("el caso debe ejecutarse de forma aislada")
            if run_is_active(self.server.run_dir):
                raise RuntimeError("hay una ejecución activa; espera a que termine antes de lanzar otra")
            url = self._launch(suite, node=node, live=live, live_step=live_step, case_id=case_id)
            raw = json.dumps({"ok": True, "url": url, "suite": suite, "node": node,
                              "live": live, "live_step": live_step, "case_id": case_id,
                              "handoff": True}).encode()
            self._headers("application/json", len(raw))
            self.wfile.write(raw)
        except Exception as exc:
            raw = json.dumps({"ok": False, "error": str(exc)}).encode()
            self.send_response(HTTPStatus.BAD_REQUEST)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

    def _catalog(self, suite: str) -> None:
        from tests.platform.catalog import SUITES
        if suite not in {"all", *SUITES}:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        try:
            raw = json.dumps(self._catalog_data(suite), ensure_ascii=False).encode()
            self._headers("application/json", len(raw))
            self.wfile.write(raw)
        except subprocess.TimeoutExpired:
            self.send_error(HTTPStatus.GATEWAY_TIMEOUT, "collection timeout")

    def _catalog_data(self, suite: str) -> dict:
        from tests.platform.catalog import build_suite_catalog, deterministic_paths
        cached = self.server.catalog_cache.get(suite)
        if cached:
            return json.loads(cached)
        paths = deterministic_paths(suite)
        if paths:
            result = subprocess.run(
                [sys.executable, "-m", "pytest", "--collect-only", "-q", *paths],
                cwd=ENGINE, capture_output=True, text=True, timeout=120,
            )
            tests = [line.strip() for line in result.stdout.splitlines()
                     if "::" in line and not line.startswith("<")]
            collection_ok = result.returncode == 0
        else:
            tests = []
            collection_ok = True
        catalog = build_suite_catalog(suite, tests)
        catalog["ok"] = collection_ok
        self.server.catalog_cache[suite] = json.dumps(catalog, ensure_ascii=False).encode()
        return catalog

    def _launch(self, suite: str, *, node: str = "", live: bool = False, live_step: str = "",
                case_id: str = "") -> str:
        if self.server.pending_launch:
            raise RuntimeError("ya hay una ejecución arrancando")
        port = int(self.server.server_address[1])
        command = [sys.executable, "-m", "tests", "run", suite, "--no-open", "--port", str(port)]
        if node:
            command.extend(["--node", node])
        if live:
            command.append("--live")
        if live_step:
            command.extend(["--live-step", live_step])
        if case_id:
            command.extend(["--case", case_id])
        self.server.pending_launch = (command, self.server.run_dir / "ui-launches.log")
        self.server.stop_requested = True
        return f"http://127.0.0.1:{port}"

    def _events(self) -> None:
        self._headers("text/event-stream; charset=utf-8")
        path = self.server.run_dir / "events.jsonl"
        position = 0
        heartbeat = time.monotonic()
        try:
            while True:
                if path.exists():
                    with path.open("rb") as stream:
                        stream.seek(position)
                        while line := stream.readline():
                            position = stream.tell()
                            self.wfile.write(b"data: " + line.rstrip(b"\n") + b"\n\n")
                            self.wfile.flush()
                if time.monotonic() - heartbeat > 12:
                    self.wfile.write(b": heartbeat\n\n")
                    self.wfile.flush()
                    heartbeat = time.monotonic()
                    self.server.last_access = heartbeat
                time.sleep(0.15)
        except (BrokenPipeError, ConnectionResetError):
            return


def serve(run_dir: Path, port: int, idle_timeout: int) -> None:
    server = DashboardServer(("127.0.0.1", port), Handler, run_dir.resolve(), idle_timeout)
    actual = server.server_address[1]
    (run_dir / "dashboard.json").write_text(
        json.dumps({"url": f"http://127.0.0.1:{actual}", "port": actual, "pid": os.getpid()}), encoding="utf-8"
    )
    server.timeout = 1
    while not server.stop_requested and time.monotonic() - server.last_access < idle_timeout:
        server.handle_request()
    server.server_close()
    if server.pending_launch:
        command, log_path = server.pending_launch
        log = log_path.open("ab")
        env = os.environ.copy()
        env.setdefault("ZAELAR_TEST_ACTOR", "dashboard-ui")
        subprocess.Popen(
            command, cwd=ENGINE, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
            start_new_session=True, close_fds=True, env=env,
        )
        log.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Zaelar test dashboard server")
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--idle-timeout", type=int, default=1800)
    args = parser.parse_args()
    serve(args.run_dir, args.port, args.idle_timeout)


if __name__ == "__main__":
    main()
