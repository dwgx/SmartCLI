"""Episode B2_confirm_prompt, track U (strict UI).

Fixture: a seeded interactive program that asks ``Overwrite <file>? [y/N]`` and
writes the file only on ``y``.
Episode: answer the prompt through the PTY so the program writes its file.

In-episode actions are PTY-only (keys / text / wait / snapshot); the fixture
program is written before the session starts and the ground truth is read from
the filesystem after the session is closed.

Run: python -B episodes/b2_confirm_prompt_20260916/driver.py
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

TASK = "B2_confirm_prompt"
TRACK = "U"
SEED = 20260916
MODEL_ID = "deepseek-v4.1-flash:max (omp backend, dispatched)"
BUDGET = {"episodes": 3, "wall_clock_minutes": 45, "usd": 0}
RUN_ID = "b2_confirm_prompt_20260916"

HERE = Path(__file__).resolve().parent
RNG = random.Random(f"{SEED}|{TASK}")
SUFFIX = f"{RNG.randrange(0x1000, 0x10000):04x}"
TARGET = HERE / f"episode_b2_{SUFFIX}.txt"
FIXTURE = HERE / "confirm_fixture.py"
RESULT = HERE / "result.json"

FIXTURE_SRC = '''"""Fixture for B2: ask for confirmation, write only on y."""
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

actions: Counter[str] = Counter()
observations: list[dict[str, Any]] = []


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def body_rows(screen: str) -> list[tuple[int, str]]:
    rows = []
    for line in screen.splitlines():
        m = re.match(r"\s*(\d+)[* ]\| (.*)$", line)
        if m:
            rows.append((int(m.group(1)), m.group(2)))
    return rows


def main() -> int:
    started = time.monotonic()

    # ---------------------------------------------------------------- setup
    FIXTURE.write_text(FIXTURE_SRC, encoding="utf-8", newline="\n")
    if TARGET.exists():
        TARGET.unlink()
    setup = [
        {"what": "fixture program", "path": str(FIXTURE), "sha256": sha256(FIXTURE),
         "outside_pty": True},
        {"what": "target file absent before the episode", "path": str(TARGET),
         "exists": TARGET.exists(), "outside_pty": True},
    ]

    argv = [sys.executable, "-B", str(FIXTURE), str(TARGET)]
    sess = PtySession(cols=90, rows=24)
    sess.start(argv)

    # ------------------------------------------------------------- episode
    actions["wait"] += 1
    reason, snap = sess.wait_ready(marker=r"\[y/N\]", max_wait_ms=10000)
    observations.append({"step": "confirmation prompt on screen", "reason": reason,
                         "screen": snap.to_text()})
    if reason == "TIMEOUT":
        return finish(False, {"in_episode_check": "the prompt never appeared"},
                      sess, setup, started, argv=argv)

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
    exit_info = wait_exit(sess, timeout_s=8.0)
    actions["snapshot"] += 1
    final_screen = sess.snapshot().to_text()
    observations.append({"step": "program exited", "reason": "exit poll", "screen": final_screen})

    close_state = sess.close()
    close_state_name = ("closed_confirmed" if close_state.get("closed_confirmed")
                        else "close_unconfirmed")

    # --------------------------- in-episode claim (from what the PTY showed) --
    m = re.search(r"ANSWER '(.*)'", final_screen)
    seen_answer = m.group(1) if m else None
    claim = bool(seen_answer == "y" and "WROTE" in final_screen
                 and exit_info["exited"] and "BYE" in final_screen)

    return finish(claim, {
        "in_episode_check": {
            "answer_echoed_by_program": seen_answer,
            "program_reported_write": "WROTE" in final_screen,
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
    """Ground truth from the FILESYSTEM, then write result.json."""
    written = TARGET.exists()
    content = TARGET.read_text(encoding="utf-8") if written else None
    state = {
        # judged keys
        "answer": (in_episode.get("in_episode_check") or {}).get("answer_echoed_by_program", None),
        "file_written": written,
        # unjudged evidence
        "target": str(TARGET),
        "bytes": TARGET.stat().st_size if written else 0,
        "content": content,
        "fixture_program": str(FIXTURE),
        "fixture_sha256": sha256(FIXTURE),
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
        "fixture_state_source": ("program's own PTY output (in-episode) for the answer; "
                                 "post-episode filesystem read after the PTY was closed "
                                 "for file_written"),
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
          f"observations={len(observations)} fixture_state=answer={state['answer']!r} "
          f"file_written={state['file_written']} wall_clock={result['session']['wall_clock_s']}s")
    print(f"[{RUN_ID}] result.json -> {RESULT}")
    return 0 if claim else 1


if __name__ == "__main__":
    raise SystemExit(main())
