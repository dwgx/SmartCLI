"""Episode B3_navigate_menu, track U, POSIX transport (E6, inside Docker).

Same fixture semantics as the Windows U episode -- a 3-item menu, DECCKM on,
reverse-video bar, state file written by the program -- with the Windows console
API calls replaced by ``termios``/``tty`` raw mode, because the container has no
``kernel32``.  Strict UI: keys/wait/snapshot only.

Run (from the host):
    docker run --rm -v "D:/Project/SmartCLI:/repo" -v "D:/Project/SmartCLI-v3-runs/W3:/w3" \\
      -w /repo -e SMARTCLI_ROOT=/repo python:3.13-slim sh -lc \\
      "pip install -q pyte==0.8.2 && python -B /w3/episodes2/posix_b3_navigate_menu_20260916/driver.py"
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import _harness as H  # noqa: E402

TASK = "B3_navigate_menu"
TRACK = "U"
TRANSPORT = "posix-pty (PosixPtyBackend, Linux/Docker) -- strict UI"
RUN_ID = f"posix_b3_navigate_menu_{H.DATE}"

from smartcli_core import PtySession  # noqa: E402

RNG = random.Random(f"{H.SEED}|{TASK}")
SUFFIX = f"{RNG.randrange(0x1000, 0x10000):04x}"

FIXTURE_SRC = '''"""Fixture for B3 on POSIX: a 3-item menu driven by arrow keys and Enter."""
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
    out("\\x1b[2J\\x1b[H\\x1b[?25l")
    out("SELECT an action (arrow keys, Enter):\\r\\n")
    for i, name in enumerate(ITEMS):
        label = ("> " if i == sel else "  ") + name
        if i == sel:
            out("\\x1b[7m" + f"{label:<20}" + "\\x1b[0m\\r\\n")
        else:
            out(" " + f"{label:<20}" + "\\r\\n")
    out(f"selected_index={sel}\\r\\n")


keys = []
sel = 0
out("\\x1b[?1h")          # DECCKM on: the app expects SS3 cursor keys
draw(sel)

while True:
    b = os.read(fd, 1)
    if not b:
        break
    if b == b"\\x1b":
        seq = b + os.read(fd, 1) + os.read(fd, 1)
        keys.append(seq)
        if seq in (b"\\x1b[A", b"\\x1bOA"):
            sel = (sel - 1) % len(ITEMS)
        elif seq in (b"\\x1b[B", b"\\x1bOB"):
            sel = (sel + 1) % len(ITEMS)
        draw(sel)
        continue
    keys.append(b)
    if b in (b"\\r", b"\\n") or b == b"\\x03":
        break

forms = sorted({"SS3" if k[1:2] == b"O" else "CSI" for k in keys if k.startswith(b"\\x1b")})
picked = ITEMS[sel]

termios.tcsetattr(fd, termios.TCSADRAIN, saved)
out("\\x1b[?1l\\x1b[2J\\x1b[H\\x1b[?25h")     # DECCKM off, clear, show cursor
out(f"KEYS_RECEIVED {[k.decode('latin-1') for k in keys]!r}\\r\\n")
out(f"CURSOR_KEY_FORM {forms!r}\\r\\n")
out(f"SELECTED: {picked}\\r\\n")
state_path.write_text(json.dumps({"selection": picked, "exited": True,
                                  "keys_received": [k.decode("latin-1") for k in keys],
                                  "cursor_key_form": forms}, indent=1), encoding="utf-8")
out(f"WROTE {state_path.name} bytes={state_path.stat().st_size} selection={picked}\\r\\n")
out("BYE\\r\\n")
sys.exit(0)
'''


def main() -> int:
    ep = H.new_episode(TASK, TRACK, TRANSPORT, dirname="posix_b3_navigate_menu_20260916")
    here, actions, observations, started = ep["dir"], ep["actions"], ep["observations"], ep["started"]
    state_file = here / f"episode_b3_{SUFFIX}.json"
    fixture = here / "menu_fixture.py"

    fixture.write_text(FIXTURE_SRC, encoding="utf-8", newline="\n")
    if state_file.exists():
        state_file.unlink()
    setup = [{"what": "fixture program (POSIX port: termios raw mode instead of kernel32)",
              "path": str(fixture), "sha256": H.sha256(fixture), "outside_pty": True},
             {"what": "program state file absent before the episode", "path": str(state_file),
              "exists": state_file.exists(), "outside_pty": True}]

    argv = [sys.executable, "-B", str(fixture), str(state_file)]
    sess = PtySession(cols=90, rows=24)
    sess.start(argv)

    actions["wait"] += 1
    reason, snap = sess.wait_ready(marker="SELECT an action", max_wait_ms=15000)
    opened_screen = snap.to_text()
    selected_at_open = snap.selected.text if snap.selected else None
    observations.append({"step": "menu drawn, selection on the first item", "reason": reason,
                         "selected": selected_at_open, "screen": opened_screen})
    if reason == "TIMEOUT":
        return H.finalize(run_id=RUN_ID, task=TASK, track=TRACK, transport=TRANSPORT,
                          episode_dir=here, actions=actions, observations=observations,
                          setup=setup, claim=False, completion_basis="claim_withheld",
                          completion_detail={"in_episode_check": "the menu never drew"},
                          fixture_state={"selection": None, "exited": False},
                          fixture_state_source="filesystem",
                          session={"driver": "smartcli_core.PtySession (PosixPtyBackend)",
                                   "argv": argv},
                          started=started, ui_claim=True,
                          track_note="strict UI (track U) over the POSIX transport")

    actions["wait"] += 1
    sess.wait_stable(quiet_ms=200, max_wait_ms=3000)

    baseline = sess.model.visual_hash()
    actions["keys"] += 1
    sess.send_keys(["Down"])
    actions["wait"] += 1
    changed, snap = sess.wait_visual_change(baseline_hash=baseline, timeout_ms=6000)
    selected_after_down = snap.selected.text if snap.selected else None
    observations.append({"step": "Down moved the selection bar",
                         "reason": f"visual_change={changed}",
                         "selected": selected_after_down, "screen": snap.to_text()})

    actions["keys"] += 1
    sess.send_keys(["Enter"])
    actions["wait"] += 1
    reason, snap = sess.wait_ready(marker="SELECTED: save", max_wait_ms=8000)
    after_enter = snap.to_text()
    observations.append({"step": "Enter picked save; program reported and exited",
                         "reason": reason, "screen": after_enter})

    actions["wait"] += 1
    exit_info = H.wait_exit(sess, timeout_s=10.0)
    actions["snapshot"] += 1
    final_screen = sess.snapshot().to_text()
    observations.append({"step": "after exit", "screen": final_screen})

    close_state = sess.close()
    close_state_name = ("closed_confirmed" if close_state.get("closed_confirmed")
                        else "close_unconfirmed")

    written = state_file.exists()
    program_state = json.loads(state_file.read_text(encoding="utf-8")) if written else {}
    claim = bool(selected_after_down and "save" in selected_after_down
                 and "SELECTED: save" in final_screen and "BYE" in final_screen
                 and program_state.get("selection") == "save" and exit_info["exited"])
    fixture_state = {
        "selection": program_state.get("selection"),
        "exited": bool(exit_info["exited"]),
        "state_file": str(state_file),
        "state_file_written": written,
        "program_keys_received": program_state.get("keys_received"),
        "program_cursor_key_form": program_state.get("cursor_key_form"),
        "selected_at_open": selected_at_open,
        "selected_after_one_down": selected_after_down,
    }
    return H.finalize(
        run_id=RUN_ID, task=TASK, track=TRACK, transport=TRANSPORT, episode_dir=here,
        actions=actions, observations=observations, setup=setup, claim=claim,
        completion_basis="child_exit_observed" if claim else "claim_withheld",
        completion_detail={"in_episode_check": fixture_state},
        fixture_state=fixture_state,
        fixture_state_source=("the program's own state file (written by it) plus the runtime's "
                              "exit observation; the screen corroborates the navigation"),
        session={"driver": "smartcli_core.PtySession (PosixPtyBackend, Linux container)",
                 "argv": argv, "cols": 90, "rows": 24, "cancel": False,
                 "process_exited": bool(exit_info["exited"]),
                 "exit_observed_by": exit_info["observation"], "exit_evidence": exit_info,
                 "close_state": close_state_name,
                 "close_observed": f"backend close_state()={close_state}",
                 "close_state_detail": close_state},
        started=started, ui_claim=True,
        track_note="strict UI (track U) over the POSIX transport (E6)")


if __name__ == "__main__":
    raise SystemExit(main())
