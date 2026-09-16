"""Dependency-free local dashboard server for EVERY durable test run at once.

It used to serve exactly one run, handed to it at startup, and starting a second run performed a
«controlled handoff»: the CLI stopped the previous server and started a new one on the same port. That
was coherent while a human launched one battery at a time, and wrong for how this repo actually works —
the agents run the tests, several of them at once, and the second agent's run silently erased the first
agent's from the operator's screen (his ask, 2026-09-16: «qué pasa si dos agentes están ejecutando tests
a la vez […] uno ha podido modificar la API y el otro el sistema de voz»).

So the server is bound to the RUNS ROOT, not to a run:

  · `/api/runs`   — every run that is alive right now, plus the last finished ones.
  · `/events`     — MULTIPLEXED: every active run's events, each line tagged with its `run_id`, and
                    runs that appear mid-stream are picked up without reconnecting.
  · `/events?run=<id>` — one run, for replaying a finished one.

Nothing launches tests from here any more. The Observatory is a window: what tests exist, how they went
last time, and what an agent is doing right now. Asking for a run is asking an agent.
"""
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


#: How many run directories the scanner ever looks at. Run ids are timestamp-prefixed, so the newest
#: are last alphabetically — and there are ~600 of them on this machine. Tailing every one of them
#: several times a second is how a monitor becomes the reason the machine is slow.
SCAN_DEPTH = 60
#: A run whose `run.json` still says "running" but whose events stopped this long ago is treated as
#: abandoned (the agent was killed, the laptop slept). It stays LISTED — with `stale: true` — because a
#: run that vanishes silently is exactly what this rewrite exists to stop.
STALE_AFTER_S = 180.0


class DashboardServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, handler, runs_root: Path, idle_timeout: int) -> None:
        super().__init__(address, handler)
        self.runs_root = runs_root
        self.idle_timeout = idle_timeout
        self.last_access = time.monotonic()
        self.catalog_cache: dict[str, bytes] = {}
        self.stop_requested = False

    def run_dirs(self) -> list[Path]:
        """The newest `SCAN_DEPTH` run directories, newest first."""
        try:
            entries = sorted((e for e in os.scandir(self.runs_root) if e.is_dir()),
                             key=lambda e: e.name, reverse=True)
        except OSError:
            return []
        return [Path(e.path) for e in entries[:SCAN_DEPTH]]

    def run_meta(self, run_dir: Path) -> dict | None:
        try:
            meta = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        meta["run_id"] = meta.get("run_id") or run_dir.name
        events = run_dir / "events.jsonl"
        try:
            meta["last_event_at"] = events.stat().st_mtime
        except OSError:
            meta["last_event_at"] = meta.get("created_at", 0)
        if meta.get("status") == "running":
            meta["stale"] = (time.time() - float(meta["last_event_at"] or 0)) > STALE_AFTER_S
        return meta

    def focused_run(self) -> Path | None:
        """The run `/api/meta` describes when nobody asked for one: the newest ACTIVE run, or simply
        the newest. Kept so an old tab and `replay` keep working."""
        runs = self.run_dirs()
        for run_dir in runs:
            meta = self.run_meta(run_dir)
            if meta and meta.get("status") == "running" and not meta.get("stale"):
                return run_dir
        return runs[0] if runs else None


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
            focused = self.server.focused_run()
            meta = (self.server.run_meta(focused) if focused else None) or {}
            payload = json.dumps(meta, ensure_ascii=False).encode()
            self._headers("application/json", len(payload))
            self.wfile.write(payload)
            return
        if self.path == "/api/runs":
            self._runs()
            return
        if self.path == "/events" or self.path.startswith("/events?"):
            self._events()
            return
        if self.path == "/api/families":
            self._families()
            return
        if self.path.startswith("/api/catalog/"):
            self._catalog(self.path.removeprefix("/api/catalog/"))
            return
        if self.path == "/api/usecases/scoreboard":
            # The functionality scoreboard (tests/use_cases/status.json, written by every e2e agent run),
            # enriched with the LAUNCH PHASE of each case (phases.py, operator-owned boundary). Served live
            # so the Observatory shows WHAT THE PRODUCT CAN DO — and how much of the v1 promise is green —
            # next to the code-integrity suites (operator ask, 2026-08-29).
            import json as _json
            sb = HERE.parent / "use_cases" / "status.json"
            data = {}
            try:
                data = _json.loads(sb.read_text(encoding="utf-8")) if sb.exists() else {}
                from tests.use_cases.e2e.agent import phases as _ph
                fases = {1: {"pass": 0, "total": 0, "parked": 0}, 2: {"pass": 0, "total": 0, "parked": 0}}
                for sid, row in (data.get("scenarios") or {}).items():
                    f = _ph.phase_of(sid)
                    row["phase"] = f
                    row["parked"] = _ph.parked_reason(sid)
                    if row["parked"]:
                        # Parked for an environmental wall: visible, but outside the gauge's denominator
                        # so the launch reading is not held down by a wall of the outside world.
                        fases[f]["parked"] += 1
                        continue
                    fases[f]["total"] += 1
                    if row.get("state") == "PASS":
                        fases[f]["pass"] += 1
                data["phases"] = {str(k): v for k, v in fases.items()}
            except Exception:  # noqa: BLE001 — an unreadable boundary must not blank the scoreboard
                pass
            payload = _json.dumps(data, ensure_ascii=False).encode("utf-8")
            self._headers("application/json", len(payload))
            self.wfile.write(payload)
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        """The only POST left is the shutdown the CLI uses to hand the port over.

        There WAS a `/api/run` here, and the dashboard had a ▶ on every suite. Both are gone by the
        operator's call (2026-09-16): «no necesitamos que haya un play en el frontend que testee nada
        […] siempre va a ser un agente el que los conduzca». A launch button on a spectator surface is a
        second way to start a run that nobody is watching the exit code of — and it competed with the
        agent that was already testing. Asking for a run is asking an agent.
        """
        self.server.last_access = time.monotonic()
        expected_origin = f"http://127.0.0.1:{self.server.server_address[1]}"
        origin = self.headers.get("Origin", "")
        if origin and origin != expected_origin:
            self.send_error(HTTPStatus.FORBIDDEN, "invalid origin")
            return
        if self.path != "/api/shutdown":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        raw = b'{"ok":true}'
        self._headers("application/json", len(raw))
        self.wfile.write(raw)
        self.server.stop_requested = True

    def _runs(self) -> None:
        """Who is testing right now — one row per run, active ones first.

        This is what feeds the box at the bottom of the rail. `launched_by.actor` is the agent's own
        name when it set `ZAELAR_TEST_ACTOR` (tests/README.md asks every agent to); otherwise the row
        falls back to user/host/branch/parent-process, which is worse but never empty.
        """
        rows = []
        for run_dir in self.server.run_dirs():
            meta = self.server.run_meta(run_dir)
            if not meta:
                continue
            rows.append({
                "run_id": meta["run_id"], "suite": meta.get("suite", ""),
                "status": meta.get("status", ""), "stale": bool(meta.get("stale")),
                "target": meta.get("target", ""), "launched_by": meta.get("launched_by", {}),
                "created_at": meta.get("created_at", 0), "finished_at": meta.get("finished_at", 0),
                "last_event_at": meta.get("last_event_at", 0),
                "tests": meta.get("tests", 0), "passed": meta.get("passed", 0),
                "failed": meta.get("failed", 0), "exit_code": meta.get("exit_code"),
            })
        live = [r for r in rows if r["status"] == "running" and not r["stale"]]
        rest = [r for r in rows if r not in live]
        payload = json.dumps({"schema": 1, "now": time.time(),
                              "runs": live + rest[:20]}, ensure_ascii=False).encode()
        self._headers("application/json", len(payload))
        self.wfile.write(payload)

    def _families(self) -> None:
        """The Observatory's spine: two locales × three families, with the real per-locale case count.

        Counted from the CATALOG, never from a hand-kept number, and served even when a locale has
        nothing in it — a family that reads `0 casos` is information; a family hidden because its
        locale is empty is a lie by omission (tests/platform/families.py).

        Deliberately cheap: it counts the rich catalog providers (use cases, journey, memory corpora)
        and reports the deterministic families by their FILE count, which `suite_rows()` already knows
        without a pytest collection. A family table must never be the thing that makes the dashboard
        take two minutes to paint.
        """
        from tests.platform import families as fam
        from tests.platform.catalog import SUITES, build_suite_catalog, suite_rows
        counts: dict[str, dict[str, int]] = {entry.id: {} for entry in fam.FAMILIES}
        files = {row["id"]: row["deterministic_files"] for row in suite_rows()}
        for entry in fam.FAMILIES:
            for locale in fam.LOCALE_IDS:
                total = 0
                for suite_id in entry.members:
                    if suite_id not in SUITES:
                        continue
                    if entry.kind == "deterministic":
                        total += int(files.get(suite_id, 0))
                        continue
                    try:
                        catalog = build_suite_catalog(suite_id, [])
                    except Exception:  # noqa: BLE001 — one broken provider must not blank the spine
                        continue
                    for step in catalog.get("steps", ()):
                        for group in step.get("case_groups", ()):
                            total += sum(1 for case in group.get("cases", ())
                                         if fam.belongs_to(case, locale))
                counts[entry.id][locale] = total
        # The use-case THEMES with a real per-locale count, so the rail can say «Búsquedas y estudios ·
        # 36» in ES and «· 14» in US instead of listing twenty `search-buy-*` rows one by one. A theme
        # with nothing in this locale is kept and shown dimmed: an empty group is a visible gap in that
        # market's set, which is information, and hiding it would make the two sets look equivalent.
        theme_rows: list[dict] = []
        try:
            from tests.use_cases import themes as th
            from tests.use_cases.cases_data import CASES as UC
            for theme in th.THEMES:
                by_locale = {loc: sum(1 for c in UC if c.locale == loc and th.theme_of(c.id) == theme["id"])
                             for loc in fam.LOCALE_IDS}
                if not sum(by_locale.values()) and theme["id"] == "otros":
                    continue
                theme_rows.append({**theme, "byLocale": by_locale})
        except Exception:  # noqa: BLE001 — the spine must paint even if the use-case catalog is broken
            theme_rows = []
        payload = {
            "schema": 1,
            "locales": list(fam.LOCALES),
            "default_locale": fam.DEFAULT_LOCALE,
            "themes": theme_rows,
            "families": fam.rows(counts),
            # `primary_case` travels with the suite so the ▶ button does not have to carry a hardcoded
            # map of "which case IS this suite" in the HTML. It used to (`'memory':'memory::group::1.4::v4'`),
            # and a dashboard rewrite silently turned Memoria's ▶ from «the conversational gateway» into
            # «every deterministic memory test» — a launch button that quietly means something else.
            "suites": {suite.id: {"label": suite.label, "description": suite.description,
                                  "primary_case": suite.primary_case}
                       for suite in SUITES.values()},
        }
        raw = json.dumps(payload, ensure_ascii=False).encode()
        self._headers("application/json", len(raw))
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

    def _events(self) -> None:
        """Every live run's events, on one stream, each line tagged with the run it came from.

        Three things this has to get right, and the first two are why it is not just `tail -f`:

        1 · **A run that starts while you are watching must appear.** The directory is rescanned every
            `RESCAN_S`, capped at `SCAN_DEPTH` entries, so a run that did not exist when the browser
            connected joins the stream without a reconnect.
        2 · **Backlog vs live.** A run that is already FINISHED is replayed from byte 0 — you asked to
            look at it, you want all of it. A run that is ALIVE when it joins mid-stream is replayed
            from the start too, because its plan and its discovery events are at the top of the file
            and the checklist is unreadable without them.
        3 · **Bounded work.** `?run=<id>` narrows to one run, and without it only ACTIVE runs are
            followed — nobody needs 600 finished runs tailed at 6 Hz.

        Two synthetic control events ride the same stream so the client never has to poll to notice:
        `observatory.run_seen` when a run joins, `observatory.run_gone` when it stops being active.
        """
        from urllib.parse import parse_qs, urlparse

        wanted = (parse_qs(urlparse(self.path).query).get("run") or [""])[0].strip()
        self._headers("text/event-stream; charset=utf-8")
        positions: dict[str, int] = {}
        seen: set[str] = set()
        last_scan = 0.0
        heartbeat = time.monotonic()
        RESCAN_S = 1.5
        try:
            while True:
                now = time.monotonic()
                if now - last_scan >= RESCAN_S:
                    last_scan = now
                    tracked = self._followable(wanted)
                    for run_id in list(seen):
                        if run_id not in tracked:
                            seen.discard(run_id)
                            self._send({"type": "observatory.run_gone", "run_id": run_id,
                                        "ts": time.time()})
                else:
                    tracked = {rid: path for rid, path in
                               ((rid, self.server.runs_root / rid) for rid in seen)}
                for run_id, run_dir in tracked.items():
                    if run_id not in seen:
                        seen.add(run_id)
                        positions.setdefault(run_id, 0)
                        meta = self.server.run_meta(run_dir) or {}
                        self._send({"type": "observatory.run_seen", "run_id": run_id,
                                    "ts": time.time(), "meta": meta})
                    positions[run_id] = self._drain(run_dir, run_id, positions.get(run_id, 0))
                if time.monotonic() - heartbeat > 12:
                    self._send_raw(b": heartbeat\n\n")
                    heartbeat = time.monotonic()
                    self.server.last_access = heartbeat
                time.sleep(0.15)
        except (BrokenPipeError, ConnectionResetError):
            return

    def _followable(self, wanted: str) -> dict[str, Path]:
        """Which runs this stream follows: the one asked for, or every ACTIVE one."""
        if wanted:
            run_dir = (self.server.runs_root / wanted).resolve()
            # A run id is a directory name, never a path — `..` must not walk out of the runs root.
            if run_dir.parent != self.server.runs_root.resolve() or not run_dir.is_dir():
                return {}
            return {wanted: run_dir}
        out: dict[str, Path] = {}
        for run_dir in self.server.run_dirs():
            meta = self.server.run_meta(run_dir)
            if meta and meta.get("status") == "running" and not meta.get("stale"):
                out[meta["run_id"]] = run_dir
        return out

    def _drain(self, run_dir: Path, run_id: str, position: int) -> int:
        """Emit whatever is new in one run's log, tagging each line with its run."""
        path = run_dir / "events.jsonl"
        if not path.exists():
            return position
        try:
            with path.open("rb") as stream:
                stream.seek(position)
                while line := stream.readline():
                    if not line.endswith(b"\n"):
                        break            # a half-written line: come back for it next tick
                    position = stream.tell()
                    body = line.rstrip(b"\n")
                    # The tag goes in without parsing the JSON: these lines arrive by the thousand and
                    # a round-trip through `json.loads`/`dumps` per line is pure waste.
                    if body.startswith(b"{"):
                        body = b'{"run_id":' + json.dumps(run_id).encode() + b"," + body[1:]
                    self._send_raw(b"data: " + body + b"\n\n")
        except OSError:
            return position
        return position

    def _send(self, payload: dict) -> None:
        self._send_raw(b"data: " + json.dumps(payload, ensure_ascii=False).encode() + b"\n\n")

    def _send_raw(self, raw: bytes) -> None:
        self.wfile.write(raw)
        self.wfile.flush()


def serve(runs_root: Path, port: int, idle_timeout: int) -> None:
    runs_root = runs_root.resolve()
    runs_root.mkdir(parents=True, exist_ok=True)
    server = DashboardServer(("127.0.0.1", port), Handler, runs_root, idle_timeout)
    actual = server.server_address[1]
    (runs_root / "dashboard.json").write_text(
        json.dumps({"url": f"http://127.0.0.1:{actual}", "port": actual, "pid": os.getpid()}),
        encoding="utf-8")
    server.timeout = 1
    while not server.stop_requested and time.monotonic() - server.last_access < idle_timeout:
        server.handle_request()
    server.server_close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Zaelar test dashboard server")
    parser.add_argument("--runs-root", type=Path, default=ENGINE / "tests" / "runs")
    # Accepted so an older CLI keeps working: it used to name ONE run, and its parent is the root.
    parser.add_argument("--run-dir", type=Path, default=None)
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--idle-timeout", type=int, default=1800)
    args = parser.parse_args()
    root = args.runs_root if args.run_dir is None else args.run_dir.resolve().parent
    serve(root, args.port, args.idle_timeout)


if __name__ == "__main__":
    main()
