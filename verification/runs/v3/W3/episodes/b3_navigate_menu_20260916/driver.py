"""Episode B3_navigate_menu, track U (strict UI).

Fixture: a seeded 3-item menu (open / save / quit) that puts the console in raw
VT mode, enables DECCKM (application cursor keys, as a curses TUI does), draws the
selection as a reverse-video bar, and writes its own state file when Enter picks
an item.
Episode: move the selection to ``save`` with the arrow keys and pick it; the
program must exit cleanly.

In-episode actions are PTY-only (keys / text / wait / snapshot); the fixture program
is written before the session starts and the ground truth is read from the
program's own state file plus the filesystem after the session is closed.

Run: python -B episodes/b3_navigate_menu_20260916/driver.py
"""
from __future__ import annotations

import hashlib
import json
import random
import re
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

sys.path.insert(0, r"D:\Project\SmartCLI")

from smartcli_core import PtySession  # noqa: E402

TASK = "B3_navigate_menu"
TRACK = "U"
SEED = 20260916
MODEL_ID = "deepseek-v4.1-flash:max (omp backend, dispatched)"
BUDGET = {"episodes": 3, "wall_clock_minutes": 45, "usd": 0}
RUN_ID = "b3_navigate_menu_20260916"

HERE = Path(__file__).resolve().parent
RNG = random.Random(f"{SEED}|{TASK}")
SUFFIX = f"{RNG.randrange(0x1000, 0x10000):04x}"
STATE_FILE = HERE / f"episode_b3_{SUFFIX}.json"
FIXTURE = HERE / "menu_fixture.py"
RESULT = HERE / "result.json"

FIXTURE_SRC = '''"""Fixture for B3: a 3-item menu driven by arrow keys and Enter."""
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
    b = os.read(0, 1)
    if not b:
        break
    if b == b"\\x1b":
        seq = b + os.read(0, 1) + os.read(0, 1)
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

out("\\x1b[?1l\\x1b[2J\\x1b[H\\x1b[?25h")     # DECCKM off, clear, show cursor
out(f"KEYS_RECEIVED {[k.decode('latin-1') for k in keys]!r}\\r\\n")
out(f"CURSOR_KEY_FORM {forms!r}\\r\\n")
out(f"SELECTED: {picked}\\r\\n")
state_path.write_text(json.dumps({"selection": picked, "exited": True,
                                  "keys_received": [k.decode("latin-1") for k in keys],
                                  "cursor_key_form": forms}, indent=1), encoding="utf-8")
out(f"WROTE {state_path.name} bytes={state_path.stat().st_size} selection={picked}\\r\\n")
out("BYE\\r\\n")
k32.SetConsoleMode(handle, saved.value)
sys.exit(0)
'''

actions: Counter[str] = Counter()
observations: list[dict[str, Any]] = []


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    started = time.monotonic()

    # ---------------------------------------------------------------- setup
    FIXTURE.write_text(FIXTURE_SRC, encoding="utf-8", newline="\n")
    if STATE_FILE.exists():
        STATE_FILE.unlink()
    setup = [
        {"what": "fixture program", "path": str(FIXTURE), "sha256": sha256(FIXTURE),
         "outside_pty": True},
        {"what": "program state file absent before the episode", "path": str(STATE_FILE),
         "exists": STATE_FILE.exists(), "outside_pty": True},
    ]

    argv = [sys.executable, "-B", str(FIXTURE), str(STATE_FILE)]
    sess = PtySession(cols=90, rows=24)
    sess.start(argv)

    # ------------------------------------------------------------- episode
    actions["wait"] += 1
    reason, snap = sess.wait_ready(marker="SELECT an action", max_wait_ms=10000)
    opened_screen = snap.to_text()
    selected_at_open = snap.selected.text if snap.selected else None
    observations.append({"step": "menu drawn, selection on the first item", "reason": reason,
                         "selected": selected_at_open, "screen": opened_screen})
    if reason == "TIMEOUT":
        return finish(False, {"in_episode_check": "the menu never drew"},
                      sess, setup, started, argv=argv)

    baseline = sess.model.visual_hash()
    actions["keys"] += 1
    sess.send_keys(["Down"])
    actions["wait"] += 1
    changed, snap = sess.wait_visual_change(baseline_hash=baseline, timeout_ms=6000)
    selected_after_down = snap.selected.text if snap.selected else None
    observations.append({"step": "Down moved the selection bar", "reason": f"visual_change={changed}",
                         "selected": selected_after_down, "screen": snap.to_text()})

    actions["keys"] += 1
    sess.send_keys(["Enter"])
    actions["wait"] += 1
    reason, snap = sess.wait_ready(marker="SELECTED: save", max_wait_ms=8000)
    after_enter = snap.to_text()
    observations.append({"step": "Enter picked save; program reported and exited",
                         "reason": reason, "screen": after_enter})

    actions["wait"] += 1
    exit_info = wait_exit(sess, timeout_s=8.0)
    actions["snapshot"] += 1
    final_screen = sess.snapshot().to_text()
    observations.append({"step": "after exit", "reason": "exit poll", "screen": final_screen})

    close_state = sess.close()
    close_state_name = ("closed_confirmed" if close_state.get("closed_confirmed")
                        else "close_unconfirmed")

    # --------------------------- in-episode claim (from what the PTY showed) --
    claim = bool(selected_after_down and "save" in selected_after_down
                 and "SELECTED: save" in final_screen and "BYE" in final_screen
                 and exit_info["exited"])

    return finish(claim, {
        "in_episode_check": {
            "selected_at_open": selected_at_open,
            "selected_after_one_down": selected_after_down,
            "program_reported_selection": "SELECTED: save" in final_screen,
            "program_reported_bye": "BYE" in final_screen,
            "child_exited": exit_info["exited"],
        },
    }, sess, setup, started, argv=argv, close_state_name=close_state_name,
        close_state=close_state, exit_info=exit_info)


def wait_exit(sess: PtySession, timeout_s: float) -> dict[str, Any]:
    t0 = time.monotonic()
    deadline = t0 + timeout_s
    alive = sess.is_alive()
    while alive and time.monotonic() < deadline:
        sess.pump()
        alive = sess.is_alive()
        if alive:
            time.sleep(0.05)
    sess.pump()
    status = {}
    try:
        status = sess.backend.read_status() or {}
    except Exception:
        status = {}
    proc = getattr(sess.backend, "_proc", None)
    return {
        "exited": not alive,
        "observation": "backend.is_alive() False after pumping to EOF",
        "alive_after_wait": alive,
        "waited_s": round(time.monotonic() - t0, 3),
        "backend_eof_latched": status.get("eof"),
        "child_exitstatus": getattr(proc, "exitstatus", None),
    }


def finish(claim: bool, in_episode: dict[str, Any], sess: PtySession, setup: list[dict[str, Any]],
           started: float, argv: list[str] | None = None, close_state_name: str = "unknown",
           close_state: dict[str, Any] | None = None,
           exit_info: dict[str, Any] | None = None) -> int:
    """Ground truth from the program's own state file + the filesystem."""
    written = STATE_FILE.exists()
    program_state = json.loads(STATE_FILE.read_text(encoding="utf-8")) if written else {}
    state = {
        # judged keys
        "selection": program_state.get("selection"),
        "exited": bool((exit_info or {}).get("exited")),
        # unjudged evidence
        "state_file": str(STATE_FILE),
        "state_file_written": written,
        "program_keys_received": program_state.get("keys_received"),
        "program_cursor_key_form": program_state.get("cursor_key_form"),
        "child_exitstatus": (exit_info or {}).get("child_exitstatus"),
    }

    result = {
        "run_id": RUN_ID,
        "task": TASK,
        "track": TRACK,
        "seed": SEED,
        "model_id": MODEL_ID,
        "budget": BUDGET,
        "actions": sorted(actions),
        "action_counts": dict(sorted(actions.items())),
        "claimed_complete": claim,
        "completion_basis": "child_exit_observed" if claim else "claim_withheld",
        "completion_detail": in_episode.get("in_episode_check", in_episode),
        "fixture_state": state,
        "fixture_state_source": ("program's own PTY output (in-episode) for the claim; the "
                                 "program's own state file (written by it) plus the runtime's "
                                 "exit observation for fixture_state"),
        "setup": setup,
        "session": {
            "driver": "smartcli_core.PtySession directly (no drive-tui CLI on this box)",
            "argv": argv or [],
            "cols": 90, "rows": 24,
            "observations": len(observations),
            "wall_clock_s": round(time.monotonic() - started, 2),
            "cancel": False,
            "cleanup": "PtySession.close() after the child had already exited",
            "process_exited": bool((exit_info or {}).get("exited")),
            "exit_observed_by": (exit_info or {}).get("observation"),
            "exit_evidence": exit_info or {},
            "close_state": close_state_name,
            "close_observed": (f"backend close_state()={close_state}" if close_state else None),
            "close_state_detail": close_state or {},
        },
        "observations": observations,
    }
    RESULT.write_text(json.dumps(result, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"[{RUN_ID}] claimed_complete={claim} actions={sorted(actions)} "
          f"observations={len(observations)} fixture_state=selection={state['selection']!r} "
          f"exited={state['exited']} cursor_key_form={state['program_cursor_key_form']} "
          f"wall_clock={result['session']['wall_clock_s']}s")
    print(f"[{RUN_ID}] result.json -> {RESULT}")
    return 0 if claim else 1


if __name__ == "__main__":
    raise SystemExit(main())
