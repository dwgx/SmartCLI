#!/usr/bin/env python3
"""mcp_server.py — expose the drive-tui daemon's verb surface as an MCP server.

Any MCP client (Claude Desktop, an agent framework, etc.) can then drive
interactive TUI programs through the same perceive -> act -> confirm loop the
CLI offers, without shelling out to `tui.py` by hand.

It reuses `tui.py`'s existing client layer verbatim — `_read_reg` /
`_send_request` — so the **per-session capability token is loaded from the 0600
registry file and attached automatically**, exactly as the CLI does. No verb is
ever exposed unauthenticated: every tool that touches a live session goes
through `_call_session`, which reads the token from the reg file the daemon
wrote. A client that cannot read that per-user file cannot drive the session.

The daemon itself binds 127.0.0.1 only (no network surface) — this server is a
thin MCP adapter in front of that same local control plane.

Run it (stdio transport, the MCP default):

    python skills/drive-tui/scripts/mcp_server.py

or register it with an MCP client pointing at this path. Requires the `mcp`
package (``pip install "smartcli-toolkit[mcp]"`` or ``pip install mcp``).
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

# Reuse tui.py's client layer (token auto-load, socket transport) rather than
# re-implementing the protocol — that keeps auth behavior identical and means a
# protocol change only has to happen in one place.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import smartcli_bootstrap  # noqa: E402

smartcli_bootstrap.locate_core()

import tui as _tui  # noqa: E402  (tui.py in the same dir)

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    sys.stderr.write(
        "error: the 'mcp' package is required for the MCP server.\n"
        "  pip install \"smartcli-toolkit[mcp]\"   (or: pip install mcp)\n")
    raise SystemExit(2)

TUI_PY = str(Path(_tui.__file__).resolve())
PY = sys.executable

mcp = FastMCP("smartcli-drive-tui")


def _call_session(sid: str, req: dict, timeout: float = 30.0) -> dict:
    """Send one authenticated request to a session daemon.

    Delegates to tui.py's `_call`, which reads the per-session token from the
    reg file and attaches it — so this adapter never has to handle the token
    itself, and an unauthenticated verb is impossible by construction. tui.py's
    client raises SystemExit on a transport/daemon error (it's CLI-first); we
    translate that into a structured error dict for the MCP client instead.
    """
    try:
        return _tui._call(sid, req, timeout=timeout)
    except SystemExit as exc:
        return {"ok": False, "error": str(exc)}


@mcp.tool()
def start(cmd: str, cols: int = 100, rows: int = 24, sid: str = "") -> dict:
    """Spawn a program in a new detached, persistent session and return its id.

    The session survives across tool calls (a localhost-only daemon owns the live
    PtySession). `cmd` is the command line to spawn, e.g. "python" or "lazygit".
    Returns {"ok", "sid"} on success. Use the returned sid for every other tool.
    """
    argv = [PY, TUI_PY, "start", "--cmd", cmd, "--cols", str(cols), "--rows", str(rows)]
    if sid:
        argv += ["--id", sid]
    proc = subprocess.run(argv, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=30)
    if proc.returncode != 0:
        return {"ok": False, "error": (proc.stderr or proc.stdout).strip()}
    new_sid = proc.stdout.strip().splitlines()[-1].strip() if proc.stdout.strip() else ""
    return {"ok": True, "sid": new_sid}


@mcp.tool()
def list_sessions() -> dict:
    """List active drive-tui sessions (id, port, pid, command)."""
    proc = subprocess.run([PY, TUI_PY, "list"], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=15)
    sessions = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        fields = dict(part.split("=", 1) for part in line.split("\t") if "=" in part)
        sid = line.split("\t", 1)[0]
        sessions.append({"sid": sid, **fields})
    return {"ok": True, "sessions": sessions}


@mcp.tool()
def snapshot(sid: str, as_json: bool = False) -> dict:
    """Read a semantic snapshot of the session's current screen.

    Returns {"ok", "alive", "text", "json"}: `text` is the rendered screen,
    `json` the structured cell/cursor model. This is the 'perceive' step —
    always snapshot after acting rather than assuming an action landed.
    """
    resp = _call_session(sid, {"action": "snapshot"})
    if not resp.get("ok"):
        return resp
    out = {"ok": True, "alive": resp.get("alive"), "text": resp.get("text", "")}
    if as_json:
        out["json"] = resp.get("json")
    return out


@mcp.tool()
def close(sid: str) -> dict:
    """Terminate a session and its daemon. Always close sessions when done."""
    return _call_session(sid, {"action": "close"})


@mcp.tool()
def send_text(sid: str, text: str) -> dict:
    """Type literal text into the session (no Enter). Use for filling fields."""
    return _call_session(sid, {"action": "send_text", "text": text})


@mcp.tool()
def send_line(sid: str, text: str) -> dict:
    """Type text followed by Enter — the common 'run this command' action."""
    return _call_session(sid, {"action": "send_line", "text": text})


@mcp.tool()
def send_keys(sid: str, keys: list[str]) -> dict:
    """Send key tokens, e.g. ["Down", "Down", "Enter"], ["C-c"], ["M-x"].

    Arrow keys adapt to the app's cursor-key mode (SS3 under DECCKM, CSI else),
    so menu navigation works in curses apps.
    """
    return _call_session(sid, {"action": "send_keys", "keys": keys})


@mcp.tool()
def wait_regex(sid: str, pattern: str, timeout_ms: int = 10000) -> dict:
    """Block until `pattern` (a regex) appears on screen, then snapshot.

    Returns {"ok", "matched", "alive", "text", "json"}. This is the readiness
    sync — prefer it over a blind delay after send_line/send_keys.
    """
    return _call_session(sid, {"action": "wait_regex", "pattern": pattern,
                               "timeout_ms": timeout_ms},
                         timeout=timeout_ms / 1000.0 + 15.0)


@mcp.tool()
def wait_ready(sid: str, marker: str = "", max_wait_ms: int = 10000,
               quiet_ms: int = 200) -> dict:
    """Wait for a regex `marker` OR for the screen to go quiet (stable), then
    snapshot. Use marker="" to wait purely for stability."""
    return _call_session(sid, {"action": "wait_ready", "marker": marker or None,
                               "max_wait_ms": max_wait_ms, "quiet_ms": quiet_ms},
                         timeout=max_wait_ms / 1000.0 + 15.0)


@mcp.tool()
def alive(sid: str) -> dict:
    """Check whether the session's child process is still running."""
    return _call_session(sid, {"action": "alive"})


@mcp.tool()
def resize(sid: str, cols: int, rows: int) -> dict:
    """Resize the session's terminal to cols x rows."""
    return _call_session(sid, {"action": "resize", "cols": cols, "rows": rows})


def main() -> int:
    # stdio transport is the MCP default; the client launches this process and
    # speaks JSON-RPC over stdin/stdout.
    mcp.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
