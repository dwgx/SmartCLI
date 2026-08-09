#!/usr/bin/env python3
"""test_daemon_concurrency.py — one connection must not stall the others.

NO PTY, NO real child process. This drives the daemon's real accept loop against a
FAKE session object, so it is deterministic and safe to run anywhere (the repo's
red line forbids spawning real programs in a gate).

WHAT IT LOCKS, and why each assertion exists
--------------------------------------------
The accept loop used to be strictly serial: `conn, _ = srv.accept()` with the
transport read — and therefore an UNAUTHENTICATED peer — inline. So one client that
connected and sent no newline blocked every other caller for its whole read budget.
`beb7583` cut that budget from 60s to 2s, which is a 30x mitigation and not a fix:
with `listen(8)`, nine held connections still meant ~18s of denial, and an attacker
who keeps reconnecting still degrades service.

  1. HEAD-OF-LINE: with `listen` backlog + 1 silent peers holding connections, an
     authenticated request still gets its reply within a small bound. This is the
     assertion the whole task exists for, and it FAILS against the serial loop.
  2. LARGE PAYLOAD: a 200 KB request necessarily spans several `recv()` calls, so a
     fixed pre-auth deadline could plausibly kill a legitimate big `send-text`.
     Locking it because it is the obvious way this change could break something.
  3. UNAUTHENTICATED PEERS STAY CHEAP: a wrong token is still rejected, and doing
     the transport off the accept thread must not create a path that skips the
     token check.
  4. SESSION ACCESS STAYS SINGLE-THREADED: the fake session records which thread
     touched it. `PtySession` is NOT thread-safe — `visual_hash()` drains
     `screen.dirty` as a side effect of a nominally read-only call, `pump()` is a
     read-modify-write over the backend and the screen, and `resize()` mutates
     cols/rows/model/_blank_hash together — so any design that lets two connections
     into the session concurrently would corrupt perception silently. That is the
     defect class this assertion prevents a future refactor from reintroducing.
"""
from __future__ import annotations

import json
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

FAILURES: list[str] = []


def check(cond: bool, label: str, detail: str = "") -> None:
    print(f"{'PASS' if cond else 'FAIL'}  {label}" + (f"  {detail}" if detail and not cond else ""))
    if not cond:
        FAILURES.append(label)


class FakeSession:
    """Stands in for PtySession. Records the threads that touched it."""

    def __init__(self) -> None:
        self.cols = 80
        self.rows = 24
        self.model = FakeModel()
        #: Recorded as (ident, name) pairs. It MUST key on the thread IDENT, not the
        #: name: every reader thread is created with the same name `conn-reader`, so
        #: a set of names collapses N readers into one entry and the invariant check
        #: passes even when several distinct threads touched the session. Measured —
        #: with names only, a mutation that handled requests directly on the reader
        #: thread still reported "single thread". A check that cannot fail.
        self.touch_threads: set[tuple[int, str]] = set()
        self.slow_wait_running = threading.Event()
        self._slow_wait_release = threading.Event()

    # -- the surface _handle uses ------------------------------------------
    def _touch(self) -> None:
        cur = threading.current_thread()
        self.touch_threads.add((cur.ident or 0, cur.name))

    def snapshot(self):
        self._touch()
        return FakeSnapshot()

    def is_alive(self) -> bool:
        self._touch()
        return True

    def send_text(self, text: str) -> None:
        self._touch()
        self.last_text = text

    def send_line(self, text: str) -> None:
        self._touch()
        self.last_text = text

    def send_keys(self, keys) -> None:
        self._touch()

    def resize(self, cols: int, rows: int) -> None:
        self._touch()
        self.cols, self.rows = cols, rows

    def close(self) -> None:
        self._touch()

    def pump(self) -> bytes:
        self._touch()
        return b""

    def wait_ready(self, *a, **k):
        self._touch()
        return (True, "STABLE", FakeSnapshot())

    def wait_stable(self, *a, **k):
        self._touch()
        return FakeSnapshot()

    def wait_for(self, *a, on_poll=None, **k):
        """A deliberately long wait, modelling `wait-regex --timeout-ms 60000`.

        It must POLL, exactly like the real one: `readiness.wait_for_regex` loops
        `read -> test -> on_poll() -> sleep(poll_ms)`. A fake that simply blocks on
        an Event would never call the hook, so the interleave assertion below would
        fail for a rig reason rather than a real one — which is what the first
        version of this file did, and it cost a debugging round. Suspect the rig.
        """
        self._touch()
        self.slow_wait_running.set()
        while not self._slow_wait_release.is_set():
            if on_poll is not None:
                on_poll()
            self._slow_wait_release.wait(timeout=0.03)  # the real default poll_ms
        return (True, FakeSnapshot())

    def wait_any(self, *a, **k):
        self._touch()
        return (0, FakeSnapshot())

    def wait_change(self, *a, **k):
        self._touch()
        return (True, 1, FakeSnapshot())

    def wait_visual_change(self, *a, **k):
        self._touch()
        return (True, 1, FakeSnapshot())

    def release_slow_wait(self) -> None:
        self._slow_wait_release.set()


class FakeModel:
    """`_snapshot_response` reads hashes and alt_screen off `sess.model`."""

    def __init__(self) -> None:
        self.n = 0

    def content_hash(self) -> int:
        return 1234

    def visual_hash(self) -> int:
        return 5678

    @property
    def alt_screen(self) -> bool:
        return False


class FakeSnapshot:
    text = "fake"
    cursor = (0, 0)
    alt_screen = False
    selected = None
    status = None
    errors = ()
    menu_items = ()

    def to_text(self) -> str:
        return "fake screen"

    def to_json(self, indent: int | None = None) -> str:
        """A STRING, matching `Snapshot.to_json` — `_snapshot_response` does
        `json.loads(snap.to_json())`, so a dict here fails with a TypeError that
        looks like a daemon bug. Shape the fake from the real signature."""
        return json.dumps({"text": "fake", "alt_screen": False})


def request(port: int, payload: dict, timeout: float) -> dict:
    """One complete request/response over a fresh connection."""
    with socket.create_connection((tui.HOST, port), timeout=timeout) as s:
        s.settimeout(timeout)
        s.sendall((json.dumps(payload) + "\n").encode("utf-8"))
        buf = b""
        while b"\n" not in buf:
            chunk = s.recv(65536)
            if not chunk:
                break
            buf += chunk
    return json.loads(buf.split(b"\n", 1)[0].decode("utf-8"))


def main() -> int:
    token = "t0kentoken"
    sess = FakeSession()

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((tui.HOST, 0))
    backlog = 8
    srv.listen(backlog)
    port = srv.getsockname()[1]

    stop = threading.Event()
    loop = threading.Thread(target=tui._serve_forever,
                            args=(srv, sess, token, stop),
                            name="serve-loop", daemon=True)
    loop.start()
    time.sleep(0.2)

    try:
        # --- sanity: the loop answers at all -----------------------------
        r = request(port, {"token": token, "action": "alive"}, timeout=5.0)
        check(r.get("ok") is True, "the loop answers an authenticated request",
              detail=repr(r))

        # --- 1. head-of-line blocking ------------------------------------
        # Hold backlog+1 connections open, each sending a byte with NO newline so
        # the daemon stays in recv() for its whole pre-auth budget. Against the old
        # serial loop these serialize: 9 x 2s = ~18s before a legitimate caller is
        # served. The bound below is far under that and far over a correct
        # implementation's cost.
        holders = []
        for _ in range(backlog + 1):
            s = socket.create_connection((tui.HOST, port), timeout=5.0)
            s.sendall(b"{")  # valid start, never a newline
            holders.append(s)
        time.sleep(0.3)  # let them all be accepted/queued

        t0 = time.monotonic()
        try:
            r = request(port, {"token": token, "action": "alive"}, timeout=8.0)
            elapsed = time.monotonic() - t0
            ok = r.get("ok") is True
        except (OSError, TimeoutError, json.JSONDecodeError) as exc:
            elapsed = time.monotonic() - t0
            ok = False
            r = {"error": f"{type(exc).__name__}: {exc}"}
        check(ok and elapsed < 3.0,
              f"an authenticated request is served while {backlog + 1} silent peers "
              f"hold connections (took {elapsed:.2f}s, bound 3.0s)",
              detail=f"ok={ok} elapsed={elapsed:.2f}s reply={r!r} — a serial accept "
                     f"loop takes ~{(backlog + 1) * 2}s here")
        for s in holders:
            try:
                s.close()
            except OSError:
                pass

        # --- 2. a legitimate LARGE request still succeeds -----------------
        big = "x" * 200_000
        r = request(port, {"token": token, "action": "send_text", "text": big},
                    timeout=10.0)
        check(r.get("ok") is True and getattr(sess, "last_text", "") == big,
              "a 200 KB request spanning many recv() calls still succeeds",
              detail=repr(r)[:200])

        # --- 3. auth is still enforced -----------------------------------
        r = request(port, {"token": "wrong", "action": "snapshot"}, timeout=5.0)
        check(r.get("ok") is not True and "fake screen" not in json.dumps(r),
              "a wrong token is rejected and leaks no screen content",
              detail=repr(r)[:200])
        r = request(port, {"action": "snapshot"}, timeout=5.0)
        check(r.get("ok") is not True,
              "a missing token is rejected", detail=repr(r)[:200])

        # --- 4. a long wait must not block an unrelated fast verb ---------
        # This is the second half of the task: `wait-regex` blocks for many seconds
        # BY DESIGN, and a design that merely moves the queue would leave a
        # concurrent `snapshot` waiting behind it.
        waiter_reply: dict = {}

        def run_wait() -> None:
            try:
                waiter_reply.update(request(
                    port, {"token": token, "action": "wait_regex",
                           "pattern": "never", "timeout_ms": 30000},
                    timeout=40.0))
            except Exception as exc:  # noqa: BLE001
                waiter_reply["error"] = f"{type(exc).__name__}: {exc}"

        wt = threading.Thread(target=run_wait, name="slow-waiter", daemon=True)
        wt.start()
        got_wait = sess.slow_wait_running.wait(timeout=5.0)
        check(got_wait, "the long wait verb is executing on the daemon")

        t0 = time.monotonic()
        try:
            r = request(port, {"token": token, "action": "snapshot"}, timeout=8.0)
            elapsed = time.monotonic() - t0
            ok = r.get("ok") is True
        except (OSError, TimeoutError, json.JSONDecodeError) as exc:
            elapsed = time.monotonic() - t0
            ok = False
            r = {"error": f"{type(exc).__name__}: {exc}"}
        check(ok and elapsed < 3.0,
              f"a snapshot is served while a long wait is in flight "
              f"(took {elapsed:.2f}s, bound 3.0s)",
              detail=f"ok={ok} elapsed={elapsed:.2f}s reply={r!r}")
        sess.release_slow_wait()
        wt.join(timeout=10.0)

        # --- 5. session access stayed on ONE thread ----------------------
        check(len(sess.touch_threads) == 1,
              "every session call happened on a single thread "
              "(PtySession is not thread-safe)",
              detail=f"threads that touched the session: {sorted(sess.touch_threads)}")

    finally:
        stop.set()
        try:
            with socket.create_connection((tui.HOST, port), timeout=2.0) as s:
                s.sendall((json.dumps({"token": token, "action": "close"}) + "\n").encode())
                s.recv(4096)
        except OSError:
            pass
        loop.join(timeout=5.0)
        try:
            srv.close()
        except OSError:
            pass

    print()
    if FAILURES:
        print(f"test_daemon_concurrency FAIL -- {len(FAILURES)} check(s):")
        for f in FAILURES:
            print("   -", f)
        return 1
    print("PASS: one connection cannot stall the others, auth still holds, and "
          "session access stays single-threaded.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
