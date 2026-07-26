"""tui_cli_probe -- automated coverage for the drive-tui persistent-session CLI.

Drives the ACTUAL CLI (skills/drive-tui/scripts/tui.py) via subprocess, reusing
one session id (SID) across separate invocations to prove the detached daemon
persists state. Covers: happy-path REPL loop, per-session TOKEN auth over the raw
loopback socket (wrong/missing token must be rejected with NO screen leak; correct
token succeeds), one-shot `run` mode, and no-leaked-sessions cleanup.

Script-style like the other probes: prints PASS/FAIL lines; exit 0 iff all pass.
Uses an isolated SMARTCLI_TUI_DIR so it never collides with real user sessions and
cleanup is deterministic. Every started session is closed in a finally block.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TUI = REPO_ROOT / "skills" / "drive-tui" / "scripts" / "tui.py"
HOST = "127.0.0.1"

# Isolated registry dir for this run: hermetic, deterministic, no collision with
# any real sessions living in the default %TEMP%\smartcli_tui.
REG_DIR = Path(tempfile.mkdtemp(prefix="tui_cli_probe_"))

_ENV = dict(os.environ)
_ENV["PYTHONIOENCODING"] = "utf-8"
_ENV["SMARTCLI_TUI_DIR"] = str(REG_DIR)

_FAILURES = 0
_STARTED: list[str] = []


def python_repl_command() -> str:
    """Return a shell-safe command for this exact interpreter on every OS."""
    argv = [sys.executable, "-i", "-q"]
    return subprocess.list2cmdline(argv) if os.name == "nt" else shlex.join(argv)


def check(cond: bool, label: str, detail: str = "") -> bool:
    global _FAILURES
    if cond:
        print(f"PASS: {label}" + (f"  [{detail}]" if detail else ""))
    else:
        _FAILURES += 1
        print(f"FAIL: {label}" + (f"  [{detail}]" if detail else ""))
    return cond


def run_cli(*args: str, timeout: float = 60.0) -> subprocess.CompletedProcess:
    """Invoke `python tui.py <args...>` as a fresh process (the daemon persists)."""
    cmd = [sys.executable, str(TUI), *args]
    return subprocess.run(cmd, cwd=str(REPO_ROOT), env=_ENV, capture_output=True,
                          text=True, encoding="utf-8", errors="replace",
                          timeout=timeout)


def start_session(cols: int = 80, rows: int = 24, *extra: str) -> str:
    cp = run_cli(
        "start",
        "--cmd",
        python_repl_command(),
        "--cols",
        str(cols),
        "--rows",
        str(rows),
        *extra,
    )
    sid = cp.stdout.strip().splitlines()[-1].strip() if cp.stdout.strip() else ""
    if cp.returncode == 0 and sid:
        _STARTED.append(sid)
    return sid if cp.returncode == 0 else ""


def close_session(sid: str) -> None:
    if not sid:
        return
    try:
        run_cli("close", "--id", sid, timeout=30.0)
    except Exception:
        pass


def raw_socket_request(port: int, req: dict, timeout: float = 15.0) -> dict:
    """Open a RAW loopback socket and send one newline-JSON request, bypassing the
    client's auto-token injection. Returns the parsed daemon response."""
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
    return json.loads(line.decode("utf-8")) if line else {}


# --------------------------------------------------------------------------
# TEST 1 -- happy path end-to-end (SID reused across separate invocations)
# --------------------------------------------------------------------------

def test_happy_path() -> None:
    print("\n--- TEST 1: happy-path REPL end-to-end ---")
    sid = start_session()
    if not check(bool(sid), "start returned a SID", detail=sid):
        return

    cp = run_cli("wait-regex", "--id", sid, ">>> ", "--timeout-ms", "15000")
    check(cp.returncode == 0, "wait-regex for prompt exit 0",
          detail=f"rc={cp.returncode} stderr={cp.stderr.strip()[-80:]}")

    cp = run_cli("send-line", "--id", sid, "print(6*7)")
    check(cp.returncode == 0, "send-line exit 0", detail=f"rc={cp.returncode}")

    # Give the child a beat to echo + compute, then snapshot (poll a few times).
    got42 = False
    snap_text = ""
    for _ in range(10):
        cp = run_cli("snapshot", "--id", sid)
        snap_text = cp.stdout
        if cp.returncode == 0 and "42" in snap_text:
            got42 = True
            break
        time.sleep(0.4)
    check(cp.returncode == 0, "snapshot exit 0", detail=f"rc={cp.returncode}")
    check(got42, "snapshot text contains 42 (no token flag needed; auto-loaded)",
          detail=repr(snap_text.strip()[-60:]))

    cp = run_cli("close", "--id", sid)
    check(cp.returncode == 0, "close exit 0", detail=f"rc={cp.returncode}")
    if sid in _STARTED:
        _STARTED.remove(sid)


# --------------------------------------------------------------------------
# TEST 2 -- per-session TOKEN auth over the raw loopback socket (security)
# --------------------------------------------------------------------------

def test_token_auth() -> None:
    print("\n--- TEST 2: per-session token auth (raw socket) ---")
    sid = start_session()
    if not check(bool(sid), "start returned a SID for auth test", detail=sid):
        return
    try:
        # Read host/port/token straight from the per-session reg file.
        reg = json.loads((REG_DIR / f"{sid}.json").read_text(encoding="utf-8"))
        port = int(reg["port"])
        real_token = reg["token"]
        check(isinstance(real_token, str) and len(real_token) >= 16,
              "reg file carries a per-session token", detail=f"len={len(real_token)}")

        # (a) WRONG token -> rejected, no screen contents leaked.
        resp_wrong = raw_socket_request(port, {"action": "snapshot",
                                               "token": "deadbeef" * 4})
        check(resp_wrong.get("ok") is False and "auth" in str(resp_wrong.get("error", "")).lower(),
              "wrong token REJECTED with auth error", detail=json.dumps(resp_wrong))
        check("text" not in resp_wrong and "json" not in resp_wrong,
              "wrong token leaks NO screen contents", detail=json.dumps(resp_wrong))

        # (b) NO token field -> rejected, no screen contents leaked.
        resp_none = raw_socket_request(port, {"action": "snapshot"})
        check(resp_none.get("ok") is False and "auth" in str(resp_none.get("error", "")).lower(),
              "missing token REJECTED with auth error", detail=json.dumps(resp_none))
        check("text" not in resp_none and "json" not in resp_none,
              "missing token leaks NO screen contents", detail=json.dumps(resp_none))

        # (c) CORRECT token -> succeeds, returns screen contents.
        resp_ok = raw_socket_request(port, {"action": "snapshot", "token": real_token})
        check(resp_ok.get("ok") is True and "text" in resp_ok,
              "correct token SUCCEEDS and returns screen", detail=json.dumps(resp_ok)[:80])
    finally:
        close_session(sid)
        if sid in _STARTED:
            _STARTED.remove(sid)


# --------------------------------------------------------------------------
# TEST 3 -- one-shot `run` mode (JSON steps against a fresh in-process session)
# --------------------------------------------------------------------------

def test_run_mode() -> None:
    print("\n--- TEST 3: one-shot run mode ---")
    steps = [
        {"action": "wait_regex", "pattern": ">>> ", "timeout_ms": 15000},
        {"action": "send_line", "text": "print(21*2)"},
        {"action": "wait_regex", "pattern": "42", "timeout_ms": 15000},
        {"action": "send_line", "text": (
            "import os; print('RUNENV', os.path.basename(os.getcwd()), "
            "os.getenv('SMARTCLI_RUN_PROBE'))"
        )},
        {"action": "wait_regex", "pattern": "RUNENV .* present", "timeout_ms": 15000},
        {"action": "snapshot"},
    ]
    steps_file = REG_DIR / "run_steps.json"
    steps_file.write_text(json.dumps(steps), encoding="utf-8")
    try:
        cp = run_cli("run", "--cmd", python_repl_command(), "--steps", str(steps_file),
                     "--cols", "80", "--rows", "24", "--cwd", str(REG_DIR),
                     "--env", "SMARTCLI_RUN_PROBE=present", timeout=90.0)
        check(cp.returncode == 0, "run mode exit 0",
              detail=f"rc={cp.returncode} stderr={cp.stderr.strip()[-80:]}")
        check("42" in cp.stdout, "run mode output contains 42",
              detail=repr(cp.stdout.strip()[-60:]))
        check("RUNENV" in cp.stdout and "present" in cp.stdout,
              "run mode forwards cwd/env", detail=repr(cp.stdout.strip()[-120:]))
    finally:
        try:
            steps_file.unlink()
        except OSError:
            pass


# --------------------------------------------------------------------------
# TEST 4 -- child cwd/env are explicit and control secrets are not inherited
# --------------------------------------------------------------------------

def test_child_environment() -> None:
    print("\n--- TEST 4: child cwd/env and capability isolation ---")
    workdir = REG_DIR / "child-workdir"
    workdir.mkdir()
    sid = start_session(
        80,
        24,
        "--cwd",
        str(workdir),
        "--env",
        "SMARTCLI_PROBE_VALUE=present",
    )
    if not check(bool(sid), "start with --cwd/--env returned a SID", detail=sid):
        return
    try:
        run_cli("wait-regex", "--id", sid, ">>> ", "--timeout-ms", "15000")
        code = (
            "import os; print('PROBE', os.getcwd(), "
            "os.getenv('SMARTCLI_PROBE_VALUE'), os.getenv('SMARTCLI_TUI_TOKEN'))"
        )
        run_cli("send-line", "--id", sid, code)
        cp = run_cli(
            "wait-regex",
            "--id",
            sid,
            r"PROBE .* present None",
            "--timeout-ms",
            "15000",
        )
        check(cp.returncode == 0 and f"{workdir.name} present None" in cp.stdout,
              "target receives cwd and requested env", detail=repr(cp.stdout[-120:]))
        check("present None" in cp.stdout,
              "target does not inherit SMARTCLI_TUI_TOKEN", detail=repr(cp.stdout[-120:]))
    finally:
        close_session(sid)
        if sid in _STARTED:
            _STARTED.remove(sid)
        try:
            workdir.rmdir()
        except OSError:
            pass


# --------------------------------------------------------------------------
# TEST 5 -- wait-visual-change over the real daemon protocol
#
# The core semantics are locked in tests/test_visual_change.py against a fake
# backend; what is NOT covered there is the daemon/CLI wiring — the action
# string, the int baseline round-trip through JSON, and the changed/visual_hash
# fields coming back. A typo in any of those is invisible to the unit test.
# --------------------------------------------------------------------------

def test_wait_visual_change() -> None:
    print("\n--- TEST 5: wait-visual-change end-to-end ---")
    sid = start_session()
    if not check(bool(sid), "start returned a SID", detail=sid):
        return
    try:
        run_cli("wait-regex", "--id", sid, ">>> ", "--timeout-ms", "15000")

        # Baseline comes from a snapshot: the CLI reports it on stderr as
        # "# hash=<int> visual_hash=<int>". Parse the visual_hash out.
        cp = run_cli("snapshot", "--id", sid)
        m = re.search(r"visual_hash=(-?\d+)", cp.stdout + cp.stderr)
        if not check(m is not None, "snapshot reports a visual_hash baseline",
                     detail=repr((cp.stdout + cp.stderr)[:120])):
            return
        baseline = m.group(1)

        # An idle screen must NOT report a change (short timeout keeps it quick).
        cp = run_cli("wait-visual-change", "--id", sid,
                     "--baseline-hash", baseline, "--timeout-ms", "1200")
        out = cp.stdout + cp.stderr
        check(cp.returncode == 0 and "changed=False" in out,
              "idle screen reports changed=False against its own baseline",
              detail=repr(out[:120]))

        # Typing text changes the screen; the same baseline must now fire.
        run_cli("send-text", "--id", sid, "1+1")
        cp = run_cli("wait-visual-change", "--id", sid,
                     "--baseline-hash", baseline, "--timeout-ms", "8000")
        out = cp.stdout + cp.stderr
        check(cp.returncode == 0 and "changed=True" in out,
              "screen change fires wait-visual-change with an int baseline",
              detail=repr(out[:120]))
        m2 = re.search(r"visual_hash=(-?\d+)", out)
        check(m2 is not None and m2.group(1) != baseline,
              "returned visual_hash differs from the baseline",
              detail=f"baseline={baseline} now={m2.group(1) if m2 else None}")
    finally:
        close_session(sid)
        if sid in _STARTED:
            _STARTED.remove(sid)


# --------------------------------------------------------------------------
# TEST 6 -- no leaked sessions at the end
# --------------------------------------------------------------------------

def test_no_leaks() -> None:
    print("\n--- TEST 6: no leaked sessions ---")
    cp = run_cli("list")
    listed = [ln for ln in cp.stdout.splitlines() if ln.strip()]
    check(cp.returncode == 0, "list exit 0", detail=f"rc={cp.returncode}")
    check(len(listed) == 0, "list shows ZERO sessions (no leaked daemons)",
          detail=f"{len(listed)} listed: {listed}")


def main() -> int:
    print(f"REG_DIR={REG_DIR}")
    print(f"TUI={TUI}")
    try:
        test_happy_path()
        test_token_auth()
        test_run_mode()
        test_child_environment()
        test_wait_visual_change()
        test_no_leaks()
    finally:
        # Always close every session we started, even on mid-test failure.
        for sid in list(_STARTED):
            close_session(sid)
        # Give daemons a moment to unlink their reg files, then remove temp dir.
        time.sleep(1.0)
        try:
            for p in REG_DIR.glob("*"):
                try:
                    p.unlink()
                except OSError:
                    pass
            REG_DIR.rmdir()
        except OSError:
            pass

    print()
    if _FAILURES == 0:
        print("ALL PASS")
        return 0
    print(f"{_FAILURES} FAILURE(S)")
    return 1


if __name__ == "__main__":
    sys.exit(main())
