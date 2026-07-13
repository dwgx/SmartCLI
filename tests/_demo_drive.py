#!/usr/bin/env python3
"""_demo_drive.py — generic real-TUI drive-and-capture for the launch reels.

Runs in the throwaway container. Drives a named target program through
smartcli_core, capturing full-color ANSI frames + captions at each beat, into
/root/frames/<target>/. Same proven pipeline as the lazygit reel, reused so we
can add htop / ncdu / nano etc. without re-inventing capture.

Usage (inside container):  python3 _demo_drive.py <target>
Targets are defined in SCRIPTS below (command + a list of (label, keys, settle)).
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, "/root")
from smartcli_core import PtySession


def _screen_to_ansi(screen) -> bytes:
    out = ["\x1b[2J\x1b[H"]
    def sgr(ch):
        codes = []
        if ch.reverse: codes.append("7")
        if ch.bold: codes.append("1")
        # pyte stores colors as either a 6-hex string OR a named ANSI color
        # (green/blue/...). Emit truecolor for hex, and the 16-color ANSI SGR for
        # names, so htop's meters / ncdu's coloring actually survive into the GIF.
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
        if f: codes.append(f)
        b = col(ch.bg, "48", 40)
        if b: codes.append(b)
        return "\x1b[0;" + ";".join(codes) + "m" if codes else "\x1b[0m"
    for y in range(screen.lines):
        row = screen.buffer[y]
        out.append("".join(sgr(row[x]) + (row[x].data or " ")
                          for x in range(screen.columns)) + "\x1b[0m\r\n")
    return "".join(out).encode("utf-8", "replace")


# each SCRIPTS entry: (argv, cols, rows, ready_regex, [ (label, keys|None, settle) ... ])
SCRIPTS = {
    # htop: live process monitor. Sort, tree view, filter — visually striking.
    "htop": (["htop"], 100, 30, r"(CPU|Mem|PID|Tasks|Load)", [
        ("perceive — htop: live CPU/mem meters + process table", None, 1.6),
        ("act — F5: switch to tree view", ["F5"], 1.4),
        ("act — Down: walk the process tree (SS3 arrow)", ["Down"], 0.9),
        ("act — Down: and further", ["Down"], 0.9),
        ("act — F6: open the sort-by menu", ["F6"], 1.2),
        ("act — Down: choose a sort column", ["Down"], 0.9),
        ("confirm — Enter: apply the sort", ["Enter"], 1.3),
    ]),
    # ncdu: scans a dir, then an interactive size browser.
    "ncdu": (["ncdu", "/usr"], 100, 30, r"(Total disk usage|Scanning|ncdu|\bDir\b)", [
        ("perceive — ncdu scanned /usr: sorted by size", None, 2.2),
        ("act — Down: move down the size list", ["Down"], 0.8),
        ("act — Down: to a big directory", ["Down"], 0.8),
        ("confirm — Enter: descend into it", ["Enter"], 1.2),
        ("act — Down: browse inside", ["Down"], 0.8),
        ("act — Left: back up a level", ["Left"], 1.0),
    ]),
    # nano: a real editor — type, navigate, see the modeline.
    "nano": (["nano", "/root/note.txt"], 100, 26, r"(GNU nano|\^G Help|\^X Exit)", [
        ("perceive — nano opened an empty buffer", None, 1.2),
        ("act — type a line of text", None, 0.6),   # text sent specially below
        ("act — Enter + more text", None, 0.6),
        ("act — Ctrl-O: write out (save)", ["C-o"], 1.0),
        ("confirm — Enter: confirm filename", ["Enter"], 1.1),
    ]),
}


def main() -> int:
    target = sys.argv[1] if len(sys.argv) > 1 else "htop"
    argv, cols, rows, ready, beats = SCRIPTS[target]
    frames = f"/root/frames/{target}"
    os.makedirs(frames, exist_ok=True)
    for f in os.listdir(frames):
        os.remove(os.path.join(frames, f))

    os.environ["TERM"] = "xterm-256color"
    sess = PtySession(cols=cols, rows=rows)
    sess.start(argv)
    reason, _ = sess.wait_ready(marker=ready, max_wait_ms=9000)
    print(f"[{target}] startup: {reason}")

    labels, n = [], 0
    for (label, keys, settle) in beats:
        # nano special: the two 'type' beats send literal text
        if target == "nano" and label.startswith("act — type"):
            sess.send_text("SmartCLI drove this editor —")
        elif target == "nano" and label.startswith("act — Enter + more"):
            sess.send_keys(["Enter"]); sess.send_text("perceive, act, confirm.")
        elif keys:
            sess.send_keys(keys)
        end = time.monotonic() + settle
        while time.monotonic() < end:
            sess.pump(); time.sleep(0.05)
        with open(f"{frames}/{n:02d}.ansi", "wb") as fh:
            fh.write(_screen_to_ansi(sess.model.screen))
        labels.append(label)
        app = sess.model.app_cursor
        print(f"[{n:02d}] {label} | DECCKM={'on' if app else 'off'}")
        n += 1

    # quit cleanly per target
    quit_keys = {"htop": ["q"], "ncdu": ["q"], "nano": ["C-x"]}
    for k in quit_keys.get(target, ["q"]):
        sess.send_keys([k]); time.sleep(0.3); sess.pump()
    sess.close()
    with open(f"{frames}/labels.txt", "w", encoding="utf-8") as fh:
        fh.write("\n".join(labels))
    print(f"OK [{target}]: {n} frames")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
