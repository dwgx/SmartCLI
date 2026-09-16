"""Fixture for B3, track H: the same 3-item menu state machine, console-free.

The presses arrive as a command list in a file instead of console keystrokes; the
draw output goes to stdout and the resulting state file is identical in shape to
the U fixture's.
"""
import json
import sys
from pathlib import Path

ITEMS = ["open", "save", "quit"]
state_path = Path(sys.argv[1])
commands = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))


def out(text):
    sys.stdout.write(text)
    sys.stdout.flush()


def draw(sel):
    out("\x1b[2J\x1b[H")
    out("SELECT an action (commands file):\n")
    for i, name in enumerate(ITEMS):
        label = ("> " if i == sel else "  ") + name
        out(("[sel] " if i == sel else "     ") + f"{label:<20}\n")
    out(f"selected_index={sel}\n")


sel = 0
draw(sel)

for command in commands:
    if command == "down":
        sel = (sel + 1) % len(ITEMS)
        draw(sel)
    elif command == "up":
        sel = (sel - 1) % len(ITEMS)
        draw(sel)
    elif command == "enter":
        break

picked = ITEMS[sel]
out(f"COMMANDS_RECEIVED {commands!r}\n")
out(f"SELECTED: {picked}\n")
state_path.write_text(json.dumps({"selection": picked, "exited": True,
                                  "channel": "commands_file",
                                  "commands_received": commands}, indent=1),
                      encoding="utf-8")
out(f"WROTE {state_path.name} bytes={state_path.stat().st_size} selection={picked}\n")
out("BYE\n")
sys.exit(0)
