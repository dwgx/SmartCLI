"""Episode B1_edit_in_editor, track U, POSIX transport (E6, inside Docker).

Same task, same fixture and same strict-UI rules as the Windows U episode: only
``keys``/``text``/``wait``/``snapshot`` are used inside the episode.  What changes
is the runtime path: ``smartcli_core.PosixPtyBackend`` (stdlib ``pty``/``termios``)
instead of ``WinptyBackend``/ConPTY, with the same pyte screen model on top.

Run (from the host):
    docker run --rm -v "D:/Project/SmartCLI:/repo" -v "D:/Project/SmartCLI-v3-runs/W3:/w3" \\
      -w /repo -e SMARTCLI_ROOT=/repo python:3.13-slim sh -lc \\
      "pip install -q pyte==0.8.2 && apt-get update -qq && apt-get install -y -qq vim && \\
       python -B /w3/episodes2/posix_b1_edit_in_editor_20260916/driver.py"
"""
from __future__ import annotations

import random
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import _harness as H  # noqa: E402

TASK = "B1_edit_in_editor"
TRACK = "U"
TRANSPORT = "posix-pty (PosixPtyBackend, Linux/Docker) -- strict UI"
RUN_ID = f"posix_b1_edit_in_editor_{H.DATE}"
THIRD = "third line from an agent"
PRE_STATE = b"line one\nline two\n"

from smartcli_core import PtySession  # noqa: E402

RNG = random.Random(f"{H.SEED}|{TASK}")
SUFFIX = f"{RNG.randrange(0x1000, 0x10000):04x}"
VIM = shutil.which("vim") or shutil.which("vi") or "/usr/bin/vim"


def main() -> int:
    ep = H.new_episode(TASK, TRACK, TRANSPORT, dirname="posix_b1_edit_in_editor_20260916")
    here, actions, observations, started = ep["dir"], ep["actions"], ep["observations"], ep["started"]
    target = here / f"episode_b1_{SUFFIX}.txt"

    target.write_bytes(PRE_STATE)
    setup = [{"what": "fixture pre-state (seeded 2-line file, written outside the PTY)",
              "path": str(target), "bytes": len(PRE_STATE), "sha256": H.sha256(target),
              "content": PRE_STATE.decode(), "outside_pty": True},
             {"what": "editor binary", "path": VIM, "outside_pty": True}]

    argv = [VIM, "-u", "NONE", "-N", str(target)]
    sess = PtySession(cols=100, rows=30)
    sess.start(argv)

    actions["wait"] += 1
    reason, snap = sess.wait_ready(marker="line two", max_wait_ms=15000)
    observations.append({"step": "vim opened the fixture file", "reason": reason,
                         "screen": snap.to_text()})
    if reason == "TIMEOUT":
        return H.finalize(run_id=RUN_ID, task=TASK, track=TRACK, transport=TRANSPORT,
                          episode_dir=here, actions=actions, observations=observations,
                          setup=setup, claim=False, completion_basis="claim_withheld",
                          completion_detail={"in_episode_check": "the buffer never painted"},
                          fixture_state={"file_lines": 2, "contains": None},
                          fixture_state_source="filesystem",
                          session={"driver": "smartcli_core.PtySession (PosixPtyBackend)",
                                   "argv": argv},
                          started=started, ui_claim=True,
                          track_note="strict UI (track U) over the POSIX transport")

    actions["keys"] += 1
    sess.send_keys(["G"])
    actions["keys"] += 1
    sess.send_keys(["o"])
    actions["wait"] += 1
    reason, snap = sess.wait_ready(marker="-- INSERT --", max_wait_ms=8000)
    observations.append({"step": "insert mode opened on a new line 3", "reason": reason,
                         "screen": snap.to_text()})

    actions["text"] += 1
    sess.send_text(THIRD)
    actions["wait"] += 1
    reason, snap = sess.wait_ready(marker=re.escape(THIRD), max_wait_ms=8000)
    in_editor_screen = snap.to_text()
    observations.append({"step": "third line typed into the buffer", "reason": reason,
                         "screen": in_editor_screen})

    actions["keys"] += 1
    sess.send_keys(["Escape"])
    actions["wait"] += 1
    sess.wait_stable(quiet_ms=250, max_wait_ms=4000)
    actions["snapshot"] += 1
    normal_mode_screen = sess.snapshot().to_text()
    observations.append({"step": "back to normal mode", "reason": "wait_stable",
                         "screen": normal_mode_screen})

    actions["text"] += 1
    sess.send_text(":w")
    actions["keys"] += 1
    sess.send_keys(["Enter"])
    actions["wait"] += 1
    reason, snap = sess.wait_ready(marker="written", max_wait_ms=8000)
    written_screen = snap.to_text()
    observations.append({"step": "editor reported the write", "reason": reason,
                         "screen": written_screen})

    actions["text"] += 1
    sess.send_text(":q")
    actions["keys"] += 1
    sess.send_keys(["Enter"])
    actions["wait"] += 1
    exit_info = H.wait_exit(sess, timeout_s=10.0)
    actions["snapshot"] += 1
    final_screen = sess.snapshot().to_text()
    observations.append({"step": "editor exited", "screen": final_screen})

    close_state = sess.close()
    close_state_name = ("closed_confirmed" if close_state.get("closed_confirmed")
                        else "close_unconfirmed")

    r1 = H.find_row(in_editor_screen, "line one")
    r2 = H.find_row(in_editor_screen, "line two")
    r3 = H.find_row(in_editor_screen, THIRD)
    ordered = None not in (r1, r2, r3) and r1 < r2 < r3
    raw = target.read_bytes()
    text = raw.decode("utf-8", "replace")
    lines = text.splitlines()
    claim = bool(ordered and "written" in written_screen and exit_info["exited"]
                 and "-- INSERT --" not in normal_mode_screen
                 and len(lines) == 3 and lines[-1] == THIRD)
    fixture_state = {
        "file_lines": len(lines),
        "contains": THIRD if THIRD in text else None,
        "target": str(target), "bytes": len(raw), "lines": lines,
        "in_episode_buffer_rows": [r1, r2, r3],
        "in_episode_buffer_ordered": ordered,
        "editor_reported_write": "written" in written_screen,
    }
    return H.finalize(
        run_id=RUN_ID, task=TASK, track=TRACK, transport=TRANSPORT, episode_dir=here,
        actions=actions, observations=observations, setup=setup, claim=claim,
        completion_basis="child_exit_observed" if claim else "claim_withheld",
        completion_detail={"in_episode_check": fixture_state},
        fixture_state=fixture_state,
        fixture_state_source=("filesystem read after the PTY was closed; the in-episode "
                              "evidence is what vim painted (buffer rows + status line)"),
        session={"driver": "smartcli_core.PtySession (PosixPtyBackend, Linux container)",
                 "argv": argv, "cols": 100, "rows": 30, "cancel": False,
                 "process_exited": bool(exit_info["exited"]),
                 "exit_observed_by": exit_info["observation"], "exit_evidence": exit_info,
                 "close_state": close_state_name,
                 "close_observed": f"backend close_state()={close_state}",
                 "close_state_detail": close_state},
        started=started, ui_claim=True,
        track_note="strict UI (track U) over the POSIX transport (E6)")


if __name__ == "__main__":
    raise SystemExit(main())
