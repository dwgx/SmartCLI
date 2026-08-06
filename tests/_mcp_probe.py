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
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# Isolated registry dir: hermetic, no collision with real sessions.
REG_DIR = Path(tempfile.mkdtemp(prefix="mcp_probe_"))
os.environ["SMARTCLI_TUI_DIR"] = str(REG_DIR)
os.environ["PYTHONIOENCODING"] = "utf-8"

if not os.environ.get("SMARTCLI_TEST_INSTALLED"):
    sys.path.insert(0, str(REPO_ROOT / "skills" / "drive-tui" / "scripts"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
except Exception:
    pass

try:
    if os.environ.get("SMARTCLI_TEST_INSTALLED"):
        from smartcli_drive import mcp_server as M  # noqa: E402
    else:
        import mcp_server as M  # type: ignore[no-redef]  # noqa: E402
except SystemExit:
    # mcp_server raises SystemExit(2) when the `mcp` package is absent. That's a
    # missing optional dependency, not a failure — skip cleanly so run_all
    # reports skip-with-note rather than a red gate.
    print("SKIP: the 'mcp' package is not installed — MCP server probe skipped.")
    try:
        REG_DIR.rmdir()
    except OSError:
        pass
    raise SystemExit(0) from None

_FAILURES = 0


def python_repl_command() -> str:
    argv = [sys.executable, "-i", "-q"]
    return subprocess.list2cmdline(argv) if os.name == "nt" else shlex.join(argv)


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
    send_keys = _fn("send_keys")

    print(f"REG_DIR={REG_DIR}")

    # The `initialize` handshake's serverInfo is what MCP directories display.
    # FastMCP does not forward a version to the Server it wraps, so without an
    # explicit assignment this reported the MCP SDK's version (1.28.1) while the
    # package was 0.2.0 — indistinguishable from a bogus version claim.
    reported = getattr(M.mcp._mcp_server, "version", None)
    expected = M._our_version()
    check(reported == expected and reported not in (None, "0.0.0+unknown"),
          "serverInfo reports this package's version, not the SDK's",
          detail=f"reported={reported!r} expected={expected!r}")

    sid = ""
    try:
        # --- start ---
        r = start(
            cmd=python_repl_command(),
            cols=80,
            rows=24,
            cwd=str(REG_DIR),
            env={"SMARTCLI_MCP_PROBE": "present"},
        )
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

        r = snapshot(sid=sid, as_json=True)
        check(r.get("ok") and "42" in r.get("text", ""),
              "snapshot text contains 42 (token auto-attached, no leak)",
              detail=repr(r.get("text", "")[-50:]))
        check(isinstance(r.get("json"), dict),
              "snapshot JSON is structured, not a nested JSON string")
        check(isinstance(r.get("hash"), int) and isinstance(r.get("visual_hash"), int),
              "snapshot exposes text and visual baselines")
        # The snapshot tool rebuilds its reply as a hand-written allowlist, and
        # alt_screen was missing from it: the daemon sent the field, the CLI
        # printed it, and only MCP clients were blind to whether a full-screen
        # program owned the screen. Assert the KEY is present rather than just
        # its value — a dropped field and a genuine False are the same thing to
        # `.get()`, which is exactly why this went unnoticed.
        check("alt_screen" in r, "snapshot reply carries alt_screen at all")
        check(r.get("alt_screen") is False,
              "alt_screen is False on a plain REPL (no full-screen program)",
              detail=repr(r.get("alt_screen")))

        check(send_line(
            sid=sid,
            text="import os; print('MCPENV', os.getenv('SMARTCLI_MCP_PROBE'))",
        ).get("ok"), "send_line for MCP env probe ok")
        r = wait_regex(sid=sid, pattern="MCPENV present", timeout_ms=15000)
        check(r.get("ok") and r.get("matched"), "MCP start forwards cwd/env")

        # --- close ---
        check(close(sid=sid).get("ok"), "close ok")
        check(close(sid=sid).get("ok"), "close is idempotent")
        sid = ""

        # --- no leaked sessions in the isolated dir ---
        # close() returns as soon as the daemon has SENT its ok reply; the daemon
        # then unlinks its reg file in a finally block, so there's a brief window
        # where `list` can still see it. Poll for it to clear (bounded) instead of
        # asserting instantly — a marker/condition is a fact, a bare timing guess
        # is not.
        n = -1
        for _ in range(20):  # up to ~5s
            r = list_sessions()
            n = len(r.get("sessions", []))
            if r.get("ok") and n == 0:
                break
            time.sleep(0.25)
        check(n == 0, "no leaked sessions after close (polled)", detail=f"{n} listed")

        # --- alt_screen must report TRUE while a full-screen program owns the
        # screen. The False assertion above cannot catch a dropped field, because a
        # missing key and a genuine False are the same thing to `.get()` — which is
        # precisely how the omission went unnoticed. So drive the state that matters.
        #
        # This needs a REAL full-screen program, not a REPL writing the escape
        # itself: `python -i` on a PTY does not execute queued lines promptly, so the
        # sequence only gets ECHOED and never runs. An echoed payload matching your
        # own wait pattern is a false PASS (the trap recorded in HANDOFF 10g).
        # `less` is used WITHOUT -X on purpose: -X disables the alternate screen,
        # i.e. the feature under test (HANDOFF 10i, one of three rig mistakes).
        #
        # Serial by construction: this session starts only after the one above is
        # closed and confirmed leak-free, per the one-PTY-at-a-time red line.
        if shutil.which("less"):
            fixture = REG_DIR / "altscreen_fixture.txt"
            fixture.write_text("\n".join(str(i) for i in range(1, 201)), encoding="utf-8")
            r = start(cmd=f"less {fixture}", cols=80, rows=24)
            sid = r.get("sid", "")
            check(bool(sid), "start real less for the alt-screen check", detail=repr(r))
            r = wait_regex(sid=sid, pattern="1", timeout_ms=15000)
            check(r.get("ok") and r.get("matched"), "less painted its first page")
            r = snapshot(sid=sid)
            check(r.get("alt_screen") is True,
                  "alt_screen is True while a full-screen program owns the screen",
                  detail=repr(r.get("alt_screen")))
            check(send_keys(sid=sid, keys=["q"]).get("ok"), "send q to quit less")
            time.sleep(1.0)
            r = snapshot(sid=sid)
            check(r.get("alt_screen") is False,
                  "alt_screen is False again once the primary screen is restored",
                  detail=repr(r.get("alt_screen")))
            close(sid=sid)
            sid = ""
        else:
            print("SKIP: less not on PATH — alt_screen True case not exercised")
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
