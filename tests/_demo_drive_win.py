#!/usr/bin/env python3
"""_demo_drive_win.py — real-TUI drive-and-capture on WINDOWS (ConPTY), 30fps.

The Windows counterpart to the Linux/mac drivers: drives real TUIs through
smartcli_core's WinptyBackend (ConPTY via pywinpty), capturing full-colour ANSI
frames at 30fps into %TEMP%/winframes/<target>/. This is SmartCLI's differentiator
shown, not asserted — driving a real curses TUI on native Windows, no WSL/Cygwin.

One PTY session at a time, closed before the next (spawn red-line). ConPTY notes:
the first prompt can lag ~3s, so we use a strict wait-regex with a generous
timeout for startup, never a bare wait.

Usage:  python tests/_demo_drive_win.py all
"""
from __future__ import annotations

import os
import sys
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
from smartcli_core import PtySession

CAP_FPS = 30
CAP_DT = 1.0 / CAP_FPS
TEMP = os.environ.get("TEMP", os.environ.get("TMP", "."))
DEMO = os.path.join(TEMP, "smartcli-demo")
LAZYGIT = os.path.expanduser(
    r"~\AppData\Local\Microsoft\WinGet\Links\lazygit.exe")


def _screen_to_ansi(screen) -> bytes:
    out = ["\x1b[2J\x1b[H"]

    def sgr(ch):
        codes = []
        if ch.reverse:
            codes.append("7")
        if ch.bold:
            codes.append("1")
        NAMED = {"black": 0, "red": 1, "green": 2, "brown": 3, "yellow": 3,
                 "blue": 4, "magenta": 5, "cyan": 6, "white": 7}

        def col(c, fgbase, ansibase):
            if not c or c == "default":
                return None
            if len(c) == 6:
                try:
                    r, g, b = int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
                    return f"{fgbase};2;{r};{g};{b}"
                except ValueError:
                    return None
            if c in NAMED:
                return str(ansibase + NAMED[c])
            return None

        f = col(ch.fg, "38", 30)
        if f:
            codes.append(f)
        b = col(ch.bg, "48", 40)
        if b:
            codes.append(b)
        return "\x1b[0;" + ";".join(codes) + "m" if codes else "\x1b[0m"

    for y in range(screen.lines):
        row = screen.buffer[y]
        out.append("".join(sgr(row[x]) + (row[x].data or " ")
                          for x in range(screen.columns)) + "\x1b[0m\r\n")
    return "".join(out).encode("utf-8", "replace")


# (argv, cols, rows, ready_regex, quit_keys, [ (label, keys|None, seconds) ])
SCRIPTS = {
    "lazygit-win": ([LAZYGIT, "-p", DEMO], 100, 30,
                    r"(Files|Status|Commits|lazygit)", ["q"], [
        ("perceive — lazygit on native Windows (ConPTY)", None, 1.2),
        ("act — Enter: dismiss the welcome popup", ["Enter"], 0.9),
        ("act — key 4: focus the Commits panel", ["4"], 0.7),
        ("act — Down: older commit (SS3 arrow via ConPTY)", ["Down"], 0.5),
        ("act — Down: and the next", ["Down"], 0.5),
        ("confirm — Enter: open that commit's diff", ["Enter"], 1.2),
        ("act — Esc: back to the commit list", ["Escape"], 0.7),
        ("act — key 3: focus Local branches", ["3"], 0.6),
        ("act — Down: highlight feature/auth", ["Down"], 0.7),
    ]),
    "python-win": ([sys.executable, "-i", "-q"], 90, 22,
                   r">>> ", ["exit()\n"], [
        ("perceive — a live Python REPL under ConPTY", None, 1.2),
        ("act — type an expression", "type:sum(range(1, 101))", 0.6),
        ("confirm — Enter: 1..100 sums to 5050", ["Enter"], 1.0),
        ("act — import + call", "type:import platform; platform.system()", 0.6),
        ("confirm — Enter: perceive returns 'Windows'", ["Enter"], 1.2),
    ]),
}


def _apply_keys(sess, keys):
    if keys is None:
        return
    if isinstance(keys, str):
        if keys.startswith("enter+type:"):
            sess.send_keys(["Enter"])
            sess.send_text(keys[len("enter+type:"):])
        elif keys.startswith("type:"):
            sess.send_text(keys[len("type:"):])
        return
    sess.send_keys(keys)


def drive_one(target: str) -> int:
    argv, cols, rows, ready, quit_keys, beats = SCRIPTS[target]
    frames = os.path.join(TEMP, "winframes", target)
    os.makedirs(frames, exist_ok=True)
    for f in os.listdir(frames):
        os.remove(os.path.join(frames, f))

    labels, n = [], 0
    # `with` guarantees close() even if a beat/startup raises — otherwise the
    # child leaks and main()'s "all" loop spawns the next target alongside it
    # (concurrent-spawn red-line). PtySession.__exit__ -> close().
    with PtySession(cols=cols, rows=rows) as sess:
        sess.start(argv)
        # ConPTY startup can lag ~3s: strict wait-regex with a generous timeout.
        reason, _ = sess.wait_ready(marker=ready, max_wait_ms=15000)
        print(f"[{target}] startup: {reason}")

        for (label, keys, seconds) in beats:
            _apply_keys(sess, keys)
            start = time.monotonic()
            next_tick = start
            end = start + seconds
            while True:
                sess.pump()
                with open(f"{frames}/{n:04d}.ansi", "wb") as fh:
                    fh.write(_screen_to_ansi(sess.model.screen))
                labels.append(label)
                n += 1
                next_tick += CAP_DT
                if next_tick >= end:
                    break
                sl = next_tick - time.monotonic()
                if sl > 0:
                    time.sleep(sl)
            print(f"  beat: {label[:46]:46s} frames->{n:4d} "
                  f"DECCKM={'on' if sess.model.app_cursor else 'off'}")

        for k in quit_keys:
            if isinstance(k, str) and k.endswith("\n"):
                sess.send_text(k)
            else:
                sess.send_keys([k])
            time.sleep(0.4)
            sess.pump()
    with open(f"{frames}/labels.txt", "w", encoding="utf-8") as fh:
        fh.write("\n".join(labels))
    print(f"OK [{target}]: {n} frames @ {CAP_FPS}fps")
    return 0


def main() -> int:
    target = sys.argv[1] if len(sys.argv) > 1 else "lazygit-win"
    if target == "all":
        for t in ("lazygit-win", "python-win"):
            try:
                drive_one(t)
            except Exception as e:
                print(f"[{t}] FAILED: {type(e).__name__}: {e}")
        return 0
    return drive_one(target)


if __name__ == "__main__":
    raise SystemExit(main())
