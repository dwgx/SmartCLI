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
import re
import secrets
import socket
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path

# --- locate smartcli_core wherever this skill folder ended up ----------------
# Package import serves the wheel/entrypoint path; the fallback preserves direct
# execution from a source checkout or standalone copied skill.
try:
    from . import smartcli_bootstrap
except ImportError:  # pragma: no cover - exercised by direct script probes
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import smartcli_bootstrap  # type: ignore[no-redef]  # noqa: E402

smartcli_bootstrap.locate_core()

from smartcli_core import PtySession  # noqa: E402


def _default_reg_dir() -> Path:
    """Return a per-user registry location, never a shared fixed /tmp path."""
    if os.name == "nt":
        # tempfile.gettempdir() resolves to the current user's temp directory on
        # supported Windows versions and carries that user's ACL.
        return Path(tempfile.gettempdir()) / "smartcli_tui"
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
    if runtime_dir:
        return Path(runtime_dir) / "smartcli_tui"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Caches" / "SmartCLI" / "sessions"
    return Path.home() / ".cache" / "smartcli" / "sessions"


REG_DIR = Path(os.environ.get("SMARTCLI_TUI_DIR") or _default_reg_dir())
HOST = "127.0.0.1"
DEFAULT_MAX_SESSIONS = 8
MAX_COLS = 1000
MAX_ROWS = 500
MAX_CELLS = 100_000
_SID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
_ENV_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# --- registry: one JSON file per session id --------------------------------

def _validate_sid(sid: str) -> str:
    """Reject path-like or unbounded session ids before touching the filesystem."""
    if not isinstance(sid, str) or not _SID_RE.fullmatch(sid):
        raise SystemExit(
            "error: session id must be 1-64 characters using only letters, "
            "digits, '.', '_' or '-', and must start with a letter or digit"
        )
    return sid


def _reg_path(sid: str) -> Path:
    sid = _validate_sid(sid)
    return REG_DIR / f"{sid}.json"


def _max_sessions() -> int:
    raw = os.environ.get("SMARTCLI_MAX_SESSIONS", str(DEFAULT_MAX_SESSIONS))
    try:
        value = int(raw)
    except ValueError as exc:
        raise SystemExit("error: SMARTCLI_MAX_SESSIONS must be an integer") from exc
    if not 1 <= value <= 128:
        raise SystemExit("error: SMARTCLI_MAX_SESSIONS must be between 1 and 128")
    return value


def _parse_env_items(items: list[str]) -> dict[str, str]:
    """Parse repeated KEY=VALUE values without invoking a shell."""
    result: dict[str, str] = {}
    for item in items:
        key, sep, value = item.partition("=")
        if not sep or not _ENV_KEY_RE.fullmatch(key):
            raise SystemExit(f"error: invalid --env {item!r}; expected KEY=VALUE")
        if key.startswith("SMARTCLI_TUI_"):
            raise SystemExit(f"error: --env may not override SmartCLI control variable {key!r}")
        result[key] = value
    return result


def _validate_size(cols: int, rows: int) -> tuple[int, int]:
    if cols < 1 or rows < 1:
        raise SystemExit("error: terminal dimensions must be positive")
    if cols > MAX_COLS or rows > MAX_ROWS or cols * rows > MAX_CELLS:
        raise SystemExit(
            f"error: terminal is too large ({cols}x{rows}); limits are "
            f"{MAX_COLS} columns, {MAX_ROWS} rows and {MAX_CELLS} cells"
        )
    return cols, rows


def _ensure_reg_dir() -> None:
    """Create the registry directory and reject an unsafe POSIX endpoint."""
    REG_DIR.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        return
    try:
        info = REG_DIR.lstat()
    except OSError as exc:
        raise SystemExit(f"error: cannot inspect session registry {REG_DIR}: {exc}") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise SystemExit(f"error: session registry is not a real directory: {REG_DIR}")
    if info.st_uid != os.getuid():
        raise SystemExit(f"error: session registry is not owned by this user: {REG_DIR}")
    try:
        os.chmod(REG_DIR, 0o700)
    except OSError as exc:
        raise SystemExit(f"error: cannot secure session registry {REG_DIR}: {exc}") from exc


def _write_reg(sid: str, info: dict) -> None:
    # The reg file holds the per-session capability token, so it must not be
    # world-readable. On POSIX create the dir 0700 and the file 0600 (a shared
    # /tmp is multi-user); on Windows the per-user temp dir already restricts it.
    _ensure_reg_dir()
    p = _reg_path(sid)
    # O_EXCL prevents a duplicate/racing daemon from replacing another
    # session's capability file. On POSIX, create it as 0600 from the start.
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if os.name != "nt":
        flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(str(p), flags, 0o600)
    else:
        flags |= getattr(os, "O_NOINHERIT", 0) | getattr(os, "O_BINARY", 0)
        fd = os.open(str(p), flags, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(info))


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
    except (TimeoutError, ConnectionRefusedError, ConnectionResetError, OSError) as exc:
        raise SystemExit(
            f"error: session '{sid}' is not reachable (stale entry? {exc}). "
            f"Close the session (CLI: close --id {sid}; MCP: the close tool) "
            "to clean up the stale entry."
        ) from exc
    if resp.get("error"):
        raise SystemExit(f"error: {resp['error']}")
    return resp


# --- daemon: owns the live PtySession, serves requests on a socket ----------

def _snapshot_response(sess: PtySession, snap, **fields) -> dict:
    """Build one consistent text/JSON/hash response for every observing verb."""
    content_hash = sess.model.content_hash()
    visual_hash = sess.model.visual_hash()
    structured = json.loads(snap.to_json())
    structured["hash"] = content_hash
    structured["visual_hash"] = visual_hash
    return {
        "ok": True,
        "alive": sess.is_alive(),
        # Whether a full-screen program owns the screen changes what the next
        # action MEANS (does `q` quit or type a letter?), so it travels with every
        # observation rather than only inside the JSON payload.
        "alt_screen": sess.model.alt_screen,
        "text": snap.to_text(),
        "json": json.dumps(structured, ensure_ascii=False),
        "hash": content_hash,
        "visual_hash": visual_hash,
        **fields,
    }


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
        return _snapshot_response(sess, snap)

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
        return _snapshot_response(sess, snap, reason=reason)

    if action == "wait_regex":
        matched, snap = sess.wait_for(
            req["pattern"], timeout_ms=int(req.get("timeout_ms", 10000)))
        return _snapshot_response(sess, snap, matched=matched)

    if action == "wait_change":
        changed, snap = sess.wait_change(
            baseline_hash=req.get("baseline_hash"),
            timeout_ms=int(req.get("timeout_ms", 10000)))
        return _snapshot_response(sess, snap, changed=changed)

    if action == "wait_visual_change":
        changed, snap = sess.wait_visual_change(
            baseline_hash=req.get("baseline_hash"),
            timeout_ms=int(req.get("timeout_ms", 10000)))
        return _snapshot_response(sess, snap, changed=changed)

    if action == "wait_any":
        index, snap = sess.wait_any(
            list(req.get("patterns", [])),
            timeout_ms=int(req.get("timeout_ms", 10000)))
        return _snapshot_response(sess, snap, index=index, matched=index >= 0)

    if action == "alive":
        sess.pump()
        return {"ok": True, "alive": sess.is_alive()}

    if action == "resize":
        # _validate_size raises SystemExit for CLI callers; SystemExit is a
        # BaseException, so it would sail through the per-connection
        # `except Exception` guard and tear down the daemon + live session.
        # Convert it to an error response here instead.
        try:
            cols, rows = _validate_size(int(req["cols"]), int(req["rows"]))
        except SystemExit as exc:
            # Strip _validate_size's own "error: " prefix. Every other daemon
            # reply stores a bare message and lets _call add the prefix once for
            # the CLI caller, so keeping it here produced "error: error: ...".
            msg = str(exc)
            return {"ok": False, "error": msg[len("error: "):]
                    if msg.startswith("error: ") else msg}
        sess.resize(cols, rows)
        return {"ok": True}

    if action == "close":
        return {"ok": True, "_shutdown": True}

    return {"ok": False, "error": f"unknown action '{action}'"}


def _run_daemon(
    sid: str,
    cmd,
    cols: int,
    rows: int,
    token: str,
    cwd: str | None = None,
    child_env: dict[str, str] | None = None,
) -> None:
    """Serve one PtySession on a localhost socket until told to close or child dies."""
    _validate_size(cols, rows)
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((HOST, 0))
    srv.listen(8)
    port = srv.getsockname()[1]

    if cwd:
        os.chdir(cwd)
    if child_env:
        os.environ.update(child_env)

    sess = PtySession(cols=cols, rows=rows)
    sess.start(cmd)
    _write_reg(sid, {"sid": sid, "port": port, "pid": os.getpid(),
                     "cmd": cmd, "cols": cols, "rows": rows,
                     "cwd": cwd or os.getcwd(),
                     "env_keys": sorted((child_env or {}).keys()),
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
                    # Cap the pre-newline buffer: the transport runs before the
                    # token check, so an unauthenticated peer must not be able to
                    # exhaust memory by streaming bytes with no newline. 4 MiB is
                    # far above any legitimate request (send-text payloads, step
                    # lists) yet bounds the damage. Over the cap -> drop the conn.
                    MAX_REQ = 4 * 1024 * 1024
                    while b"\n" not in buf:
                        chunk = conn.recv(65536)
                        if not chunk:
                            break
                        buf.extend(chunk)
                        if len(buf) > MAX_REQ:
                            raise ValueError("request exceeds max size")
                    if not buf:
                        continue
                    req = json.loads(bytes(buf).split(b"\n", 1)[0].decode("utf-8"))
                    resp = _handle(sess, req, token)
                    shutdown = bool(resp.get("_shutdown"))
                    conn.sendall((json.dumps(resp) + "\n").encode("utf-8"))
                except (TimeoutError, OSError, ValueError, UnicodeDecodeError) as exc:
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
    _validate_size(cols, rows)
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
            elif act == "wait_any":
                index, snap = sess.wait_any(
                    list(step.get("patterns", [])),
                    timeout_ms=int(step.get("timeout_ms", 10000)))
                emit(f"step{i}:wait_any", snap, f"index={index} alive={sess.is_alive()}")
            elif act == "wait_change":
                changed, snap = sess.wait_change(
                    baseline_hash=step.get("baseline_hash"),
                    timeout_ms=int(step.get("timeout_ms", 10000)))
                emit(f"step{i}:wait_change", snap, f"changed={changed} alive={sess.is_alive()}")
            elif act == "wait_visual_change":
                changed, snap = sess.wait_visual_change(
                    baseline_hash=step.get("baseline_hash"),
                    timeout_ms=int(step.get("timeout_ms", 10000)))
                emit(
                    f"step{i}:wait_visual_change",
                    snap,
                    f"changed={changed} alive={sess.is_alive()}",
                )
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
    _validate_size(args.cols, args.rows)
    sid = args.id or f"s{os.getpid()}_{int(time.time() * 1000) % 100000}"
    _validate_sid(sid)
    if _reg_path(sid).exists():
        raise SystemExit(f"error: session '{sid}' already exists")
    _ensure_reg_dir()
    active_count = sum(1 for _ in REG_DIR.glob("*.json"))
    max_sessions = _max_sessions()
    if active_count >= max_sessions:
        raise SystemExit(
            f"error: session limit reached ({active_count}/{max_sessions}); "
            "close an existing session or raise SMARTCLI_MAX_SESSIONS"
        )
    cwd = _resolve_cwd(args.cwd)
    child_env = _parse_env_items(list(args.env or []))
    # Mint a per-session capability token: only holders of this token (the
    # creator, who can read the per-user reg file where it is persisted) may
    # drive the loopback daemon. Passed to the daemon via an ENV VAR, NOT argv —
    # argv is world-visible in `ps`/Task Manager, so a token on the command line
    # would leak to any local user. The daemon writes it into the (0600) reg file
    # so client subcommands can auto-load it.
    token = secrets.token_hex(16)
    # Re-exec this module as a detached daemon process.
    daemon = [sys.executable, os.path.abspath(__file__), "_daemon",
              "--id", sid, "--cmd", args.cmd,
              "--cols", str(args.cols), "--rows", str(args.rows)]
    if cwd:
        daemon += ["--cwd", cwd]
    daemon_env = {
        **os.environ,
        "SMARTCLI_TUI_TOKEN": token,
        "SMARTCLI_TUI_CHILD_ENV": json.dumps(child_env),
    }
    popen_kwargs = dict(close_fds=True, stdin=subprocess.DEVNULL,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                        env=daemon_env)
    if os.name == "nt":
        # CREATE_NO_WINDOW (0x08000000) | CREATE_NEW_PROCESS_GROUP.
        # We use CREATE_NO_WINDOW rather than the old DETACHED_PROCESS (0x08):
        # DETACHED_PROCESS only means "don't inherit the parent console" — it does
        # NOT stop a console window from being created, so when winpty/ConPTY
        # allocates its pseudo-console to spawn the target program, a conhost
        # window can flash up and STEAL FOCUS from whatever the user is doing.
        # CREATE_NO_WINDOW explicitly runs the console child with no window, which
        # is the correct "silent, never grab focus" disposition and still gives a
        # fully detached process (its own group, no inherited console, DEVNULL io).
        popen_kwargs["creationflags"] = (
            subprocess.CREATE_NEW_PROCESS_GROUP | 0x08000000  # CREATE_NO_WINDOW
        )
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
    if args.json:
        print(json.dumps({"ok": True, "sid": sid}))
    else:
        print(sid)
    return 0


def cmd_snapshot(args) -> int:
    resp = _call(args.id, {"action": "snapshot"})
    print(
        f"# hash={resp.get('hash')} visual_hash={resp.get('visual_hash')} "
        f"alive={resp.get('alive')} alt_screen={resp.get('alt_screen')}",
        file=sys.stderr,
    )
    _print_snap(resp, args.json)
    return 0


def _resolve_send_text(args) -> str:
    """Text for send-text/send-line: from stdin if --stdin, else the argument.

    stdin is the path-conversion-safe channel: Git Bash / MSYS rewrites a leading
    '/' in a native argv (so '/model' arrives as 'D:/Software/Git/model'), but it
    never touches piped stdin. A trailing newline from the pipe is stripped.
    """
    if getattr(args, "stdin", False):
        return sys.stdin.read().rstrip("\r\n")
    if args.text is None:
        raise SystemExit("error: give TEXT, or pass --stdin to read it from a pipe "
                         "(use --stdin for slash-commands like /model on Git Bash)")
    return args.text


def cmd_send_text(args) -> int:
    _call(args.id, {"action": "send_text", "text": _resolve_send_text(args)})
    return 0


def cmd_send_line(args) -> int:
    _call(args.id, {"action": "send_line", "text": _resolve_send_text(args)})
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


def cmd_wait_change(args) -> int:
    req = {"action": "wait_change", "timeout_ms": args.timeout_ms}
    if args.baseline_hash is not None:
        req["baseline_hash"] = args.baseline_hash
    resp = _call(args.id, req, timeout=args.timeout_ms / 1000.0 + 15.0)
    print(f"# changed={resp.get('changed')} hash={resp.get('hash')} "
          f"alive={resp.get('alive')}", file=sys.stderr)
    _print_snap(resp, args.json)
    return 0


def cmd_wait_visual_change(args) -> int:
    req = {"action": "wait_visual_change", "timeout_ms": args.timeout_ms}
    if args.baseline_hash is not None:
        req["baseline_hash"] = args.baseline_hash
    resp = _call(args.id, req, timeout=args.timeout_ms / 1000.0 + 15.0)
    print(
        f"# changed={resp.get('changed')} visual_hash={resp.get('visual_hash')} "
        f"alive={resp.get('alive')}",
        file=sys.stderr,
    )
    _print_snap(resp, args.json)
    return 0


def cmd_wait_any(args) -> int:
    # Patterns via repeated --pattern, or one-per-line on stdin (--stdin) so MSYS
    # Git-bash path-conversion can't mangle a regex like "/foo" into "D:/.../foo".
    patterns = list(args.pattern or [])
    if args.stdin:
        patterns += [ln for ln in sys.stdin.read().splitlines() if ln]
    if not patterns:
        print("error: wait-any needs at least one --pattern (or --stdin)",
              file=sys.stderr)
        return 2
    resp = _call(args.id, {"action": "wait_any", "patterns": patterns,
                           "timeout_ms": args.timeout_ms},
                 timeout=args.timeout_ms / 1000.0 + 15.0)
    idx = resp.get("index", -1)
    hit = patterns[idx] if idx is not None and idx >= 0 else None
    print(f"# index={idx} matched={resp.get('matched')} pattern={hit!r} "
          f"alive={resp.get('alive')}", file=sys.stderr)
    _print_snap(resp, args.json)
    return 0


def cmd_alive(args) -> int:
    resp = _call(args.id, {"action": "alive"})
    print("alive" if resp.get("alive") else "dead")
    return 0 if resp.get("alive") else 1


def cmd_resize(args) -> int:
    # The daemon owns validation: it converts _validate_size's SystemExit into
    # an error REPLY so an out-of-range size cannot tear down a live session.
    # _call then turns that reply back into SystemExit for the CLI caller, which
    # is the shared convention for every verb here — so a rejected size exits
    # non-zero with the daemon's message and never reaches the lines below.
    resp = _call(args.id, {"action": "resize", "cols": args.cols, "rows": args.rows})
    if args.json:
        print(json.dumps({"ok": True, "sid": args.id,
                          "cols": args.cols, "rows": args.rows}))
    else:
        print(f"resized {args.id} to {args.cols}x{args.rows}")
    return 0


def cmd_close(args) -> int:
    try:
        _call(args.id, {"action": "close"})
    except SystemExit:
        # The documented stale-entry cleanup path must actually remove the file.
        try:
            _reg_path(args.id).unlink()
        except OSError:
            pass
    if args.json:
        print(json.dumps({"ok": True, "sid": args.id, "closed": True}))
    else:
        print(f"closed {args.id}")
    return 0


def cmd_list(args) -> int:
    sessions = []
    for p in sorted(REG_DIR.glob("*.json")) if REG_DIR.exists() else []:
        try:
            info = json.loads(p.read_text(encoding="utf-8"))
            sessions.append({
                "sid": info["sid"],
                "port": int(info["port"]),
                "pid": int(info["pid"]),
                "cmd": info["cmd"],
                "cols": int(info.get("cols", 0)),
                "rows": int(info.get("rows", 0)),
                "cwd": info.get("cwd"),
                "started": info.get("started"),
            })
        except Exception:
            continue
    if args.json:
        print(json.dumps({"ok": True, "sessions": sessions}))
    else:
        for info in sessions:
            print(
                f"{info['sid']}\tport={info['port']}\tpid={info['pid']}\t"
                f"cmd={info['cmd']}\tcwd={info['cwd']}"
            )
    return 0


def cmd_run(args) -> int:
    steps = json.loads(Path(args.steps).read_text(encoding="utf-8"))
    if not isinstance(steps, list):
        raise SystemExit("error: steps file must contain a JSON list")
    cwd = _resolve_cwd(args.cwd)
    child_env = _parse_env_items(list(args.env or []))
    old_cwd = os.getcwd()
    old_env = {key: os.environ.get(key) for key in child_env}
    try:
        if cwd:
            os.chdir(cwd)
        os.environ.update(child_env)
        return _run_steps(args.cmd, steps, args.cols, args.rows)
    finally:
        os.chdir(old_cwd)
        for key, previous in old_env.items():
            if previous is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = previous


def _resolve_cwd(value: str | None) -> str | None:
    if not value:
        return None
    cwd = str(Path(value).expanduser().resolve())
    if not Path(cwd).is_dir():
        raise SystemExit(f"error: --cwd is not a directory: {cwd}")
    return cwd


def cmd__daemon(args) -> int:
    # The token arrives via env (SMARTCLI_TUI_TOKEN), not argv, so it never shows
    # up in `ps`/Task Manager. Fall back to --token only for backward compat.
    token = os.environ.get("SMARTCLI_TUI_TOKEN") or getattr(args, "token", None)
    if not token:
        raise SystemExit("error: daemon started without a token")
    try:
        child_env = json.loads(os.environ.pop("SMARTCLI_TUI_CHILD_ENV", "{}"))
    except json.JSONDecodeError as exc:
        raise SystemExit("error: invalid internal child environment payload") from exc
    # The controlled process must not inherit the capability used to control its
    # daemon. Remove it before PtySession spawns the target.
    os.environ.pop("SMARTCLI_TUI_TOKEN", None)
    _run_daemon(args.id, args.cmd, args.cols, args.rows, token, args.cwd, child_env)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="tui.py",
        description="Drive interactive TUI programs via smartcli_core.")
    p.add_argument("--install-deps", action="store_true",
                   help="pip-install any missing runtime deps (pyte/pywinpty) "
                        "now, then continue; otherwise missing deps are only "
                        "reported. Same as SMARTCLI_AUTO_INSTALL=1.")
    sub = p.add_subparsers(
        dest="command", required=True,
        # Hand-maintained: argparse would otherwise list `_daemon` too, which is
        # internal. ADD NEW VERBS HERE as well as registering the subparser —
        # `resize` was invisible in --help for exactly that reason.
        metavar="{start,snapshot,send-text,send-line,keys,wait,wait-regex,"
                "wait-change,wait-visual-change,wait-any,alive,resize,close,"
                "list,run,doctor}")

    sp = sub.add_parser("start", help="spawn a program in a detached persistent session")
    sp.add_argument("--cmd", required=True, help="command line to spawn, e.g. \"python\"")
    sp.add_argument("--id", help="session id (default: auto-generated)")
    sp.add_argument("--cols", type=int, default=100)
    sp.add_argument("--rows", type=int, default=30)
    sp.add_argument("--cwd", help="working directory for the target program")
    sp.add_argument("--env", action="append", default=[], metavar="KEY=VALUE",
                    help="environment variable for the target (repeatable)")
    sp.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    sp.set_defaults(func=cmd_start)

    sp = sub.add_parser("snapshot", help="print a semantic snapshot of the session")
    sp.add_argument("--id", required=True)
    sp.add_argument("--json", action="store_true", help="emit Snapshot.to_json() instead of to_text()")
    sp.set_defaults(func=cmd_snapshot)

    sp = sub.add_parser("send-text", help="type literal text (no Enter). "
                        "Use --stdin for text with a leading '/' (see note below).")
    sp.add_argument("--id", required=True)
    sp.add_argument("text", nargs="?",
                    help="text to type; omit and pass --stdin to read from stdin")
    sp.add_argument("--stdin", action="store_true",
                    help="read the text from stdin instead of the argument. "
                         "REQUIRED for slash-commands like /model on Git Bash / "
                         "MSYS, where a leading '/' in an argv is rewritten to a "
                         "Windows path (e.g. '/model' -> 'D:/Software/Git/model') "
                         "before Python sees it. Piping via stdin bypasses that.")
    sp.set_defaults(func=cmd_send_text)

    sp = sub.add_parser("send-line", help="type text followed by Enter. "
                        "Use --stdin for text with a leading '/' (see note below).")
    sp.add_argument("--id", required=True)
    sp.add_argument("text", nargs="?",
                    help="text to type; omit and pass --stdin to read from stdin")
    sp.add_argument("--stdin", action="store_true",
                    help="read the text from stdin instead of the argument. "
                         "REQUIRED for slash-commands like /model on Git Bash / "
                         "MSYS, where a leading '/' in an argv is rewritten to a "
                         "Windows path before Python sees it. Piping bypasses that.")
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

    sp = sub.add_parser("wait-change",
                        help="wait until the screen content changes (from a baseline "
                             "hash, or from now), then snapshot — the precise "
                             "'did my action land?' primitive")
    sp.add_argument("--id", required=True)
    sp.add_argument("--baseline-hash", dest="baseline_hash", type=int, default=None,
                    help="hash to wait to change away from (default: the screen now). "
                         "Pass the 'hash' from a prior snapshot/wait-change.")
    sp.add_argument("--timeout-ms", dest="timeout_ms", type=int, default=10000)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_wait_change)

    sp = sub.add_parser(
        "wait-visual-change",
        help="wait for text, styling, selection or cursor state to change",
    )
    sp.add_argument("--id", required=True)
    sp.add_argument("--baseline-hash", dest="baseline_hash", type=int, default=None,
                    help="visual_hash from a prior snapshot (default: current state)")
    sp.add_argument("--timeout-ms", dest="timeout_ms", type=int, default=10000)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_wait_visual_change)

    sp = sub.add_parser("wait-any",
                        help="wait for ANY of several regexes (pexpect expect([...]) "
                             "style); reports WHICH matched first, then snapshot")
    sp.add_argument("--id", required=True)
    sp.add_argument("--pattern", action="append",
                    help="a regex to race (repeat for several; earliest in the "
                         "list wins a same-poll tie)")
    sp.add_argument("--stdin", action="store_true",
                    help="also read patterns one-per-line from stdin (MSYS "
                         "path-conversion-safe for regexes containing slashes)")
    sp.add_argument("--timeout-ms", dest="timeout_ms", type=int, default=10000)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_wait_any)

    sp = sub.add_parser("alive", help="check whether the child process is still running")
    sp.add_argument("--id", required=True)
    sp.set_defaults(func=cmd_alive)

    sp = sub.add_parser("resize", help="change the terminal size of a live session")
    sp.add_argument("--id", required=True)
    sp.add_argument("--cols", required=True, type=int)
    sp.add_argument("--rows", required=True, type=int)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_resize)

    sp = sub.add_parser("close", help="terminate the session and its daemon")
    sp.add_argument("--id", required=True)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_close)

    sp = sub.add_parser("list", help="list active sessions")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_list)

    sp = sub.add_parser("run", help="one-shot: run a JSON step list against a fresh program")
    sp.add_argument("--cmd", required=True)
    sp.add_argument("--steps", required=True, help="path to a JSON file: a list of step objects")
    sp.add_argument("--cols", type=int, default=100)
    sp.add_argument("--rows", type=int, default=30)
    sp.add_argument("--cwd", help="working directory for the target program")
    sp.add_argument("--env", action="append", default=[], metavar="KEY=VALUE",
                    help="environment variable for the target (repeatable)")
    sp.set_defaults(func=cmd_run)

    sp = sub.add_parser("doctor", help="report smartcli_core location + dependency status")
    sp.set_defaults(func=cmd_doctor)

    # No help= on purpose: parsers without help are omitted from --help, which
    # keeps this internal re-exec verb out of the public command list.
    sp = sub.add_parser("_daemon")
    sp.add_argument("--id", required=True)
    sp.add_argument("--cmd", required=True)
    # token now arrives via the SMARTCLI_TUI_TOKEN env var (not argv, which leaks
    # in ps). Kept optional for backward compat only.
    sp.add_argument("--token", default=None)
    sp.add_argument("--cols", type=int, default=100)
    sp.add_argument("--rows", type=int, default=30)
    sp.add_argument("--cwd", default=None)
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
