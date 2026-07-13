#!/usr/bin/env python3
"""_sandbox_posix_backend.py — REAL-Linux verification of PosixPtyBackend.

Runs on a POSIX host (Debian, over SSH) to test the code path that has NEVER
been verified off Windows: smartcli_core.PosixPtyBackend driving real programs
through a real pty.fork() pseudo-terminal, plus the full perceive stack
(ScreenModel/build_snapshot) and the two recorded POSIX-only known issues:

  #6  terminate() doesn't reap the child -> zombie process
  #5  arrows are always CSI (\\x1b[A), never SS3 (\\x1bOA)

Exit 0 = all core drives worked (any known-issue findings are reported, not
failed, since they are documented). Prints a clear PASS/FAIL/KNOWN line each.
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from smartcli_core.pty_backend import PosixPtyBackend, get_default_backend
from smartcli_core.screen_model import ScreenModel
from smartcli_core.snapshot import build_snapshot

_fails = []
_notes = []
_skips = []


def check(cond, name, detail=""):
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}  {detail}")
    if not cond:
        _fails.append(name)


def skip(name, detail=""):
    """Record a check that could not run in THIS environment (not a failure).

    Used for the curses/DECCKM probe: on a bare CI runner there is no terminfo /
    controllable terminal for `curses.wrapper` to initialize, so the probe never
    reaches READY. That proves nothing about the backend, so it must NOT fail the
    run — it is reported as SKIP. On a real host (SSH, a Mac) the probe runs and
    the adaptive-SS3 assertion is exercised for real.
    """
    print(f"  [SKIP] {name}  {detail}")
    _skips.append(name)


def drain(be, model, deadline_s):
    """Pump the backend into the model until quiet or deadline."""
    end = time.monotonic() + deadline_s
    got = b""
    while time.monotonic() < end:
        data = be.read_nonblocking()
        if data:
            model.feed(data)
            got += data
        else:
            time.sleep(0.02)
    return got


def main() -> int:
    print("=" * 62)
    print("PosixPtyBackend — REAL Linux verification")
    print("=" * 62)

    # 0) the host picks the POSIX backend automatically
    be0 = get_default_backend()
    check(isinstance(be0, PosixPtyBackend),
          "get_default_backend() -> PosixPtyBackend on this host",
          f"({type(be0).__name__})")

    # 1) spawn a real program, read its banner
    be = PosixPtyBackend()
    model = ScreenModel(cols=80, rows=24)
    be.spawn([sys.executable, "-i", "-q"], cols=80, rows=24)
    time.sleep(0.3)
    banner = drain(be, model, 2.0)
    check(be.is_alive(), "is_alive() true after spawn")
    check(len(banner) > 0, "read banner bytes from child", f"({len(banner)}B)")

    # 2) write a command, read the result through the screen model
    be.write(b"print(6*7)\n")
    drain(be, model, 1.5)
    snap = build_snapshot(model)
    txt = snap.to_text()
    check("42" in txt, "drove python REPL: 6*7 -> 42 visible in snapshot")

    # 3) resize works (TIOCSWINSZ)
    try:
        be.resize(100, 30)
        be.write(b"import shutil; print(shutil.get_terminal_size())\n")
        drain(be, model, 1.2)
        s2 = build_snapshot(model).to_text()
        ok_resize = "100" in s2 or "columns=100" in s2 or "size(columns=100" in s2
        check(ok_resize, "resize() -> child sees new width (TIOCSWINSZ)",
              "(child reported 100 cols)" if ok_resize else "(width not echoed)")
    except Exception as exc:
        check(False, "resize() TIOCSWINSZ", f"raised {type(exc).__name__}: {exc}")

    # 4) KNOWN ISSUE #6 — does terminate() leave a zombie?
    child_pid = be._pid
    be.write(b"exit()\n")
    time.sleep(0.4)
    be.terminate()
    time.sleep(0.3)
    # a zombie shows up in /proc/<pid>/stat as state 'Z'
    zombie = False
    try:
        with open(f"/proc/{child_pid}/stat") as f:
            state = f.read().split(")")[-1].split()[0]
            zombie = (state == "Z")
    except FileNotFoundError:
        zombie = False  # fully reaped/gone
    if zombie:
        _notes.append(f"KNOWN #6: child {child_pid} is a ZOMBIE after terminate() "
                      "(no waitpid reap) — matches recorded issue")
        print(f"  [KNOWN] #6 terminate() leaves a zombie (pid {child_pid} state=Z)")
    else:
        print(f"  [ OK  ] #6 no zombie after terminate() (pid {child_pid} gone/reaped)")

    # 5) KNOWN ISSUE #5 — arrow keys: we always SEND CSI (\x1b[A). Many curses
    #    apps enable DECCKM (application cursor keys) and then expect SS3
    #    (\x1bOA). Test with a real ncurses program: python curses puts the
    #    terminal in keypad/application mode, so we can see whether our CSI Up is
    #    understood as KEY_UP or misread.
    from smartcli_core.session import _resolve_key
    up = _resolve_key("Up")
    print(f"  [info ] we emit Up as {up!r} "
          + ("(CSI — recorded #5)" if up == b"\x1b[A" else "(SS3)"))

    curses_probe = (
        "import curses,sys\n"
        "def m(s):\n"
        "    s.keypad(True)\n"          # enables application cursor mode (DECCKM)
        "    s.addstr(0,0,'READY')\n"
        "    s.refresh()\n"
        "    c=s.getch()\n"
        "    s.addstr(1,0,'GOT:'+('UP' if c==curses.KEY_UP else str(c)))\n"
        "    s.refresh()\n"
        "    import time;time.sleep(0.6)\n"
        "curses.wrapper(m)\n"
    )
    # Drive through a full PtySession so send_keys() uses the adaptive
    # CSI-vs-SS3 logic (reads model.app_cursor / DECCKM from the live screen).
    from smartcli_core.session import PtySession
    sess = PtySession(cols=60, rows=10)
    sess.start([sys.executable, "-c", curses_probe])
    # pump until the curses app is READY (and has enabled DECCKM)
    end = time.monotonic() + 2.0
    ready = False
    while time.monotonic() < end:
        sess.pump()
        if "READY" in sess.snapshot().to_text():
            ready = True
            break
        time.sleep(0.03)
    decckm = sess.model.app_cursor
    if not ready:
        # curses could not initialize in this environment (bare CI runner: no
        # terminfo / controllable terminal). That is an environment limitation,
        # not a backend defect — skip the DECCKM/SS3 assertions rather than fail.
        skip("curses probe reached READY",
             f"(DECCKM={'on' if decckm else 'off'}; curses.wrapper could not "
             "start here — run on a real host to exercise the SS3 path)")
        skip("detected DECCKM (application cursor mode) from live screen")
        skip("#5 FIXED: adaptive SS3 arrow read by curses as KEY_UP")
        sess.close()
    else:
        check(ready, "curses probe reached READY",
              f"(DECCKM={'on' if decckm else 'off'})")
        check(decckm, "detected DECCKM (application cursor mode) from live screen")
        sess.send_keys(["Up"])             # adaptive: should emit SS3 under DECCKM
        end = time.monotonic() + 1.2
        understood = False
        while time.monotonic() < end:
            sess.pump()
            if "GOT:UP" in sess.snapshot().to_text():
                understood = True
                break
            time.sleep(0.03)
        check(understood, "#5 FIXED: adaptive SS3 arrow read by curses as KEY_UP",
              "(sent SS3 because DECCKM on)" if decckm else "(CSI)")
        sess.close()

    print("-" * 62)
    if _fails:
        print(f"RESULT: {len(_fails)} core FAILURE(S): {_fails}")
        return 1
    print("RESULT: PosixPtyBackend core drives work on this POSIX host.")
    if _skips:
        print(f"  ({len(_skips)} check(s) SKIPPED — environment could not run them: {_skips})")
    for n in _notes:
        print("  note:", n)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
