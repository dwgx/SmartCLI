#!/usr/bin/env python3
"""_demo_lazygit.py — drive the REAL lazygit TUI with drive-tui, capturing the
perceive -> act -> confirm loop as a sequence of frames for the launch demo.

Runs in the throwaway Debian container (lazygit 0.63 + a demo git repo). This is
the proof reel: an agent driving a real full-screen curses app through
smartcli_core — reading the pyte screen grid, moving with arrow keys (which take
the adaptive SS3/CSI path since lazygit enables DECCKM), and confirming each
screen changed. NOT a toy app.

Writes each captured frame's raw bytes to /root/frames/NN.ansi and prints a
narration line per beat so we can see it worked.
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, "/root")
from smartcli_core import PtySession

FRAMES = "/root/frames"
os.makedirs(FRAMES, exist_ok=True)
_n = 0
_labels = []


def beat(sess, label, keys=None, settle=0.9):
    """Send keys, let lazygit repaint, then snapshot a fresh full-color frame.

    We re-drive a throwaway pyte ByteStream from the accumulated raw PTY bytes so
    each saved frame is the REAL ANSI lazygit painted (color intact) — rendered
    to a PNG later on the host where PIL + fonts live.
    """
    global _n
    if keys:
        sess.send_keys(keys)
    end = time.monotonic() + settle
    while time.monotonic() < end:
        sess.pump()
        time.sleep(0.05)
    # dump the current full-color screen as raw ANSI: home + each display row.
    # (We reconstruct SGR from the pyte buffer so the GIF has lazygit's colors.)
    raw = _screen_to_ansi(sess.model.screen)
    with open(f"{FRAMES}/{_n:02d}.ansi", "wb") as f:
        f.write(raw)
    _labels.append(label)
    app = sess.model.app_cursor
    head = sess.snapshot().to_text().splitlines()[0] if raw else ""
    print(f"[{_n:02d}] {label}  | DECCKM={'on' if app else 'off'} | {head[:66]}")
    _n += 1


def _screen_to_ansi(screen) -> bytes:
    """Serialize a pyte Screen to a full ANSI frame (with SGR colors)."""
    out = ["\x1b[2J\x1b[H"]
    NAMED = {"default": None}
    def sgr(ch):
        codes = []
        fg, bg = ch.fg, ch.bg
        if ch.reverse: codes.append("7")
        if ch.bold: codes.append("1")
        # truecolor if 6-hex, else leave default (pyte stores names or hex)
        def col(c, base):
            if c and c != "default" and len(c) == 6:
                try:
                    r, g, b = int(c[0:2],16), int(c[2:4],16), int(c[4:6],16)
                    return f"{base};2;{r};{g};{b}"
                except ValueError:
                    return None
            return None
        f = col(fg, "38")
        if f: codes.append(f)
        b = col(bg, "48")
        if b: codes.append(b)
        return "\x1b[0;" + ";".join(codes) + "m" if codes else "\x1b[0m"
    for y in range(screen.lines):
        row = screen.buffer[y]
        parts = []
        for x in range(screen.columns):
            ch = row[x]
            parts.append(sgr(ch) + (ch.data or " "))
        out.append("".join(parts) + "\x1b[0m\r\n")
    return "".join(out).encode("utf-8", "replace")


def main() -> int:
    os.environ["TERM"] = "xterm-256color"
    sess = PtySession(cols=100, rows=30)
    # lazygit in the demo repo
    sess.start(["lazygit", "-p", "/root/demo"])

    # 1) perceive: wait for lazygit's first full paint
    reason, snap = sess.wait_ready(marker=r"(Files|Status|Commits|lazygit)",
                                   max_wait_ms=8000)
    print(f"startup wait: reason={reason}")
    # lazygit opens with a welcome popup — dismiss it with Enter (perceive it first)
    beat(sess, "perceive — lazygit opened (welcome popup)", settle=1.0)
    beat(sess, "act — Enter: dismiss the welcome popup", keys=["Enter"], settle=1.0)

    # 2) focus the Commits panel (lazygit: number key 4) and read history
    beat(sess, "act — key 4: focus the Commits panel", keys=["4"])
    beat(sess, "act — Down: move to an older commit (SS3 arrow, DECCKM)", keys=["Down"])
    beat(sess, "act — Down: and the next", keys=["Down"])
    beat(sess, "confirm — Enter: open that commit's diff", keys=["Enter"], settle=1.1)
    beat(sess, "act — Esc: back to the commit list", keys=["Escape"], settle=0.8)

    # 3) branches panel — show we perceive the highlighted branch row
    beat(sess, "act — key 3: focus Local branches", keys=["3"])
    beat(sess, "act — Down: highlight feature/auth", keys=["Down"])

    # quit lazygit (its quit key is 'q'); then close the session
    sess.send_keys(["q"])
    time.sleep(0.5)
    sess.pump()
    print(f"alive after q: {sess.is_alive()}")
    sess.close()
    with open(f"{FRAMES}/labels.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(_labels))
    print(f"OK: captured {_n} frames to {FRAMES}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
