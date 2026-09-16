"""Episode B2_confirm_prompt, track U, POSIX transport (E6, inside Docker).

Same fixture as the Windows U episode (byte-identical source), same strict-UI rules
(keys/text/wait/snapshot only); the runtime path is ``PosixPtyBackend`` under Linux.

Run (from the host):
    docker run --rm -v "D:/Project/SmartCLI:/repo" -v "D:/Project/SmartCLI-v3-runs/W3:/w3" \\
      -w /repo -e SMARTCLI_ROOT=/repo python:3.13-slim sh -lc \\
      "pip install -q pyte==0.8.2 && python -B /w3/episodes2/posix_b2_confirm_prompt_20260916/driver.py"
"""
from __future__ import annotations

import random
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import _harness as H  # noqa: E402

TASK = "B2_confirm_prompt"
TRACK = "U"
TRANSPORT = "posix-pty (PosixPtyBackend, Linux/Docker) -- strict UI"
RUN_ID = f"posix_b2_confirm_prompt_{H.DATE}"

from smartcli_core import PtySession  # noqa: E402

RNG = random.Random(f"{H.SEED}|{TASK}")
SUFFIX = f"{RNG.randrange(0x1000, 0x10000):04x}"

FIXTURE_SRC = '''"""Fixture for B2 on POSIX: ask for confirmation, write only on y."""
import pathlib
import sys

target = pathlib.Path(sys.argv[1])
print(f"Overwrite {target.name}? [y/N] ", end="", flush=True)
line = sys.stdin.readline()
answer = line.strip()[:1].lower()
print(f"ANSWER {answer!r}")
if answer == "y":
    target.write_text("written after confirmation\\n", encoding="utf-8")
    print(f"WROTE {target.name} bytes={target.stat().st_size} file_written=True")
else:
    print(f"NO-WRITE {target.name} file_written=False")
print("BYE")
'''


def main() -> int:
    ep = H.new_episode(TASK, TRACK, TRANSPORT, dirname="posix_b2_confirm_prompt_20260916")
    here, actions, observations, started = ep["dir"], ep["actions"], ep["observations"], ep["started"]
    target = here / f"episode_b2_{SUFFIX}.txt"
    fixture = here / "confirm_fixture.py"

    fixture.write_text(FIXTURE_SRC, encoding="utf-8", newline="\n")
    if target.exists():
        target.unlink()
    setup = [{"what": "fixture program", "path": str(fixture), "sha256": H.sha256(fixture),
              "outside_pty": True},
             {"what": "target file absent before the episode", "path": str(target),
              "exists": target.exists(), "outside_pty": True}]

    argv = [sys.executable, "-B", str(fixture), str(target)]
    sess = PtySession(cols=90, rows=24)
    sess.start(argv)

    actions["wait"] += 1
    reason, snap = sess.wait_ready(marker=r"\[y/N\]", max_wait_ms=15000)
    observations.append({"step": "confirmation prompt on screen", "reason": reason,
                         "screen": snap.to_text()})
    if reason == "TIMEOUT":
        return H.finalize(run_id=RUN_ID, task=TASK, track=TRACK, transport=TRANSPORT,
                          episode_dir=here, actions=actions, observations=observations,
                          setup=setup, claim=False, completion_basis="claim_withheld",
                          completion_detail={"in_episode_check": "the prompt never appeared"},
                          fixture_state={"answer": None, "file_written": target.exists()},
                          fixture_state_source="filesystem",
                          session={"driver": "smartcli_core.PtySession (PosixPtyBackend)",
                                   "argv": argv},
                          started=started, ui_claim=True,
                          track_note="strict UI (track U) over the POSIX transport")

    actions["text"] += 1
    sess.send_text("y")
    actions["keys"] += 1
    sess.send_keys(["Enter"])
    actions["wait"] += 1
    reason, snap = sess.wait_ready(marker="WROTE", max_wait_ms=8000)
    after_answer = snap.to_text()
    observations.append({"step": "program answered and reported its own write",
                         "reason": reason, "screen": after_answer})

    actions["wait"] += 1
    exit_info = H.wait_exit(sess, timeout_s=10.0)
    actions["snapshot"] += 1
    final_screen = sess.snapshot().to_text()
    observations.append({"step": "program exited", "screen": final_screen})

    close_state = sess.close()
    close_state_name = ("closed_confirmed" if close_state.get("closed_confirmed")
                        else "close_unconfirmed")

    m = re.search(r"ANSWER '(.*)'", final_screen)
    seen_answer = m.group(1) if m else None
    written = target.exists()
    claim = bool(seen_answer == "y" and "WROTE" in final_screen and written
                 and exit_info["exited"] and "BYE" in final_screen)
    fixture_state = {
        "answer": seen_answer,
        "file_written": written,
        "target": str(target),
        "bytes": target.stat().st_size if written else 0,
        "content": target.read_text(encoding="utf-8") if written else None,
    }
    return H.finalize(
        run_id=RUN_ID, task=TASK, track=TRACK, transport=TRANSPORT, episode_dir=here,
        actions=actions, observations=observations, setup=setup, claim=claim,
        completion_basis="child_exit_observed" if claim else "claim_withheld",
        completion_detail={"in_episode_check": fixture_state},
        fixture_state=fixture_state,
        fixture_state_source=("the program's own PTY output for the answer; filesystem read "
                              "after the PTY was closed for file_written"),
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
