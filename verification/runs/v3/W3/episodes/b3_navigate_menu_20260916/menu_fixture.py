"""Fixture for B3: a 3-item menu driven by arrow keys and Enter."""
import ctypes
import json
import os
import sys
from pathlib import Path

ITEMS = ["open", "save", "quit"]
state_path = Path(sys.argv[1])

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
STD_INPUT_HANDLE = -10
ENABLE_PROCESSED_INPUT = 0x0001
ENABLE_LINE_INPUT = 0x0002
ENABLE_ECHO_INPUT = 0x0004
ENABLE_VIRTUAL_TERMINAL_INPUT = 0x0200

handle = k32.GetStdHandle(STD_INPUT_HANDLE)
saved = ctypes.c_uint32()
k32.GetConsoleMode(handle, ctypes.byref(saved))
raw = ((saved.value & ~(ENABLE_PROCESSED_INPUT | ENABLE_LINE_INPUT | ENABLE_ECHO_INPUT))
       | ENABLE_VIRTUAL_TERMINAL_INPUT)
k32.SetConsoleMode(handle, raw)


def out(text):
    sys.stdout.write(text)
    sys.stdout.flush()


def draw(sel):
    # no alt screen: clear + home, selection bar in reverse video
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
    b = os.read(0, 1)
    if not b:
        break
    if b == b"\x1b":
        seq = b + os.read(0, 1) + os.read(0, 1)
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

out("\x1b[?1l\x1b[2J\x1b[H\x1b[?25h")     # DECCKM off, clear, show cursor
out(f"KEYS_RECEIVED {[k.decode('latin-1') for k in keys]!r}\r\n")
out(f"CURSOR_KEY_FORM {forms!r}\r\n")
out(f"SELECTED: {picked}\r\n")
state_path.write_text(json.dumps({"selection": picked, "exited": True,
                                  "keys_received": [k.decode("latin-1") for k in keys],
                                  "cursor_key_form": forms}, indent=1), encoding="utf-8")
out(f"WROTE {state_path.name} bytes={state_path.stat().st_size} selection={picked}\r\n")
out("BYE\r\n")
k32.SetConsoleMode(handle, saved.value)
sys.exit(0)
