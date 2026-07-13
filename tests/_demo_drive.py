#!/usr/bin/env python3
"""_demo_drive.py — generic real-TUI drive-and-capture for the launch reels.

Runs in the throwaway container. Drives a named target program through
smartcli_core, capturing full-color ANSI frames + captions at a steady 30fps
cadence into /root/frames/<target>/, so the reel shows real MOTION (menus
opening, selection moving, htop's live meters) instead of a one-frame-per-beat
slideshow. Identical consecutive frames are fine — the H.264/VP9 encoder on the
host collapses them to almost nothing, so a 30fps reel stays tiny.

Output per target dir:
  0000.ansi, 0001.ansi, ...   one raw full-colour ANSI frame per 30fps tick
  labels.txt                  one caption line per frame (same slug per beat)

Usage (inside container):  python3 _demo_drive.py <target>          # one reel
                           python3 _demo_drive.py all               # all, serial
Targets are defined in SCRIPTS below (command + a list of beats). Each beat is
(label, keys|None, seconds) — after the keys are sent we sample the screen at
CAP_FPS for `seconds`, capturing the repaint. One PTY session at a time; each is
closed before the next target starts (repo CLAUDE.md spawn red-line).
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, "/root")
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
        # pyte stores colors as a 6-hex string OR a named ANSI color. Emit
        # truecolor for hex, 16-color SGR for names, so htop's meters / ncdu's
        # coloring survive into the reel.
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


# each SCRIPTS entry: (argv, cols, rows, ready_regex, quit_keys, [ beats ... ])
# a beat is (label, keys|None, seconds) — seconds is the 30fps capture window.
SCRIPTS = {
    "htop": (["htop"], 100, 30, r"(CPU|Mem|PID|Tasks|Load)", ["q"], [
        ("perceive — htop: live CPU/mem meters + process table", None, 1.3),
        ("act — F5: switch to tree view", ["F5"], 0.9),
        ("act — Down: walk the process tree (SS3 arrow)", ["Down"], 0.5),
        ("act — Down: and further down the tree", ["Down"], 0.5),
        ("act — F6: open the sort-by menu", ["F6"], 0.9),
        ("act — Down: choose a sort column", ["Down"], 0.5),
        ("confirm — Enter: apply the sort", ["Enter"], 1.1),
    ]),
    "ncdu": (["ncdu", "/usr"], 100, 30,
             r"(Total disk usage|Scanning|ncdu|\bDir\b)", ["q"], [
        ("perceive — ncdu scanned /usr: sorted by size", None, 1.6),
        ("act — Down: move down the size list", ["Down"], 0.45),
        ("act — Down: to a big directory", ["Down"], 0.45),
        ("confirm — Enter: descend into it", ["Enter"], 1.0),
        ("act — Down: browse inside", ["Down"], 0.45),
        ("act — Left: back up a level", ["Left"], 0.9),
    ]),
    "nano": (["nano", "/root/note.txt"], 100, 26,
             r"(GNU nano|\^G Help|\^X Exit)", ["C-x"], [
        ("perceive — nano opened an empty buffer", None, 1.0),
        ("act — type a line of text", "type:SmartCLI drove this editor —", 0.7),
        ("act — Enter + more text", "enter+type:perceive, act, confirm.", 0.7),
        ("act — Ctrl-O: write out (save)", ["C-o"], 0.9),
        ("confirm — Enter: confirm filename", ["Enter"], 1.0),
    ]),
    "lazygit": (["lazygit", "-p", "/root/demo"], 100, 30,
                r"(Files|Status|Commits|lazygit)", ["q"], [
        ("perceive — lazygit opened (welcome popup)", None, 1.0),
        ("act — Enter: dismiss the welcome popup", ["Enter"], 0.9),
        ("act — key 4: focus the Commits panel", ["4"], 0.7),
        ("act — Down: move to an older commit (SS3 arrow, DECCKM)", ["Down"], 0.5),
        ("act — Down: and the next", ["Down"], 0.5),
        ("confirm — Enter: open that commit's diff", ["Enter"], 1.2),
        ("act — Esc: back to the commit list", ["Escape"], 0.7),
        ("act — key 3: focus Local branches", ["3"], 0.6),
        ("act — Down: highlight feature/auth", ["Down"], 0.7),
    ]),
}


def _apply_keys(sess, keys):
    """keys may be a list (send_keys) or a 'type:'/'enter+type:' text directive."""
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
    frames = f"/root/frames/{target}"
    os.makedirs(frames, exist_ok=True)
    for f in os.listdir(frames):
        os.remove(os.path.join(frames, f))

    os.environ["TERM"] = "xterm-256color"
    sess = PtySession(cols=cols, rows=rows)
    sess.start(argv)
    reason, _ = sess.wait_ready(marker=ready, max_wait_ms=9000)
    print(f"[{target}] startup: {reason}")

    labels = []
    n = 0
    for (label, keys, seconds) in beats:
        _apply_keys(sess, keys)
        # sample at a steady 30fps wall-clock schedule for `seconds`
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
            sleep = next_tick - time.monotonic()
            if sleep > 0:
                time.sleep(sleep)
        app = sess.model.app_cursor
        print(f"  beat done: {label[:52]:52s} | frames->{n:4d} | "
              f"DECCKM={'on' if app else 'off'}")

    for k in quit_keys:
        sess.send_keys([k])
        time.sleep(0.3)
        sess.pump()
    sess.close()
    with open(f"{frames}/labels.txt", "w", encoding="utf-8") as fh:
        fh.write("\n".join(labels))
    print(f"OK [{target}]: {n} frames @ {CAP_FPS}fps")
    return 0


def main() -> int:
    target = sys.argv[1] if len(sys.argv) > 1 else "htop"
    if target == "all":
        # strictly serial — one PTY session at a time, each closed before next.
        for t in ("htop", "ncdu", "nano", "lazygit"):
            drive_one(t)
        return 0
    return drive_one(target)


if __name__ == "__main__":
    raise SystemExit(main())
