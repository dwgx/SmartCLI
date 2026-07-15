"""loop.py — the perceive→decide→act→wait→confirm loop, LLM-agnostic.

The agent loop is parametrised by a ``decide_fn`` so the control flow can be unit
tested with a scripted decider (no LLM, no Docker). ``decide_fn(instruction,
screen, history) -> AgentStep`` returns the next action; the loop executes it over
a :class:`TmuxSessionDriver`, waits for the screen to settle, and repeats until the
decider signals ``done`` or the step budget is exhausted.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List, Optional


@dataclass
class AgentStep:
    """One decision from the decider.

    ``done=True`` ends the loop (the task is believed complete). Otherwise the loop
    sends ``keys`` (a list of key tokens/strings for ``send_keys``) or, if ``keys``
    is None and ``line`` is set, types ``line`` + Enter. ``wait_for`` (optional)
    is a regex the loop waits for after acting; if None it waits for stability.
    """

    done: bool = False
    keys: Optional[List[str]] = None
    line: Optional[str] = None
    wait_for: Optional[str] = None
    note: str = ""


@dataclass
class LoopResult:
    """Outcome of :func:`run_agent_loop`."""

    steps_taken: int
    done: bool                    # did the decider signal completion (vs budget hit)
    final_screen: str
    history: List[AgentStep] = field(default_factory=list)


# decide_fn(instruction, screen, history) -> AgentStep
DecideFn = Callable[[str, str, List[AgentStep]], AgentStep]


def run_agent_loop(
    instruction: str,
    driver,
    decide_fn: DecideFn,
    max_steps: int = 30,
    settle_timeout_sec: float = 10.0,
) -> LoopResult:
    """Run perceive→decide→act→wait→confirm until done or the step budget is hit.

    Args:
        instruction: the task instruction (passed to the decider each step).
        driver: a :class:`TmuxSessionDriver` (or anything with the same surface).
        decide_fn: chooses the next :class:`AgentStep` from the current screen.
        max_steps: hard ceiling on decide/act cycles (prevents runaway loops).
        settle_timeout_sec: per-step wait ceiling.

    Returns:
        :class:`LoopResult` with the step count, whether the decider signalled done,
        the final screen, and the step history.
    """
    history: List[AgentStep] = []
    steps = 0
    while steps < max_steps:
        screen = driver.snapshot()               # PERCEIVE
        step = decide_fn(instruction, screen, history)  # DECIDE
        history.append(step)
        if step.done:                            # CONFIRM (decider says complete)
            return LoopResult(steps, True, screen, history)

        steps += 1
        if step.keys is not None:                # ACT
            driver.send_keys(step.keys)
        elif step.line is not None:
            driver.send_line(step.line)
        else:
            # a no-op step with neither keys nor line: just re-observe (WAIT below).
            pass

        if step.wait_for:                        # WAIT (marker) …
            driver.wait_for(step.wait_for, timeout_sec=settle_timeout_sec)
        else:                                    # … or WAIT (stability)
            driver.wait_stable(timeout_sec=settle_timeout_sec)

    return LoopResult(steps, False, driver.snapshot(), history)
