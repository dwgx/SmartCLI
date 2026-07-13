#!/usr/bin/env python3
"""_demo_drive_mac.py — real-TUI drive-and-capture on macOS, 30fps.

Same streaming-capture approach as tests/_demo_drive.py, but with macOS paths
(HOME instead of /root) and Apple-Silicon-friendly targets. Drives each TUI
through smartcli_core's PosixPtyBackend (BSD pty), capturing full-colour ANSI
frames at 30fps into ~/smartcli-reel/frames/<target>/. One PTY session at a time,
closed before the next (spawn red-line). ffmpeg on the Mac encodes locally; the
tiny frame files are what come back over SFTP if needed.

Usage (on the Mac):  python3 _demo_drive_mac.py all
"""
from __future__ import annotations

import os
import sys
import time

HOME = os.path.expanduser("~")
ROOT = os.path.join(HOME, "smartcli-reel")
sys.path.insert(0, ROOT)
from smartcli_core import PtySession

CAP_FPS = 30
CAP_DT = 1.0 / CAP_FPS


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


DEMO = os.path.join(ROOT, "demo")
NOTE = os.path.join(ROOT, "note.txt")

# (argv, cols, rows, ready_regex, quit_keys, [ (label, keys|None, seconds) ])
SCRIPTS = {
    "lazygit": (["lazygit", "-p", DEMO], 100, 30,
                r"(Files|Status|Commits|lazygit)", ["q"], [
        ("perceive — lazygit opened on macOS (welcome popup)", None, 1.0),
        ("act — Enter: dismiss the welcome popup", ["Enter"], 0.9),
        ("act — key 4: focus the Commits panel", ["4"], 0.7),
        ("act — Down: older commit (SS3 arrow, DECCKM)", ["Down"], 0.5),
        ("act — Down: and the next", ["Down"], 0.5),
        ("confirm — Enter: open that commit's diff", ["Enter"], 1.2),
        ("act — Esc: back to the commit list", ["Escape"], 0.7),
        ("act — key 3: focus Local branches", ["3"], 0.6),
        ("act — Down: highlight feature/auth", ["Down"], 0.7),
    ]),
    "ncdu": (["ncdu", os.path.join(HOME, "smartcli-reel")], 100, 30,
             r"(Total disk usage|Scanning|ncdu|\bDir\b)", ["q"], [
        ("perceive — ncdu scanned the dir: sorted by size", None, 1.8),
        ("act — Down: move down the size list", ["Down"], 0.45),
        ("act — Down: to a bigger entry", ["Down"], 0.45),
        ("confirm — Enter: descend into it", ["Enter"], 1.0),
        ("act — Left: back up a level", ["Left"], 0.9),
    ]),
    "nano": (["nano", NOTE], 100, 26,
             r"(GNU nano|\^G Help|\^X Exit|nano)", ["C-x"], [
        ("perceive — nano opened a buffer on macOS", None, 1.0),
        ("act — type a line of text", "type:SmartCLI drove nano on macOS —", 0.7),
        ("act — Enter + more text", "enter+type:perceive, act, confirm.", 0.7),
        ("act — Ctrl-O: write out (save)", ["C-o"], 0.9),
        ("confirm — Enter: confirm filename", ["Enter"], 1.0),
    ]),
    # htop needs sudo for the full process table; run it non-privileged (shows
    # our own processes) so no interactive sudo prompt can hang the driver.
    "htop": (["htop", "-u", os.environ.get("USER", "dwgx")], 100, 30,
             r"(CPU|Mem|PID|Tasks|Load|htop)", ["q"], [
        ("perceive — htop on macOS: live meters + process table", None, 1.3),
        ("act — F5: switch to tree view", ["F5"], 0.9),
        ("act — Down: walk the process tree (SS3 arrow)", ["Down"], 0.5),
        ("act — Down: and further", ["Down"], 0.5),
        ("confirm — F6: open the sort-by menu", ["F6"], 1.1),
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
    frames = os.path.join(ROOT, "frames", target)
    os.makedirs(frames, exist_ok=True)
    for f in os.listdir(frames):
        os.remove(os.path.join(frames, f))

    os.environ["TERM"] = "xterm-256color"
    labels, n = [], 0
    # `with` guarantees close() even if a beat/startup raises — otherwise the
    # child would leak and main()'s "all" loop would spawn the next target
    # alongside it (the concurrent-spawn red-line). PtySession.__exit__ -> close().
    with PtySession(cols=cols, rows=rows) as sess:
        sess.start(argv)
        reason, _ = sess.wait_ready(marker=ready, max_wait_ms=9000)
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
            print(f"  beat: {label[:48]:48s} frames->{n:4d} DECCKM="
                  f"{'on' if sess.model.app_cursor else 'off'}")

        for k in quit_keys:
            sess.send_keys([k])
            time.sleep(0.3)
            sess.pump()
    with open(f"{frames}/labels.txt", "w", encoding="utf-8") as fh:
        fh.write("\n".join(labels))
    print(f"OK [{target}]: {n} frames @ {CAP_FPS}fps")
    return 0


def main() -> int:
    target = sys.argv[1] if len(sys.argv) > 1 else "lazygit"
    if target == "all":
        for t in ("lazygit", "ncdu", "nano", "htop"):
            try:
                drive_one(t)
            except Exception as e:
                print(f"[{t}] FAILED: {type(e).__name__}: {e}")
        return 0
    return drive_one(target)


if __name__ == "__main__":
    raise SystemExit(main())
