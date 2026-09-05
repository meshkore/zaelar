"""The HTTP plumbing: read a request, decide whether to serve it, write a JSON answer.

WHAT LIVES HERE AND WHAT DOES NOT. This module knows about sockets, headers and status codes. It knows nothing
about files, folders or permissions — it calls into `daemon.security.guards` for the admission decision and into
the route table for the work, and its only opinion of its own is that every answer is JSON and every refusal
looks the same from outside.

THAT SAMENESS IS DELIBERATE. A caller that is refused always gets one `unauthorized` with one message, whichever
of the five guards fired. Telling an attacker which one they tripped is a free map of the defences: it turns
"try things until something works" into "read the error and adapt". The precise reason goes to the audit log
instead, which is where somebody entitled to know can read it.

EVERY REFUSAL IS AUDITED, INCLUDING THE UNAUTHORIZED ONES — and that used to be the gap. The old shape returned
401 before it recorded anything, so the single most security-relevant signal there is (a run of failed attempts,
or a page that keeps trying) left no trace at all, in a log whose own docstring says refusals are the half that
earns the file. They are recorded now, and collapsed by `daemon.security.throttle` so a flood cannot push the
interesting line off the end of a rotated log.
"""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler

from .. import VERSION, audit, config
from ..fs.refusal import Refusal
from ..security import guards, throttle

# Routes reachable without the token. `/health` says only that a daemon is running and what version it is —
# nothing about the user, their folders or their files — so the engine can poll it to paint the status icon
# before it has read the token, and the wizard can tell "not installed" from "installed, not paired". It is
# still refused to a browser: a page must not be able to fingerprint that a Zaelar daemon is here.
PUBLIC_PATHS = frozenset({"/health"})

# One request may not declare a body larger than this. The number is generous for JSON and small enough that a
# thousand concurrent liars cannot make the daemon the reason the machine is out of memory.
MAX_BODY_BYTES = 1_000_000

# A connection that goes quiet is dropped rather than held. Without this, anything on the machine can open
# sockets, send one byte each and never finish — every thread waits forever and the daemon stops answering the
# engine, with no error anywhere.
REQUEST_TIMEOUT_S = 20.0

# An over-sized body is refused, and refusing it politely means READING it first. A server that answers and
# closes while the client is still writing produces a TCP reset, and the client never gets to read the answer:
# the caller sees "connection reset by peer" instead of "your request was too large", which is the difference
# between a bug they can fix and a bug they report. Discarded in chunks, so the politeness costs one buffer and
# not the body. Past this ceiling nothing is drained — a caller sending sixteen megabytes to a daemon that
# declared a one-megabyte limit is not owed a graceful conversation.
DRAIN_CEILING_BYTES = 16 * MAX_BODY_BYTES
DRAIN_CHUNK = 64 * 1024

_UNAUTHORIZED = {
    "ok": False,
    "error": "unauthorized",
    "message": "This daemon only answers the Zaelar engine on this machine.",
}


def operation_of(path: str) -> str:
    """`/files/read` → `files.read`. The audit log's vocabulary is the route's, so a new route is a new
    operation name without anybody having to remember to add one."""
    return path.strip("/").replace("/", ".") or "root"


class Handler(BaseHTTPRequestHandler):
    server_version = "zaelar-daemon/" + VERSION
    sys_version = ""                       # do not advertise the Python version to anything that connects
    protocol_version = "HTTP/1.0"          # no keep-alive: one request, one connection, no thread held open
    timeout = REQUEST_TIMEOUT_S

    # Set by the server that builds this handler, so the Host guard can check the port it is really serving.
    bound_port: int = 0
    routes: dict = {}

    # ── plumbing ──────────────────────────────────────────────────────────────────────────────────────────

    def log_message(self, fmt: str, *args) -> None:      # noqa: A003 — BaseHTTPRequestHandler's name
        """Silence the default stderr access log. Operations are recorded in `daemon.audit`, which logs the
        thing that matters (which path, allowed or refused) instead of a request line."""
        return

    def _send(self, code: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        try:
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            # Never a CORS header — their absence is a guard, not an oversight.
            self.send_header("X-Content-Type-Options", "nosniff")
            # The body can be the contents of the user's file. Nothing between here and the engine may keep a
            # copy, and there IS something between them the day a proxy or a debugging tool is in the path.
            self.send_header("Cache-Control", "no-store")
            self.send_header("Referrer-Policy", "no-referrer")
            self.end_headers()
            self.wfile.write(body)
        except Exception:       # noqa: BLE001 — client hung up mid-write
            pass

    def _declared_body_length(self) -> int:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return -1
        return length

    def _drain(self, length: int) -> None:
        """Read and discard a body we are not going to use, so the answer can be delivered before the socket
        closes. Bounded twice: by the ceiling, and by the socket timeout that is already on this connection."""
        remaining = min(length, DRAIN_CEILING_BYTES)
        try:
            while remaining > 0:
                chunk = self.rfile.read(min(DRAIN_CHUNK, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
        except Exception:       # noqa: BLE001 — the peer gave up mid-write, which is its right
            pass

    def _read_body(self, length: int) -> dict:
        if length <= 0 or length > MAX_BODY_BYTES:
            return {}
        try:
            parsed = json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception:       # noqa: BLE001 — malformed body is an empty body; handlers refuse by argument
            return {}
        return parsed if isinstance(parsed, dict) else {}

    def _caller(self) -> str:
        """Who is asking. Only `local` exists today; the relay will mark its own traffic so the audit log can
        tell the user's own engine from a cloud agent reaching in — the distinction they care about most, since
        only one of those is on their machine."""
        return "relay" if self.headers.get("X-Zaelar-Relay") else "local"

    # ── routing ───────────────────────────────────────────────────────────────────────────────────────────

    def do_OPTIONS(self) -> None:       # noqa: N802 — the framework's naming
        self._send(405, {"ok": False, "error": "no_cors",
                         "message": "This daemon is not reachable from a browser."})

    def do_GET(self) -> None:           # noqa: N802
        self._dispatch("GET")

    def do_POST(self) -> None:          # noqa: N802
        self._dispatch("POST")

    def _refuse(self, reason: str, path: str) -> None:
        """One shape of refusal for the caller, the precise reason for the log, and a delay that makes a flood
        cost the sender more than it costs us."""
        should_record, delay, suppressed = throttle.SHARED.note(reason)
        if should_record:
            detail = {"reason": reason}
            if suppressed:
                detail["also_suppressed"] = suppressed
            audit.record(operation_of(path), caller=self._caller(), outcome="refused",
                         reason=reason.split(":", 1)[0], detail=detail)
        if delay:
            import time
            time.sleep(delay)
        self._send(401, _UNAUTHORIZED)

    def _dispatch(self, method: str) -> None:
        path = self.path.split("?", 1)[0]
        declared = self._declared_body_length()
        if declared > MAX_BODY_BYTES:
            self._drain(declared)
            self._send(413, {"ok": False, "error": "too_large",
                             "message": f"That request is larger than the {MAX_BODY_BYTES} byte limit."})
            return

        verdict = guards.admit(
            method=method,
            path=path,
            headers=self.headers,
            peer_ip=self.client_address[0] if self.client_address else "",
            port=self.bound_port,
            expected_token=config.token(),
            public_paths=PUBLIC_PATHS,
            has_body=declared > 0,
        )
        if not verdict.ok:
            # Drain first, for the same reason the 413 does: answering while the peer is still writing resets
            # the connection, and the caller sees a transport error instead of the refusal we took the trouble
            # to phrase. Bounded by the size check just above.
            self._drain(declared)
            self._refuse(verdict.reason, path)
            return
        throttle.SHARED.note_success()

        caller = self._caller()
        payload: dict = {}
        try:
            payload = self._read_body(declared) if method == "POST" else {}
            handler = self.routes.get((method, path))
            if handler is None:
                self._send(404, {"ok": False, "error": "unknown_route",
                                 "message": f"No route {method} {path}."})
                return
            self._send(200, handler(self, payload))
        except Refusal as r:
            # A refusal is a normal, expected answer with a reason attached — not a server failure. 403 with the
            # boundary named, so the engine can tell the user something true instead of inventing an
            # explanation for a bare status code.
            audit.record(operation_of(path), caller=caller, path=str(payload.get("path") or "") or None,
                         outcome="refused", reason=r.code)
            self._send(403, r.as_dict())
        except Exception as e:  # noqa: BLE001 — anything unexpected is still an answer, never a hung socket
            # The exception TEXT stays out of the response. It routinely contains absolute paths and internal
            # names, and the caller that most wants to read it is the one that should not. It goes to the audit
            # log, where the user can.
            audit.record(operation_of(path), caller=caller, outcome="error",
                         reason=type(e).__name__, detail={"message": str(e)[:400]})
            self._send(500, {"ok": False, "error": "internal",
                             "message": "Something went wrong on my side; the details are in the daemon log."})
