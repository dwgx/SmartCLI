#!/usr/bin/env python3
"""run_all.py — unified self-test aggregator for SmartCLI.

Shells out to every self-test / probe in the repo with the correct cwd and
PYTHONPATH, aggregates their exit codes, and reports ONE overall pass/fail.
This is the thing that keeps the otherwise-orphaned self-tests from silently
rotting: run it and every engine + integration probe gets exercised.

Usage:  python tests/run_all.py
Exit 0 iff every (non-skipped) test passed; exit 1 otherwise.

Notes:
  * PYTHONIOENCODING=utf-8 + PYTHONUTF8=1 are forced in each child so the
    box-drawing / braille proof dumps encode on legacy Windows codepages.
  * Drive probes run real ConPTY sessions and are SLOW — each gets its own
    generous timeout; they are never assumed fast.
  * verify_fx has a known random-seconds flake — one automatic rerun is
    allowed before it is counted as a failure.
  * Optional tests (_drive_probe6, test_readiness) may be added by other
    agents; if absent they are skipped-with-note, not failed.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"
TUI = ROOT / "skills" / "tui-ui"

# Child env: force UTF-8 everywhere so glyph dumps don't blow up on CP936.
CHILD_ENV = dict(os.environ)
CHILD_ENV["PYTHONIOENCODING"] = "utf-8"
CHILD_ENV["PYTHONUTF8"] = "1"

PY = sys.executable


class Test:
    """One aggregated test: how to invoke it, where, and how long to wait."""

    def __init__(self, label, argv, cwd, timeout, optional=False, rerun=False):
        self.label = label
        self.argv = argv
        self.cwd = cwd
        self.timeout = timeout
        self.optional = optional      # missing => skip-with-note, not fail
        self.rerun = rerun            # allow ONE automatic rerun on failure

    def _target_path(self):
        """Best-effort path the invocation points at (for existence checks)."""
        for tok in self.argv:
            if tok.endswith(".py"):
                p = Path(tok)
                return p if p.is_absolute() else (Path(self.cwd) / p)
        return None

    def exists(self):
        # Module runs (-m ui.foo) have no .py token — resolve the module file.
        if "-m" in self.argv:
            mod = self.argv[self.argv.index("-m") + 1]
            rel = Path(*mod.split(".")).with_suffix(".py")
            return (Path(self.cwd) / rel).exists()
        tgt = self._target_path()
        return tgt is None or tgt.exists()

    def run_once(self):
        """Run once. Returns (rc, timed_out)."""
        try:
            proc = subprocess.run(
                self.argv, cwd=str(self.cwd), env=CHILD_ENV,
                timeout=self.timeout,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            )
            return proc.returncode, False
        except subprocess.TimeoutExpired:
            return None, True


def build_suite():
    """Assemble the ordered test list. Optional entries are included whether
    or not present; existence is checked at run time so 'skip-with-note' is a
    real reported outcome, not a silent omission."""
    suite = []

    # --- root regression / integration probes (run from repo root) --------
    suite.append(Test("verify_fx (fx live PTY harness)",
                      [PY, str(TESTS / "verify_fx.py")], ROOT, 300, rerun=True))
    suite.append(Test("_readme_literal (README import order)",
                      [PY, str(TESTS / "_readme_literal.py")], ROOT, 60))
    suite.append(Test("probe_pty_fx (fx bytes through PTY)",
                      [PY, str(TESTS / "probe_pty_fx.py")], ROOT, 120))

    # --- drive-tui probes: real ConPTY, SLOW — generous per-probe timeout --
    for i in range(1, 6):
        suite.append(Test(f"_drive_probe{i}",
                          [PY, str(TESTS / f"_drive_probe{i}.py")], ROOT, 120))
    # probe6 is optional (another agent may be adding it).
    suite.append(Test("_drive_probe6 (optional)",
                      [PY, str(TESTS / "_drive_probe6.py")], ROOT, 120,
                      optional=True))
    # drive-tui persistent-session CLI coverage: happy path + token auth +
    # one-shot run + no-leak. Real ConPTY like the probes above, so generous.
    suite.append(Test("_tui_cli_probe (drive-tui CLI end-to-end)",
                      [PY, str(TESTS / "_tui_cli_probe.py")], ROOT, 180))
    # MCP server end-to-end: drives a real session through the MCP tool surface
    # (token auto-attached, no-leak). Optional — needs the `mcp` package.
    suite.append(Test("_mcp_probe (drive-tui MCP server end-to-end)",
                      [PY, str(TESTS / "_mcp_probe.py")], ROOT, 180,
                      optional=True))

    # --- tui-ui: top-level self-tests (run from skills/tui-ui) -------------
    suite.append(Test("tui-ui self_test.py",
                      [PY, "self_test.py"], TUI, 120))
    suite.append(Test("tui-ui _selftest_effort_widgets.py",
                      [PY, "_selftest_effort_widgets.py"], TUI, 120))

    # --- tui-ui: engine module self-tests (relative imports => run as -m) --
    suite.append(Test("tui-ui ui.field (python -m ui.field)",
                      [PY, "-m", "ui.field"], TUI, 60))
    suite.append(Test("tui-ui ui.raster (python -m ui.raster)",
                      [PY, "-m", "ui.raster"], TUI, 60))
    suite.append(Test("tui-ui ui.box_junction (python -m ui.box_junction)",
                      [PY, "-m", "ui.box_junction"], TUI, 60))

    # --- optional readiness gate (another agent may add it) ---------------
    suite.append(Test("test_readiness (optional)",
                      [PY, str(TESTS / "test_readiness.py")], ROOT, 120,
                      optional=True))

    # --- deterministic pure-memory gates (fast, zero-process) -------------
    suite.append(Test("test_vendor_sync (drive-tui _vendor == canonical)",
                      [PY, str(TESTS / "test_vendor_sync.py")], ROOT, 60,
                      optional=True))
    suite.append(Test("test_degenerate_inputs (regression locks)",
                      [PY, str(TESTS / "test_degenerate_inputs.py")], ROOT, 60,
                      optional=True))
    suite.append(Test("test_fx_contract (19 fx x sizes)",
                      [PY, str(TESTS / "test_fx_contract.py")], ROOT, 120,
                      optional=True))
    suite.append(Test("test_doc_counts (docs match code, anti-drift)",
                      [PY, str(TESTS / "test_doc_counts.py")], ROOT, 60,
                      optional=True))
    suite.append(Test("test_golden_frames (tui-ui widget snapshots)",
                      [PY, str(TESTS / "test_golden_frames.py")], ROOT, 60,
                      optional=True))
    suite.append(Test("test_cpr_reply (device-query auto-answer)",
                      [PY, str(TESTS / "test_cpr_reply.py")], ROOT, 60,
                      optional=True))
    suite.append(Test("test_char_width (width knobs + default stability)",
                      [PY, str(TESTS / "test_char_width.py")], ROOT, 60,
                      optional=True))
    suite.append(Test("_sandbox_fuzz_core (pure-memory fuzz)",
                      [PY, str(TESTS / "_sandbox_fuzz_core.py")], ROOT, 180,
                      optional=True))
    suite.append(Test("_sandbox_daemon_robustness (daemon transport)",
                      [PY, str(TESTS / "_sandbox_daemon_robustness.py")], ROOT, 90,
                      optional=True))

    return suite


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

    suite = build_suite()
    results = []   # (label, status) where status in PASS/FAIL/SKIP/TIMEOUT
    notes = []

    print("=" * 70)
    print("SmartCLI unified self-test runner")
    print(f"repo root: {ROOT}")
    print("=" * 70)

    for t in suite:
        if not t.exists():
            if t.optional:
                print(f"[SKIP] {t.label}  (not present — optional)")
                results.append((t.label, "SKIP"))
                notes.append(f"{t.label}: optional, absent — skipped")
            else:
                print(f"[FAIL] {t.label}  (MISSING required test file)")
                results.append((t.label, "FAIL"))
                notes.append(f"{t.label}: required file missing")
            continue

        rc, timed_out = t.run_once()

        # Known flake: one automatic rerun for rerun=True tests.
        if t.rerun and (timed_out or rc != 0):
            print(f"[warn] {t.label} failed first attempt "
                  f"(rc={rc}, timeout={timed_out}) — retrying once")
            notes.append(f"{t.label}: failed once then retried (known flake)")
            rc, timed_out = t.run_once()

        if timed_out:
            print(f"[FAIL] {t.label}  (TIMEOUT after {t.timeout}s)")
            results.append((t.label, "TIMEOUT"))
        elif rc == 0:
            print(f"[PASS] {t.label}  (exit 0)")
            results.append((t.label, "PASS"))
        else:
            print(f"[FAIL] {t.label}  (exit {rc})")
            results.append((t.label, "FAIL"))

    n_pass = sum(1 for _, s in results if s == "PASS")
    n_skip = sum(1 for _, s in results if s == "SKIP")
    n_fail = sum(1 for _, s in results if s in ("FAIL", "TIMEOUT"))
    n_ran = n_pass + n_fail   # skips excluded from the pass ratio

    print("=" * 70)
    if notes:
        print("Notes:")
        for note in notes:
            print(f"  - {note}")
        print("-" * 70)
    print(f"SUMMARY: {n_pass}/{n_ran} passed"
          + (f", {n_skip} skipped" if n_skip else "")
          + (f", {n_fail} failed" if n_fail else ""))
    if n_fail:
        print("Failing tests:")
        for label, status in results:
            if status in ("FAIL", "TIMEOUT"):
                print(f"  - {label}  [{status}]")
        print("RUN-ALL: FAIL")
        sys.exit(1)
    print("RUN-ALL: OK")
    sys.exit(0)


if __name__ == "__main__":
    main()
