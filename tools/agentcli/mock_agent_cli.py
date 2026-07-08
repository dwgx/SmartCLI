"""Mock agent CLI scenarios for SmartCLI control-plane validation.

This program deliberately behaves like common agent CLIs without calling any
model provider: it asks for confirmation, shows progress, emits subagent status
lines, and exits predictably. The validation harness drives it through a real
PTY using SmartCLI skills.
"""
from __future__ import annotations

import argparse
import sys
import time


def cmd_confirm(_args) -> int:
    ans = input("Allow tool action? [y/N] ")
    if ans.strip().lower() in ("y", "yes"):
        print("APPROVED: tool action executed")
    else:
        print("DENIED: tool action skipped")
    return 0


def cmd_progress(_args) -> int:
    for pct in (0, 25, 50, 75, 100):
        sys.stdout.write(f"\rProcessing agent task... {pct}%")
        sys.stdout.flush()
        time.sleep(0.12)
    sys.stdout.write("\rProcessing agent task... 100%\nDONE\n")
    sys.stdout.flush()
    return 0


def cmd_subagents(_args) -> int:
    print("AGENTCLI coordinator: spawning workers")
    for name in ("research", "harness", "review"):
        print(f"subagent {name}: started")
        sys.stdout.flush()
        time.sleep(0.08)
        print(f"subagent {name}: completed")
        sys.stdout.flush()
    print("ALL SUBAGENTS DONE")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="mock-agent-cli")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("confirm", help="ask for a y/N tool confirmation").set_defaults(func=cmd_confirm)
    sub.add_parser("progress", help="show a bounded progress screen").set_defaults(func=cmd_progress)
    sub.add_parser("subagents", help="emit deterministic subagent lifecycle lines").set_defaults(func=cmd_subagents)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
