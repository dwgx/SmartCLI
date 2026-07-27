#!/usr/bin/env python3
"""_tmux_launcher_probe.py — verify the cmd-art tmux launchers on a REAL tmux.

`skills/cmd-art/tmux/fx-split.sh` and `fx-popup.sh` shipped unverified for the
project's whole life: the dev box had no tmux, so both HANDOFF and NEXT-STEPS
carried "tmux launchers need a real tmux host" as a permanent open item. This
probe closes that gap wherever tmux exists, and it found a real bug doing so
(fx-popup exited 1 with tmux's cryptic "no current client" when the session had
no attached client, violating its own documented clean-exit contract).

What is asserted:
  * no tmux on PATH        -> both scripts explain themselves and exit 0
  * tmux, but no $TMUX     -> both refuse with the "start one first" message
  * tmux, detached session -> fx-popup refuses cleanly (a popup needs a client)
  * tmux, real client       -> fx-popup actually runs (exit 0)
  * tmux session            -> fx-split really splits the window and renders

RED LINE COMPLIANCE: one tmux server at a time, killed between cases and in a
finally block; the attached client is a single short-lived pty child; zero
residue asserted at the end. tmux runs with `-f /dev/null` so the user's own
config cannot affect the result.

Exit 0 = pass. SKIP (exit 0) when tmux is absent.
"""
from __future__ import annotations

import os
import pty
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TMUX_DIR = ROOT / "skills" / "cmd-art" / "tmux"
SPLIT = TMUX_DIR / "fx-split.sh"
POPUP = TMUX_DIR / "fx-popup.sh"

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

FAILURES: list[str] = []


def check(cond: bool, label: str, detail: str = "") -> None:
    if not cond:
        FAILURES.append(label)
    print(f"  [{'PASS' if cond else 'FAIL'}] {label}" + (f"  {detail}" if detail and not cond else ""))


def tm(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["tmux", "-f", "/dev/null", *args],
                          capture_output=True, text=True, timeout=30)


def kill_server() -> None:
    subprocess.run(["tmux", "-f", "/dev/null", "kill-server"],
                   capture_output=True, text=True, timeout=30)


def run_in_pane(session: str, script: Path, args: str, logfile: Path,
                settle: float = 4.0) -> tuple[int, str]:
    """Run a launcher inside a pane's shell (so $TMUX is set) and read its rc."""
    cmd = (f"sh '{script}' {args} 2>'{logfile}'; echo RC=$? >>'{logfile}'")
    tm("send-keys", "-t", session, cmd, "Enter")
    deadline = time.time() + settle
    while time.time() < deadline:
        if logfile.exists() and "RC=" in logfile.read_text(errors="replace"):
            break
        time.sleep(0.2)
    text = logfile.read_text(errors="replace") if logfile.exists() else ""
    rc = -1
    for line in text.splitlines():
        if line.startswith("RC="):
            rc = int(line[3:].strip())
    return rc, text


def main() -> int:
    if subprocess.run(["which", "tmux"], capture_output=True).returncode != 0:
        print("SKIP: tmux not on PATH (this probe needs a real tmux host)")
        return 0
    ver = subprocess.run(["tmux", "-V"], capture_output=True, text=True).stdout.strip()
    print("=" * 68)
    print(f"cmd-art tmux launchers on a real tmux  |  {ver}")
    print("=" * 68)

    tmpdir = Path(os.environ.get("TMPDIR", "/tmp")) / f"fxtmux_{os.getpid()}"
    tmpdir.mkdir(parents=True, exist_ok=True)

    try:
        # 1. No tmux at all: the documented clean-exit fallback.
        print("\n--- no tmux on PATH: clean exit 0 ---")
        env = {**os.environ, "PATH": "/usr/bin:/bin"}
        for name, script in (("fx-split", SPLIT), ("fx-popup", POPUP)):
            cp = subprocess.run(["sh", str(script), "donut"], capture_output=True,
                                text=True, env=env, timeout=60)
            check(cp.returncode == 0, f"{name}: exits 0 without tmux",
                  detail=f"rc={cp.returncode}")
            check("tmux is not installed" in cp.stdout + cp.stderr,
                  f"{name}: explains that tmux is missing")

        # 2. tmux present but not inside a session.
        print("\n--- tmux present, not inside a session: refuse clearly ---")
        for name, script in (("fx-split", SPLIT), ("fx-popup", POPUP)):
            cp = subprocess.run(["sh", str(script), "donut"], capture_output=True,
                                text=True, env={k: v for k, v in os.environ.items()
                                                if k != "TMUX"}, timeout=60)
            check(cp.returncode == 4, f"{name}: exit 4 when not inside tmux",
                  detail=f"rc={cp.returncode}")
            check("not inside a tmux session" in cp.stderr,
                  f"{name}: says to start a session first")

        # 3. fx-split inside a real session must actually split.
        print("\n--- fx-split in a real session: window really splits ---")
        kill_server()
        tm("new-session", "-d", "-s", "fxprobe", "-x", "100", "-y", "30")
        time.sleep(0.5)
        before = len(tm("list-panes", "-t", "fxprobe").stdout.splitlines())
        rc, text = run_in_pane("fxprobe", SPLIT, "donut --seconds 4",
                               tmpdir / "split.log", settle=5.0)
        after = len(tm("list-panes", "-t", "fxprobe").stdout.splitlines())
        check(rc == 0, "fx-split: exit 0 inside a session", detail=f"rc={rc} {text[:120]!r}")
        check(after == before + 1, "fx-split: pane count grew by one",
              detail=f"before={before} after={after}")
        pane1 = tm("capture-pane", "-p", "-t", "fxprobe.1").stdout
        check(bool(pane1.strip()), "fx-split: the new pane is rendering an effect",
              detail=repr(pane1[:80]))
        kill_server()

        # 4. fx-popup in a DETACHED session: must refuse cleanly, not emit
        #    tmux's raw "no current client" with a non-zero rc. This is the bug
        #    this probe found.
        print("\n--- fx-popup, detached session: refuses cleanly ---")
        tm("new-session", "-d", "-s", "fxpop", "-x", "90", "-y", "24")
        time.sleep(0.5)
        rc, text = run_in_pane("fxpop", POPUP, "plasma --seconds 3",
                               tmpdir / "pop_detached.log", settle=5.0)
        check(rc == 4, "fx-popup: exit 4 with no attached client", detail=f"rc={rc}")
        check("no attached client" in text,
              "fx-popup: explains the popup needs a client", detail=repr(text[:140]))
        check("no current client" not in text.replace("no current client\")", ""),
              "fx-popup: does not leak tmux's raw error", detail=repr(text[:140]))
        kill_server()

        # 5. fx-popup WITH a real attached client: it must actually run.
        print("\n--- fx-popup, real attached client: runs ---")
        tm("new-session", "-d", "-s", "fxpop2", "-x", "90", "-y", "24")
        time.sleep(0.5)
        pid, fd = pty.fork()
        if pid == 0:  # child: a genuine tmux client on a real pty
            os.execvp("tmux", ["tmux", "-f", "/dev/null", "attach", "-t", "fxpop2"])
        try:
            time.sleep(2.0)
            clients = len([ln for ln in tm("list-clients", "-t", "fxpop2").stdout
                           .splitlines() if ln.strip()])
            check(clients >= 1, "a real client is attached", detail=f"clients={clients}")
            rc, text = run_in_pane("fxpop2", POPUP, "plasma --seconds 3",
                                   tmpdir / "pop_attached.log", settle=8.0)
            check(rc == 0, "fx-popup: exit 0 with a client attached",
                  detail=f"rc={rc} {text[:140]!r}")
        finally:
            try:
                os.close(fd)
            except OSError:
                pass
            try:
                os.kill(pid, 15)
                os.waitpid(pid, 0)
            except (OSError, ChildProcessError):
                pass
            kill_server()
    finally:
        kill_server()
        for f in tmpdir.glob("*"):
            try:
                f.unlink()
            except OSError:
                pass
        try:
            tmpdir.rmdir()
        except OSError:
            pass

    # Zero residue.
    cp = subprocess.run(["tmux", "-f", "/dev/null", "list-sessions"],
                        capture_output=True, text=True)
    leaked = [ln for ln in cp.stdout.splitlines()
              if ln.startswith(("fxprobe", "fxpop"))]
    check(not leaked, "zero leaked tmux sessions", detail=str(leaked))

    if FAILURES:
        print(f"\n_tmux_launcher_probe FAIL -- {len(FAILURES)} check(s):")
        for f in FAILURES:
            print("   -", f)
        return 1
    print("\nPASS: both tmux launchers verified on a real tmux host.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
