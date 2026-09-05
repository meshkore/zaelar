"""Whether an HTTP request may be served at all — a PURE decision over headers.

WHY LOOPBACK IS NOT A BOUNDARY. Binding 127.0.0.1 keeps the daemon off the network, and that is where the
reasoning usually stops. It should not: 127.0.0.1 is reachable by every other process on the machine AND by any
web page the user has open, because a browser will happily `fetch('http://127.0.0.1:45817/files/read')` from any
site in the world. A daemon that serves the user's documents to whoever asks first is a worse hole than the one
it was built to close.

FIVE GUARDS, none of them trusted alone, in this order:

  1. THE PEER IS LOOPBACK. Belt to the bind's braces. If the bind address is ever widened by accident — an env
     var, a well-meaning "make it reachable from my phone" patch — this is what still refuses the LAN.

  2. NOTHING THAT SMELLS OF A BROWSER. Any request carrying `Origin` or `Sec-Fetch-Site` is refused outright.
     Browsers attach those; a server-side client never does. This holds EVEN IF the token leaked into a page,
     which is what makes the browser vector structurally impossible rather than merely unlikely.

  3. THE HOST HEADER NAMES A LOOPBACK ADDRESS. Guard 2 has a hole and it is not hypothetical: a page on
     `evil.example` whose DNS is re-pointed at 127.0.0.1 makes a SAME-ORIGIN request, and a same-origin request
     carries NO `Origin` header at all. Modern browsers still send `Sec-Fetch-Site: same-origin`, so guard 2
     usually catches it — but "usually" is one header away from nothing, and the engine has already paid for
     this exact class once (the rebind-residual GET against the cluster control plane). What betrays the
     rebind is `Host`: the browser still names the site it THINKS it is on. Exact match, never a suffix — a
     `startswith` check on "127.0.0.1" is satisfied by `127.0.0.1.evil.example`.

  4. A BODY MUST BE JSON. A browser can send `text/plain`, `application/x-www-form-urlencoded` or
     `multipart/form-data` cross-origin with NO preflight — those are "simple requests". Requiring
     `application/json` means the browser must preflight, and the preflight never succeeds (guard 5). This one
     closes the vector on its own, independently of Origin and Sec-Fetch, which is why it is worth its lines.

  5. THE BEARER TOKEN, compared in constant time. 32 bytes of urandom is not guessable; the constant-time
     compare is there because a timing oracle on a loopback socket is a real one, and because the day this
     grows a shorter token nobody will remember to add it.

EVERY REFUSAL LOOKS THE SAME FROM OUTSIDE and different from inside. The caller always gets one `unauthorized`
with one message — telling an attacker WHICH guard fired is a free map of the defences — while the `Verdict`
carries the precise reason for the audit log, which is where somebody who is allowed to know can read it.
"""
from __future__ import annotations

import hmac
from typing import NamedTuple

# Exactly the names a loopback request can legitimately carry. `local.zaelar.com` is in the engine's list
# because a real DNS A record pins it to 127.0.0.1; the daemon is never addressed that way, so it is not here —
# the shortest correct list is the one that ages best.
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1", "[::1]"})

# Content types a JSON body may legitimately arrive with. Anything else is either a simple request (guard 4's
# whole reason) or a caller that is confused about what this API speaks.
_JSON_TYPES = ("application/json",)


class Verdict(NamedTuple):
    """`ok` decides. `reason` is for the audit log and NEVER for the response body."""

    ok: bool
    reason: str = ""

    def __bool__(self) -> bool:      # so call sites can read `if not admit(...)`
        return self.ok


ALLOWED = Verdict(True)


def is_loopback(peer_ip: str) -> bool:
    """IPv4 loopback is a whole /8, not just 127.0.0.1 — and `::ffff:127.0.0.1` is how a dual-stack socket
    reports an IPv4 peer. Both are this machine."""
    ip = (peer_ip or "").strip().lower()
    if ip.startswith("::ffff:"):
        ip = ip[len("::ffff:"):]
    if ip in {"::1", "0:0:0:0:0:0:0:1"}:
        return True
    parts = ip.split(".")
    if len(parts) == 4 and parts[0] == "127":
        return all(p.isdigit() and 0 <= int(p) <= 255 for p in parts)
    return False


def host_is_loopback(host_header: str, port: int) -> bool:
    """The Host header must name a loopback address AND this daemon's port.

    Splitting on the LAST colon is what makes `[::1]:45817` work: an IPv6 literal is full of them."""
    raw = (host_header or "").strip()
    if not raw:
        # HTTP/1.1 requires a Host header. A request without one is not a browser and not a well-formed client;
        # refusing it costs nothing and removes a way to skip this guard entirely.
        return False
    name, sep, port_text = raw.rpartition(":")
    if not sep or (raw.endswith("]") and not name.endswith("]")):
        # No port given (or the colon belonged to an unbracketed IPv6 literal): a bare hostname.
        name, port_text = raw, ""
    if port_text and port_text != str(port):
        return False
    return name.strip().lower() in _LOOPBACK_HOSTS


def _looks_like_a_browser(headers) -> str:
    """Guard 2. Returns the offending header name, or "" if this does not look like a browser."""
    for header in ("Origin", "Sec-Fetch-Site", "Sec-Fetch-Mode", "Referer"):
        if headers.get(header):
            return header
    return ""


def _body_type_ok(headers) -> bool:
    """Guard 4. Only meaningful when there IS a body; an empty POST carries no content type and needs none."""
    declared = (headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
    return declared in _JSON_TYPES


def admit(*, method: str, path: str, headers, peer_ip: str, port: int,
          expected_token: str, public_paths: frozenset[str], has_body: bool) -> Verdict:
    """The whole admission decision, in the order the module docstring explains.

    `headers` is anything with a `.get(name)` that is case-insensitive — `http.client.HTTPMessage` is, and so is
    a plain dict in a test if the test spells the names as they arrive on the wire."""
    if not is_loopback(peer_ip):
        return Verdict(False, f"off_machine:{peer_ip}")

    browser_header = _looks_like_a_browser(headers)
    if browser_header:
        return Verdict(False, f"browser:{browser_header.lower()}")

    if not host_is_loopback(headers.get("Host") or "", port):
        # The rebind signature: a real client on this machine has no reason to name anything else.
        return Verdict(False, f"bad_host:{(headers.get('Host') or '(absent)')[:64]}")

    if has_body and not _body_type_ok(headers):
        return Verdict(False, "bad_content_type")

    if path in public_paths:
        return ALLOWED

    auth = (headers.get("Authorization") or "").strip()
    if not expected_token:
        # No token on disk means the daemon could not read its own config. Serving files in that state would be
        # serving them with no authentication at all, so it refuses instead.
        return Verdict(False, "no_local_token")
    if not auth.lower().startswith("bearer "):
        return Verdict(False, "no_token")
    if not hmac.compare_digest(auth[7:].strip(), expected_token):
        return Verdict(False, "bad_token")
    return ALLOWED
