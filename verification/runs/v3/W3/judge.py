"""A minimal offline benchmark: fixture, judge, and the judge's own negative controls.

The order matters: the JUDGE is proven first, because a benchmark whose judge
accepts a fabricated result produces confident numbers that mean nothing. Nothing
here starts a process, a PTY, a network call or a model: the fixture is a small
deterministic state machine and the judge compares the model's *reported* outcome
against the fixture's *own* state.

Three tracks, as BENCHMARK_MIN.md requires:
  U (strict UI)      only terminal actions are allowed; a file read is a violation
  A (app-adapted)    an enumerated application channel is allowed, and counted
  H (hybrid)         files/APIs are allowed; the result is NOT a UI claim

Run:
    python -B W3/judge.py judge-selftest
    python -B -m unittest discover -s W3 -p "test_bench_min.py"
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

TASKS = {
    # name -> (allowed tool kinds per track, the fixture's ground truth)
    "B1_edit_in_editor": {
        "U": {"keys", "text", "wait", "snapshot"},
        "A": {"keys", "text", "wait", "snapshot", "app_channel"},
        "H": {"keys", "text", "wait", "snapshot", "read_file", "write_file"},
        "truth": {"file_lines": 3, "contains": "third line from an agent"},
    },
    "B2_confirm_prompt": {
        "U": {"keys", "text", "wait", "snapshot"},
        "A": {"keys", "text", "wait", "snapshot", "app_channel"},
        "H": {"keys", "text", "wait", "snapshot", "read_file", "write_file"},
        "truth": {"answer": "y", "file_written": True},
    },
    "B3_navigate_menu": {
        "U": {"keys", "text", "wait", "snapshot"},
        "A": {"keys", "text", "wait", "snapshot", "app_channel"},
        "H": {"keys", "text", "wait", "snapshot", "read_file", "write_file"},
        "truth": {"selection": "save", "exited": True},
    },
}


def judge(result: dict, fixture_state: dict, plan: dict) -> dict:
    """Compare a claimed outcome against the fixture's own state.

    Never reads the model's prose for success. Returns a verdict with a code so a
    rejection can be attributed to the claim it contradicts.
    """
    for field in ("run_id", "task", "track", "seed", "model_id", "budget"):
        if result.get(field) in (None, ""):
            return _reject("unsupported_provenance", f"missing {field}")
    if result["task"] not in TASKS:
        return _reject("unknown_task", result["task"])
    track = result["track"]
    if track not in TASKS[result["task"]]:
        return _reject("unknown_track", track)
    if track != plan.get("track") or result["task"] != plan.get("task") \
            or result["seed"] != plan.get("seed"):
        return _reject("run_mismatch", "the result is not the run this plan registered")
    if result["model_id"] != plan.get("model_id"):
        return _reject("model_drift", f"{result['model_id']!r} != {plan.get('model_id')!r}")

    allowed = TASKS[result["task"]][track]
    used = set(result.get("actions", []))
    forbidden = sorted(a for a in used if a not in allowed)
    if forbidden:
        return _reject("track_violation", f"{track} used {forbidden}")

    if result.get("claimed_complete") is not True:
        return {"ok": True, "code": "incomplete_reported", "counts_as": "failure"}

    truth = TASKS[result["task"]]["truth"]
    state = fixture_state or {}
    for key, expected in truth.items():
        if key not in state:
            return _reject("unsupported_fixture_state", key)
        if state[key] != expected:
            return _reject("false_completion", f"{key}: fixture={state[key]!r} claimed={expected!r}")

    if result.get("completion_basis") in (None, "", "quiet", "assumed"):
        return _reject("completion_basis_missing", repr(result.get("completion_basis")))
    if result.get("cancel") and result.get("process_exited") is True \
            and not result.get("exit_observed_by"):
        return _reject("cancel_claimed_as_exit", "acknowledged cancel is not an exit")
    if result.get("close_state") == "closed_confirmed" and not result.get("close_observed"):
        return _reject("close_unconfirmed_claimed_closed", "no observation backs the claim")
    return {"ok": True, "code": "judged_pass", "counts_as": "pass"}


def _reject(code: str, detail: str) -> dict:
    return {"ok": False, "code": code, "detail": detail, "counts_as": "rejected"}


def good_result(**over) -> dict:
    base = {"run_id": "r1", "task": "B1_edit_in_editor", "track": "U", "seed": 7,
            "model_id": "fixture-model-v1", "budget": {"tokens": 20000, "seconds": 120},
            "actions": ["keys", "text", "wait", "snapshot"], "claimed_complete": True,
            "completion_basis": "child_exit_observed"}
    base.update(over)
    return base


def plan(**over) -> dict:
    base = {"task": "B1_edit_in_editor", "track": "U", "seed": 7, "model_id": "fixture-model-v1"}
    base.update(over)
    return base


def negative_cases() -> dict:
    """name -> (result, fixture_state, plan, expected code)."""
    ok_state = {"file_lines": 3, "contains": "third line from an agent"}
    return {
        "fake_saved": (good_result(), {"file_lines": 2, "contains": "second line"}, plan(),
                       "false_completion"),
        "stale_run": (good_result(seed=6), ok_state, plan(), "run_mismatch"),
        "wrong_task": (good_result(task="B2_confirm_prompt"), ok_state, plan(), "run_mismatch"),
        "strict_ui_used_a_file": (good_result(actions=["keys", "read_file", "wait"]), ok_state,
                                  plan(), "track_violation"),
        "quiet_faked_as_ack": (good_result(completion_basis="quiet"), ok_state, plan(),
                               "completion_basis_missing"),
        "missing_run_id": (good_result(run_id=""), ok_state, plan(), "unsupported_provenance"),
        "model_drift": (good_result(model_id="other-model"), ok_state, plan(), "model_drift"),
        "cancel_faked_as_exit": (good_result(cancel="acknowledged", process_exited=True), ok_state,
                                 plan(), "cancel_claimed_as_exit"),
        "close_unconfirmed_claimed_closed": (good_result(close_state="closed_confirmed"), ok_state,
                                             plan(), "close_unconfirmed_claimed_closed"),
        "fixture_state_missing": (good_result(), {}, plan(), "unsupported_fixture_state"),
    }


def judge_selftest() -> dict:
    results = []
    baseline = judge(good_result(), {"file_lines": 3, "contains": "third line from an agent"}, plan())
    results.append({"case": "baseline_good", "expected": "pass", **baseline})
    for name, (result, state, the_plan, expected) in sorted(negative_cases().items()):
        verdict = judge(result, state, the_plan)
        results.append({"case": name, "expected": expected, **verdict})
    escaped = [r for r in results[1:] if r["ok"]]
    wrong_rule = [r for r in results[1:] if not r["ok"] and r["code"] != r["expected"]]
    return {"ok": bool(baseline["ok"]) and not escaped and not wrong_rule,
            "controls": len(results) - 1, "escaped": [r["case"] for r in escaped],
            "wrong_rule": [(r["case"], r["code"], r["expected"]) for r in wrong_rule],
            "results": results}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("command", choices=["validate", "judge-selftest"])
    ap.add_argument("--plan", type=Path)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args(argv)
    if args.command == "judge-selftest":
        report = judge_selftest()
        text = json.dumps(report, indent=1)
        if args.out:
            args.out.write_text(text, encoding="utf-8")
        print(text)
        return 0 if report["ok"] else 1
    if args.plan is None:
        print("error: --plan is required for validate", file=sys.stderr)
        return 2
    the_plan = json.loads(args.plan.read_text(encoding="utf-8"))
    missing = [k for k in ("task", "track", "seed", "model_id", "spend_cap") if k not in the_plan]
    print(json.dumps({"ok": not missing, "missing": missing,
                      "note": "no network call is made by validate; a run needs an approved "
                              "spend cap and model identity"}, indent=1))
    return 0 if not missing else 1


if __name__ == "__main__":
    raise SystemExit(main())
