#!/usr/bin/env python3
"""test_tbench_adapter.py — smartcli_tbench driver + loop (deterministic, no Docker).

Proves the Terminal-Bench adapter's LOGIC on any box (incl. Windows) without
Docker, terminal-bench, or an LLM:
  * TmuxSessionDriver.wait_for / wait_any / wait_change / wait_stable fire correctly
    over a scripted FakeTmuxSession (fake clock + no-op sleep — instant, deterministic),
  * run_agent_loop executes perceive→decide→act→wait→confirm, terminates on the
    decider's done signal, and respects the step budget,
  * send_keys / send_line reach the session.

The LLM-backed SmartCliAgent itself needs terminal-bench (CI/Linux); this locks
everything below that seam.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from smartcli_tbench.driver import TmuxSessionDriver  # noqa: E402
from smartcli_tbench.loop import AgentStep, run_agent_loop  # noqa: E402

failures = 0


def check(cond, label, detail=""):
    global failures
    if not cond:
        failures += 1
    print(f"{'PASS' if cond else 'FAIL'}  {label}" + (f"  -- {detail}" if detail else ""))


class FakeClock:
    """Monotonic clock that only advances when the driver sleeps, so wait loops
    hit their deadline deterministically without real time passing."""

    def __init__(self):
        self.t = 0.0

    def now(self):
        return self.t

    def sleep(self, s):
        self.t += s


class FakeTmuxSession:
    """Scripts capture_pane() outputs: each poll returns the next screen; the last
    screen repeats forever. Records sent keys. With ``cycle=True`` the script loops
    (to model a screen that alternates forever and truly never settles)."""

    def __init__(self, screens, cycle=False):
        self._screens = list(screens)
        self._i = 0
        self._cycle = cycle
        self.sent = []

    def capture_pane(self, capture_entire=False):
        if self._cycle:
            s = self._screens[self._i % len(self._screens)]
        else:
            s = self._screens[min(self._i, len(self._screens) - 1)]
        self._i += 1
        return s

    def send_keys(self, keys, block=False, max_timeout_sec=180.0, **kw):
        self.sent.append(list(keys))


def _driver(screens):
    clk = FakeClock()
    sess = FakeTmuxSession(screens)
    return TmuxSessionDriver(sess, poll_ms=100, clock=clk.now, sleep=clk.sleep), sess, clk


def test_wait_for_matches():
    d, _, _ = _driver(["booting...", "booting...", "$ ready"])
    ok, screen = d.wait_for(r"\$ ready", timeout_sec=5)
    check(ok is True, "wait_for finds the marker once it appears")
    check("ready" in screen, "wait_for returns the matching screen")


def test_wait_for_timeout():
    d, _, _ = _driver(["nope", "nope", "nope"])
    ok, _ = d.wait_for(r"never", timeout_sec=1)
    check(ok is False, "wait_for times out when the marker never appears")


def test_wait_any_index_and_tie():
    d, _, _ = _driver(["...", "ERROR: boom"])
    idx, _ = d.wait_any([r">>> ", r"ERROR"], timeout_sec=5)
    check(idx == 1, "wait_any returns the index of the matching pattern", f"idx={idx}")
    # same-poll tie -> earliest in list wins
    d2, _, _ = _driver(["ERROR: boom"])
    idx2, _ = d2.wait_any([r"ERROR", r"boom"], timeout_sec=5)
    check(idx2 == 0, "wait_any tie: earliest-in-list wins", f"idx={idx2}")
    # empty list short-circuits
    d3, _, _ = _driver(["anything"])
    idx3, _ = d3.wait_any([], timeout_sec=5)
    check(idx3 == -1, "wait_any empty patterns -> -1", f"idx={idx3}")


def test_wait_change():
    d, _, _ = _driver(["same", "same", "DIFFERENT"])
    changed, screen = d.wait_change(timeout_sec=5)
    check(changed is True, "wait_change detects the screen changing from baseline")
    check("DIFFERENT" in screen, "wait_change returns the changed screen")

    d2, _, _ = _driver(["frozen", "frozen", "frozen"])
    changed2, _ = d2.wait_change(timeout_sec=1)
    check(changed2 is False, "wait_change times out when nothing changes")


def test_wait_stable():
    # changes for two polls, then holds -> becomes stable (min_wait_sec=0 to isolate
    # the dwell logic from the stale-screen floor, which is tested separately below).
    d, _, _ = _driver(["a", "b", "c", "c", "c"])
    ok = d.wait_stable(quiet_polls=2, timeout_sec=5, min_wait_sec=0)
    check(ok is True, "wait_stable settles once the screen stops changing")


def test_wait_stable_never_settles():
    # A screen that alternates FOREVER (cycle=True) must never satisfy the dwell
    # counter -> can only exit via timeout. Uses a truly non-clamping fake so this
    # is a real never-settle, not a clamp-then-freeze artifact.
    clk = FakeClock()
    sess = FakeTmuxSession(["A", "B"], cycle=True)
    d = TmuxSessionDriver(sess, poll_ms=100, clock=clk.now, sleep=clk.sleep)
    ok = d.wait_stable(quiet_polls=2, timeout_sec=1, min_wait_sec=0)
    check(ok is False, "wait_stable never settles on an alternating screen -> timeout")


def test_wait_stable_min_wait_guards_stale_screen():
    # The stale-screen race (finding 1): the screen is ALREADY static from poll 0
    # (the shell echoed the command instantly) but real output is still pending.
    # With min_wait_sec, wait_stable must NOT declare stable before the floor, even
    # though the dwell counter is satisfied immediately.
    clk = FakeClock()
    sess = FakeTmuxSession(["prompt$ cmd"], cycle=True)  # static from the very start
    d = TmuxSessionDriver(sess, poll_ms=100, clock=clk.now, sleep=clk.sleep)
    t0 = clk.now()
    ok = d.wait_stable(quiet_polls=2, timeout_sec=5, min_wait_sec=0.5)
    elapsed = clk.now() - t0
    check(ok is True, "wait_stable eventually settles on a static screen")
    check(elapsed >= 0.5, "min_wait_sec floor delays settle past the stale-screen race",
          f"elapsed={elapsed:.2f}s")
    # And without the floor it would settle almost immediately (proves the guard bites):
    clk2 = FakeClock()
    d2 = TmuxSessionDriver(FakeTmuxSession(["prompt$ cmd"], cycle=True),
                           poll_ms=100, clock=clk2.now, sleep=clk2.sleep)
    d2.wait_stable(quiet_polls=2, timeout_sec=5, min_wait_sec=0)
    check(clk2.now() < 0.5, "without the floor, settle is immediate (guard is what delays)",
          f"elapsed={clk2.now():.2f}s")


def test_send_helpers():
    d, sess, _ = _driver(["scr"])
    d.send_keys(["Down", "Enter"])
    d.send_line("echo hi")
    check(sess.sent[0] == ["Down", "Enter"], "send_keys forwards key tokens")
    check(sess.sent[1] == ["echo hi", "Enter"], "send_line appends Enter")


def test_loop_runs_to_done():
    # Decider: step 0 types a command, step 1 declares done.
    d, sess, _ = _driver(["prompt$ ", "prompt$ output", "prompt$ output"])

    def decide(instruction, screen, history):
        if len(history) == 0:
            return AgentStep(line="run the thing", wait_for=None)
        return AgentStep(done=True)

    res = run_agent_loop("do it", d, decide, max_steps=10)
    check(res.done is True, "loop ends when the decider signals done")
    check(res.steps_taken == 1, "one action taken before done", f"steps={res.steps_taken}")
    check(sess.sent and sess.sent[0] == ["run the thing", "Enter"],
          "loop actually sent the decided line")


def test_loop_respects_step_budget():
    d, _, _ = _driver(["x"])
    # Decider never says done -> must stop at max_steps.
    def decide(instruction, screen, history):
        return AgentStep(keys=["a"])
    res = run_agent_loop("loop forever", d, decide, max_steps=5)
    check(res.done is False, "loop stops at the step budget when never done")
    check(res.steps_taken == 5, "exactly max_steps actions taken", f"steps={res.steps_taken}")


def test_agent_module_imports_without_tb():
    # Importing the agent module must NOT require terminal-bench; SmartCliAgent is
    # None here (TB absent), which is the documented non-TB-host behavior.
    import smartcli_tbench.agent as ag
    check(hasattr(ag, "SmartCliAgent"), "agent module imports without terminal-bench")
    check(ag.SmartCliAgent is None, "SmartCliAgent is None on a non-TB host (expected)")


def main():
    for fn in (test_wait_for_matches, test_wait_for_timeout, test_wait_any_index_and_tie,
               test_wait_change, test_wait_stable, test_wait_stable_never_settles,
               test_wait_stable_min_wait_guards_stale_screen, test_send_helpers,
               test_loop_runs_to_done, test_loop_respects_step_budget,
               test_agent_module_imports_without_tb):
        fn()
    print("-" * 60)
    if failures:
        print(f"test_tbench_adapter FAIL -- {failures} check(s) failed")
        return 1
    print("test_tbench_adapter PASS -- driver + loop logic locked (no Docker/LLM)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
