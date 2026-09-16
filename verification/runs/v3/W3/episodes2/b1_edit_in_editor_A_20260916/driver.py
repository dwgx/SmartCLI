"""Episode B1_edit_in_editor, track A (app-adapted).

Transport: the same ConPTY session as track U, plus vim's *own enumerated
application channel* -- the client-server protocol (``--servername`` /
``--remote-expr`` / ``--remote-send``).  The edit and the write are performed
through that channel and are counted as ``app_channel`` actions.

Enumerated app channel: ``vim --servername <name> --remote-expr|--remote-send``
(documented in ``vim --help``; this build reports ``+clientserver``).

Track U used keystrokes only.  Here no keystroke is sent into the UI: the buffer
insertion, the write and the quit all travel over the client-server channel, and
the PTY is used to observe what the editor itself painted.

Run: python -B episodes2/b1_edit_in_editor_A_20260916/driver.py
"""
from __future__ import annotations

import random
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import _harness as H  # noqa: E402

TASK = "B1_edit_in_editor"
TRACK = "A"
TRANSPORT = "windows-conpty (WinptyBackend) + vim client-server app channel"
RUN_ID = f"b1_edit_in_editor_{TRACK}_{H.DATE}"
VIM = r"C:\Program Files\Git\usr\bin\vim.exe"
THIRD = "third line from an agent"
PRE_STATE = b"line one\nline two\n"

from smartcli_core import PtySession  # noqa: E402

RNG = random.Random(f"{H.SEED}|{TASK}")
SUFFIX = f"{RNG.randrange(0x1000, 0x10000):04x}"


def server_expr(name: str, expr: str) -> dict:
    """One round trip on the app channel: evaluate ``expr`` in the running vim."""
    p = subprocess.run([VIM, "--servername", name, "--remote-expr", expr],
                       capture_output=True, text=True, timeout=20)
    return {"kind": "remote-expr", "expr": expr, "rc": p.returncode,
            "stdout": p.stdout.strip(), "stderr": p.stderr.strip()}


def server_send(name: str, keys: str) -> dict:
    """One round trip on the app channel: hand vim a key notation string."""
    p = subprocess.run([VIM, "--servername", name, "--remote-send", keys],
                       capture_output=True, text=True, timeout=20)
    return {"kind": "remote-send", "keys": keys, "rc": p.returncode,
            "stdout": p.stdout.strip(), "stderr": p.stderr.strip()}


def main() -> int:
    ep = H.new_episode(TASK, TRACK, TRANSPORT)
    here, actions, observations, started = ep["dir"], ep["actions"], ep["observations"], ep["started"]
    target = here / f"episode_b1_{SUFFIX}.txt"
    server = f"OMPA1{SUFFIX.upper()}"

    target.write_bytes(PRE_STATE)
    setup = [{"what": "fixture pre-state (seeded 2-line file, written outside the PTY)",
              "path": str(target), "bytes": len(PRE_STATE), "sha256": H.sha256(target),
              "content": PRE_STATE.decode(), "outside_pty": True},
             {"what": "enumerated app channel", "kind": "vim clientserver",
              "servername": server, "outside_pty": True}]

    argv = [VIM, "-u", "NONE", "-N", "--servername", server, str(target)]
    sess = PtySession(cols=100, rows=30)
    sess.start(argv)

    actions["wait"] += 1
    reason, snap = sess.wait_ready(marker="line two", max_wait_ms=10000)
    observations.append({"step": "vim opened the fixture file", "reason": reason,
                         "screen": snap.to_text()})
    if reason == "TIMEOUT":
        return H.finalize(run_id=RUN_ID, task=TASK, track=TRACK, transport=TRANSPORT,
                          episode_dir=here, actions=actions, observations=observations,
                          setup=setup, claim=False, completion_basis="claim_withheld",
                          completion_detail={"in_episode_check": "the buffer never painted"},
                          fixture_state={"file_lines": 2, "contains": None},
                          fixture_state_source="filesystem",
                          session={"driver": "smartcli_core.PtySession", "argv": argv},
                          started=started, ui_claim=False,
                          track_note="app-adapted: clientserver channel plus PTY observation")

    # ---------------------------------------------- app channel: the edit
    actions["app_channel"] += 1
    insert = server_expr(server, f"append(2, '{THIRD}')")
    actions["app_channel"] += 1
    buffer = server_expr(server, "join(getline(1, '$'), ' | ')")
    observations.append({"step": "third line appended to the buffer over the app channel",
                         "append": insert, "buffer_after": buffer})

    actions["app_channel"] += 1
    redraw = server_send(server, ":redraw<CR>")
    actions["wait"] += 1
    sess.wait_stable(quiet_ms=250, max_wait_ms=4000)
    actions["snapshot"] += 1
    in_editor_screen = sess.snapshot().to_text()
    observations.append({"step": "screen after the channel edit", "redraw": redraw,
                         "screen": in_editor_screen})

    # ---------------------------------------------- app channel: the write
    actions["app_channel"] += 1
    write = server_send(server, ":w<CR>")
    actions["wait"] += 1
    reason, snap = sess.wait_ready(marker="written", max_wait_ms=8000)
    written_screen = snap.to_text()
    observations.append({"step": "editor reported the write after the channel :w",
                         "write": write, "reason": reason, "screen": written_screen})

    actions["app_channel"] += 1
    quit_ = server_send(server, ":q<CR>")
    actions["wait"] += 1
    exit_info = H.wait_exit(sess, timeout_s=8.0)
    actions["snapshot"] += 1
    final_screen = sess.snapshot().to_text()
    observations.append({"step": "editor exited", "quit": quit_, "screen": final_screen})

    close_state = sess.close()
    close_state_name = ("closed_confirmed" if close_state.get("closed_confirmed")
                        else "close_unconfirmed")

    r1 = H.find_row(in_editor_screen, "line one")
    r2 = H.find_row(in_editor_screen, "line two")
    r3 = H.find_row(in_editor_screen, THIRD)
    ordered = None not in (r1, r2, r3) and r1 < r2 < r3
    file_bytes = target.read_bytes().decode("utf-8", "replace")
    lines = file_bytes.splitlines()
    claim = bool(insert["stdout"] == "0"
                 and buffer["stdout"] == f"line one | line two | {THIRD}"
                 and "written" in written_screen
                 and exit_info["exited"])
    fixture_state = {
        "file_lines": len(lines),
        "contains": THIRD if THIRD in file_bytes else None,
        "target": str(target), "bytes": len(target.read_bytes()), "lines": lines,
        "in_episode_buffer_rows": [r1, r2, r3],
        "in_episode_buffer_ordered": ordered,
        "append_returned": insert["stdout"],
        "editor_reported_write": "written" in written_screen,
    }
    return H.finalize(
        run_id=RUN_ID, task=TASK, track=TRACK, transport=TRANSPORT, episode_dir=here,
        actions=actions, observations=observations, setup=setup, claim=claim,
        completion_basis="child_exit_observed" if claim else "claim_withheld",
        completion_detail={"in_episode_check": fixture_state},
        fixture_state=fixture_state,
        fixture_state_source=("filesystem read after the PTY was closed; the in-episode "
                              "evidence is the app channel's own return values plus the "
                              "editor's status line"),
        session={"driver": "smartcli_core.PtySession + vim clientserver",
                 "argv": argv, "cols": 100, "rows": 30, "cancel": False,
                 "process_exited": bool(exit_info["exited"]),
                 "exit_observed_by": exit_info["observation"], "exit_evidence": exit_info,
                 "close_state": close_state_name,
                 "close_observed": f"backend close_state()={close_state}",
                 "close_state_detail": close_state},
        started=started, ui_claim=False,
        track_note=("app-adapted (track A): the edit, the write and the quit travelled over "
                    "vim's client-server channel; counted as app_channel actions"))


if __name__ == "__main__":
    raise SystemExit(main())
