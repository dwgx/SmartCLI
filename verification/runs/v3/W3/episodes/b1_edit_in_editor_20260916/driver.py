"""Episode B1_edit_in_editor, track U (strict UI).

Fixture: a seeded 2-line temp file inside this run directory.
Episode: Git's vim (real editor) is driven through ``smartcli_core.PtySession``
(ConPTY / WinptyBackend) and must leave a third line ``third line from an agent``.

In-episode actions are PTY-only (keys / text / wait / snapshot). The fixture
pre-state is written before the session starts and the ground truth is read from
the FILESYSTEM after the session is closed -- both are recorded separately from
``actions`` so the track claim stays honest.

Run: python -B episodes/b1_edit_in_editor_20260916/driver.py
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

TASK = "B1_edit_in_editor"
TRACK = "U"
SEED = 20260916
MODEL_ID = "deepseek-v4.1-flash:max (omp backend, dispatched)"
BUDGET = {"episodes": 3, "wall_clock_minutes": 45, "usd": 0}
RUN_ID = "b1_edit_in_editor_20260916"
VIM = r"C:\Program Files\Git\usr\bin\vim.exe"
THIRD = "third line from an agent"
PRE_STATE = b"line one\nline two\n"

HERE = Path(__file__).resolve().parent
RNG = random.Random(f"{SEED}|{TASK}")
SUFFIX = f"{RNG.randrange(0x1000, 0x10000):04x}"
TARGET = HERE / f"episode_b1_{SUFFIX}.txt"
RESULT = HERE / "result.json"

actions: Counter[str] = Counter()
observations: list[dict[str, Any]] = []


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def body_rows(screen: str) -> list[tuple[int, str]]:
    """``(row, text)`` for every rendered screen row (collapsed blank runs skipped)."""
    rows = []
    for line in screen.splitlines():
        m = re.match(r"\s*(\d+)[* ]\| (.*)$", line)
        if m:
            rows.append((int(m.group(1)), m.group(2)))
    return rows


def find_row(screen: str, needle: str) -> int | None:
    for row, text in body_rows(screen):
        if needle in text:
            return row
    return None


def main() -> int:
    started = time.monotonic()

    # ---------------------------------------------------------------- setup
    # Pre-episode fixture state, written OUTSIDE the PTY (recorded, not an action).
    TARGET.write_bytes(PRE_STATE)
    setup = [{
        "what": "fixture pre-state (seeded 2-line temp file)",
        "path": str(TARGET),
        "bytes": len(PRE_STATE),
        "sha256": sha256(TARGET),
        "content": PRE_STATE.decode(),
        "outside_pty": True,
    }]

    argv = [VIM, "-u", "NONE", "-N", str(TARGET)]
    sess = PtySession(cols=100, rows=30)
    sess.start(argv)

    # ------------------------------------------------------------- episode
    actions["wait"] += 1
    reason, snap = sess.wait_ready(marker=re.escape(TARGET.name) + r'" \[unix\]',
                                   max_wait_ms=10000)
    observations.append({"step": "vim opened the fixture file", "reason": reason,
                         "screen": snap.to_text()})
    if reason == "TIMEOUT":
        return finish(False, {"in_episode_check": "vim never painted its status line"},
                      sess, setup, started)

    # G = last line, o = open a new line below it -> INSERT mode on line 3.
    actions["keys"] += 1
    sess.send_keys(["G"])
    actions["keys"] += 1
    sess.send_keys(["o"])
    actions["wait"] += 1
    reason, snap = sess.wait_ready(marker="-- INSERT --", max_wait_ms=6000)
    observations.append({"step": "insert mode opened on a new line 3", "reason": reason,
                         "screen": snap.to_text()})

    actions["text"] += 1
    sess.send_text(THIRD)
    actions["wait"] += 1
    reason, snap = sess.wait_ready(marker=re.escape(THIRD), max_wait_ms=6000)
    in_editor_screen = snap.to_text()
    observations.append({"step": "third line typed into the buffer", "reason": reason,
                         "screen": in_editor_screen})

    actions["keys"] += 1
    sess.send_keys(["Escape"])
    actions["wait"] += 1
    sess.wait_stable(quiet_ms=250, max_wait_ms=4000)
    actions["snapshot"] += 1
    snap = sess.snapshot()
    normal_mode_screen = snap.to_text()
    observations.append({"step": "back to normal mode", "reason": "wait_stable",
                         "screen": normal_mode_screen})

    # ``:w`` so the editor itself reports the write on its own status line.
    actions["text"] += 1
    sess.send_text(":w")
    actions["keys"] += 1
    sess.send_keys(["Enter"])
    actions["wait"] += 1
    reason, snap = sess.wait_ready(marker="written", max_wait_ms=6000)
    written_screen = snap.to_text()
    observations.append({"step": "editor reported the write", "reason": reason,
                         "screen": written_screen})

    actions["text"] += 1
    sess.send_text(":q")
    actions["keys"] += 1
    sess.send_keys(["Enter"])
    actions["wait"] += 1
    exit_info = wait_exit(sess, timeout_s=8.0)
    actions["snapshot"] += 1
    final_screen = sess.snapshot().to_text()
    observations.append({"step": "editor exited", "reason": "exit poll",
                         "screen": final_screen})

    close_state = sess.close()
    close_state_name = "closed_confirmed" if close_state.get("closed_confirmed") else "close_unconfirmed"

    # --------------------------- in-episode claim (from what the PTY showed) --
    r1, r2, r3 = (find_row(in_editor_screen, "line one"),
                  find_row(in_editor_screen, "line two"),
                  find_row(in_editor_screen, THIRD))
    ordered = None not in (r1, r2, r3) and r1 < r2 < r3
    editor_reported_write = "written" in written_screen
    claim = bool(ordered and editor_reported_write and exit_info["exited"]
                 and "-- INSERT --" not in normal_mode_screen)

    return finish(claim, {
        "in_episode_check": {
            "buffer_rows_line_one_two_third": [r1, r2, r3],
            "third_line_is_last_of_the_three": ordered,
            "editor_status_line_reported_write": editor_reported_write,
            "left_insert_mode": "-- INSERT --" not in normal_mode_screen,
            "vim_exited_on_its_own_after": ":q",
        },
    }, sess, setup, started, close_state_name=close_state_name,
        close_state=close_state, exit_info=exit_info, argv=argv)


def wait_exit(sess: PtySession, timeout_s: float) -> dict[str, Any]:
    """Poll the live child until it is gone. This is the exit observation."""
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
           started: float, close_state_name: str = "unknown",
           close_state: dict[str, Any] | None = None,
           exit_info: dict[str, Any] | None = None,
           argv: list[str] | None = None) -> int:
    """Ground truth from the FILESYSTEM, then write result.json and score-shape it."""
    raw = TARGET.read_bytes()
    text = raw.decode("utf-8", "replace")
    lines = text.splitlines()
    state = {
        # judged keys
        "file_lines": len(lines),
        "contains": THIRD if THIRD in text else None,
        # unjudged evidence
        "target": str(TARGET),
        "bytes": len(raw),
        "lines": lines,
        "raw_repr": raw.decode("utf-8", "replace").replace("\r", "\\r").replace("\n", "\\n"),
        "third_line_is_last": bool(lines and lines[-1] == THIRD),
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
        "fixture_state_source": ("program's own PTY output (in-episode) for the claim; "
                                 "post-episode filesystem read after the PTY was closed "
                                 "for fixture_state"),
        "setup": setup,
        "session": {
            "driver": "smartcli_core.PtySession directly (no drive-tui CLI on this box)",
            "argv": argv or [],
            "cols": 100, "rows": 30,
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
          f"observations={len(observations)} fixture_state={state['lines']!r} "
          f"wall_clock={result['session']['wall_clock_s']}s")
    print(f"[{RUN_ID}] result.json -> {RESULT}")
    return 0 if claim else 1


if __name__ == "__main__":
    raise SystemExit(main())
