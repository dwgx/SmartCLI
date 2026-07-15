"""_mcp_probe.py — end-to-end coverage for the drive-tui MCP server.

Calls the MCP tool functions directly (they're plain functions under the
FastMCP decorator) to drive a real python REPL session through the full
perceive -> act -> confirm loop, proving the MCP adapter drives the SAME daemon
the CLI does, WITH the per-session token auto-attached (start a session, send a
line, wait for the result, snapshot it, close — then confirm no leaked sessions).

Script-style like the other probes: prints PASS/FAIL, exit 0 iff all pass. Uses
an isolated SMARTCLI_TUI_DIR so it never collides with real user sessions, and
closes the session in a finally block. Real ConPTY — SLOW; run serially.
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# Isolated registry dir: hermetic, no collision with real sessions.
REG_DIR = Path(tempfile.mkdtemp(prefix="mcp_probe_"))
os.environ["SMARTCLI_TUI_DIR"] = str(REG_DIR)
os.environ["PYTHONIOENCODING"] = "utf-8"

sys.path.insert(0, str(REPO_ROOT / "skills" / "drive-tui" / "scripts"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
except Exception:
    pass

try:
    import mcp_server as M  # noqa: E402
except SystemExit:
    # mcp_server raises SystemExit(2) when the `mcp` package is absent. That's a
    # missing optional dependency, not a failure — skip cleanly so run_all
    # reports skip-with-note rather than a red gate.
    print("SKIP: the 'mcp' package is not installed — MCP server probe skipped.")
    try:
        REG_DIR.rmdir()
    except OSError:
        pass
    raise SystemExit(0)

_FAILURES = 0


def check(cond: bool, label: str, detail: str = "") -> bool:
    global _FAILURES
    if not cond:
        _FAILURES += 1
    print(f"{'PASS' if cond else 'FAIL'}: {label}" + (f"  [{detail}]" if detail else ""))
    return cond


def _fn(tool_name: str):
    """Unwrap the plain callable behind a FastMCP @tool (robust across versions)."""
    obj = getattr(M, tool_name, None)
    if callable(obj):
        return obj
    raise RuntimeError(f"tool {tool_name!r} not found on mcp_server")


def main() -> int:
    start = _fn("start")
    snapshot = _fn("snapshot")
    send_line = _fn("send_line")
    wait_regex = _fn("wait_regex")
    close = _fn("close")
    list_sessions = _fn("list_sessions")
    alive = _fn("alive")

    print(f"REG_DIR={REG_DIR}")
    sid = ""
    try:
        # --- start ---
        r = start(cmd="python", cols=80, rows=24)
        sid = r.get("sid", "")
        if not check(r.get("ok") and bool(sid), "start returns a sid", detail=str(r)):
            return 1

        # --- wait for the REPL prompt (readiness sync, not a blind sleep) ---
        r = wait_regex(sid=sid, pattern=">>> ", timeout_ms=15000)
        check(r.get("ok") and r.get("matched"), "wait_regex matches the prompt",
              detail=f"matched={r.get('matched')}")

        # --- alive ---
        r = alive(sid=sid)
        check(r.get("ok") and r.get("alive"), "alive reports the child running")

        # --- act: run a line, wait for its result, confirm via snapshot ---
        check(send_line(sid=sid, text="print(6*7)").get("ok"), "send_line ok")
        r = wait_regex(sid=sid, pattern="42", timeout_ms=15000)
        check(r.get("ok") and r.get("matched"), "wait_regex sees the computed 42")

        r = snapshot(sid=sid)
        check(r.get("ok") and "42" in r.get("text", ""),
              "snapshot text contains 42 (token auto-attached, no leak)",
              detail=repr(r.get("text", "")[-50:]))

        # --- close ---
        check(close(sid=sid).get("ok"), "close ok")
        sid = ""

        # --- no leaked sessions in the isolated dir ---
        r = list_sessions()
        n = len(r.get("sessions", []))
        check(r.get("ok") and n == 0, "no leaked sessions after close", detail=f"{n} listed")
    finally:
        if sid:
            try:
                close(sid=sid)
            except Exception:
                pass
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
