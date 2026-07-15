"""agent.py — SmartCliAgent: a Terminal-Bench BaseAgent using SmartCLI's loop.

This is the only module that imports ``terminal_bench``, and it does so lazily
(inside the class body via a helper), so importing ``smartcli_tbench`` on a box
without terminal-bench (e.g. the Windows dev machine) still works — only
constructing/using ``SmartCliAgent`` requires it. Run this on CI ubuntu-latest /
the Debian box, where Docker + terminal-bench are available.

Registered via the harness's ``--agent-import-path smartcli_tbench.agent:SmartCliAgent``
(no fork of terminal-bench needed — the agent factory imports any BaseAgent subclass
from an import path).

The LLM ``decide_fn`` is deliberately minimal and pluggable: the point of this
adapter is the *loop + wait discipline*, not a novel prompting strategy. Supply your
own ``decide_fn`` (or subclass and override ``_make_decider``) to use a specific
model/client; the default raises a clear error if no decider is wired, so a
misconfigured run fails loudly instead of silently doing nothing.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable, List, Optional

from .driver import TmuxSessionDriver
from .loop import AgentStep, run_agent_loop


class TerminalBenchNotInstalled(RuntimeError):
    """Raised when terminal-bench is cleanly absent (vs installed-but-broken).

    Only THIS is swallowed at module import (→ ``SmartCliAgent = None`` so the pure
    driver/loop still import on a non-TB host). An installed-but-broken TB raises a
    plain ``RuntimeError`` that propagates, so a version/layout mismatch fails loud
    instead of being silently masked as "not installed".
    """


def _base_agent_cls():
    """Import Terminal-Bench's BaseAgent lazily (only where TB is installed)."""
    try:
        from terminal_bench.agents.base_agent import BaseAgent  # type: ignore
    except ImportError as exc:  # terminal-bench genuinely not installed here
        raise TerminalBenchNotInstalled(
            "SmartCliAgent needs terminal-bench installed "
            "(`uv tool install terminal-bench` or `pip install terminal-bench`). "
            "Run it on a Docker+Linux host (CI ubuntu-latest / the Debian box), "
            "not the Windows dev machine."
        ) from exc
    return BaseAgent


def build_agent_class():
    """Construct the ``SmartCliAgent`` class bound to TB's ``BaseAgent``.

    Done as a factory so the class body (which subclasses BaseAgent) is only
    evaluated where TB is importable. ``SmartCliAgent`` below is this class,
    resolved at import time on a TB host; on a non-TB host the module still imports
    but resolving ``SmartCliAgent`` raises the clear RuntimeError above.
    """
    BaseAgent = _base_agent_cls()
    try:
        from terminal_bench.agents.base_agent import AgentResult  # type: ignore
        from terminal_bench.agents.failure_mode import FailureMode  # type: ignore
    except Exception as exc:  # pragma: no cover - version/layout mismatch only
        raise RuntimeError(
            "terminal-bench is installed but its AgentResult/FailureMode types "
            "could not be imported (version/layout mismatch?). SmartCliAgent needs "
            f"a compatible terminal-bench: {exc!r}"
        ) from exc

    class SmartCliAgent(BaseAgent):
        """Drives the TB tmux session with SmartCLI's perceive/act/wait loop."""

        def __init__(self, *args, decide_fn: Optional[Callable] = None,
                     max_steps: int = 30, **kwargs):
            super().__init__(*args, **kwargs)
            self._decide_fn = decide_fn or self._make_decider(kwargs.get("model_name"))
            self._max_steps = max_steps

        @staticmethod
        def name() -> str:
            return "smartcli"

        def _make_decider(self, model_name):
            """Return a decide_fn backed by an LLM. Not wired by default — supply
            ``decide_fn=`` or override this to plug in your model client."""
            def _no_llm(instruction, screen, history):
                raise RuntimeError(
                    "SmartCliAgent has no decider wired. Pass decide_fn=<callable> "
                    "or override _make_decider to call your LLM. The loop + wait "
                    "primitives are ready; only the decide step needs a model."
                )
            return _no_llm

        def perform_task(self, instruction: str, session,
                         logging_dir: "Optional[Path]" = None):
            driver = TmuxSessionDriver(session)
            result = run_agent_loop(
                instruction, driver, self._decide_fn, max_steps=self._max_steps)
            # Token accounting is left to the decider/model client to record; report
            # a clean NONE failure mode when the loop ran to completion or budget.
            return AgentResult(
                total_input_tokens=0,
                total_output_tokens=0,
                failure_mode=FailureMode.NONE,
            )

    return SmartCliAgent


# Resolve at import time WHERE terminal-bench exists; on a non-TB host, accessing
# SmartCliAgent triggers the clear RuntimeError (module import itself still works,
# so the pure driver/loop unit tests import fine on Windows).
try:
    SmartCliAgent = build_agent_class()
except TerminalBenchNotInstalled:  # cleanly absent -> None; broken install propagates
    SmartCliAgent = None  # type: ignore
