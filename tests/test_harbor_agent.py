#!/usr/bin/env python3
"""test_harbor_agent.py — exercise the Harbor adapter without Harbor or Docker.

The adapter's whole risk is interface drift: Harbor's ``BaseAgent`` contract and
``BaseEnvironment.exec`` signature are someone else's API, and a mismatch would
only surface during a real (slow, Docker-bound) benchmark run. So this test
stands up a **fake environment** matching the signature read from the Harbor
source and drives the adapter's loop end to end against it.

What it locks:
  * the adapter builds against a BaseAgent-shaped base class and exposes the four
    members Harbor requires: name(), version(), setup(), run()
  * setup() installs smartcli-toolkit via exec, and FAILS LOUDLY on a non-zero
    return code rather than proceeding to a broken run
  * run() starts a session, snapshots, applies each decided action, and — the
    part that matters most — **always closes the session**, including when the
    decide_fn raises
  * every action after the first is followed by a screen-settle wait, never a sleep
  * a missing decide_fn is reported, not silently scored as zero
  * the sid is parsed out of --json output

Pure/in-memory: no Harbor, no Docker, no PTY, no subprocess. Exit 0 = pass.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

FAILURES: list[str] = []


def check(cond: bool, label: str, detail: str = "") -> None:
    if not cond:
        FAILURES.append(label)
    print(f"  [{'PASS' if cond else 'FAIL'}] {label}" + (f"  {detail}" if detail and not cond else ""))


def run_async(coro):
    import asyncio
    return asyncio.new_event_loop().run_until_complete(coro)


# --------------------------------------------------------------------------
# A stand-in for harbor.agents.base.BaseAgent, shaped from the real source:
# __init__(logs_dir, model_name=None, logger=None, ...) plus a `logger` attr.
# --------------------------------------------------------------------------
class FakeBaseAgent:
    def __init__(self, logs_dir=None, model_name=None, logger=None, **kwargs):
        import logging
        self.logs_dir = logs_dir or Path("/tmp")
        self.model_name = model_name
        self.logger = logger or logging.getLogger("fake")


class FakeExecResult:
    def __init__(self, return_code=0, stdout="", stderr=""):
        self.return_code = return_code
        self.stdout = stdout
        self.stderr = stderr


class FakeEnvironment:
    """Records every exec() call so the drive sequence can be asserted."""

    def __init__(self, install_rc: int = 0, sid: str = "s123_456"):
        self.calls: list[str] = []
        self._install_rc = install_rc
        self._sid = sid

    async def exec(self, command: str, cwd=None, env=None,
                   timeout_sec=None, user=None) -> FakeExecResult:
        self.calls.append(command)
        if command.startswith("pip install"):
            return FakeExecResult(self._install_rc, "", "boom" if self._install_rc else "")
        if " start " in command:
            return FakeExecResult(0, '{"ok": true, "sid": "%s"}\n' % self._sid)
        if " snapshot " in command:
            return FakeExecResult(0, "[screen 30x100] cursor=r0c2\n  0*| $ \n")
        return FakeExecResult(0, "# ok\n")


class FakeContext:
    def __init__(self):
        self.logs: list[dict] = []


def build(**kwargs):
    """Build the adapter class against the fake base, as the factory would."""
    import smartcli_tbench.harbor_agent as H
    real = H._base_agent_cls
    H._base_agent_cls = lambda: FakeBaseAgent          # type: ignore[assignment]
    try:
        cls = H.build_agent_class()
    finally:
        H._base_agent_cls = real                        # type: ignore[assignment]
    return cls(logs_dir=Path("/tmp"), **kwargs)


print("--- the adapter satisfies Harbor's BaseAgent contract ---")
agent = build()
for member in ("name", "version", "setup", "run"):
    check(callable(getattr(agent, member, None)),
          f"exposes {member}()")
check(agent.name() == "smartcli", "name() is stable", detail=repr(agent.name()))
check(agent.SUPPORTS_WINDOWS is False,
      "declares no Windows support (setup uses pip + POSIX shell)")

print("\n--- setup() installs into the environment and fails loudly ---")
envr = FakeEnvironment()
run_async(build().setup(envr))
check(any(c.startswith("pip install") and "smartcli-toolkit" in c for c in envr.calls),
      "setup() pip-installs smartcli-toolkit", detail=str(envr.calls))

bad = FakeEnvironment(install_rc=1)
raised = False
try:
    run_async(build().setup(bad))
except RuntimeError:
    raised = True
check(raised, "setup() raises when the install fails, rather than continuing")

print("\n--- run() drives, then always closes the session ---")
script = [
    {"action": "send_line", "text": "ls"},
    {"action": "send_keys", "keys": ["Down", "Enter"]},
    {"action": "done"},
]


def scripted(instruction, screen):
    return script.pop(0) if script else {"action": "done"}


envr = FakeEnvironment()
ctx = FakeContext()
run_async(build(decide_fn=scripted).run("do a thing", envr, ctx))
joined = " || ".join(envr.calls)
check(" start " in joined and "--cols" in joined, "starts a persistent session")
check(" snapshot " in joined, "snapshots the screen to perceive it")
check("send-line" in joined and "ls" in joined, "applies send_line")
check("keys" in joined and "Down" in joined, "applies send_keys")
check(joined.count(" wait ") >= 3,
      "waits on screen state after each action (never sleeps)",
      detail=f"wait calls={joined.count(' wait ')}")
check(envr.calls[-1].startswith("smartcli-tui close"),
      "closes the session last", detail=envr.calls[-1])
check(any("screen" in e for e in ctx.logs) and any("action" in e for e in ctx.logs),
      "records screens and actions into the context")

print("\n--- a raising decide_fn must not leak the session ---")


def exploding(instruction, screen):
    raise ValueError("model blew up")


envr = FakeEnvironment()
leaked = None
try:
    run_async(build(decide_fn=exploding).run("x", envr, FakeContext()))
except ValueError:
    leaked = not any(c.startswith("smartcli-tui close") for c in envr.calls)
check(leaked is False, "session is closed even when decide_fn raises",
      detail=str(envr.calls[-1:]))

print("\n--- a missing decide_fn is reported, not silently zero ---")
envr = FakeEnvironment()
ctx = FakeContext()
run_async(build().run("x", envr, ctx))
check(any("error" in e for e in ctx.logs),
      "records an error when no decide_fn is supplied", detail=str(ctx.logs))
check(not any(" start " in c for c in envr.calls),
      "does not start a session it cannot drive")

print("\n--- sid parsing ---")
import smartcli_tbench.harbor_agent as H
check(H.build_agent_class.__doc__ is not None, "factory is documented")
cls = build()
check(cls._parse_sid('{"ok": true, "sid": "abc_1"}') == "abc_1", "parses sid from JSON")
check(cls._parse_sid("no json here") is None, "returns None when absent")
check(cls._parse_sid('noise\n{"ok":true,"sid":"z9"}\nmore') == "z9",
      "finds the JSON line among noise")

if FAILURES:
    print(f"\ntest_harbor_agent FAIL -- {len(FAILURES)} check(s):")
    for f in FAILURES:
        print("   -", f)
    sys.exit(1)
print("\nPASS: the Harbor adapter drives, records and cleans up correctly.")
sys.exit(0)
