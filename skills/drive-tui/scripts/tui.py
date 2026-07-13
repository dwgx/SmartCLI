#!/usr/bin/env python3
"""tui.py -- thin CLI over smartcli_core for driving interactive TUI programs.

Two modes:

* Persistent session (default): ``start`` spawns a detached per-session daemon
  that owns a live PtySession; ``send-*`` / ``keys`` / ``wait`` / ``snapshot``
  connect to it over a localhost-only TCP socket so state survives across shell
  invocations. This is the perceive->decide->act loop from the shell.

* One-shot script (``run``): execute a JSON list of steps against a freshly
  spawned program in a single process and print snapshots. No daemon needed.

The daemon binds 127.0.0.1 only; it is local process control, no network surface.
"""

from __future__ import annotations

import argparse
import hmac
import json
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

# --- locate smartcli_core wherever this skill folder ended up ----------------
# Robust discovery (repo checkout / standalone skill / plugin drop-in / pip):
# see smartcli_bootstrap.locate_core. Makes "drop the folder in and it works"
# real instead of assuming a fixed repo-root depth.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import smartcli_bootstrap  # noqa: E402

smartcli_bootstrap.locate_core()

from smartcli_core import PtySession  # noqa: E402

REG_DIR = Path(
    os.environ.get("SMARTCLI_TUI_DIR") or (Path(tempfile.gettempdir()) / "smartcli_tui")
)
HOST = "127.0.0.1"

# --- registry: one JSON file per session id --------------------------------

def _reg_path(sid: str) -> Path:
    return REG_DIR / f"{sid}.json"


def _write_reg(sid: str, info: dict) -> None:
    REG_DIR.mkdir(parents=True, exist_ok=True)
    _reg_path(sid).write_text(json.dumps(info), encoding="utf-8")


def _read_reg(sid: str) -> dict:
    p = _reg_path(sid)
    if not p.exists():
        raise SystemExit(f"error: no such session '{sid}' (looked in {p})")
    return json.loads(p.read_text(encoding="utf-8"))


# --- IPC: newline-delimited JSON request/response over a TCP socket ----------

def _send_request(port: int, req: dict, timeout: float = 30.0) -> dict:
    with socket.create_connection((HOST, port), timeout=timeout) as sock:
        sock.settimeout(timeout)
        sock.sendall((json.dumps(req) + "\n").encode("utf-8"))
        buf = bytearray()
        while b"\n" not in buf:
            chunk = sock.recv(65536)
            if not chunk:
                break
            buf.extend(chunk)
    line = bytes(buf).split(b"\n", 1)[0]
    if not line:
        raise SystemExit("error: empty response from session daemon")
    return json.loads(line.decode("utf-8"))


def _call(sid: str, req: dict, timeout: float = 30.0) -> dict:
    """Send one request to the session daemon.

    ``timeout`` is the socket timeout. For blocking waits the daemon does not
    reply until the wait finishes, so callers pass a socket timeout derived
    from the wait's own timeout (see cmd_wait/cmd_wait_regex) — otherwise a
    long wait would trip the default socket timeout and crash the client while
    the daemon kept running.
    """
    info = _read_reg(sid)
    # Auto-include the per-session capability token so only the creator (who can
    # read the per-user reg file) can drive the session. Callers never pass it.
    token = info.get("token")
    if token is not None and "token" not in req:
        req = {**req, "token": token}
    try:
        resp = _send_request(int(info["port"]), req, timeout=timeout)
    except (ConnectionRefusedError, ConnectionResetError, socket.timeout, OSError) as exc:
        raise SystemExit(
            f"error: session '{sid}' is not reachable (stale entry? {exc}). "
            f"Run 'close --id {sid}' to clean up."
        )
    if resp.get("error"):
        raise SystemExit(f"error: {resp['error']}")
    return resp


# --- daemon: owns the live PtySession, serves requests on a socket ----------

def _handle(sess: PtySession, req: dict, expected_token: str) -> dict:
    """Dispatch one request against the live session. Returns a JSON-able dict.

    Every request MUST carry a ``token`` field matching the per-session
    capability token minted at ``start``. Missing/wrong tokens are rejected
    with a constant-time compare before any action is performed, so an
    unauthenticated local process on the loopback port cannot inject keystrokes,
    read the screen, or close the session.
    """
    supplied = req.get("token")
    if not isinstance(supplied, str) or not hmac.compare_digest(supplied, expected_token):
        return {"ok": False, "error": "auth: bad or missing token"}

    action = req.get("action")

    if action == "snapshot":
        sess.pump()
        snap = sess.snapshot()
        return {"ok": True, "alive": sess.is_alive(), "text": snap.to_text(),
                "json": snap.to_json()}

    if action == "send_text":
        sess.send_text(req.get("text", ""))
        return {"ok": True}

    if action == "send_line":
        sess.send_line(req.get("text", ""))
        return {"ok": True}

    if action == "send_keys":
        sess.send_keys(list(req.get("keys", [])))
        return {"ok": True}

    if action == "wait_ready":
        reason, snap = sess.wait_ready(
            marker=req.get("marker"),
            max_wait_ms=int(req.get("max_wait_ms", 10000)),
            quiet_ms=int(req.get("quiet_ms", 200)),
        )
        return {"ok": True, "reason": reason, "alive": sess.is_alive(),
                "text": snap.to_text(), "json": snap.to_json()}

    if action == "wait_regex":
        matched, snap = sess.wait_for(
            req["pattern"], timeout_ms=int(req.get("timeout_ms", 10000)))
        return {"ok": True, "matched": matched, "alive": sess.is_alive(),
                "text": snap.to_text(), "json": snap.to_json()}

    if action == "alive":
        sess.pump()
        return {"ok": True, "alive": sess.is_alive()}

    if action == "resize":
        sess.resize(int(req["cols"]), int(req["rows"]))
        return {"ok": True}

    if action == "close":
        return {"ok": True, "_shutdown": True}

    return {"error": f"unknown action '{action}'"}


def _run_daemon(sid: str, cmd, cols: int, rows: int, token: str) -> None:
    """Serve one PtySession on a localhost socket until told to close or child dies."""
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((HOST, 0))
    srv.listen(8)
    port = srv.getsockname()[1]

    sess = PtySession(cols=cols, rows=rows)
    sess.start(cmd)
    _write_reg(sid, {"sid": sid, "port": port, "pid": os.getpid(),
                     "cmd": cmd, "cols": cols, "rows": rows,
                     "token": token, "started": time.time()})
    try:
        while True:
            conn, _ = srv.accept()
            shutdown = False
            try:
                # The ENTIRE per-connection body is guarded: a malformed request
                # (non-JSON bytes, a truncated line, an idle client that trips the
                # 60s recv timeout, or a non-dict payload) must only drop THAT
                # connection — it must never propagate to the outer `finally` and
                # tear down the whole daemon + live session. Note the transport /
                # parse steps run BEFORE the token check in _handle, so without
                # this guard an unauthenticated peer could kill the session with a
                # single garbage byte sequence.
                try:
                    conn.settimeout(60.0)
                    buf = bytearray()
                    while b"\n" not in buf:
                        chunk = conn.recv(65536)
                        if not chunk:
                            break
                        buf.extend(chunk)
                    if not buf:
                        continue
                    req = json.loads(bytes(buf).split(b"\n", 1)[0].decode("utf-8"))
                    resp = _handle(sess, req, token)
                    shutdown = bool(resp.get("_shutdown"))
                    conn.sendall((json.dumps(resp) + "\n").encode("utf-8"))
                except (socket.timeout, OSError, ValueError,
                        UnicodeDecodeError) as exc:
                    # ValueError covers json.JSONDecodeError and non-dict .get();
                    # OSError/timeout cover a slow/rude client. Best-effort error
                    # reply, then close — the daemon keeps serving.
                    try:
                        conn.sendall((json.dumps(
                            {"ok": False,
                             "error": f"bad request: {type(exc).__name__}"})
                            + "\n").encode("utf-8"))
                    except OSError:
                        pass
                except Exception as exc:  # never let one bad request kill the daemon
                    try:
                        conn.sendall((json.dumps(
                            {"error": f"{type(exc).__name__}: {exc}"})
                            + "\n").encode("utf-8"))
                    except OSError:
                        pass
            finally:
                conn.close()
            if shutdown:
                break
    finally:
        sess.close()
        srv.close()
        try:
            _reg_path(sid).unlink()
        except OSError:
            pass


# --- one-shot script mode: run steps against a fresh program ----------------

def _run_steps(cmd, steps, cols: int, rows: int) -> int:
    """Execute a JSON step list against a freshly spawned program; print snapshots."""
    def emit(label, snap, extra=""):
        print(f"===== {label}{(' ' + extra) if extra else ''} =====")
        print(snap.to_text())
        print()

    with PtySession(cols=cols, rows=rows) as sess:
        sess.start(cmd)
        for i, step in enumerate(steps):
            act = step.get("action")
            if act == "send_text":
                sess.send_text(step.get("text", ""))
            elif act == "send_line":
                sess.send_line(step.get("text", ""))
            elif act == "send_keys":
                sess.send_keys(list(step.get("keys", [])))
            elif act == "wait_ready":
                reason, snap = sess.wait_ready(
                    marker=step.get("marker"),
                    max_wait_ms=int(step.get("max_wait_ms", 10000)))
                emit(f"step{i}:wait_ready", snap, f"reason={reason} alive={sess.is_alive()}")
            elif act in ("wait_regex", "wait_for"):
                matched, snap = sess.wait_for(
                    step["pattern"], timeout_ms=int(step.get("timeout_ms", 10000)))
                emit(f"step{i}:wait_regex", snap, f"matched={matched} alive={sess.is_alive()}")
            elif act == "snapshot":
                sess.pump()
                emit(f"step{i}:snapshot", sess.snapshot(), f"alive={sess.is_alive()}")
            else:
                print(f"error: unknown step action '{act}' at index {i}", file=sys.stderr)
                return 2
    return 0


# --- command handlers -------------------------------------------------------

def _print_snap(resp: dict, as_json: bool) -> None:
    if as_json:
        print(resp.get("json", "{}"))
    else:
        print(resp.get("text", ""))


def cmd_start(args) -> int:
    sid = args.id or f"s{os.getpid()}_{int(time.time() * 1000) % 100000}"
    if _reg_path(sid).exists():
        raise SystemExit(f"error: session '{sid}' already exists")
    # Mint a per-session capability token: only holders of this token (the
    # creator, who can read the per-user reg file where it is persisted) may
    # drive the loopback daemon. Passed to the daemon via argv; the daemon
    # writes it into the reg file so client subcommands can auto-load it.
    token = secrets.token_hex(16)
    # Re-exec this module as a detached daemon process.
    daemon = [sys.executable, os.path.abspath(__file__), "_daemon",
              "--id", sid, "--cmd", args.cmd, "--token", token,
              "--cols", str(args.cols), "--rows", str(args.rows)]
    popen_kwargs = dict(close_fds=True, stdin=subprocess.DEVNULL,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if os.name == "nt":
        # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | 0x00000008
    else:
        # Detach from the launching shell's session so a SIGHUP on shell exit
        # (or Ctrl-C to the process group) does not kill the daemon — this is
        # what makes "state survives across separate shell calls" hold on POSIX.
        popen_kwargs["start_new_session"] = True
    subprocess.Popen(daemon, **popen_kwargs)
    # Wait for the daemon to register + bind.
    deadline = time.time() + 10.0
    while time.time() < deadline:
        if _reg_path(sid).exists():
            break
        time.sleep(0.05)
    else:
        raise SystemExit("error: session daemon did not start in time")
    print(sid)
    return 0


def cmd_snapshot(args) -> int:
    _print_snap(_call(args.id, {"action": "snapshot"}), args.json)
    return 0


def cmd_send_text(args) -> int:
    _call(args.id, {"action": "send_text", "text": args.text})
    return 0


def cmd_send_line(args) -> int:
    _call(args.id, {"action": "send_line", "text": args.text})
    return 0


def cmd_keys(args) -> int:
    _call(args.id, {"action": "send_keys", "keys": args.keys})
    return 0


def cmd_wait(args) -> int:
    resp = _call(args.id, {"action": "wait_ready", "marker": args.marker,
                           "max_wait_ms": args.timeout_ms},
                 timeout=args.timeout_ms / 1000.0 + 15.0)
    print(f"# reason={resp.get('reason')} alive={resp.get('alive')}", file=sys.stderr)
    _print_snap(resp, args.json)
    return 0


def cmd_wait_regex(args) -> int:
    resp = _call(args.id, {"action": "wait_regex", "pattern": args.pattern,
                           "timeout_ms": args.timeout_ms},
                 timeout=args.timeout_ms / 1000.0 + 15.0)
    print(f"# matched={resp.get('matched')} alive={resp.get('alive')}", file=sys.stderr)
    _print_snap(resp, args.json)
    return 0


def cmd_alive(args) -> int:
    resp = _call(args.id, {"action": "alive"})
    print("alive" if resp.get("alive") else "dead")
    return 0 if resp.get("alive") else 1


def cmd_close(args) -> int:
    try:
        _call(args.id, {"action": "close"})
    except SystemExit:
        pass
    print(f"closed {args.id}")
    return 0


def cmd_list(args) -> int:
    if not REG_DIR.exists():
        return 0
    for p in sorted(REG_DIR.glob("*.json")):
        try:
            info = json.loads(p.read_text(encoding="utf-8"))
            print(f"{info['sid']}\tport={info['port']}\tpid={info['pid']}\tcmd={info['cmd']}")
        except Exception:
            continue
    return 0


def cmd_run(args) -> int:
    steps = json.loads(Path(args.steps).read_text(encoding="utf-8"))
    if not isinstance(steps, list):
        raise SystemExit("error: steps file must contain a JSON list")
    return _run_steps(args.cmd, steps, args.cols, args.rows)


def cmd__daemon(args) -> int:
    _run_daemon(args.id, args.cmd, args.cols, args.rows, args.token)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="tui.py",
        description="Drive interactive TUI programs via smartcli_core.")
    p.add_argument("--install-deps", action="store_true",
                   help="pip-install any missing runtime deps (pyte/pywinpty) "
                        "now, then continue; otherwise missing deps are only "
                        "reported. Same as SMARTCLI_AUTO_INSTALL=1.")
    sub = p.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("start", help="spawn a program in a detached persistent session")
    sp.add_argument("--cmd", required=True, help="command line to spawn, e.g. \"python\"")
    sp.add_argument("--id", help="session id (default: auto-generated)")
    sp.add_argument("--cols", type=int, default=100)
    sp.add_argument("--rows", type=int, default=30)
    sp.set_defaults(func=cmd_start)

    sp = sub.add_parser("snapshot", help="print a semantic snapshot of the session")
    sp.add_argument("--id", required=True)
    sp.add_argument("--json", action="store_true", help="emit Snapshot.to_json() instead of to_text()")
    sp.set_defaults(func=cmd_snapshot)

    sp = sub.add_parser("send-text", help="type literal text (no Enter)")
    sp.add_argument("--id", required=True)
    sp.add_argument("text")
    sp.set_defaults(func=cmd_send_text)

    sp = sub.add_parser("send-line", help="type text followed by Enter")
    sp.add_argument("--id", required=True)
    sp.add_argument("text")
    sp.set_defaults(func=cmd_send_line)

    sp = sub.add_parser("keys", help="send key tokens, e.g. Down Down Enter, C-c, M-x")
    sp.add_argument("--id", required=True)
    sp.add_argument("keys", nargs="+")
    sp.set_defaults(func=cmd_keys)

    sp = sub.add_parser("wait", help="wait for a regex marker OR screen stability, then snapshot")
    sp.add_argument("--id", required=True)
    sp.add_argument("--marker", help="regex to wait for (optional; omit to wait for stability)")
    sp.add_argument("--timeout-ms", dest="timeout_ms", type=int, default=10000)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_wait)

    sp = sub.add_parser("wait-regex", help="wait strictly for a regex to appear, then snapshot")
    sp.add_argument("--id", required=True)
    sp.add_argument("pattern")
    sp.add_argument("--timeout-ms", dest="timeout_ms", type=int, default=10000)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_wait_regex)

    sp = sub.add_parser("alive", help="check whether the child process is still running")
    sp.add_argument("--id", required=True)
    sp.set_defaults(func=cmd_alive)

    sp = sub.add_parser("close", help="terminate the session and its daemon")
    sp.add_argument("--id", required=True)
    sp.set_defaults(func=cmd_close)

    sp = sub.add_parser("list", help="list active sessions")
    sp.set_defaults(func=cmd_list)

    sp = sub.add_parser("run", help="one-shot: run a JSON step list against a fresh program")
    sp.add_argument("--cmd", required=True)
    sp.add_argument("--steps", required=True, help="path to a JSON file: a list of step objects")
    sp.add_argument("--cols", type=int, default=100)
    sp.add_argument("--rows", type=int, default=30)
    sp.set_defaults(func=cmd_run)

    sp = sub.add_parser("doctor", help="report smartcli_core location + dependency status")
    sp.set_defaults(func=cmd_doctor)

    sp = sub.add_parser("_daemon", help=argparse.SUPPRESS)
    sp.add_argument("--id", required=True)
    sp.add_argument("--cmd", required=True)
    sp.add_argument("--token", required=True)
    sp.add_argument("--cols", type=int, default=100)
    sp.add_argument("--rows", type=int, default=30)
    sp.set_defaults(func=cmd__daemon)

    return p


def cmd_doctor(args) -> int:
    """Print where smartcli_core resolved from and whether deps are present."""
    try:
        where = smartcli_bootstrap.locate_core()
    except ImportError as exc:
        print(f"smartcli_core: NOT FOUND\n  {exc}")
        return 1
    print(f"smartcli_core: {where or 'installed (pip)'}")
    missing = smartcli_bootstrap._missing_deps()
    if missing:
        print(f"missing deps: {', '.join(missing)}")
        print(f"  install: {smartcli_bootstrap._install_cmd(missing)}")
        return 1
    print("dependencies: all present")
    return 0


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    # Offer to install missing runtime deps before doing work that needs them.
    # 'doctor' reports on its own; '_daemon' inherits the parent's environment.
    if getattr(args, "command", None) not in ("doctor", "_daemon"):
        smartcli_bootstrap.ensure_deps(
            auto_install=True if getattr(args, "install_deps", False) else None)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
