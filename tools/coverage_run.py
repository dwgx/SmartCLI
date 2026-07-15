#!/usr/bin/env python3
"""coverage_run.py — measure test coverage across the script-style, multi-process
SmartCLI suite.

tests/run_all.py runs each self-test as a SEPARATE subprocess and inherits the
parent environment (`CHILD_ENV = dict(os.environ)`). So the recipe is:

  1. Set COVERAGE_PROCESS_START=.coveragerc and prepend the repo root to
     PYTHONPATH. run_all passes both down to every child.
  2. sitecustomize.py (repo root) sees COVERAGE_PROCESS_START and calls
     coverage.process_startup() in each child, so every test process records
     coverage into its own .coverage.<host>.<pid> data file (parallel=true).
  3. Run tests/run_all.py.
  4. `coverage combine` merges all the per-process data files, then `report`
     prints totals and (optionally) writes coverage.xml / coverage.json /
     a badge-friendly total.

By default it runs the DETERMINISTIC subset — the pure/in-memory gates that are
safe to instrument and reproduce identically on every OS (the same set CI runs).
The PTY drive-probes and the fuzz sandbox are excluded from the coverage run:
they spawn/instrument child processes in ways that don't compose with coverage's
process-startup hook (the fuzz sandbox notably fails under instrumentation while
passing bare), and CI deliberately keeps them out of the runner too. `--full`
opts into the whole run_all suite anyway (expect the fuzz sandbox to complain).

Usage:
    python tools/coverage_run.py              # deterministic subset + combine + report
    python tools/coverage_run.py --xml        # also write coverage.xml (for Codecov)
    python tools/coverage_run.py --full        # run the ENTIRE run_all suite (PTY + fuzz)
    python tools/coverage_run.py --no-run      # just combine + report existing data

Exit code mirrors the tests it ran (0 iff they passed); coverage reporting never
changes the pass/fail verdict.

NOTE (spawn red-line): the deterministic subset spawns NO PTYs. `--full` drives
real PTYs serially — run it deliberately, never fan out multiple runs at once.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable


def _env_for_children() -> dict:
    env = dict(os.environ)
    env["COVERAGE_PROCESS_START"] = str(ROOT / ".coveragerc")
    # Prepend repo root so children can import sitecustomize.py regardless of
    # their own cwd (run_all launches some tests from skills/tui-ui, etc.).
    prev = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(ROOT) + (os.pathsep + prev if prev else "")
    # Force UTF-8 in children (glyph dumps on legacy Windows codepages).
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    return env


# Deterministic, instrument-friendly gates (no PTY spawn, no self-fork). These
# are the coverage-meaningful tests and match what CI runs on every OS.
DETERMINISTIC_TESTS = [
    "test_fx_contract.py",
    "test_readiness.py",
    "test_degenerate_inputs.py",
    "test_doc_counts.py",
    "test_golden_frames.py",
    "test_cpr_reply.py",
    "test_vendor_sync.py",
    "_readme_literal.py",
]


def _run(cmd: list[str], env: dict | None = None) -> int:
    return subprocess.run(cmd, cwd=str(ROOT), env=env).returncode


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Coverage over the SmartCLI suite.")
    ap.add_argument("--xml", action="store_true", help="write coverage.xml (Codecov)")
    ap.add_argument("--json", action="store_true", help="write coverage.json")
    ap.add_argument("--full", action="store_true",
                    help="run the ENTIRE run_all suite (PTY probes + fuzz) instead "
                         "of the deterministic subset")
    ap.add_argument("--no-run", action="store_true",
                    help="skip running tests; combine + report existing data")
    args = ap.parse_args(argv)

    try:
        import coverage  # noqa: F401
    except ImportError:
        print("error: coverage.py not installed. `pip install coverage`",
              file=sys.stderr)
        return 2

    env = _env_for_children()
    suite_rc = 0

    if not args.no_run:
        # Clean any stale per-process data so the combine is a true snapshot.
        _run([PY, "-m", "coverage", "erase"])
        print("=" * 70)
        if args.full:
            print("Running FULL run_all.py under coverage (PTY + fuzz included)")
            print("=" * 70)
            suite_rc = _run([PY, str(ROOT / "tests" / "run_all.py")], env=env)
        else:
            print("Running deterministic subset under coverage "
                  f"({len(DETERMINISTIC_TESTS)} gates)")
            print("=" * 70)
            for name in DETERMINISTIC_TESTS:
                rc = _run([PY, str(ROOT / "tests" / name)], env=env)
                print(f"  [{'PASS' if rc == 0 else 'FAIL'}] {name} (exit {rc})")
                if rc != 0:
                    suite_rc = 1

    # Merge every .coverage.<host>.<pid> into one .coverage.
    _run([PY, "-m", "coverage", "combine"])

    print("=" * 70)
    print("Coverage report (shipped source only — see .coveragerc)")
    print("=" * 70)
    _run([PY, "-m", "coverage", "report"])

    if args.xml:
        _run([PY, "-m", "coverage", "xml"])
        print("wrote coverage.xml")
    if args.json:
        _run([PY, "-m", "coverage", "json"])
        print("wrote coverage.json")

    # Print the single total percentage last so CI / a badge step can grep it.
    total = subprocess.run([PY, "-m", "coverage", "report", "--format=total"],
                           cwd=str(ROOT), capture_output=True, text=True)
    pct = total.stdout.strip()
    if pct:
        print(f"TOTAL_COVERAGE: {pct}%")

    if args.no_run:
        return 0
    print(f"SUITE_EXIT: {suite_rc}")
    return suite_rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
