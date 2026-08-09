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
  * verify_fx has a known random-seconds flake, and _diff_fuzz_tmux a
    load-dependent one (its tmux capture can settle early once the suite has
    spawned dozens of PTYs) — each gets one automatic rerun before it counts as
    a failure. Both use fixed inputs, so a real failure recurs on the rerun.
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


def _as_text(raw) -> str:
    """Decode captured child output. subprocess.run is called without text=True
    (a child emitting invalid UTF-8 must not raise here), so this decodes with
    replacement — which is also why box-drawing/CJK output survives a failure dump.
    """
    if raw is None:
        return ""
    if isinstance(raw, bytes):
        return raw.decode("utf-8", "replace")
    return str(raw)


class Test:
    """One aggregated test: how to invoke it, where, and how long to wait."""

    def __init__(self, label, argv, cwd, timeout, optional=False, rerun=False):
        self.label = label
        self.argv = argv
        self.cwd = cwd
        self.timeout = timeout
        self.optional = optional      # missing => skip-with-note, not fail
        self.rerun = rerun            # allow ONE automatic rerun on failure
        self.output = ""              # last run's captured stdout+stderr

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
        """Run once. Returns (rc, timed_out). Child output is kept on self.output.

        The output used to be captured and DROPPED, so a failure in the suite was
        reportable only as a return code and had to be re-run standalone to see
        why — and a probe that fails inside the suite but passes in isolation is
        exactly the case where the lost text was the evidence. It is retained now
        and printed by the caller on failure. It also carries any internal
        "SKIP:" line, which was previously invisible: a probe could skip the very
        case it exists for and still report [PASS].
        """
        try:
            proc = subprocess.run(
                self.argv, cwd=str(self.cwd), env=CHILD_ENV,
                timeout=self.timeout,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            )
            self.output = _as_text(proc.stdout)
            return proc.returncode, False
        except subprocess.TimeoutExpired as exc:
            self.output = _as_text(exc.stdout)
            return None, True


_GIT_TRACKED: set[str] | None = None


def _tracked_files() -> set[str]:
    """Repo-relative paths git knows about, resolved once.

    Returns an empty set when git is unavailable or this is not a checkout (a
    tarball install, a vendored copy), which makes the caller fall back to the
    hand-set `optional` flag rather than failing everything.
    """
    global _GIT_TRACKED
    if _GIT_TRACKED is None:
        try:
            out = subprocess.run(["git", "-C", str(ROOT), "ls-files"],
                                 capture_output=True, text=True, timeout=30)
            _GIT_TRACKED = ({ln.strip() for ln in out.stdout.splitlines() if ln.strip()}
                            if out.returncode == 0 else set())
        except (OSError, subprocess.SubprocessError):
            _GIT_TRACKED = set()
    return _GIT_TRACKED


def _is_tracked_by_git(t) -> bool:
    """Is this entry's target file under version control?

    If it is, its absence on disk is a deleted or renamed gate — a regression —
    not an optional extra that happens not to be installed.
    """
    tracked = _tracked_files()
    if not tracked:
        return False
    if "-m" in t.argv:
        mod = t.argv[t.argv.index("-m") + 1]
        rel = Path(*mod.split(".")).with_suffix(".py")
        target = (Path(t.cwd) / rel)
    else:
        target = t._target_path()
    if target is None:
        return False
    try:
        return str(Path(target).resolve().relative_to(ROOT)).replace("\\", "/") in tracked
    except ValueError:
        return False


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
    suite.append(Test("test_fx_contract (every fx effect x sizes)",
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
    suite.append(Test("test_wait_change (drive-tui await-change primitive)",
                      [PY, str(TESTS / "test_wait_change.py")], ROOT, 60,
                      optional=True))
    suite.append(Test("test_visual_change (selection/cursor-aware wait)",
                      [PY, str(TESTS / "test_visual_change.py")], ROOT, 60,
                      optional=True))
    suite.append(Test("test_drive_security (control-plane boundaries)",
                      [PY, str(TESTS / "test_drive_security.py")], ROOT, 60,
                      optional=True))
    # Drives the REAL accept loop against a fake session — no PTY, no child process,
    # so it is safe under the red line. 90s because one assertion deliberately
    # waits out a bound to prove a serial loop would have blocked.
    suite.append(Test("test_daemon_concurrency (one peer cannot stall the others)",
                      [PY, str(TESTS / "test_daemon_concurrency.py")], ROOT, 90,
                      optional=True))
    suite.append(Test("test_dependency_sync (one dependency fact, one value)",
                      [PY, str(TESTS / "test_dependency_sync.py")], ROOT, 60,
                      optional=True))
    suite.append(Test("test_version_sync (ten version sites agree)",
                      [PY, str(TESTS / "test_version_sync.py")], ROOT, 60,
                      optional=True))
    suite.append(Test("test_readiness_properties (Hypothesis wait invariants)",
                      [PY, str(TESTS / "test_readiness_properties.py")], ROOT, 300,
                      optional=True))
    suite.append(Test("test_perf_contract (wait-primitive cost ceilings)",
                      [PY, str(TESTS / "test_perf_contract.py")], ROOT, 120,
                      optional=True))
    suite.append(Test("test_terminal_fidelity (real-terminal divergence locks)",
                      [PY, str(TESTS / "test_terminal_fidelity.py")], ROOT, 60,
                      optional=True))
    # Real-tmux probes: SKIP themselves when tmux is absent, so they are safe to
    # register unconditionally. They spawn one tmux server at a time.
    # The README's headline demo. It drives the real vim binary, so it is a
    # real-process probe: SKIPs itself when vim is absent.
    suite.append(Test("drive_vim example (real vim, end-to-end)",
                      [PY, str(ROOT / "examples" / "drive_vim.py")], ROOT, 120,
                      optional=True))
    suite.append(Test("_tmux_launcher_probe (cmd-art tmux launchers, real tmux)",
                      [PY, str(TESTS / "_tmux_launcher_probe.py")], ROOT, 240,
                      optional=True))
    suite.append(Test("_diff_tmux_pyte (screen model vs real tmux)",
                      [PY, str(TESTS / "_diff_tmux_pyte.py")], ROOT, 300,
                      optional=True))
    # Generative differential fuzz. NOTE: seed 8 has one KNOWN unfixed
    # divergence (see KNOWN_UNFIXED in that file), so run_all uses a clean seed
    # and the seed-8 case is tracked as an open task, not silently filtered.
    suite.append(Test("_diff_two_refs (tmux AND GNU screen vs our model)",
                      [PY, str(TESTS / "_diff_two_refs.py")], ROOT, 900,
                      optional=True))
    # rerun=True for a load-dependent flake, not a random one. The seed is FIXED,
    # so both attempts feed tmux byte-for-byte the same 40 payloads: a real
    # divergence fails twice, while a slow capture fails once. Observed failing
    # here in a full-suite run and passing standalone with the identical argv,
    # including immediately after _diff_two_refs — by that point the suite has
    # already spawned verify_fx and six drive probes, and the probe's
    # settle-polling can return before tmux has finished painting.
    suite.append(Test("_diff_fuzz_tmux (generative differential fuzz)",
                      [PY, str(TESTS / "_diff_fuzz_tmux.py"), "--count", "40",
                       "--seed", "2"], ROOT, 600, optional=True, rerun=True))
    suite.append(Test("test_wait_any (pexpect-style multi-marker wait)",
                      [PY, str(TESTS / "test_wait_any.py")], ROOT, 60,
                      optional=True))
    suite.append(Test("test_sixel (sixel wire-format lock)",
                      [PY, str(TESTS / "test_sixel.py")], ROOT, 60,
                      optional=True))
    suite.append(Test("test_harbor_agent (Harbor BaseAgent adapter, no Docker)",
                      [PY, str(TESTS / "test_harbor_agent.py")], ROOT, 60,
                      optional=True))
    suite.append(Test("test_tbench_adapter (driver+loop, no Docker)",
                      [PY, str(TESTS / "test_tbench_adapter.py")], ROOT, 60,
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
            # `optional` means "may legitimately be absent". It does NOT cover a
            # file that is committed to git: that one vanishing is a deleted or
            # renamed gate, i.e. exactly the regression this aggregator exists to
            # notice. 20 committed deterministic gates were registered optional
            # (several with the stale rationale "another agent may be adding it"),
            # so removing any of them produced a green SKIP while CLAUDE.md
            # advertises "exit 0 iff everything passes".
            #
            # Derived from git rather than hand-maintained, because a second
            # hand-kept list of "which optionals are really required" would rot the
            # same way. Absent git (a tarball install), fall back to the flag.
            if t.optional and not _is_tracked_by_git(t):
                print(f"[SKIP] {t.label}  (not present — optional)")
                results.append((t.label, "SKIP"))
                notes.append(f"{t.label}: optional, absent — skipped")
            else:
                why = ("MISSING required test file" if not t.optional
                       else "MISSING — the file is tracked by git, so its absence "
                            "is a deleted/renamed gate, not an optional extra")
                print(f"[FAIL] {t.label}  ({why})")
                results.append((t.label, "FAIL"))
                notes.append(f"{t.label}: {why}")
            continue

        rc, timed_out = t.run_once()

        # Known flake: one automatic rerun for rerun=True tests.
        if t.rerun and (timed_out or rc != 0):
            print(f"[warn] {t.label} failed first attempt "
                  f"(rc={rc}, timeout={timed_out}) — retrying once")
            notes.append(f"{t.label}: failed once then retried (known flake)")
            rc, timed_out = t.run_once()

        def _dump(tail_lines: int = 40) -> None:
            """Print the child's own output so a failure is diagnosable HERE.

            Without this a suite failure was a bare return code, and the only way
            to learn why was to re-run the test standalone — where an
            order-dependent or load-dependent failure often does not reproduce.
            """
            text = (t.output or "").rstrip()
            if not text:
                print("       (child produced no output)")
                return
            lines = text.splitlines()
            if len(lines) > tail_lines:
                print(f"       ... {len(lines) - tail_lines} earlier line(s) omitted")
                lines = lines[-tail_lines:]
            for ln in lines:
                print("       | " + ln)

        if timed_out:
            print(f"[FAIL] {t.label}  (TIMEOUT after {t.timeout}s)")
            _dump()
            results.append((t.label, "TIMEOUT"))
        elif rc == 0:
            print(f"[PASS] {t.label}  (exit 0)")
            # An internal skip can be a real reduction in coverage, so surface it
            # even on a pass: a probe that skips the case it exists for otherwise
            # reports an unqualified [PASS]. Matched on the "SKIP:" convention
            # (with the colon) so a per-item "SKIP  <name> -- not applicable",
            # which is normal reporting rather than lost coverage, stays quiet.
            for ln in (t.output or "").splitlines():
                s = ln.strip()
                if s.startswith("SKIP:"):
                    print(f"       | {s}")
                    notes.append(f"{t.label}: internal skip — {s[:90]}")
            results.append((t.label, "PASS"))
        else:
            print(f"[FAIL] {t.label}  (exit {rc})")
            _dump()
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
