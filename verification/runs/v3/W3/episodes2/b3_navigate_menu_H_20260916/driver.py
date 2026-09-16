"""Episode B3_navigate_menu, track H (hybrid).

No PTY is opened and no keystroke is sent.  The menu is run console-free: its
command list arrives through a file/API channel (``commands.json``), the same state
machine (down moves the bar, enter picks) runs, and the program writes its own
state file.  The selection is then read off the filesystem and the exit is the real
OS process exit.

Track H permits this; the result is recorded as ``ui_claim: false`` -- it is NOT a
UI pass.

Run: python -B episodes2/b3_navigate_menu_H_20260916/driver.py
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import _harness as H  # noqa: E402

TASK = "B3_navigate_menu"
TRACK = "H"
TRANSPORT = "filesystem/API only (no PTY): menu commands sourced from a file"
RUN_ID = f"b3_navigate_menu_{TRACK}_{H.DATE}"

FIXTURE_SRC = '''"""Fixture for B3, track H: the same 3-item menu state machine, console-free.

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
    out("\\x1b[2J\\x1b[H")
    out("SELECT an action (commands file):\\n")
    for i, name in enumerate(ITEMS):
        label = ("> " if i == sel else "  ") + name
        out(("[sel] " if i == sel else "     ") + f"{label:<20}\\n")
    out(f"selected_index={sel}\\n")


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
out(f"COMMANDS_RECEIVED {commands!r}\\n")
out(f"SELECTED: {picked}\\n")
state_path.write_text(json.dumps({"selection": picked, "exited": True,
                                  "channel": "commands_file",
                                  "commands_received": commands}, indent=1),
                      encoding="utf-8")
out(f"WROTE {state_path.name} bytes={state_path.stat().st_size} selection={picked}\\n")
out("BYE\\n")
sys.exit(0)
'''


def main() -> int:
    ep = H.new_episode(TASK, TRACK, TRANSPORT)
    here, actions, observations, started = ep["dir"], ep["actions"], ep["observations"], ep["started"]
    state_file = here / "episode_b3_hybrid.json"
    commands_file = here / "commands.json"
    fixture = here / "menu_commands_fixture.py"

    fixture.write_text(FIXTURE_SRC, encoding="utf-8", newline="\n")
    for p in (state_file, commands_file):
        if p.exists():
            p.unlink()
    setup = [{"what": "fixture program (console-free variant of the U menu fixture)",
              "path": str(fixture), "sha256": H.sha256(fixture), "outside_pty": True},
             {"what": "program state file absent before the episode", "path": str(state_file),
              "exists": state_file.exists(), "outside_pty": True},
             {"what": "hybrid channel", "kind": "command list read from a file",
              "path": str(commands_file), "outside_pty": True}]

    # ---------------------------------------------- hybrid: the command list
    actions["write_file"] += 1
    commands_file.write_text(json.dumps(["down", "enter"]), encoding="utf-8", newline="\n")
    observations.append({"step": "menu commands written to the channel file",
                         "path": str(commands_file),
                         "content": commands_file.read_text(encoding="utf-8")})

    argv = [sys.executable, "-B", str(fixture), str(state_file), str(commands_file)]
    actions["wait"] += 1
    proc = subprocess.run(argv, capture_output=True, text=True, timeout=30)
    observations.append({"step": "program ran console-free and exited",
                         "argv": argv, "returncode": proc.returncode, "stdout": proc.stdout,
                         "stderr": proc.stderr})

    actions["read_file"] += 1
    written = state_file.exists()
    program_state = json.loads(state_file.read_text(encoding="utf-8")) if written else {}
    observations.append({"step": "program state file read back", "state": program_state})

    claim = bool(proc.returncode == 0 and program_state.get("selection") == "save"
                 and "SELECTED: save" in proc.stdout and "BYE" in proc.stdout)
    fixture_state = {
        "selection": program_state.get("selection"),
        "exited": proc.returncode == 0,
        "state_file": str(state_file),
        "state_file_written": written,
        "program_channel": program_state.get("channel"),
        "program_commands_received": program_state.get("commands_received"),
    }
    return H.finalize(
        run_id=RUN_ID, task=TASK, track=TRACK, transport=TRANSPORT, episode_dir=here,
        actions=actions, observations=observations, setup=setup, claim=claim,
        completion_basis="artifact_readback_verified" if claim else "claim_withheld",
        completion_detail={"in_episode_check": fixture_state},
        fixture_state=fixture_state,
        fixture_state_source=("the program's own state file (written by it) plus the real OS "
                              "process exit (returncode 0)"),
        session={"driver": "none (no PTY session; the program ran as a plain API call)",
                 "argv": argv, "cancel": False, "process_exited": proc.returncode == 0,
                 "exit_observed_by": f"subprocess returncode {proc.returncode}",
                 "close_state": "not_applicable", "close_observed": None},
        started=started, ui_claim=False,
        track_note=("hybrid (track H): the menu was driven from a command file and its state "
                    "file read back; no terminal action was used, so this is NOT a UI pass"))


if __name__ == "__main__":
    raise SystemExit(main())
