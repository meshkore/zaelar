"""search/public_fetch.py — ONE guarded GET for a URL that came from the open web (V2-840 H4).

A row's `url` and a worker's `image` are written by whoever read a page, so fetching them from the engine is a
request the engine makes on behalf of a stranger. The guard is the consequence bound, never a list of sites:

  · **public hosts only** — every address the name resolves to must be globally routable (no loopback, private,
    link-local, carrier-grade NAT, multicast or reserved range); one non-public answer refuses the whole name;
  · **the connection goes to the address that was checked** — the request is sent to that IP with the original
    `Host` header and TLS server name, so a second DNS answer (rebinding) cannot swap the target after the check;
  · **redirects are followed by hand**, each hop through the same check, at most `MAX_REDIRECTS`;
  · **bounded** — a timeout per request and a byte cap read off the stream, so a huge body is cut, not buffered;
  · **declared type** — the caller says which content types it accepts; anything else is refused before the body.

`get()` returns a `Fetched` or raises `Refused(reason)` with a short stable slug the caller logs and counts.
`resolve` and `transport` are seams for tests: no test touches the network.
"""
from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit, urlunsplit

MAX_REDIRECTS = 4
_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")


class Refused(Exception):
    """A fetch that did not happen or was cut, with `reason` — a slug, never a header value or a body."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


@dataclass
class Fetched:
    url: str              # the final URL, after redirects
    content_type: str     # the declared media type, lowercased, without parameters
    body: bytes


def _system_resolve(host: str, port: int) -> list[str]:
    return sorted({ai[4][0] for ai in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)})


def public_address(host: str, port: int, resolve=_system_resolve) -> str:
    """The address to connect to for `host`, or `Refused` when the name is not public. A literal IP is judged
    as itself; a name is judged by EVERY answer, so a name that also points inside the network is refused."""
    try:
        addrs = [str(ipaddress.ip_address(host))]
    except ValueError:                                   # a name, not a literal: every answer is judged
        try:
            addrs = resolve(host, port)
        except Exception:  # noqa: BLE001 — an unresolvable name is a refusal, not a crash
            raise Refused("dns") from None
    if not addrs:
        raise Refused("dns")
    for a in addrs:
        ip = ipaddress.ip_address(a.split("%", 1)[0])
        if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
            ip = ip.ipv4_mapped
        if not ip.is_global or ip.is_multicast:
            raise Refused("non_public_address")
    return addrs[0]


def _pinned(url: str, resolve) -> tuple[str, dict, dict]:
    """(the URL with its host replaced by the checked address, headers, request extensions)."""
    p = urlsplit(url)
    if p.scheme not in ("http", "https") or not p.hostname:
        raise Refused("scheme")
    if p.username or p.password:
        raise Refused("credentials_in_url")
    port = p.port or (443 if p.scheme == "https" else 80)
    addr = public_address(p.hostname, port, resolve)
    netloc = (f"[{addr}]" if ":" in addr else addr) + (f":{p.port}" if p.port else "")
    host_header = p.hostname + (f":{p.port}" if p.port else "")
    ext = {"sni_hostname": p.hostname} if p.scheme == "https" else {}
    return urlunsplit((p.scheme, netloc, p.path or "/", p.query, "")), {"Host": host_header}, ext


def get(url: str, *, accept: tuple[str, ...], max_bytes: int, timeout: float = 8.0, truncate: bool = False,
        resolve=_system_resolve, transport=None) -> Fetched:
    """GET `url` under the guard above. `accept` = media types (exact, or a prefix ending in `/`). `truncate` keeps
    the first `max_bytes` of a longer body (a page's head is enough to read its declared cover) instead of refusing."""
    import httpx
    current = str(url or "").strip()
    with httpx.Client(timeout=timeout, follow_redirects=False, transport=transport,
                      headers={"User-Agent": _UA, "Accept": ",".join(accept) + ",*/*;q=0.1"}) as client:
        for _hop in range(MAX_REDIRECTS + 1):
            target, headers, ext = _pinned(current, resolve)
            req = client.build_request("GET", target, headers=headers, extensions=ext)
            try:
                resp = client.send(req, stream=True)
            except httpx.TimeoutException:
                raise Refused("timeout") from None
            except httpx.HTTPError:
                raise Refused("network") from None
            try:
                if resp.status_code in (301, 302, 303, 307, 308):
                    loc = resp.headers.get("location") or ""
                    if not loc:
                        raise Refused("redirect_without_location")
                    current = urljoin(current, loc)
                    continue
                if resp.status_code != 200:
                    raise Refused(f"http_{resp.status_code}")
                ctype = (resp.headers.get("content-type") or "").split(";", 1)[0].strip().lower()
                if not any(ctype == a or (a.endswith("/") and ctype.startswith(a)) for a in accept):
                    raise Refused("content_type")
                declared = resp.headers.get("content-length") or ""
                if not truncate and declared.isdigit() and int(declared) > max_bytes:
                    raise Refused("too_large")
                body = bytearray()
                try:
                    for chunk in resp.iter_bytes():
                        body.extend(chunk)
                        if len(body) > max_bytes:
                            if truncate:
                                del body[max_bytes:]
                                break
                            raise Refused("too_large")
                except httpx.TimeoutException:
                    raise Refused("timeout") from None
                except httpx.HTTPError:
                    raise Refused("network") from None
                return Fetched(url=current, content_type=ctype, body=bytes(body))
            finally:
                resp.close()
    raise Refused("too_many_redirects")
