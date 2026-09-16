"""Episode B1_edit_in_editor, track H (hybrid).

No PTY is opened and no keystroke is sent: the artifact is produced through the
filesystem (a file write) and verified by reading it back.  Track H allows exactly
that; the result is therefore recorded as ``ui_claim: false`` -- it is NOT a UI
pass and must never be counted as one.

Run: python -B episodes2/b1_edit_in_editor_H_20260916/driver.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import _harness as H  # noqa: E402

TASK = "B1_edit_in_editor"
TRACK = "H"
TRANSPORT = "filesystem only (no PTY, no keystrokes)"
RUN_ID = f"b1_edit_in_editor_{TRACK}_{H.DATE}"
THIRD = "third line from an agent"
CONTENT = f"line one\nline two\n{THIRD}\n"


def main() -> int:
    ep = H.new_episode(TASK, TRACK, TRANSPORT)
    here, actions, observations, started = ep["dir"], ep["actions"], ep["observations"], ep["started"]
    target = here / "episode_b1_hybrid.txt"

    if target.exists():
        target.unlink()
    setup = [{"what": "artifact absent before the episode", "path": str(target),
              "exists": target.exists(), "outside_pty": True},
             {"what": "hybrid channel", "kind": "filesystem write/readback",
              "outside_pty": True}]

    # ------------------------------------------------------- hybrid: the write
    actions["write_file"] += 1
    target.write_text(CONTENT, encoding="utf-8", newline="\n")
    observations.append({"step": "artifact written through the filesystem",
                         "path": str(target), "bytes": target.stat().st_size})

    # ---------------------------------------------------- hybrid: the readback
    actions["read_file"] += 1
    raw = target.read_bytes()
    text = raw.decode("utf-8", "replace")
    lines = text.splitlines()
    observations.append({"step": "artifact read back", "lines": lines,
                         "sha256": H.sha256(target)})

    claim = bool(len(lines) == 3 and lines[-1] == THIRD)
    fixture_state = {
        "file_lines": len(lines),
        "contains": THIRD if THIRD in text else None,
        "target": str(target), "bytes": len(raw), "lines": lines,
    }
    return H.finalize(
        run_id=RUN_ID, task=TASK, track=TRACK, transport=TRANSPORT, episode_dir=here,
        actions=actions, observations=observations, setup=setup, claim=claim,
        completion_basis="artifact_readback_verified" if claim else "claim_withheld",
        completion_detail={"in_episode_check": fixture_state},
        fixture_state=fixture_state,
        fixture_state_source="filesystem readback of the artifact the episode wrote",
        session={"driver": "none (no PTY session was opened for this episode)",
                 "argv": [], "cancel": False, "process_exited": False,
                 "close_state": "not_applicable", "close_observed": None},
        started=started, ui_claim=False,
        track_note=("hybrid (track H): the artifact was produced by a file write and verified "
                    "by a file read; no terminal action was used, so this is NOT a UI pass"))


if __name__ == "__main__":
    raise SystemExit(main())
