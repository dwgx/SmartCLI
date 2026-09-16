"""Episode B2_confirm_prompt, track H (hybrid).

No PTY is opened and no keystroke is sent.  The confirmation travels through a
file/API channel: the answer is written to a file and the fixture -- byte-identical
to the U fixture, which simply reads its standard input -- is launched with that
file attached as its stdin.  The program's own output is the record of the answer
it received, and the target file on disk is the record of the write.

Track H permits this; the result is recorded as ``ui_claim: false`` -- it is NOT a
UI pass.

Run: python -B episodes2/b2_confirm_prompt_H_20260916/driver.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import _harness as H  # noqa: E402

TASK = "B2_confirm_prompt"
TRACK = "H"
TRANSPORT = "filesystem/API only (no PTY): answer file piped to the program's stdin"
RUN_ID = f"b2_confirm_prompt_{TRACK}_{H.DATE}"

FIXTURE_SRC = '''"""Fixture for B2, track H: byte-identical to the U fixture (stdin-driven)."""
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
print("CHANNEL stdin_file")
print("BYE")
'''


def main() -> int:
    ep = H.new_episode(TASK, TRACK, TRANSPORT)
    here, actions, observations, started = ep["dir"], ep["actions"], ep["observations"], ep["started"]
    target = here / "episode_b2_hybrid.txt"
    answer_file = here / "answer.txt"
    fixture = here / "confirm_stdin_fixture.py"

    fixture.write_text(FIXTURE_SRC, encoding="utf-8", newline="\n")
    for p in (target, answer_file):
        if p.exists():
            p.unlink()
    setup = [{"what": "fixture program (stdin-driven, same target semantics as track U)",
              "path": str(fixture), "sha256": H.sha256(fixture), "outside_pty": True},
             {"what": "target file absent before the episode", "path": str(target),
              "exists": target.exists(), "outside_pty": True},
             {"what": "hybrid channel", "kind": "answer file attached as the program's stdin",
              "path": str(answer_file), "outside_pty": True}]

    # --------------------------------------------------- hybrid: the answer file
    actions["write_file"] += 1
    answer_file.write_text("y\n", encoding="utf-8", newline="\n")
    observations.append({"step": "answer written to the channel file",
                         "path": str(answer_file), "content": answer_file.read_text()})

    argv = [sys.executable, "-B", str(fixture), str(target)]
    actions["wait"] += 1
    with answer_file.open("rb") as stdin:
        proc = subprocess.run(argv, stdin=stdin, capture_output=True, text=True, timeout=30)
    stdout = proc.stdout
    observations.append({"step": "program ran with the answer file as its stdin",
                         "argv": argv, "returncode": proc.returncode,
                         "stdout": stdout, "stderr": proc.stderr})

    actions["read_file"] += 1
    written = target.exists()
    content = target.read_text(encoding="utf-8") if written else None
    observations.append({"step": "target artifact read back", "exists": written,
                         "content": content})

    claim = bool(proc.returncode == 0 and "ANSWER 'y'" in stdout and "WROTE" in stdout
                 and written and content == "written after confirmation\n")
    fixture_state = {
        "answer": "y" if "ANSWER 'y'" in stdout else None,
        "file_written": written,
        "target": str(target),
        "bytes": target.stat().st_size if written else 0,
        "content": content,
        "program_returncode": proc.returncode,
    }
    return H.finalize(
        run_id=RUN_ID, task=TASK, track=TRACK, transport=TRANSPORT, episode_dir=here,
        actions=actions, observations=observations, setup=setup, claim=claim,
        completion_basis="artifact_readback_verified" if claim else "claim_withheld",
        completion_detail={"in_episode_check": fixture_state},
        fixture_state=fixture_state,
        fixture_state_source=("the program's own stdout for the answer it received; filesystem "
                              "readback for file_written"),
        session={"driver": "none (no PTY session; the program ran as a plain API call)",
                 "argv": argv, "cancel": False,
                 "process_exited": proc.returncode == 0,
                 "exit_observed_by": f"subprocess returncode {proc.returncode}",
                 "close_state": "not_applicable", "close_observed": None},
        started=started, ui_claim=False,
        track_note=("hybrid (track H): the answer travelled through a file attached to the "
                    "program's stdin; no terminal action was used, so this is NOT a UI pass"))


if __name__ == "__main__":
    raise SystemExit(main())
