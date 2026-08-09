#!/usr/bin/env python3
"""mcp_stdio_smoke.py — speak real JSON-RPC to an MCP server over stdio and
assert the answers an MCP directory would check.

WHY THIS EXISTS
---------------
`docker.yml` built and pushed the image but never RAN it, so `CMD ["mcp"]` had
shipped in three releases with no automated test ever starting it. That is
exactly how a directory (Glama, Docker's MCP catalog) validates a server: run the
image with no arguments and speak JSON-RPC to its stdin. This project has already
been bitten there twice —

  * the image once defaulted to `CMD ["fx gallery"]`, so a directory would have
    received an ANIMATION on stdout and scored the server broken;
  * `serverInfo` once reported the MCP SDK's version (1.28.1) instead of ours,
    because FastMCP does not forward a version to the `Server` it wraps, and that
    value is what directory pages display.

Both are invisible to a build that merely succeeds. This script makes them
observable, and it is deliberately transport-agnostic so the same assertions run
against a container (`docker run -i <tag>`) and against a bare interpreter.

USAGE
-----
    python tools/mcp_stdio_smoke.py --expect-version 0.2.2 -- docker run -i --rm <tag>
    python tools/mcp_stdio_smoke.py -- python skills/drive-tui/scripts/mcp_server.py

With no `--expect-version`, the version is read from `pyproject.toml`, so CI does
not have to restate it (a restated constant is a tenth version site waiting to
drift — see `tests/test_version_sync.py`).

PROTOCOL NOTE, learned the hard way: the server does not answer `tools/list`
until it has received the `notifications/initialized` message between the two
requests. Omitting it hangs forever rather than erroring.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
except Exception:
    pass

#: Tool count is asserted against the live registry rather than a literal, for the
#: same reason test_doc_counts imports the registries: a hard-coded number here
#: would be one more place to drift. Falls back to a literal only if the import
#: is impossible (e.g. running this script against a container from a bare
#: checkout without deps installed), and says so.
EXPECTED_TOOL_COUNT_FALLBACK = 14

FAILURES: list[str] = []


def check(cond: bool, label: str, detail: str = "") -> None:
    print(f"  [{'PASS' if cond else 'FAIL'}] {label}" + (f"  {detail}" if detail and not cond else ""))
    if not cond:
        FAILURES.append(label)


def version_from_pyproject() -> str:
    """Read the reference version with a regex, not tomllib.

    tomllib is stdlib only from 3.11 while this project's floor is 3.10, and a
    gate that cannot run on the floor it supports is a defect this repo has
    already shipped once (HANDOFF 10h). test_version_sync.py uses regexes for
    exactly this reason; follow the precedent.
    """
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.M)
    if not m:
        raise SystemExit("error: could not read version from pyproject.toml")
    return m.group(1)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--expect-version", default=None,
                    help="version serverInfo must report (default: from pyproject.toml)")
    ap.add_argument("--timeout", type=float, default=90.0,
                    help="hard cap on the whole exchange (default 90s; a container "
                         "pulling/starting is slower than an interpreter)")
    ap.add_argument("cmd", nargs=argparse.REMAINDER,
                    help="-- followed by the command that starts the server on stdio")
    args = ap.parse_args()

    cmd = [a for a in args.cmd if a != "--"]
    if not cmd:
        raise SystemExit("error: give the server command after `--`, e.g. "
                         "`-- docker run -i --rm ghcr.io/dwgx/smartcli`")

    want_version = args.expect_version or version_from_pyproject()

    print("=" * 70)
    print("MCP stdio smoke — the check an MCP directory performs")
    print("=" * 70)
    print(f"server command : {' '.join(cmd)}")
    print(f"expected version: {want_version}")

    # Speak like a REAL client: send, wait for the reply, then send the next.
    #
    # The first version of this wrote all three messages at once via
    # `subprocess.run(input=...)`, which closes stdin immediately. The server then
    # races its own reply against EOF, and loses: measured 5/5 locally with
    # `tools/list` never answered while stderr showed "Processing request of type
    # ListToolsRequest" — it had started the work and the process was torn down
    # underneath it. The three CI runs that passed before were timing luck, which
    # is worse than a red gate: it published a green check for an exchange that had
    # not completed. An MCP directory holds the pipe open, so matching that is also
    # the more faithful test.
    try:
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE)
    except FileNotFoundError:
        raise SystemExit(f"error: cannot execute {cmd[0]!r} — is it installed and on PATH?")

    out_lines: list[str] = []
    err_text = ""

    def send(obj: dict) -> None:
        assert proc.stdin is not None
        proc.stdin.write((json.dumps(obj) + "\n").encode("utf-8"))
        proc.stdin.flush()

    def read_reply(deadline: float) -> str:
        """One line from stdout, or '' if the server died / ran out of time."""
        assert proc.stdout is not None
        while time.monotonic() < deadline:
            line = proc.stdout.readline()
            if not line:
                return ""
            text = line.decode("utf-8", errors="replace").strip()
            if text:
                out_lines.append(text)
                return text
        return ""

    deadline = time.monotonic() + args.timeout
    try:
        send({"jsonrpc": "2.0", "id": 1, "method": "initialize",
              "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                         "clientInfo": {"name": "smartcli-smoke", "version": "0"}}})
        read_reply(deadline)
        # NOT optional: without it the server never answers `tools/list`.
        send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        send({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        read_reply(deadline)
    except (BrokenPipeError, OSError):
        pass  # the checks below report it against what did arrive
    finally:
        try:
            if proc.stdin is not None:
                proc.stdin.close()
        except OSError:
            pass
        try:
            proc.terminate()
            _, err_bytes = proc.communicate(timeout=10)
            err_text = err_bytes.decode("utf-8", errors="replace") if err_bytes else ""
        except Exception:  # noqa: BLE001
            proc.kill()

    out = "\n".join(out_lines)
    err = err_text

    replies: dict[int, dict] = {}
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            # Non-JSON on stdout is itself the `fx gallery` failure mode: a
            # directory speaking JSON-RPC would choke on it. Reported below.
            continue
        if isinstance(msg, dict) and isinstance(msg.get("id"), int):
            replies[msg["id"]] = msg

    print()
    # 1. stdout must be JSON-RPC and nothing else. This is the assertion that
    #    catches a demo-by-default CMD, which is the bug that shipped once.
    non_json = [ln for ln in out.splitlines()
                if ln.strip() and not ln.strip().startswith("{")]
    check(not non_json, "stdout carries only JSON-RPC (no banner/animation)",
          detail=f"{len(non_json)} non-JSON line(s), first={non_json[0][:80]!r}" if non_json else "")

    init = replies.get(1)
    check(init is not None, "initialize was answered",
          detail=f"stdout={out[:200]!r} stderr={err[-300:]!r}")
    if init is None:
        print("\nMCP smoke FAIL — no initialize reply; nothing further can be checked.")
        return 1

    result = init.get("result", {})
    server_info = result.get("serverInfo", {})
    got_version = server_info.get("version")

    # 2. serverInfo must report OUR version, not the SDK's. Directory pages show
    #    this value, so a wrong one reads as a bogus version claim.
    check(got_version == want_version,
          f"serverInfo.version is ours ({want_version})",
          detail=f"got {got_version!r} — the MCP SDK's own version appearing here is a "
                 f"known regression shape (FastMCP does not forward a version)")
    check(bool(server_info.get("name")), "serverInfo.name is present",
          detail=repr(server_info))
    check(bool(result.get("protocolVersion")), "protocolVersion is present",
          detail=repr(result.get("protocolVersion")))

    tools_reply = replies.get(2)
    check(tools_reply is not None,
          "tools/list was answered after notifications/initialized",
          detail=f"stderr={err[-300:]!r}")
    if tools_reply is None:
        print("\nMCP smoke FAIL — no tools/list reply.")
        return 1

    tools = tools_reply.get("result", {}).get("tools", [])
    names = sorted(t.get("name", "") for t in tools)

    expected_count, count_source = _expected_tool_count()
    check(len(tools) == expected_count,
          f"tools/list returns {expected_count} tools ({count_source})",
          detail=f"got {len(tools)}: {','.join(names)}")

    # 3. A directory that lists this server advertises it as a TUI driver, so the
    #    verbs that make that true must be present. Spot-check rather than pin the
    #    whole list: a new tool should not fail this, a missing core verb should.
    for required in ("start", "snapshot", "close", "wait_regex"):
        check(required in names, f"core verb {required!r} is exposed",
              detail=f"have: {','.join(names)}")

    # 4. `snapshot` must advertise alt_screen. It was dropped from the MCP reply
    #    for a whole release because the tool rebuilds its payload from a
    #    hand-written allowlist — the one surface nobody re-checked.
    snap = next((t for t in tools if t.get("name") == "snapshot"), None)
    if snap is not None:
        desc = json.dumps(snap)
        check("alt_screen" in desc, "snapshot advertises alt_screen",
              detail="the MCP reply silently omitted this field for an entire release")

    print()
    if FAILURES:
        print(f"MCP smoke FAIL -- {len(FAILURES)} check(s):")
        for f in FAILURES:
            print("   -", f)
        if err.strip():
            print("\nserver stderr (last 20 lines):")
            for ln in err.strip().splitlines()[-20:]:
                print("  |", ln)
        return 1

    print(f"MCP smoke PASS -- serverInfo {got_version}, {len(tools)} tools, "
          f"stdout is clean JSON-RPC")
    return 0


def _expected_tool_count() -> tuple[int, str]:
    """Count the tools the server actually registers, not a literal."""
    try:
        sys.path.insert(0, str(ROOT / "skills" / "drive-tui" / "scripts"))
        import mcp_server  # type: ignore
        tools = getattr(mcp_server, "mcp", None)
        if tools is not None:
            reg = getattr(tools, "_tool_manager", None)
            if reg is not None and hasattr(reg, "_tools"):
                return len(reg._tools), "counted from the live FastMCP registry"
    except Exception:
        pass
    return EXPECTED_TOOL_COUNT_FALLBACK, "literal fallback — registry not importable here"


if __name__ == "__main__":
    sys.exit(main())
