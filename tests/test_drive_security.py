#!/usr/bin/env python3
"""Pure checks for drive-tui's local control-plane input boundaries."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "drive-tui" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import tui  # noqa: E402

failures = 0


def check(condition: bool, label: str) -> None:
    global failures
    if not condition:
        failures += 1
    print(f"{'PASS' if condition else 'FAIL'}  {label}")


def raises_system_exit(fn) -> bool:
    try:
        fn()
    except SystemExit:
        return True
    return False


def raises_oserror(fn) -> bool:
    try:
        fn()
    except OSError:
        return True
    return False


def test_session_ids() -> None:
    check(tui._validate_sid("agent.1_test-run") == "agent.1_test-run",
          "portable session id is accepted")
    for value in ("../outside", "/absolute", "with space", "", "a" * 65):
        check(raises_system_exit(lambda value=value: tui._reg_path(value)),
              f"unsafe session id is rejected: {value!r}")


def test_environment_parser() -> None:
    parsed = tui._parse_env_items(["A=1", "URL=https://example.test/?a=b"])
    check(parsed == {"A": "1", "URL": "https://example.test/?a=b"},
          "KEY=VALUE parsing preserves equals signs in values")
    check(raises_system_exit(lambda: tui._parse_env_items(["1BAD=value"])),
          "invalid environment key is rejected")
    check(raises_system_exit(
        lambda: tui._parse_env_items(["SMARTCLI_TUI_TOKEN=stolen"])
    ), "control-plane environment cannot be overridden")


def test_session_limit() -> None:
    old = os.environ.get("SMARTCLI_MAX_SESSIONS")
    try:
        os.environ["SMARTCLI_MAX_SESSIONS"] = "12"
        check(tui._max_sessions() == 12, "configured session limit is accepted")
        for value in ("0", "129", "not-a-number"):
            os.environ["SMARTCLI_MAX_SESSIONS"] = value
            check(raises_system_exit(tui._max_sessions),
                  f"invalid session limit is rejected: {value!r}")
    finally:
        if old is None:
            os.environ.pop("SMARTCLI_MAX_SESSIONS", None)
        else:
            os.environ["SMARTCLI_MAX_SESSIONS"] = old


def test_terminal_size_limit() -> None:
    check(tui._validate_size(80, 24) == (80, 24),
          "normal terminal dimensions are accepted")
    for cols, rows in ((0, 24), (80, 0), (1001, 24), (500, 500)):
        check(raises_system_exit(lambda cols=cols, rows=rows: tui._validate_size(cols, rows)),
              f"unsafe terminal dimensions are rejected: {cols}x{rows}")


def test_registry_symlink() -> None:
    if os.name == "nt" or not hasattr(os, "O_NOFOLLOW"):
        print("SKIP  registry symlink refusal (POSIX O_NOFOLLOW only)")
        return
    old_dir = tui.REG_DIR
    with tempfile.TemporaryDirectory(prefix="smartcli_security_") as tmp:
        root = Path(tmp)
        real_registry = root / "real-registry"
        real_registry.mkdir()
        linked_registry = root / "registry"
        linked_registry.symlink_to(real_registry, target_is_directory=True)
        tui.REG_DIR = linked_registry
        check(raises_system_exit(tui._ensure_reg_dir),
              "registry directory itself may not be a symlink")

        target = root / "target"
        target.write_text("untouched", encoding="utf-8")
        (real_registry / "linked.json").symlink_to(target)
        tui.REG_DIR = real_registry
        try:
            refused = False
            try:
                tui._write_reg("linked", {"token": "secret"})
            except OSError:
                refused = True
            check(refused, "registry writer refuses a symlink target")
            check(target.read_text(encoding="utf-8") == "untouched",
                  "symlink target remains unchanged")

            tui._write_reg("exclusive", {"token": "first"})
            check(raises_oserror(
                lambda: tui._write_reg("exclusive", {"token": "second"})
            ), "duplicate registry write is refused")
            saved = (real_registry / "exclusive.json").read_text(encoding="utf-8")
            check("first" in saved and "second" not in saved,
                  "duplicate write cannot replace an existing capability")
        finally:
            tui.REG_DIR = old_dir


def main() -> int:
    test_session_ids()
    test_environment_parser()
    test_session_limit()
    test_terminal_size_limit()
    test_registry_symlink()
    print()
    if failures:
        print(f"{failures} FAILURE(S)")
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
