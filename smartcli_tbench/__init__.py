"""smartcli_tbench — a Terminal-Bench agent adapter built on SmartCLI's loop.

Terminal-Bench (laude-institute/terminal-bench) owns the terminal: each task runs
in a Docker container and the harness hands an agent a live ``TmuxSession`` to
drive. SmartCLI's value here is NOT the PTY layer (TB provides that) — it's the
**perceive → decide → act → wait → confirm** discipline and the wait primitives
(``wait_stable`` / ``wait_for`` / ``wait_change``) reimplemented over the tmux
session's ``capture_pane()``. The stock ``naive`` agent is fire-and-forget and
blind between commands; this adapter watches the screen and only proceeds once its
action has landed.

Layout (deliberately layered so most of it is testable on Windows without Docker,
Terminal-Bench, or an LLM):
  * ``driver.py``  — ``TmuxSessionDriver``: the wait primitives over any object
                     exposing ``send_keys``/``capture_pane``/``get_incremental_output``.
                     Pure; unit-tested with a fake session.
  * ``loop.py``    — ``run_agent_loop``: the perceive→decide→act→wait→confirm loop,
                     parametrised by a ``decide_fn`` so it runs with a scripted
                     decider in tests (no LLM needed).
  * ``agent.py``   — ``SmartCliAgent(BaseAgent)``: imports Terminal-Bench lazily and
                     wires an LLM-backed ``decide_fn`` into the loop. Only importable
                     where ``terminal-bench`` is installed (CI/Linux/Docker).

This package is intentionally OUTSIDE ``smartcli_core`` so the benchmark dependency
never leaks into the shipped skill/package.
"""
from __future__ import annotations

from .driver import TmuxSessionDriver
from .loop import AgentStep, LoopResult, run_agent_loop

__all__ = ["TmuxSessionDriver", "run_agent_loop", "AgentStep", "LoopResult"]
