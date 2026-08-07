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
    # Case variants: Windows env names are case-insensitive and CPython upcases
    # keys on assignment, so `smartcli_tui_token` BECOMES SMARTCLI_TUI_TOKEN in the
    # child — re-injecting the capability the daemon deliberately pops. An
    # exact-case guard let all of these through.
    for variant in ("smartcli_tui_token=stolen", "SmartCli_Tui_Token=stolen",
                    "sMaRtCli_TUI_dir=/tmp/evil"):
        check(raises_system_exit(lambda v=variant: tui._parse_env_items([v])),
              f"case variant is rejected too: {variant.split('=')[0]}")
    # The other variables the CLI itself reads are control plane as well.
    for reserved in ("SMARTCLI_ROOT=/tmp/evil", "SMARTCLI_MAX_SESSIONS=999",
                     "SMARTCLI_AUTO_INSTALL=1", "smartcli_root=/tmp/evil"):
        check(raises_system_exit(lambda v=reserved: tui._parse_env_items([v])),
              f"reserved control variable is rejected: {reserved.split('=')[0]}")
    # A name that merely starts with the same letters is NOT reserved — the guard
    # must not become a blanket ban on the user's own SMARTCLI-ish names.
    check(tui._parse_env_items(["SMARTCLI_USER_THING=ok"]) ==
          {"SMARTCLI_USER_THING": "ok"},
          "an unreserved SMARTCLI_* name is still allowed")


def test_non_dict_request_is_rejected_cleanly() -> None:
    """A non-dict JSON payload must get the standard error shape, pre-auth.

    `[1,2,3]` used to reach `_handle` and raise AttributeError on `req.get(...)`,
    which is not in the connection guard's narrow tuple, so the generic handler
    replied `{"error": "AttributeError: 'list' object has no attribute 'get'"}` —
    missing the `ok` field every other reply carries, and echoing an interpreter
    exception to a peer that had not authenticated.
    """
    for payload in ([1, 2, 3], "hi", None, 42, True):
        raised = False
        try:
            tui._handle(object(), payload, "tok")  # type: ignore[arg-type]
        except AttributeError:
            raised = True
        except Exception:
            raised = False
        check(raised,
              f"_handle still cannot digest a non-dict itself ({type(payload).__name__})"
              " -> the caller must reject it first")
    # And the daemon loop's guard is what does the rejecting: assert the isinstance
    # check exists on the request path, since the loop itself needs a socket to run.
    src = (ROOT / "skills/drive-tui/scripts/tui.py").read_text(encoding="utf-8")
    check("if not isinstance(req, dict):" in src,
          "the daemon rejects a non-dict request before _handle sees it")


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


def test_daemon_resize_survives_bad_size() -> None:
    # _validate_size raises SystemExit (a BaseException), which would sail
    # through the daemon's per-connection `except Exception` guard and kill
    # the live session. The resize action must convert it to an error reply.
    # sess is never touched when validation fails, so a bare object suffices.
    for cols, rows in ((0, 24), (5000, 24), (500, 500)):
        try:
            resp = tui._handle(object(), {"token": "t", "action": "resize",
                                          "cols": cols, "rows": rows}, "t")
        except BaseException as exc:  # noqa: BLE001 — the regression under test
            check(False, f"resize {cols}x{rows} escaped as {type(exc).__name__}")
        else:
            check(resp.get("ok") is False and "error" in resp,
                  f"out-of-range resize {cols}x{rows} returns an error reply")


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


def test_close_keeps_a_live_daemons_entry() -> None:
    """A failed close request must NOT delete the registry entry of a LIVE daemon.

    That file is the only store of the capability token AND the daemon pid, so
    unlinking it while the daemon runs leaves a PTY child that can be reached by
    neither protocol nor kill — while `list` reports zero sessions, inverting the
    project's hardest operational invariant. A timeout is not proof of death: the
    daemon's accept loop is serial, so a busy daemon looks exactly like a dead one.
    """
    old_dir = tui.REG_DIR
    with tempfile.TemporaryDirectory(prefix="smartcli_close_") as tmp:
        tui.REG_DIR = Path(tmp)

        def entry(sid: str, pid: int) -> Path:
            # port 1: nothing listens, so _call always fails -> the recovery path
            tui._write_reg(sid, {"sid": sid, "port": 1, "pid": pid,
                                 "token": "tok"})
            return tui._reg_path(sid)

        class Args:
            def __init__(self, sid: str, force: bool = False) -> None:
                self.id, self.json, self.force = sid, False, force

        try:
            live = entry("livepid", os.getpid())
            rc = tui.cmd_close(Args("livepid"))
            check(rc != 0 and live.exists(),
                  f"close REFUSES to delete the entry of a live daemon "
                  f"(rc={rc}, entry kept={live.exists()})")

            dead = entry("deadpid", 999999)
            rc = tui.cmd_close(Args("deadpid"))
            check(rc == 0 and not dead.exists(),
                  f"close DOES clean up a genuinely dead daemon's entry "
                  f"(rc={rc}, entry gone={not dead.exists()})")

            forced = entry("forced", os.getpid())
            rc = tui.cmd_close(Args("forced", force=True))
            check(rc == 0 and not forced.exists(),
                  f"--force overrides the liveness guard "
                  f"(rc={rc}, entry gone={not forced.exists()})")

            check(tui._pid_is_alive(os.getpid()) and not tui._pid_is_alive(999999)
                  and not tui._pid_is_alive(0),
                  "_pid_is_alive: true for self, false for absent and for 0")
        finally:
            tui.REG_DIR = old_dir


def main() -> int:
    test_session_ids()
    test_environment_parser()
    test_session_limit()
    test_terminal_size_limit()
    test_daemon_resize_survives_bad_size()
    test_registry_symlink()
    test_close_keeps_a_live_daemons_entry()
    test_non_dict_request_is_rejected_cleanly()
    print()
    if failures:
        print(f"{failures} FAILURE(S)")
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
