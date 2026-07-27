#!/usr/bin/env python3
"""mcp_server.py — expose the drive-tui daemon's verb surface as an MCP server.

Any MCP client (Claude Desktop, an agent framework, etc.) can then drive
interactive TUI programs through the same perceive -> act -> confirm loop the
CLI offers, without shelling out to `tui.py` by hand.

Session verbs (snapshot, send_*, wait_*, alive, resize) go through
`_call_session`, a thin wrapper over `tui.py`'s client layer (`_call`), so the
**per-session capability token is loaded from the 0600 registry file and
attached automatically**, exactly as the CLI does. Lifecycle verbs (start,
close, list_sessions) run `tui.py` itself as a subprocess and parse its
`--json` output. No verb is ever exposed unauthenticated: a client that cannot
read the per-user reg file the daemon wrote cannot drive the session.

The daemon itself binds 127.0.0.1 only (no network surface) — this server is a
thin MCP adapter in front of that same local control plane.

Run it (stdio transport, the MCP default):

    python3 skills/drive-tui/scripts/mcp_server.py

or install the package and run ``smartcli-mcp``. The PyPI distribution includes
the MCP runtime dependency.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

# Reuse tui.py's client layer (token auto-load, socket transport) rather than
# re-implementing the protocol — that keeps auth behavior identical and means a
# protocol change only has to happen in one place. The fallback preserves direct
# execution from a standalone copied skill.
try:
    from . import smartcli_bootstrap
except ImportError:  # pragma: no cover - exercised by direct script probes
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import smartcli_bootstrap  # type: ignore[no-redef]  # noqa: E402

smartcli_bootstrap.locate_core()

try:
    from . import tui as _tui
except ImportError:  # pragma: no cover - exercised by direct script probes
    import tui as _tui  # type: ignore[no-redef]  # noqa: E402

try:
    from mcp.server.fastmcp import FastMCP
    from mcp.types import ToolAnnotations
except ImportError:
    sys.stderr.write(
        "error: the 'mcp' package is required for the MCP server.\n"
        "  pip install smartcli-toolkit   (or: pip install mcp)\n")
    raise SystemExit(2) from None

TUI_PY = str(Path(_tui.__file__).resolve())
PY = sys.executable

def _our_version() -> str:
    """This package's version, for the MCP `serverInfo` handshake.

    Without an explicit version FastMCP reports the MCP SDK's own version, so
    `initialize` answered `1.28.1` while the package was 0.2.0 — which is what
    MCP directories display, and it reads like a bogus version claim. Resolved
    from installed metadata first so it stays correct without a second bump site.
    """
    try:
        from importlib.metadata import version
        return version("smartcli-toolkit")
    except Exception:
        pass
    try:  # source checkout, package not installed
        from smartcli_core import __version__
        return __version__
    except Exception:
        return "0.0.0+unknown"


mcp = FastMCP("smartcli-drive-tui")
# FastMCP does not forward a version to the low-level Server it wraps, so set it
# on that object directly; it is what the `initialize` handshake reports.
mcp._mcp_server.version = _our_version()


def _call_session(sid: str, req: dict, timeout: float = 30.0) -> dict:
    """Send one authenticated request to a session daemon.

    Delegates to tui.py's `_call`, which reads the per-session token from the
    reg file and attaches it — so this adapter never has to handle the token
    itself, and an unauthenticated verb is impossible by construction. tui.py's
    client raises SystemExit on a transport/daemon error (it's CLI-first); we
    translate that into a structured error dict for the MCP client instead.
    """
    try:
        resp = _tui._call(sid, req, timeout=timeout)
        raw_json = resp.get("json")
        if isinstance(raw_json, str):
            try:
                resp["json"] = json.loads(raw_json)
            except json.JSONDecodeError:
                pass
        return resp
    except SystemExit as exc:
        return {"ok": False, "error": str(exc)}


@mcp.tool(annotations=ToolAnnotations(
    title="Start a TUI session",
    readOnlyHint=False, destructiveHint=False, idempotentHint=False,
    openWorldHint=True,  # spawns an arbitrary external program
))
def start(
    cmd: str,
    cols: int = 100,
    rows: int = 30,
    sid: str = "",
    cwd: str = "",
    env: dict[str, str] | None = None,
) -> dict:
    """Spawn a program in a new detached, persistent session and return its id.

    The session survives across tool calls (a localhost-only daemon owns the live
    PtySession). `cmd` is the command line to spawn, e.g. "python3" or
    "lazygit". `cwd` and `env` configure only the controlled child process.
    Returns {"ok", "sid"} on success. Use the returned sid for every other tool.

    Server-side limits (violations return an error): at most 8 concurrent
    sessions by default (tunable via SMARTCLI_MAX_SESSIONS); `sid` must be 1-64
    chars matching [A-Za-z0-9][A-Za-z0-9_.-]*; `env` keys must be valid
    identifiers and may not start with SMARTCLI_TUI_; `cwd` must be an existing
    directory; terminal size is capped at 1000 cols x 500 rows (100000 cells).
    Note: `env` values pass through the process command line briefly (visible
    in `ps`) — avoid secrets.
    """
    argv = [
        PY,
        TUI_PY,
        "start",
        "--cmd",
        cmd,
        "--cols",
        str(cols),
        "--rows",
        str(rows),
        "--json",
    ]
    if sid:
        argv += ["--id", sid]
    if cwd:
        argv += ["--cwd", cwd]
    for key, value in (env or {}).items():
        argv += ["--env", f"{key}={value}"]
    proc = subprocess.run(argv, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=30)
    if proc.returncode != 0:
        return {"ok": False, "error": (proc.stderr or proc.stdout).strip()}
    try:
        result = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"ok": False, "error": "start returned invalid JSON"}
    return result


@mcp.tool(annotations=ToolAnnotations(
    title="List active sessions",
    readOnlyHint=True, destructiveHint=False, idempotentHint=True,
    openWorldHint=False,
))
def list_sessions() -> dict:
    """List active drive-tui sessions.

    Returns {"ok", "sessions"}: each entry carries "sid", "port", "pid",
    "cmd", "cols", "rows", "cwd" and "started".
    """
    proc = subprocess.run([PY, TUI_PY, "list", "--json"], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=15)
    if proc.returncode != 0:
        return {"ok": False, "error": (proc.stderr or proc.stdout).strip()}
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"ok": False, "error": "list returned invalid JSON"}


@mcp.tool(annotations=ToolAnnotations(
    title="Snapshot the screen",
    readOnlyHint=True, destructiveHint=False, idempotentHint=True,
    openWorldHint=False,
))
def snapshot(sid: str, as_json: bool = False) -> dict:
    """Read a semantic snapshot of the session's current screen.

    Returns {"ok", "alive", "text", "hash", "visual_hash"}: `text` is the
    rendered screen; `json` (the structured cell/cursor model) is included only
    when as_json=true. `hash` covers text content only — use it as the
    wait_change baseline; `visual_hash` also covers styling, selection and
    cursor state — use it as the wait_visual_change baseline. Don't mix the
    two. This is the 'perceive' step — always snapshot after acting rather
    than assuming an action landed.
    """
    resp = _call_session(sid, {"action": "snapshot"})
    if not resp.get("ok"):
        return resp
    out = {
        "ok": True,
        "alive": resp.get("alive"),
        "text": resp.get("text", ""),
        "hash": resp.get("hash"),
        "visual_hash": resp.get("visual_hash"),
    }
    if as_json:
        out["json"] = resp.get("json")
    return out


@mcp.tool(annotations=ToolAnnotations(
    title="Close a session",
    readOnlyHint=False, destructiveHint=True,  # terminates the child process
    idempotentHint=True,  # closing an already-closed session is a no-op
    openWorldHint=False,
))
def close(sid: str) -> dict:
    """Terminate a session and its daemon. Always close sessions when done."""
    proc = subprocess.run(
        [PY, TUI_PY, "close", "--id", sid, "--json"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )
    if proc.returncode != 0:
        return {"ok": False, "error": (proc.stderr or proc.stdout).strip()}
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"ok": False, "error": "close returned invalid JSON"}


@mcp.tool(annotations=ToolAnnotations(
    title="Type text",
    readOnlyHint=False, destructiveHint=False, idempotentHint=False,
    openWorldHint=False,
))
def send_text(sid: str, text: str) -> dict:
    """Type literal text into the session (no Enter). Use for filling fields."""
    return _call_session(sid, {"action": "send_text", "text": text})


@mcp.tool(annotations=ToolAnnotations(
    title="Type a line",
    readOnlyHint=False, destructiveHint=False, idempotentHint=False,
    openWorldHint=False,
))
def send_line(sid: str, text: str) -> dict:
    """Type text followed by Enter — the common 'run this command' action."""
    return _call_session(sid, {"action": "send_line", "text": text})


@mcp.tool(annotations=ToolAnnotations(
    title="Send key tokens",
    readOnlyHint=False, destructiveHint=False, idempotentHint=False,
    openWorldHint=False,
))
def send_keys(sid: str, keys: list[str]) -> dict:
    """Send key tokens, e.g. ["Down", "Down", "Enter"], ["C-c"], ["M-x"].

    Named tokens: Enter, Return, Tab, BackTab, Space, Backspace, Delete,
    Escape, Esc, Up, Down, Right, Left, Home, End, PageUp, PageDown, Insert,
    F1-F12. Combos: "C-<char>" or "^<char>" (Ctrl — letters plus @, Space,
    [, \\, ]) and "M-<char>" (Meta/Alt, ESC prefix). Any other token is not
    an error — it is typed as literal text.

    Arrow keys adapt to the app's cursor-key mode (SS3 under DECCKM, CSI else),
    so menu navigation works in curses apps.
    """
    return _call_session(sid, {"action": "send_keys", "keys": keys})


@mcp.tool(annotations=ToolAnnotations(
    title="Wait for a regex",
    readOnlyHint=True,  # waiting/observing doesn't change the program
    destructiveHint=False, idempotentHint=True, openWorldHint=False,
))
def wait_regex(sid: str, pattern: str, timeout_ms: int = 10000) -> dict:
    """Block until `pattern` (a regex) appears on screen, then snapshot.

    Returns {"ok", "matched", "alive", "text", "json"}. Timeout is not an
    error: the call returns ok=true with matched=false plus the final screen
    snapshot. Screen lines are right-padded with spaces — end-anchored
    patterns never match; use unanchored markers. This is the readiness sync —
    prefer it over a blind delay after send_line/send_keys.
    """
    return _call_session(sid, {"action": "wait_regex", "pattern": pattern,
                               "timeout_ms": timeout_ms},
                         timeout=timeout_ms / 1000.0 + 15.0)


@mcp.tool(annotations=ToolAnnotations(
    title="Wait for the screen to change",
    readOnlyHint=True, destructiveHint=False, idempotentHint=True,
    openWorldHint=False,
))
def wait_change(sid: str, baseline_hash: int | None = None, timeout_ms: int = 10000) -> dict:
    """Block until the screen content changes, then snapshot.

    The precise "did my action land?" primitive: call it right after send_line/
    send_keys to wait for ANY change from the baseline (default: the screen at
    call time; or pass a prior `hash` to change away from). Returns {"ok",
    "changed", "hash", "alive", "text", "json"} — `hash` is the new screen hash,
    reusable as the next baseline. Timeout is not an error: the call returns
    ok=true with changed=false plus the final screen snapshot. Can't
    false-positive on text that was already on screen, unlike wait_regex.
    """
    req = {"action": "wait_change", "timeout_ms": timeout_ms}
    if baseline_hash is not None:
        req["baseline_hash"] = baseline_hash
    return _call_session(sid, req, timeout=timeout_ms / 1000.0 + 15.0)


@mcp.tool(annotations=ToolAnnotations(
    title="Wait for a visual screen change",
    readOnlyHint=True, destructiveHint=False, idempotentHint=True,
    openWorldHint=False,
))
def wait_visual_change(
    sid: str,
    baseline_hash: int | None = None,
    timeout_ms: int = 10000,
) -> dict:
    """Wait for text, selection styling, or cursor position to change.

    Prefer this after arrow/navigation keys in full-screen TUIs. Pass a prior
    `visual_hash`, or omit it to use the current rendered state as the baseline.
    Timeout is not an error: the call returns ok=true with changed=false plus
    the final screen snapshot.
    """
    req = {"action": "wait_visual_change", "timeout_ms": timeout_ms}
    if baseline_hash is not None:
        req["baseline_hash"] = baseline_hash
    return _call_session(sid, req, timeout=timeout_ms / 1000.0 + 15.0)


@mcp.tool(annotations=ToolAnnotations(
    title="Wait for any of several patterns",
    readOnlyHint=True, destructiveHint=False, idempotentHint=True,
    openWorldHint=False,
))
def wait_any(sid: str, patterns: list[str], timeout_ms: int = 10000) -> dict:
    """Wait for ANY of `patterns` to appear on screen (pexpect expect([...]) style).

    Race several possible outcomes at once — e.g. patterns=[">>> ", "Error",
    "Password:"] — and learn WHICH happened. Patterns are scanned in list order
    each poll, so the earliest in the list wins a same-poll tie (put the most
    specific first). Screen lines are right-padded with spaces — end-anchored
    patterns never match; use unanchored markers. Returns {"ok", "index",
    "matched", "alive", "text", "json"} where `index` is the 0-based position
    of the matched pattern. Timeout is not an error: the call returns ok=true
    with index=-1 and matched=false plus the final screen snapshot.
    """
    return _call_session(sid, {"action": "wait_any", "patterns": patterns,
                               "timeout_ms": timeout_ms},
                         timeout=timeout_ms / 1000.0 + 15.0)


@mcp.tool(annotations=ToolAnnotations(
    title="Wait for readiness",
    readOnlyHint=True, destructiveHint=False, idempotentHint=True,
    openWorldHint=False,
))
def wait_ready(sid: str, marker: str = "", max_wait_ms: int = 10000,
               quiet_ms: int = 200) -> dict:
    """Wait for a regex `marker` OR for the screen to go quiet (stable), then
    snapshot. Use marker="" to wait purely for stability.

    Returns a snapshot plus `reason`: "MARKER" (the regex appeared), "STABLE"
    (the screen went quiet), or "TIMEOUT". Timeout is not an error: the call
    still returns ok=true with the final screen snapshot. Screen lines are
    right-padded with spaces — end-anchored markers never match; use
    unanchored markers.
    """
    return _call_session(sid, {"action": "wait_ready", "marker": marker or None,
                               "max_wait_ms": max_wait_ms, "quiet_ms": quiet_ms},
                         timeout=max_wait_ms / 1000.0 + 15.0)


@mcp.tool(annotations=ToolAnnotations(
    title="Check if alive",
    readOnlyHint=True, destructiveHint=False, idempotentHint=True,
    openWorldHint=False,
))
def alive(sid: str) -> dict:
    """Check whether the session's child process is still running."""
    return _call_session(sid, {"action": "alive"})


@mcp.tool(annotations=ToolAnnotations(
    title="Resize the terminal",
    readOnlyHint=False, destructiveHint=False,
    idempotentHint=True,  # resizing to the same size again is a no-op
    openWorldHint=False,
))
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
