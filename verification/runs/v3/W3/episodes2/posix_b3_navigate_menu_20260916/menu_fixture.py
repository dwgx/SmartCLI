"""Fixture for B3 on POSIX: a 3-item menu driven by arrow keys and Enter."""
import json
import os
import sys
import termios
import tty
from pathlib import Path

ITEMS = ["open", "save", "quit"]
state_path = Path(sys.argv[1])

fd = 0
saved = termios.tcgetattr(fd)
tty.setraw(fd)


def out(text):
    sys.stdout.write(text)
    sys.stdout.flush()


def draw(sel):
    out("\x1b[2J\x1b[H\x1b[?25l")
    out("SELECT an action (arrow keys, Enter):\r\n")
    for i, name in enumerate(ITEMS):
        label = ("> " if i == sel else "  ") + name
        if i == sel:
            out("\x1b[7m" + f"{label:<20}" + "\x1b[0m\r\n")
        else:
            out(" " + f"{label:<20}" + "\r\n")
    out(f"selected_index={sel}\r\n")


keys = []
sel = 0
out("\x1b[?1h")          # DECCKM on: the app expects SS3 cursor keys
draw(sel)

while True:
    b = os.read(fd, 1)
    if not b:
        break
    if b == b"\x1b":
        seq = b + os.read(fd, 1) + os.read(fd, 1)
        keys.append(seq)
        if seq in (b"\x1b[A", b"\x1bOA"):
            sel = (sel - 1) % len(ITEMS)
        elif seq in (b"\x1b[B", b"\x1bOB"):
            sel = (sel + 1) % len(ITEMS)
        draw(sel)
        continue
    keys.append(b)
    if b in (b"\r", b"\n") or b == b"\x03":
        break

forms = sorted({"SS3" if k[1:2] == b"O" else "CSI" for k in keys if k.startswith(b"\x1b")})
picked = ITEMS[sel]

termios.tcsetattr(fd, termios.TCSADRAIN, saved)
out("\x1b[?1l\x1b[2J\x1b[H\x1b[?25h")     # DECCKM off, clear, show cursor
out(f"KEYS_RECEIVED {[k.decode('latin-1') for k in keys]!r}\r\n")
out(f"CURSOR_KEY_FORM {forms!r}\r\n")
out(f"SELECTED: {picked}\r\n")
state_path.write_text(json.dumps({"selection": picked, "exited": True,
                                  "keys_received": [k.decode("latin-1") for k in keys],
                                  "cursor_key_form": forms}, indent=1), encoding="utf-8")
out(f"WROTE {state_path.name} bytes={state_path.stat().st_size} selection={picked}\r\n")
out("BYE\r\n")
sys.exit(0)
