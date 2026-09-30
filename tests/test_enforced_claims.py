#!/usr/bin/env python3
"""test_enforced_claims.py — gates for two claims that were PROSE ONLY.

Both of the claims below are asserted in a document and enforced nowhere. That
is the failure mode this repo keeps re-learning: a sentence in SECURITY.md or
README.md reads like a measured fact, and the measurement does not exist. Every
other bound in the SECURITY.md paragraph that mentions the 4 MiB cap IS gated
(`tests/test_daemon_concurrency.py`, `tests/test_drive_security.py`,
`tests/test_liveness_gaps.py`); this one was the gap in that paragraph. The
registry-name invariant in README.md lines 2-5 is the same shape: the marker is
the thing MCP Registry ownership verification matches against, and nothing
compared it to `server.json` or to what the server actually reports.

NO PTY, NO real child process, NO subprocess of any kind. Part 1 drives the
daemon's real `_read_request` against an in-memory fake socket and then the real
`_serve_forever` accept loop against a real loopback socket with a three-method
fake session (no PtySession is constructed). Part 2 imports `mcp_server`, which
builds a FastMCP object and nothing else. The PTY-probe red line at the top of
CLAUDE.md is not approached.

Run: python -B tests/test_enforced_claims.py
"""
from __future__ import annotations

import json
import re
import socket
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "drive-tui" / "scripts"
sys.path.insert(0, str(SCRIPTS))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
except Exception:
    pass

import tui  # noqa: E402

failures = 0
skipped: list[str] = []


def check(condition: bool, label: str, detail: str = "") -> None:
    global failures
    if not condition:
        failures += 1
    print(f"{'PASS' if condition else 'FAIL'}  {label}" + (f"  {detail}" if detail and not condition else ""))


def skip(label: str, detail: str) -> None:
    """A check that could not run HERE. Never counted as a pass: `skipped` is
    reported separately so a green board cannot hide a gate that never ran."""
    skipped.append(label)
    print(f"SKIP  {label}  {detail}")


# =============================================================================
# 1. The 4 MiB pre-auth request bound (SECURITY.md: "Request size is bounded
#    (4 MiB) so memory exhaustion is covered separately")
#
#    The bound is `tui.MAX_REQ`, enforced in `_read_request` on the per-
#    connection reader thread. Two properties are asserted, and each can turn
#    red on its own:
#      * OVERSIZED is refused. Without the `len(buf) > MAX_REQ` check an
#        unauthenticated peer streams bytes forever into the reader's
#        bytearray — the exact memory-exhaustion primitive the sentence claims
#        is covered "separately".
#      * AT-OR-BELOW is NOT refused. The check is `> MAX_REQ`, not `>=`, so a
#        request of exactly MAX_REQ bytes is legitimate and must parse. An
#        off-by-one in the other direction would silently break large
#        `send_text` calls.
#    The e2e leg then proves the refusal REACHES the peer as the standard error
#    shape and does not wedge the daemon: a ValueError refusal, not a
#    TimeoutError one (both are `bad request: <Type>`, so the error text is what
#    distinguishes "we capped it" from "it was merely slow"), and the next
#    legitimate caller is still served.
# =============================================================================


class _FakeConn:
    """The two socket methods `_read_request` uses: `settimeout` and `recv`.

    Serves a fixed byte string in `chunk`-sized pieces, then EOF. The chunking
    matters: the real loopback peer also arrives in pieces, and a check that
    only fires on a single oversized `recv` would be measuring the fake.
    """

    def __init__(self, payload: bytes, chunk: int = 65536) -> None:
        self._buf = bytearray(payload)
        self._chunk = chunk
        self.recv_calls = 0

    def settimeout(self, _value) -> None:  # the deadline is wall-clock in the test
        return None

    def recv(self, n: int) -> bytes:
        self.recv_calls += 1
        take = min(n, self._chunk, len(self._buf))
        out = bytes(self._buf[:take])
        del self._buf[:take]
        return out


def _request_of_exactly(size: int) -> bytes:
    """A syntactically valid, authenticated request of exactly `size` bytes on
    the wire, newline included. Padding rides in a JSON string field so the
    result parses — a refusal caused by malformed JSON would not be the
    size bound refusing anything."""
    prefix = b'{"token":"t","action":"alive","pad":"'
    suffix = b'"}\n'
    pad = size - len(prefix) - len(suffix)
    if pad < 0:
        raise ValueError(f"size {size} is too small to hold a request")
    return prefix + b"x" * pad + suffix


def test_request_bound_refuses_oversized() -> None:
    # -- the cap is the documented size, checked FIRST ----------------------
    # Not a constant-vs-constant restatement: SECURITY.md's own sentence is the
    # reference, so editing either the doc or the code without the other fails.
    # It runs first because a drifted MAX_REQ makes every leg below allocate
    # megabytes the documentation does not sanction, and that diagnosis belongs
    # ahead of the noise rather than buried under it.
    doc = (ROOT / "SECURITY.md").read_text(encoding="utf-8")
    m = re.search(r"Request size is\s+bounded \((\d+) MiB\)", doc)
    if m is None:
        check(False, "SECURITY.md still states the request bound in MiB",
              "no 'Request size is bounded (N MiB)' sentence found — the claim "
              "this file gates was reworded or removed")
        return
    documented = int(m.group(1)) * 1024 * 1024
    check(tui.MAX_REQ == documented,
          f"the enforced cap is the {m.group(1)} MiB SECURITY.md claims",
          f"SECURITY.md says {documented} bytes, tui.MAX_REQ is {tui.MAX_REQ}")
    if tui.MAX_REQ != documented:
        return

    # -- the streaming vector: no newline, ever, past the cap ---------------
    # This is what the doc sentence is about. It must raise rather than keep
    # buffering, and it must do so on the cap, not on the 2 s read deadline.
    junk = b"A" * (tui.MAX_REQ + 1)
    conn = _FakeConn(junk)
    try:
        tui._read_request(conn)  # type: ignore[arg-type]
        check(False, "a pre-newline stream past MAX_REQ is refused",
              f"no exception: _read_request returned after {conn.recv_calls} recv()s "
              f"and buffered {tui.MAX_REQ + 1} bytes")
    except ValueError as exc:
        check("max size" in str(exc),
              "a pre-newline stream past MAX_REQ is refused by the CAP, not the "
              "read deadline",
              f"raised ValueError({exc!r}) — expected the max-size refusal")
    except TimeoutError as exc:
        check(False, "a pre-newline stream past MAX_REQ is refused by the CAP",
              f"raised TimeoutError({exc!r}) — the 2s pre-auth deadline fired "
              f"first, so the cap never engaged")

    # -- one byte over, fully formed, newline terminated ---------------------
    over = _request_of_exactly(tui.MAX_REQ + 1)
    try:
        tui._read_request(_FakeConn(over))  # type: ignore[arg-type]
        check(False, "a request one byte over MAX_REQ is refused",
              f"parsed a {len(over)}-byte request as valid")
    except ValueError as exc:
        check("max size" in str(exc),
              "a request one byte over MAX_REQ is refused by the size cap",
              f"raised ValueError({exc!r}) — refused, but not for the size")
    except Exception as exc:  # noqa: BLE001 - a wrong refusal is still a finding
        check(False, "a request one byte over MAX_REQ is refused by the size cap",
              f"raised {type(exc).__name__}({exc}) instead of the max-size refusal")

    # -- exactly at the cap is legitimate ------------------------------------
    at_cap = _request_of_exactly(tui.MAX_REQ)
    try:
        got = tui._read_request(_FakeConn(at_cap))  # type: ignore[arg-type]
        check(got.get("action") == "alive",
              f"a request of exactly MAX_REQ ({len(at_cap)} bytes) still parses",
              f"got {got!r}")
    except Exception as exc:  # noqa: BLE001 - any refusal here is a finding
        check(False, f"a request of exactly MAX_REQ ({len(at_cap)} bytes) still parses",
              f"refused: {type(exc).__name__}({exc}) — the bound is `>`, so this "
              f"must be accepted")

    # -- an ordinary request is untouched ------------------------------------
    small = b'{"token":"t","action":"alive"}\n'
    got = tui._read_request(_FakeConn(small))  # type: ignore[arg-type]
    check(got == {"token": "t", "action": "alive"},
          "an ordinary small request is served normally", f"got {got!r}")


class _FakeSession:
    """The three session methods the two verbs below touch. `alive` calls
    `pump()` + `is_alive()`; `close` calls `close()`. No PtySession, no
    backend, no child — the loop only needs something that answers."""

    def pump(self, *a, **k) -> bytes:
        return b""

    def is_alive(self) -> bool:
        return True

    def close(self) -> None:
        return None


def _read_reply(sock: socket.socket, timeout: float) -> dict:
    sock.settimeout(timeout)
    buf = b""
    while b"\n" not in buf:
        chunk = sock.recv(65536)
        if not chunk:
            break
        buf += chunk
    if not buf:
        raise OSError("peer closed with no reply")
    return json.loads(buf.split(b"\n", 1)[0].decode("utf-8"))


def test_daemon_refuses_oversized_end_to_end() -> None:
    """The real accept loop, a real loopback socket, a fake session.

    Asserts the peer is TOLD it was refused, that the refusal names the size
    cap rather than the read deadline, and that the daemon is still serving the
    next caller — an enforcement path that killed the loop would leave the
    first assertion green and the second hanging.
    """
    token = "t0kentoken"
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((tui.HOST, 0))
    srv.listen(8)
    port = srv.getsockname()[1]

    stop = threading.Event()
    loop = threading.Thread(target=tui._serve_forever,
                            args=(srv, _FakeSession(), token, stop),
                            name="serve-loop", daemon=True)
    loop.start()
    time.sleep(0.2)
    try:
        # baseline: the loop answers at all, so a later failure is ours
        with socket.create_connection((tui.HOST, port), timeout=5.0) as s:
            s.sendall(b'{"token":"' + token.encode() + b'","action":"alive"}\n')
            base = _read_reply(s, 5.0)
        check(base.get("ok") is True, "the loop serves an authenticated request",
              f"reply {base!r}")

        # the attack: MAX_REQ + 1 bytes and NO newline
        with socket.create_connection((tui.HOST, port), timeout=20.0) as s:
            s.sendall(b"A" * (tui.MAX_REQ + 1))
            try:
                reply = _read_reply(s, 20.0)
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                reply = {"error": f"{type(exc).__name__}: {exc}"}
        err = str(reply.get("error", ""))
        check(reply.get("ok") is not True and "ValueError" in err,
              "an oversized request is refused with the size-cap error shape",
              f"reply {reply!r} — expected ok=false and "
              f"'bad request: ValueError' (a TimeoutError here would mean the "
              f"2s pre-auth budget fired before the cap)")

        # and the daemon is still alive for the next caller
        with socket.create_connection((tui.HOST, port), timeout=5.0) as s:
            s.sendall(b'{"token":"' + token.encode() + b'","action":"alive"}\n')
            after = _read_reply(s, 5.0)
        check(after.get("ok") is True,
              "the daemon still serves a legitimate request after refusing an "
              "oversized one", f"reply {after!r}")
    finally:
        stop.set()
        try:
            with socket.create_connection((tui.HOST, port), timeout=2.0) as s:
                s.sendall(b'{"token":"' + token.encode() + b'","action":"close"}\n')
                s.recv(4096)
        except OSError:
            pass
        loop.join(timeout=5.0)
        try:
            srv.close()
        except OSError:
            pass


# =============================================================================
# 2. The `mcp-name` marker <-> server.json <-> the name the server reports
#
#    README.md lines 2-5: the marker "must appear in the published package's
#    README (= PyPI description) and match server.json's `name`". That is an
#    ownership claim for the MCP Registry entry, and until now nothing compared
#    the two.
#
#    The third source is the runtime `serverInfo` handshake. NOTE, because it
#    looks like a contradiction and is not: the runtime name is
#    `smartcli-drive-tui`, a PLAIN protocol server name, while the marker is
#    `io.github.dwgx/smartcli`, a reverse-DNS REGISTRY identity. Those are two
#    different namespaces and no MCP client requires them to be equal, so
#    asserting that would be asserting a falsehood. What CAN be compared is the
#    runtime name against the name docs/DISTRIBUTION-CHANNELS.md records as the
#    measured handshake output — two independently derived facts (a live import
#    and a written record of a live observation), which is the comparison that
#    catches a rename that left the record stale, or a record that no longer
#    describes the server.
# =============================================================================

#: Boundary-anchored on purpose: the registry's own matcher is anchored too
#: (registry commit 04623ed92), so a marker substring appearing somewhere else
#: in the README must not satisfy this.
_MARKER_RE = re.compile(r"^<!--\s*mcp-name:\s*(\S+)\s*-->\s*$", re.MULTILINE)
#: The handshake transcript DISTRIBUTION-CHANNELS.md records as observed
#: against the installed wheel.
_HANDSHAKE_RE = re.compile(r"serverInfo\s*\{name:\s*([^,}]+?)\s*,")


def test_mcp_name_invariant() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    markers = _MARKER_RE.findall(readme)
    if not markers:
        check(False, "README.md carries the boundary-anchored mcp-name marker",
              "no line matches `<!-- mcp-name: NAME -->`; this marker is what "
              "MCP Registry ownership is verified against")
        return
    check(len(markers) == 1,
          "README.md carries exactly one mcp-name marker",
          f"found {len(markers)}: {markers}")
    marker = markers[0]

    server = json.loads((ROOT / "server.json").read_text(encoding="utf-8"))
    check(marker == server.get("name"),
          f"the README marker equals server.json's name ({marker})",
          f"README says {marker!r}, server.json says {server.get('name')!r}")

    # The runtime half. `mcp` is a REQUIRED dependency (requirements.txt), so a
    # missing one is an environment problem, not a reason to report a pass.
    try:
        import mcp_server  # noqa: PLC0415
    except (ImportError, SystemExit) as exc:
        skip("the runtime serverInfo name is compared against the recorded "
             "handshake", f"mcp_server not importable: {type(exc).__name__}: {exc} "
                          f"— `pip install -r requirements.txt`")
        return

    runtime_name = getattr(getattr(mcp_server.mcp, "_mcp_server", None), "name", None)
    check(isinstance(runtime_name, str) and runtime_name != "",
          "the server reports a non-empty serverInfo name",
          f"got {runtime_name!r} from mcp_server.mcp._mcp_server.name")

    doc = (ROOT / "docs" / "DISTRIBUTION-CHANNELS.md").read_text(encoding="utf-8")
    recorded = _HANDSHAKE_RE.search(doc)
    if recorded is None:
        check(False, "DISTRIBUTION-CHANNELS.md records the observed serverInfo "
                     "handshake", "no `serverInfo {name: ..., ...}` transcript found")
        return
    check(runtime_name == recorded.group(1),
          f"the runtime serverInfo name matches the recorded handshake "
          f"({recorded.group(1)})",
          f"the server reports {runtime_name!r} but "
          f"docs/DISTRIBUTION-CHANNELS.md records {recorded.group(1)!r}")

    # And the namespace difference is asserted so nobody 'fixes' it by making
    # the two equal — the registry identity is not a protocol server name.
    check(runtime_name != marker,
          "the registry identity and the protocol server name stay distinct "
          "namespaces",
          f"both are {runtime_name!r}; the marker is a reverse-DNS registry "
          f"identity, the serverInfo name is a plain protocol name")


def main() -> int:
    test_request_bound_refuses_oversized()
    test_daemon_refuses_oversized_end_to_end()
    test_mcp_name_invariant()
    print()
    if skipped:
        print(f"{len(skipped)} check(s) SKIPPED (not counted as passes):")
        for s in skipped:
            print(f"   - {s}")
    if failures:
        print(f"{failures} FAILURE(S)")
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
