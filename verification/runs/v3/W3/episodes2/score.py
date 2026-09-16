"""Score every episodes2 result with the real judge and write SUMMARY.json.

The judge is imported from the run root (``W3/judge.py``) -- this script defines no
scoring of its own.  Each episode's ``plan.json`` is the pre-registered run
(task/track/seed/model_id/spend cap); ``fixture_state`` comes from the episode's own
``result.json``, which each driver filled from the filesystem or the program's own
output.

Run: python -B episodes2/score.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

import judge as J  # noqa: E402

MODEL_ID = "deepseek-v4.1-flash:max (omp backend, dispatched)"


def load(d: Path) -> tuple[dict, dict, dict]:
    result = json.loads((d / "result.json").read_text(encoding="utf-8"))
    the_plan = json.loads((d / "plan.json").read_text(encoding="utf-8"))
    return result, result["fixture_state"], the_plan


def main() -> int:
    episodes = []
    for d in sorted(HERE.iterdir()):
        if not (d.is_dir() and (d / "result.json").exists()):
            continue
        result, state, the_plan = load(d)
        verdict = J.judge(result, state, the_plan)
        line = {"run_id": result["run_id"], "task": result["task"], "track": result["track"],
                "transport": result["transport"], "verdict": verdict["code"],
                "counts_as": verdict["counts_as"],
                "reject_code": None if verdict["ok"] else verdict["code"],
                "wall_clock_s": result.get("wall_clock_s"),
                "actions": result["actions"], "model_id": result["model_id"],
                "ui_claim": result.get("ui_claim"),
                "result_json": str(d / "result.json"),
                "fixture_state": state}
        episodes.append(line)
        print(f"[{result['run_id']}] task={result['task']} track={result['track']} "
              f"transport={result['transport']!r} verdict={json.dumps(verdict)} "
              f"wall_clock={result.get('wall_clock_s')}s actions={result['actions']}")

    # ------------------------------------------- negative controls on this work
    controls = []
    for cname, run_id, mutate in (
            ("hybrid_result_relabelled_as_strict_ui", "b1_edit_in_editor_H_20260916",
             {"track": "U"}),
            ("app_channel_result_relabelled_as_strict_ui", "b1_edit_in_editor_A_20260916",
             {"track": "U"}),
    ):
        d = next(x for x in HERE.iterdir() if x.is_dir() and (x / "result.json").exists()
                 and json.loads((x / "result.json").read_text(encoding="utf-8"))["run_id"] == run_id)
        result, state, the_plan = load(d)
        result = {**result, **mutate}
        the_plan = {**the_plan, **mutate}
        verdict = J.judge(result, state, the_plan)
        controls.append({"control": cname, "source": run_id, "expected": "track_violation",
                         "code": verdict["code"], "passes_control": verdict["code"] == "track_violation"})
        print(f"[control] {cname}: {json.dumps(verdict)}")

    # a fabricated pass on top of a real episode: same run, false fixture claim
    d = next(x for x in HERE.iterdir() if x.is_dir() and (x / "result.json").exists()
             and json.loads((x / "result.json").read_text(encoding="utf-8"))["run_id"]
             == "b1_edit_in_editor_H_20260916")
    result, state, the_plan = load(d)
    verdict = J.judge(result, {**state, "file_lines": 2}, the_plan)
    controls.append({"control": "fabricated_completion_on_a_real_hybrid_run",
                     "source": result["run_id"], "expected": "false_completion",
                     "code": verdict["code"], "passes_control": verdict["code"] == "false_completion"})
    print(f"[control] fabricated_completion_on_a_real_hybrid_run: {json.dumps(verdict)}")

    counts = {"pass": 0, "failure": 0, "rejected": 0}
    for e in episodes:
        counts[e["counts_as"]] += 1
    summary = {
        "benchmark": "W3 minimal benchmark (judge.py) -- episodes2: tracks A/H on this box + POSIX E6",
        "model_id": MODEL_ID,
        "budget": {"episodes": 9, "wall_clock_minutes": 60, "usd": 0},
        "runtime_under_test": "D:\\Project\\SmartCLI\\smartcli_core v0.3.2 (imported, never edited); "
                              "Windows WinptyBackend/ConPTY for tracks A/H-episode PTYs, Linux "
                              "PosixPtyBackend inside python:3.13-slim for the POSIX set",
        "judge": "W3/judge.py (imported by this scorer; nothing re-implemented here)",
        "judge_selftest": {k: v for k, v in J.judge_selftest().items() if k != "results"},
        "transports": {
            "windows-conpty": "smartcli_core.PtySession -> WinptyBackend (ConPTY), host Python 3.14",
            "posix-pty": "smartcli_core.PtySession -> PosixPtyBackend (stdlib pty/termios), "
                         "python:3.13-slim container, pyte==0.8.2",
            "filesystem/api": "no PTY opened at all (track H) -- files/APIs only",
        },
        "episodes": episodes,
        "totals": {"episodes_run": len(episodes), **counts,
                   "wall_clock_s": round(sum(e["wall_clock_s"] or 0 for e in episodes), 2)},
        "negative_controls_on_this_work": controls,
        "note": ("`actions` lists only what each episode did while it was running; fixture pre-state, "
                 "launch argv, channel endpoints and ground-truth reads live in setup/session.  "
                 "Track H results carry ui_claim=false and are not UI passes -- the control "
                 "'hybrid_result_relabelled_as_strict_ui' is what the judge does to a hybrid result "
                 "presented as a UI one."),
    }
    (HERE / "SUMMARY.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False) + "\n",
                                       encoding="utf-8")
    print(f"\nepisodes={len(episodes)} pass={counts['pass']} failure={counts['failure']} "
          f"rejected={counts['rejected']}")
    print(f"SUMMARY.json -> {HERE / 'SUMMARY.json'}")
    return 0 if counts["pass"] == len(episodes) and all(c["passes_control"] for c in controls) else 1


if __name__ == "__main__":
    raise SystemExit(main())
