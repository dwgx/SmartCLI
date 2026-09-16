"""Shared plumbing for the episodes2 round (tracks A/H on this box, POSIX in Docker).

Result shape is the one the U-track drivers under ``episodes/`` produced, so
``judge.py`` scores these files unchanged.  This round adds four fields the
summary needs and the judge ignores: ``transport``, ``ui_claim``, ``track_note``
and a top-level ``wall_clock_s``.

Only the *in-episode* actions are recorded in ``result['actions']``; fixture
pre-state, launch argv, ground-truth reads and channel plumbing live in
``setup``/``session``, exactly as the U episodes did it.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

SMARTCLI_ROOT = os.environ.get("SMARTCLI_ROOT", r"D:\Project\SmartCLI")
if SMARTCLI_ROOT not in sys.path:
    sys.path.insert(0, SMARTCLI_ROOT)

SEED = 20260916
MODEL_ID = "deepseek-v4.1-flash:max (omp backend, dispatched)"
BUDGET = {"episodes": 9, "wall_clock_minutes": 60, "usd": 0}
DATE = "20260916"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def wait_exit(sess: Any, timeout_s: float = 8.0) -> dict[str, Any]:
    """Poll the live child until it is gone.  This is the exit observation."""
    t0 = time.monotonic()
    deadline = t0 + timeout_s
    alive = sess.is_alive()
    while alive and time.monotonic() < deadline:
        sess.pump()
        alive = sess.is_alive()
        if alive:
            time.sleep(0.05)
    sess.pump()
    try:
        status = sess.backend.read_status() or {}
    except Exception:
        status = {}
    proc = getattr(sess.backend, "_proc", None)  # WinptyBackend only
    return {
        "exited": not alive,
        "observation": "backend.is_alive() False after pumping to EOF",
        "alive_after_wait": alive,
        "waited_s": round(time.monotonic() - t0, 3),
        "backend_eof_latched": status.get("eof"),
        "child_exitstatus": getattr(proc, "exitstatus", None),
        "backend_pid": getattr(sess.backend, "_pid", None),
    }


def body_rows(screen: str) -> list[tuple[int, str]]:
    """``(row, text)`` for every vim buffer row rendered on the screen."""
    import re
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


def write_plan(episode_dir: Path, task: str, track: str, note: str) -> dict[str, Any]:
    """Pre-registered run parameters, the shape ``judge.py validate`` asks for."""
    the_plan = {
        "task": task,
        "track": track,
        "transport": note,
        "seed": SEED,
        "model_id": MODEL_ID,
        "spend_cap": {"usd": 0, "note": "no paid calls: local PTY/file episodes on this box"},
    }
    (episode_dir / "plan.json").write_text(json.dumps(the_plan, indent=1) + "\n", encoding="utf-8")
    return the_plan


def finalize(*, run_id: str, task: str, track: str, transport: str, episode_dir: Path,
             actions: Counter[str], observations: list[dict[str, Any]],
             setup: list[dict[str, Any]], claim: bool, completion_basis: str,
             completion_detail: dict[str, Any], fixture_state: dict[str, Any],
             fixture_state_source: str, session: dict[str, Any], started: float,
             ui_claim: bool, track_note: str) -> int:
    """Write ``result.json`` and return the episode's process exit code."""
    wall = round(time.monotonic() - started, 2)
    session = dict(session)
    session.setdefault("observations", len(observations))
    session["wall_clock_s"] = wall
    result = {
        "run_id": run_id,
        "task": task,
        "track": track,
        "seed": SEED,
        "model_id": MODEL_ID,
        "budget": BUDGET,
        "transport": transport,
        "actions": sorted(actions),
        "action_counts": dict(sorted(actions.items())),
        "claimed_complete": claim,
        "completion_basis": completion_basis,
        "completion_detail": completion_detail,
        "fixture_state": fixture_state,
        "fixture_state_source": fixture_state_source,
        "ui_claim": ui_claim,
        "track_note": track_note,
        "setup": setup,
        "session": session,
        "observations": observations,
        "wall_clock_s": wall,
    }
    (episode_dir / "result.json").write_text(
        json.dumps(result, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"[{run_id}] claimed_complete={claim} actions={sorted(actions)} "
          f"observations={len(observations)} fixture_state={fixture_state} "
          f"wall_clock={wall}s")
    print(f"[{run_id}] result.json -> {episode_dir / 'result.json'}")
    return 0 if claim else 1


TASK_SLUGS = {"B1_edit_in_editor": "b1_edit_in_editor",
              "B2_confirm_prompt": "b2_confirm_prompt",
              "B3_navigate_menu": "b3_navigate_menu"}


def new_episode(task: str, track: str, transport: str, dirname: str | None = None) -> dict[str, Any]:
    """Common scaffolding: the episode directory, its plan, and empty counters."""
    here = Path(__file__).resolve().parent
    episode_dir = here / (dirname or f"{TASK_SLUGS[task]}_{track}_{DATE}")
    episode_dir.mkdir(parents=True, exist_ok=True)
    write_plan(episode_dir, task, track, transport)
    return {
        "dir": episode_dir,
        "actions": Counter(),
        "observations": [],
        "started": time.monotonic(),
    }
