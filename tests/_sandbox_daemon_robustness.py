"""Sandbox: adversarial robustness probe for the drive-tui daemon transport.

Hypothesis (from reading scripts/tui.py::_run_daemon): the daemon's per-request
`except Exception` guards ONLY `_handle()`, not the `conn.recv()` read loop or
`json.loads()`. So a single malformed (non-JSON) request, or an idle client that
never sends a newline, should crash the WHOLE daemon (it falls through to the
outer `finally: sess.close()`), killing an otherwise-healthy session — and this
happens BEFORE the token check, so it needs no credential.

This is a REAL-PATH probe: it spawns the actual daemon via the real CLI, talks to
it over a real loopback socket, and re-checks liveness with a legitimate,
authenticated request afterward. No monkeypatching.

Exit 0 = daemon SURVIVED every abuse (no defect / defect fixed).
Exit 1 = daemon DIED on malformed transport input (defect reproduced).
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TUI = REPO / "skills" / "drive-tui" / "scripts" / "tui.py"
HOST = "127.0.0.1"


def _reg_dir() -> Path:
    return Path(os.environ.get("SMARTCLI_TUI_DIR")
                or (Path(tempfile.gettempdir()) / "smartcli_tui"))


def _read_reg(sid: str) -> dict:
    return json.loads((_reg_dir() / f"{sid}.json").read_text(encoding="utf-8"))


def _raw_send(port: int, payload: bytes, timeout: float = 5.0,
              read_reply: bool = True) -> bytes:
    """Send raw bytes to the daemon; optionally read a reply line."""
    with socket.create_connection((HOST, port), timeout=timeout) as s:
        s.settimeout(timeout)
        s.sendall(payload)
        if not read_reply:
            return b""
        buf = bytearray()
        try:
            while b"\n" not in buf:
                chunk = s.recv(65536)
                if not chunk:
                    break
                buf.extend(chunk)
        except (socket.timeout, OSError):
            pass
        return bytes(buf)


def _authed(port: int, token: str, action: str, timeout: float = 5.0) -> dict:
    line = _raw_send(port, (json.dumps({"action": action, "token": token})
                            + "\n").encode("utf-8"), timeout=timeout)
    if not line:
        return {"_dead": True}
    try:
        return json.loads(line.split(b"\n", 1)[0].decode("utf-8"))
    except Exception:
        return {"_unparseable": line[:80].decode("utf-8", "replace")}


def main() -> int:
    sid = f"sbx_{os.getpid()}_{int(time.time()*1000) % 100000}"
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    # Start a real daemon owning a real python child. Use the bare command name
    # "python" (winpty resolves it on PATH) rather than sys.executable — a
    # space-containing absolute path does not spawn cleanly under ConPTY.
    r = subprocess.run(
        [sys.executable, str(TUI), "start", "--cmd", "python",
         "--id", sid, "--cols", "80", "--rows", "24"],
        env=env, capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        print(f"FAIL setup: start exited {r.returncode}\n{r.stderr}")
        return 2
    time.sleep(1.5)
    reg = _read_reg(sid)
    port, token = reg["port"], reg["token"]

    results = []
    try:
        # Sanity: authenticated snapshot works.
        pre = _authed(port, token, "snapshot")
        results.append(("baseline snapshot", pre.get("ok") is True))

        # ABUSE 1: non-JSON garbage terminated by newline (reaches json.loads).
        _raw_send(port, b"this is not json at all\n", read_reply=True)
        alive1 = _authed(port, token, "alive")
        survived1 = alive1.get("ok") is True and not alive1.get("_dead")
        results.append(("survives non-JSON garbage", survived1))

        if survived1:
            # ABUSE 2: valid JSON but not an object (list) -> req.get crashes?
            _raw_send(port, b"[1,2,3]\n", read_reply=True)
            alive2 = _authed(port, token, "alive")
            survived2 = alive2.get("ok") is True and not alive2.get("_dead")
            results.append(("survives non-dict JSON", survived2))

            # ABUSE 3: connect, send a partial line, close without newline.
            try:
                with socket.create_connection((HOST, port), timeout=5.0) as s:
                    s.sendall(b'{"action": "snap')  # no newline, then close
            except OSError:
                pass
            alive3 = _authed(port, token, "alive")
            survived3 = alive3.get("ok") is True and not alive3.get("_dead")
            results.append(("survives truncated request", survived3))
    finally:
        subprocess.run([sys.executable, str(TUI), "close", "--id", sid],
                       env=env, capture_output=True, text=True, timeout=15)

    print("=" * 60)
    ok = True
    for name, passed in results:
        print(f"  [{'PASS' if passed else 'FAIL'}] {name}")
        ok = ok and passed
    print("=" * 60)
    if ok:
        print("RESULT: daemon SURVIVED all malformed transport input (robust).")
        return 0
    print("RESULT: daemon DIED on malformed input — DEFECT REPRODUCED.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
