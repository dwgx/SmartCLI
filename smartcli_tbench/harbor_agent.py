"""harbor_agent.py — a Harbor ``BaseAgent`` that drives the terminal with SmartCLI.

Harbor (github.com/laude-institute/harbor) is where the public Terminal-Bench
leaderboard moved. Its agent interface is **not** the classic Terminal-Bench one
that ``agent.py`` targets, and the difference is fundamental rather than cosmetic:

    classic TB:  perform_task(instruction, session: TmuxSession)
                 -> session.send_keys(...) / session.capture_pane()
    Harbor:      async run(instruction, environment: BaseEnvironment, context)
                 -> await environment.exec(command) -> ExecResult

**Harbor hands you a one-shot command runner, not a live terminal.** There is no
tmux handle and no ``capture_pane``, so ``driver.py``'s whole approach is
unavailable here. That is also precisely the gap this project fills: we install
``smartcli-toolkit`` inside the environment and drive its persistent-session CLI
through ``exec``, which gives the agent a real PTY plus screen-state waits that
Harbor does not otherwise provide.

Verified against the Harbor source (2026-08-05 checkout):
  * ``BaseAgent`` requires ``name()``, ``version()``, ``setup()``, ``run()``.
  * ``AgentConfig.import_path`` exists, so this class can be selected without
    forking Harbor or adding an ``AgentName`` enum member.
  * ``BaseEnvironment.exec(command, cwd=, env=, timeout_sec=, user=)`` returns an
    ``ExecResult``; ``upload_file``/``download_file`` also exist.

Harbor is imported lazily so that importing ``smartcli_tbench`` on a host without
Harbor installed does not fail — mirroring how ``agent.py`` treats classic TB.
This module is intentionally NOT shipped in the wheel.
"""
from __future__ import annotations

import json
import shlex
from pathlib import Path
from typing import Any, Callable

# The instruction handed to the model each turn. Kept here rather than inline so
# the decide_fn contract is visible in one place.
STEP_PROMPT = """\
You are driving a terminal through a screen-aware session. You see the rendered
screen as a cell grid, not a byte stream.

Task: {instruction}

Current screen:
{screen}

Reply with exactly one action as JSON, no prose:
  {{"action": "send_line", "text": "<a shell command>"}}
  {{"action": "send_keys", "keys": ["Down", "Enter"]}}
  {{"action": "wait"}}
  {{"action": "done"}}
"""


class HarborNotInstalled(RuntimeError):
    """Raised when Harbor is not importable in this interpreter."""


def _base_agent_cls():
    """Import Harbor's BaseAgent lazily, only where Harbor is installed."""
    try:
        from harbor.agents.base import BaseAgent  # type: ignore
    except ImportError as exc:  # pragma: no cover - depends on host
        raise HarborNotInstalled(
            "Harbor is not installed. `pip install harbor` (or run inside the "
            "Harbor repo) to use SmartCliHarborAgent."
        ) from exc
    return BaseAgent


def build_agent_class():
    """Construct ``SmartCliHarborAgent`` bound to Harbor's ``BaseAgent``.

    A factory so the class body — which subclasses BaseAgent — is only evaluated
    where Harbor exists. Same pattern as ``agent.build_agent_class``.
    """
    BaseAgent = _base_agent_cls()

    class SmartCliHarborAgent(BaseAgent):  # type: ignore[misc, valid-type]
        """Drives the environment's terminal through smartcli-tui over ``exec``.

        Select it without forking Harbor:

            agent:
              import_path: "smartcli_tbench.harbor_agent:SmartCliHarborAgent"

        A ``decide_fn`` is deliberately NOT bundled: this project supplies the
        perception and the driving loop, not a model client. Pass one in, or
        subclass and override ``_make_decider``. Without it the agent reports a
        clear error into the context rather than silently scoring zero.
        """

        # Linux-only: the setup path uses pip and a POSIX shell.
        SUPPORTS_WINDOWS: bool = False

        # Screen dimensions for the driven session. 80x24 keeps wrapping
        # behaviour conventional; the screen model is exact at any size.
        COLS = 100
        ROWS = 30

        MAX_STEPS = 40

        def __init__(
            self,
            *args: Any,
            decide_fn: Callable[[str, str], dict] | None = None,
            max_steps: int | None = None,
            **kwargs: Any,
        ) -> None:
            super().__init__(*args, **kwargs)
            self._decide_fn = decide_fn
            self._max_steps = max_steps or self.MAX_STEPS
            self._sid: str | None = None

        # --- Harbor's required identity ---------------------------------------

        @staticmethod
        def name() -> str:
            return "smartcli"

        def version(self) -> str | None:
            try:
                from importlib.metadata import version
                return version("smartcli-toolkit")
            except Exception:
                return None

        # --- setup: install SmartCLI inside the environment -------------------

        async def setup(self, environment: Any) -> None:
            """Install smartcli-toolkit in the environment.

            Harbor gives no PTY, so the driver has to live *inside* the
            environment. pip is used rather than a vendored copy so the run
            exercises the same artifact users install.
            """
            result = await environment.exec(
                command="pip install --no-cache-dir 'smartcli-toolkit>=0.2.0'",
                timeout_sec=300,
                user="root",
            )
            if getattr(result, "return_code", 1) != 0:
                raise RuntimeError(
                    "failed to install smartcli-toolkit in the environment: "
                    f"{getattr(result, 'stderr', '')[:400]}"
                )
            self.logger.info("smartcli-toolkit installed in the environment")

        # --- the driving loop --------------------------------------------------

        async def _tui(self, environment: Any, *args: str,
                       timeout_sec: int = 60) -> tuple[int, str]:
            """Run one smartcli-tui verb inside the environment."""
            cmd = "smartcli-tui " + " ".join(shlex.quote(a) for a in args)
            result = await environment.exec(command=cmd, timeout_sec=timeout_sec)
            return (getattr(result, "return_code", 1),
                    (getattr(result, "stdout", "") or "")
                    + (getattr(result, "stderr", "") or ""))

        def _make_decider(self) -> Callable[[str, str], dict] | None:
            """Override to plug in a model client. See the class docstring."""
            return self._decide_fn

        async def run(self, instruction: str, environment: Any,
                      context: Any) -> None:
            decide = self._make_decider()
            if decide is None:
                msg = ("SmartCliHarborAgent has no decide_fn: this adapter "
                       "provides perception and the drive loop, not a model "
                       "client. Pass decide_fn= or override _make_decider.")
                self.logger.error(msg)
                self._record(context, "error", msg)
                return

            # Start a persistent session running a shell. This is the capability
            # Harbor's exec-only interface lacks.
            rc, out = await self._tui(
                environment, "start", "--cmd", "bash -i",
                "--cols", str(self.COLS), "--rows", str(self.ROWS), "--json")
            sid = self._parse_sid(out)
            if rc != 0 or not sid:
                self._record(context, "error",
                             f"could not start a session (rc={rc}): {out[:300]}")
                return
            self._sid = sid
            self.logger.info("driving session %s", sid)

            try:
                # Wait for the first prompt on screen rather than sleeping.
                await self._tui(environment, "wait", "--id", sid,
                                "--timeout-ms", "15000")
                for step in range(self._max_steps):
                    _, screen = await self._tui(environment, "snapshot",
                                                "--id", sid)
                    action = decide(instruction, screen)
                    self._record(context, "screen", screen)
                    self._record(context, "action", json.dumps(action))
                    if not await self._apply(environment, sid, action):
                        break
            finally:
                # Always close: a leaked daemon would outlive the trial.
                await self._tui(environment, "close", "--id", sid)
                self._sid = None

        async def _apply(self, environment: Any, sid: str,
                         action: dict) -> bool:
            """Apply one decided action. Returns False when the loop should stop."""
            kind = (action or {}).get("action")
            if kind == "done":
                return False
            if kind == "send_line":
                await self._tui(environment, "send-line", "--id", sid,
                                str(action.get("text", "")))
            elif kind == "send_keys":
                keys = [str(k) for k in (action.get("keys") or [])]
                if keys:
                    await self._tui(environment, "keys", "--id", sid, *keys)
            elif kind == "wait":
                pass
            else:
                self.logger.warning("unknown action %r; treating as wait", kind)
            # After ANY action, wait for the screen to settle instead of
            # sleeping — this is the whole point of the project.
            await self._tui(environment, "wait", "--id", sid,
                            "--timeout-ms", "10000")
            return True

        # --- helpers -----------------------------------------------------------

        @staticmethod
        def _parse_sid(output: str) -> str | None:
            for line in output.splitlines():
                line = line.strip()
                if line.startswith("{"):
                    try:
                        sid = json.loads(line).get("sid")
                    except ValueError:
                        continue
                    if sid:
                        return str(sid)
            return None

        def _record(self, context: Any, kind: str, value: str) -> None:
            """Append to Harbor's AgentContext, tolerating API differences.

            Harbor's context API is richer than this adapter needs and has
            changed shape before, so every access is guarded: a trial must not
            fail because a logging call moved.
            """
            try:
                logs = getattr(context, "logs", None)
                if isinstance(logs, list):
                    logs.append({kind: value})
                    return
            except Exception:
                pass
            self.logger.info("[%s] %s", kind, value[:400])

    return SmartCliHarborAgent


try:  # pragma: no cover - depends on host
    SmartCliHarborAgent = build_agent_class()
except HarborNotInstalled:
    # Importable on a host without Harbor; the pure pieces stay usable.
    SmartCliHarborAgent = None  # type: ignore[assignment]
