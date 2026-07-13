#!/usr/bin/env python3
"""_demo_drive_linux2.py — a second wave of Linux drive reels, showcase-strong.

Drives dialog-style form/menu/checklist TUIs and vim through smartcli_core in a
throwaway container, capturing at 30fps to /root/frames2/<target>/. These lean
into the "drive an interactive FORM/MENU, not just a pager" story. One PTY at a
time, closed before the next.

Usage (in container):  python3 _demo_drive_linux2.py all
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, "/root")
from smartcli_core import PtySession

CAP_FPS = 30
CAP_DT = 1.0 / CAP_FPS

# A self-contained whiptail wizard: a menu, then a checklist, then a yes/no.
WHIP = (
    "whiptail --title 'SmartCLI drove this' "
    "--menu 'Pick a component to configure:' 15 60 4 "
    "core 'PTY + pyte screen model' "
    "art 'terminal visual effects' "
    "drive 'drive interactive TUIs' "
    "ui 'cell-accurate layout' 3>&1 1>&2 2>&3"
)

SCRIPTS = {
    # dialog checklist — a real form with toggleable rows.
    "dialog": (["dialog", "--title", "SmartCLI · drive a form",
                "--checklist", "Toggle skills to install (Space), Enter to confirm:",
                "15", "62", "4",
                "cmd-art", "terminal visual effects", "on",
                "drive-tui", "drive interactive TUIs", "off",
                "tui-ui", "cell-accurate layout engine", "off",
                "core", "the shared PTY+pyte core", "on"],
               80, 24, r"(Toggle|cmd-art|SmartCLI)", ["Enter"], [
        ("perceive — a dialog checklist form (2 pre-checked)", None, 1.4),
        ("act — Down: move to drive-tui", ["Down"], 0.6),
        ("act — Space: toggle it ON", ["Space"], 0.7),
        ("act — Down: move to tui-ui", ["Down"], 0.6),
        ("act — Space: toggle it ON too", ["Space"], 0.7),
        ("confirm — Enter: submit the form", ["Enter"], 1.2),
    ]),
    # vim — modal editing: insert text, ESC, save+quit.
    "vim": (["vim", "-u", "NONE", "-N", "/root/vimnote.txt"], 80, 24,
            r"(VIM|~|vimnote)", [":wq\r"], [
        ("perceive — vim opened an empty buffer", None, 1.2),
        ("act — i: enter insert mode", ["i"], 0.6),
        ("act — type a line", "type:SmartCLI drove vim through a PTY.", 0.8),
        ("act — Enter + more", "enter+type:perceive -> act -> confirm, modal and all.", 0.8),
        ("act — Esc: back to normal mode", ["Escape"], 0.7),
        ("confirm — :wq to write and quit", "type::wq", 0.8),
    ]),
}


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
    frames = f"/root/frames2/{target}"
    os.makedirs(frames, exist_ok=True)
    for f in os.listdir(frames):
        os.remove(os.path.join(frames, f))

    os.environ["TERM"] = "xterm-256color"
    sess = PtySession(cols=cols, rows=rows)
    sess.start(argv)
    reason, _ = sess.wait_ready(marker=ready, max_wait_ms=9000)
    print(f"[{target}] startup: {reason}")

    labels, n = [], 0
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
        if isinstance(k, str) and (k.endswith("\r") or k.endswith("\n")):
            sess.send_text(k)
        else:
            sess.send_keys([k])
        time.sleep(0.3)
        sess.pump()
    sess.close()
    with open(f"{frames}/labels.txt", "w", encoding="utf-8") as fh:
        fh.write("\n".join(labels))
    print(f"OK [{target}]: {n} frames @ {CAP_FPS}fps")
    return 0


def main() -> int:
    target = sys.argv[1] if len(sys.argv) > 1 else "dialog"
    if target == "all":
        for t in ("dialog", "vim"):
            try:
                drive_one(t)
            except Exception as e:
                print(f"[{t}] FAILED: {type(e).__name__}: {e}")
        return 0
    return drive_one(target)


if __name__ == "__main__":
    raise SystemExit(main())
