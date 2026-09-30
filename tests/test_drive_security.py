#!/usr/bin/env python3
"""Pure checks for drive-tui's local control-plane input boundaries."""
from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "drive-tui" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import tui  # noqa: E402
from smartcli_core import readiness  # noqa: E402

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


# /proc/<pid>/stat with a comm that itself contains spaces AND parentheses, the
# two ways the naive "split the whole line on whitespace" parse goes wrong.
_PROC_STAT = ("1234 (my prog (x)) S 1 1234 1234 0 -1 4194560 100 0 0 0 "
              "1 2 3 4 20 0 1 0 987654 123 456")
_PROC_STAT_FIELDS_AFTER_NAME = 22  # starttime's 1-based field number


def test_starttime_extraction() -> None:
    """Field 22 of /proc/<pid>/stat is read by position AFTER the name field.

    The name field is parenthesised and untrusted (it can hold spaces and
    parentheses of its own), so an implementation that splits the whole line
    silently returns utime here. Exercised on fixed text: no live process, and
    no platform where /proc exists is required.
    """
    parse = getattr(tui, "_parse_proc_stat_starttime", None)
    check(callable(parse), "tui.py exposes _parse_proc_stat_starttime")
    if not callable(parse):
        return
    starttime = _PROC_STAT[_PROC_STAT.rfind(")") + 1:].split()[_PROC_STAT_FIELDS_AFTER_NAME - 3]
    check(parse(_PROC_STAT) == int(starttime) == 987654,
          f"starttime is read as field 22 ({parse(_PROC_STAT)!r}), not as a "
          f"whitespace index")
    check(parse(_PROC_STAT[:_PROC_STAT.rfind(")")]) is None,
          "a stat body with no closing paren yields None, not a guess")
    check(parse(_PROC_STAT[:_PROC_STAT.index(" 0 -1 ")]) is None,
          "a stat body that ends before field 22 yields None, not a short read")
    nonnumeric = _PROC_STAT.replace("0 987654 ", "0 later ", 1)
    check(parse(nonnumeric) is None,
          "a non-numeric starttime yields None instead of raising")


def test_close_is_identity_aware() -> None:
    """close must not read a bare pid as proof that the recorded daemon is alive.

    A pid names a slot, not a process. The slot answers "alive" for whoever
    holds it next, so the pid-only test that stood in for "is this daemon
    still there" is wrong twice over with no malice required (an unrelated
    process inherits the number) and wrong on demand for anyone who can write
    the registry file. The daemon therefore records its creation time next to
    the pid, and close treats a contradiction as "not proven dead" — the
    fail-closed direction, because a false "still running" costs one --force
    while a false "dead" orphans a PTY child nothing can reach.

    Uses a live pid (this process) and a pinned _proc_identity, so it is
    deterministic and spawns nothing.
    """
    old_dir = tui.REG_DIR
    me = os.getpid()
    with tempfile.TemporaryDirectory(prefix="smartcli_identity_") as tmp:
        tui.REG_DIR = Path(tmp)

        def entry(sid: str, **fields) -> Path:
            # port 1: nothing listens, so _call always fails -> the recovery path
            tui._write_reg(sid, {"sid": sid, "port": 1, "pid": me,
                                 "token": "tok", **fields})
            return tui._reg_path(sid)

        class Args:
            def __init__(self, sid: str, force: bool = False) -> None:
                self.id, self.json, self.force = sid, False, force

        def close(sid: str, force: bool = False) -> tuple[int, str]:
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                rc = tui.cmd_close(Args(sid, force))
            return rc, err.getvalue()

        patched = hasattr(tui, "_proc_identity")
        original = tui._proc_identity if patched else None
        try:
            if patched:
                tui._proc_identity = lambda pid: "ident-A"

            # The real round trip, no pinning: this process's identity is
            # stable across calls and is not the forged string.
            real = tui._proc_identity(me) if patched else None
            if real is None:
                print("SKIP  live-process identity round trip "
                      "(no /proc and no GetProcessTimes on this platform)")
            else:
                check(real == tui._proc_identity(me) and real != "ident-B",
                      f"_proc_identity is stable and process-specific ({real!r})")

            forged = entry("forged", pid_born="ident-B")
            rc, err = close("forged")
            check(rc != 0 and forged.exists() and "recycled" in err,
                  f"a live pid whose creation time contradicts the record is "
                  f"KEPT, and the reason says the pid was recycled "
                  f"(rc={rc}, kept={forged.exists()}, err={err.strip()[:90]!r})")

            agreed = entry("agreed", pid_born="ident-A")
            rc, err = close("agreed")
            check(rc != 0 and agreed.exists() and "matches the recorded" in err,
                  f"a live pid whose creation time MATCHES the record is still "
                  f"kept (rc={rc}, kept={agreed.exists()}, "
                  f"err={err.strip()[:90]!r})")

            unreadable = entry("unreadable", pid_born="ident-B")
            if patched:
                tui._proc_identity = lambda pid: None
            rc, err = close("unreadable")
            check(rc != 0 and unreadable.exists() and "unreadable" in err,
                  f"an identity the OS will not report fails CLOSED, not open "
                  f"(rc={rc}, kept={unreadable.exists()}, "
                  f"err={err.strip()[:90]!r})")

            legacy = entry("legacy")  # written before the identity field existed
            rc, err = close("legacy")
            check(rc != 0 and legacy.exists()
                  and "predates the creation-time field" in err
                  and "weaker" in err,
                  f"a legacy entry falls back to the pid-only check AND names "
                  f"that weakness in the refusal (rc={rc}, kept={legacy.exists()}, "
                  f"err={err.strip()[:140]!r})")

            # Nothing was guessed here: the pid is positively gone, so even the
            # pid-only check is a definite answer and the cleanup stays silent.
            legacy_dead = entry("legacydead", pid=999999)
            rc, err = close("legacydead")
            check(rc == 0 and not legacy_dead.exists() and err == "",
                  f"a legacy entry whose pid is gone is cleaned up silently "
                  f"(rc={rc}, gone={not legacy_dead.exists()}, err={err!r})")

            forced = entry("forced", pid_born="ident-B")
            rc, err = close("forced", force=True)
            check(rc == 0 and not forced.exists(),
                  f"--force still overrides the identity-aware guard "
                  f"(rc={rc}, entry gone={not forced.exists()})")

            forced_legacy = entry("forcedlegacy")
            rc, err = close("forcedlegacy", force=True)
            check(rc == 0 and not forced_legacy.exists() and "warning" in err,
                  f"--force on a legacy entry deletes it but still warns "
                  f"(rc={rc}, entry gone={not forced_legacy.exists()})")

            # A pid that is positively gone is the ONE case that must still be
            # cleanable, identity or not: a dead slot cannot be the daemon.
            reaped = entry("reaped", pid=999999, pid_born="ident-A")
            rc, err = close("reaped")
            check(rc == 0 and not reaped.exists(),
                  f"a vanished pid is still cleanable even with a recorded "
                  f"identity (rc={rc}, entry gone={not reaped.exists()})")
        finally:
            if patched:
                tui._proc_identity = original
            tui.REG_DIR = old_dir


# --- Windows registry privacy -------------------------------------------------
# Everything below reads the DACL back with its OWN ctypes calls rather than
# asking tui.py what it thinks it set. A test that re-reads the constant the
# implementation just computed proves nothing: it would pass unchanged if the
# code wrote a different constant. Here the question is always "what does the
# filesystem say about the object the code actually created".

_SID_SYSTEM = "S-1-5-18"
_SID_ADMINS = "S-1-5-32-544"
#: Any of these bits in a grant ACE means the trustee can do something here.
_SENSITIVE_MASK = 0x001F01FF | 0x01000000 | 0x02000000 | 0xF0000000


def _win_sid_of_account() -> str:
    """This account's SID, read from this process's own token.

    The independence that matters is in _win_foreign_grantees, which walks the
    ACL with its own bindings; resolving who "I" am needs the token either way.
    """
    import ctypes
    from ctypes import wintypes
    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    advapi32.OpenProcessToken.argtypes = [ctypes.c_void_p, wintypes.DWORD,
                                          ctypes.POINTER(ctypes.c_void_p)]
    advapi32.OpenProcessToken.restype = wintypes.BOOL
    advapi32.GetTokenInformation.argtypes = [ctypes.c_void_p, ctypes.c_int,
                                              ctypes.c_void_p, wintypes.DWORD,
                                              ctypes.POINTER(wintypes.DWORD)]
    advapi32.GetTokenInformation.restype = wintypes.BOOL
    advapi32.ConvertSidToStringSidW.argtypes = [ctypes.c_void_p,
                                                ctypes.POINTER(ctypes.c_wchar_p)]
    advapi32.ConvertSidToStringSidW.restype = wintypes.BOOL
    kernel32.GetCurrentProcess.argtypes = []
    kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel32.CloseHandle.restype = wintypes.BOOL

    class SidAndAttributes(ctypes.Structure):
        _fields_ = [("Sid", ctypes.c_void_p), ("Attributes", wintypes.DWORD)]

    class TokenUser(ctypes.Structure):
        _fields_ = [("User", SidAndAttributes)]

    token = ctypes.c_void_p()
    if not advapi32.OpenProcessToken(kernel32.GetCurrentProcess(), 0x0008,
                                     ctypes.byref(token)):
        raise AssertionError("OpenProcessToken failed")
    try:
        needed = wintypes.DWORD(0)
        advapi32.GetTokenInformation(token, 1, None, 0, ctypes.byref(needed))
        buf = ctypes.create_string_buffer(needed.value)
        if not advapi32.GetTokenInformation(token, 1, buf, needed,
                                            ctypes.byref(needed)):
            raise AssertionError("GetTokenInformation failed for TOKEN_USER")
        user = ctypes.cast(buf, ctypes.POINTER(TokenUser)).contents.User
        text = ctypes.c_wchar_p()
        advapi32.ConvertSidToStringSidW(user.Sid, ctypes.byref(text))
        return text.value or ""
    finally:
        kernel32.CloseHandle(token)


_ALLOWED_CACHE: set | None = None


def _win_allowed_sids() -> set:
    global _ALLOWED_CACHE
    if _ALLOWED_CACHE is None:
        _ALLOWED_CACHE = {_win_sid_of_account(), _SID_SYSTEM, _SID_ADMINS}
    return _ALLOWED_CACHE


def _win_foreign_grantees(path: Path) -> set:
    """SID strings granted something sensitive on ``path`` that we did not name.

    Returns None-ish evidence by RAISING if the DACL cannot be walked at all,
    which the callers treat as a failure too: an unreadable verdict is not a
    clean bill of health.
    """
    import ctypes
    from ctypes import wintypes
    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    advapi32.GetNamedSecurityInfoW.argtypes = [ctypes.c_wchar_p, ctypes.c_int,
                                               wintypes.DWORD, ctypes.c_void_p,
                                               ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p),
                                               ctypes.c_void_p,
                                               ctypes.POINTER(ctypes.c_void_p)]
    advapi32.GetNamedSecurityInfoW.restype = wintypes.DWORD
    advapi32.GetAclInformation.argtypes = [ctypes.c_void_p, ctypes.c_void_p,
                                           wintypes.DWORD, ctypes.c_int]
    advapi32.GetAclInformation.restype = wintypes.BOOL
    advapi32.GetAce.argtypes = [ctypes.c_void_p, wintypes.DWORD,
                                ctypes.POINTER(ctypes.c_void_p)]
    advapi32.GetAce.restype = wintypes.BOOL
    advapi32.ConvertSidToStringSidW.argtypes = [ctypes.c_void_p,
                                                ctypes.POINTER(ctypes.c_wchar_p)]
    advapi32.ConvertSidToStringSidW.restype = wintypes.BOOL

    class AclSizeInformation(ctypes.Structure):
        _fields_ = [("AceCount", wintypes.DWORD), ("AclBytesInUse", wintypes.DWORD),
                    ("AclBytesFree", wintypes.DWORD)]

    class AclAceHeader(ctypes.Structure):
        _fields_ = [("AceType", ctypes.c_ubyte), ("AceSize", ctypes.c_ubyte),
                    ("AceFlags", ctypes.c_ubyte)]

    class AccessAllowedAce(ctypes.Structure):
        _fields_ = [("Header", AclAceHeader), ("Mask", wintypes.DWORD),
                    ("SidStart", wintypes.DWORD)]

    dacl, descriptor = ctypes.c_void_p(), ctypes.c_void_p()
    rc = advapi32.GetNamedSecurityInfoW(str(path), 1, 0x4, None, None,
                                         ctypes.byref(dacl), None,
                                         ctypes.byref(descriptor))
    if rc != 0 or not dacl:
        raise AssertionError(f"cannot read the DACL of {path} (rc={rc})")
    try:
        info = AclSizeInformation()
        if not advapi32.GetAclInformation(dacl, ctypes.byref(info), ctypes.sizeof(info), 2):
            raise AssertionError(f"cannot size the DACL of {path}")
        allowed = _win_allowed_sids()
        foreign = set()
        for index in range(info.AceCount):
            ace = ctypes.c_void_p()
            if not advapi32.GetAce(dacl, index, ctypes.byref(ace)):
                raise AssertionError(f"cannot read ACE {index} of {path}")
            body = ctypes.cast(ace, ctypes.POINTER(AccessAllowedAce)).contents
            if body.Header.AceType != 0x00:  # only ACCESS_ALLOWED_ACE grants
                continue
            if not body.Mask & _SENSITIVE_MASK:
                continue
            sid_at = ctypes.addressof(body) + AccessAllowedAce.SidStart.offset
            text = ctypes.c_wchar_p()
            advapi32.ConvertSidToStringSidW(ctypes.c_void_p(sid_at), ctypes.byref(text))
            sid = text.value or ""
            if sid and sid not in allowed:
                foreign.add(sid)
        return foreign
    finally:
        ctypes.WinDLL("kernel32").LocalFree(descriptor)



#: Well-known trustees this test may hand the fixture to, best first:
#: BUILTIN\Users, then BUILTIN\Guest. "Foreign" is decided by
#: _win_allowed_sids and not by the name: what matters is a trustee the
#: production DACL is not allowed to name, and the running account is free to
#: BE one of the well-known groups.
_WIN_FOREIGN_SIDS = ("S-1-5-32-545", "S-1-5-2")
#: FILE_ALL_ACCESS -- what a permissive host hands a stranger, and what
#: _ensure_reg_dir must never leave behind.
_WIN_ALL_ACCESS = 0x001F01FF


def _win_pick_foreign_sid() -> str:
    """A well-known SID that is provably not one this account may hand a file to."""
    allowed = _win_allowed_sids()
    for sid in _WIN_FOREIGN_SIDS:
        if sid not in allowed:
            return sid
    raise AssertionError(f"no foreign principal to test with: every candidate is "
                         f"this account's own ({sorted(allowed)})")


def _win_grant_foreign(path: Path, sid_text: str,
                       mask: int = _WIN_ALL_ACCESS) -> None:
    """Grant ``sid_text`` ``mask`` on ``path``, on top of whatever it inherited.

    The hostile precondition has to be BUILT, not hoped for. This used to be
    read off the host: a fresh directory under the system temp directory was
    assumed to arrive with a permissive ACL, which is true of some machines and
    false of a Windows runner whose %TEMP% is owner-only -- the assertion then
    measured the runner image and went red on code that was fine. So the fixture
    grants the ACE here, through the same Win32 entry points the production code
    uses and none of its code, and _win_foreign_grantees reads the result back
    with its own bindings: an implementation that is wrong cannot agree with
    this test by sharing a helper with it.

    The ACE is added with NO_INHERITANCE on purpose. The claim under test is
    about THIS directory, and a grant that flowed down to whatever the code
    created inside it would turn one broken DACL into two red checks.
    """
    import ctypes
    from ctypes import wintypes
    handle = ctypes.c_void_p
    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    # argtypes AND restype on every call: a handle that comes back as a default
    # c_int is truncated to 32 bits on a 64-bit host, and a truncated handle is
    # a plausible wrong answer rather than a crash.
    advapi32.GetNamedSecurityInfoW.argtypes = [ctypes.c_wchar_p, ctypes.c_int,
                                               wintypes.DWORD, ctypes.c_void_p,
                                               ctypes.c_void_p,
                                               ctypes.POINTER(handle),
                                               ctypes.c_void_p,
                                               ctypes.POINTER(handle)]
    advapi32.GetNamedSecurityInfoW.restype = wintypes.DWORD
    advapi32.GetAclInformation.argtypes = [handle, ctypes.c_void_p,
                                           wintypes.DWORD, ctypes.c_int]
    advapi32.GetAclInformation.restype = wintypes.BOOL
    advapi32.ConvertStringSidToSidW.argtypes = [ctypes.c_wchar_p,
                                                ctypes.POINTER(handle)]
    advapi32.ConvertStringSidToSidW.restype = wintypes.BOOL
    advapi32.GetLengthSid.argtypes = [handle]
    advapi32.GetLengthSid.restype = wintypes.DWORD
    advapi32.InitializeAcl.argtypes = [handle, wintypes.DWORD, wintypes.DWORD]
    advapi32.InitializeAcl.restype = wintypes.BOOL
    advapi32.AddAccessAllowedAceEx.argtypes = [handle, wintypes.DWORD,
                                               wintypes.DWORD, wintypes.DWORD,
                                               handle]
    advapi32.AddAccessAllowedAceEx.restype = wintypes.BOOL
    advapi32.SetNamedSecurityInfoW.argtypes = [ctypes.c_wchar_p, ctypes.c_int,
                                               wintypes.DWORD, ctypes.c_void_p,
                                               ctypes.c_void_p, ctypes.c_void_p,
                                               ctypes.c_void_p]
    advapi32.SetNamedSecurityInfoW.restype = wintypes.DWORD
    kernel32.LocalFree.argtypes = [handle]
    kernel32.LocalFree.restype = handle

    class AclSizeInformation(ctypes.Structure):
        _fields_ = [("AceCount", wintypes.DWORD), ("AclBytesInUse", wintypes.DWORD),
                    ("AclBytesFree", wintypes.DWORD)]

    dacl, descriptor, sid = handle(), handle(), handle()
    rc = advapi32.GetNamedSecurityInfoW(str(path), 1, 0x4, None, None,
                                        ctypes.byref(dacl), None,
                                        ctypes.byref(descriptor))
    if rc != 0 or not descriptor:
        raise AssertionError(f"cannot read the DACL of {path} to extend (rc={rc})")
    try:
        if not advapi32.ConvertStringSidToSidW(sid_text, ctypes.byref(sid)):
            raise AssertionError(f"ConvertStringSidToSidW failed for {sid_text}")
        inherited = 0
        if dacl:  # a NULL DACL is "everyone may do anything": nothing to copy
            info = AclSizeInformation()
            if not advapi32.GetAclInformation(dacl, ctypes.byref(info),
                                              ctypes.sizeof(info), 2):
                raise AssertionError(f"cannot size the DACL of {path}")
            inherited = info.AclBytesInUse
        # An ACCESS_ALLOWED_ACE is an 8-byte header plus the SID inline.
        size = inherited + 8 + advapi32.GetLengthSid(sid)
        buf = ctypes.create_string_buffer(size)
        acl = ctypes.cast(buf, handle)
        if not advapi32.InitializeAcl(acl, size, 2):
            raise AssertionError(f"InitializeAcl failed for a {size}-byte ACL")
        if inherited:
            ctypes.memmove(acl, dacl, inherited)
        # The ACL header declares its own size in the third 16-bit field
        # (revision, sbz1, size, ace count, sbz2), and AddAccessAllowedAceEx
        # bumps the ACE count but leaves that field to the caller.
        ctypes.memmove(ctypes.addressof(buf) + 2,
                       (size & 0xFFFF).to_bytes(2, "little"), 2)
        if not advapi32.AddAccessAllowedAceEx(acl, 2, 0x00, mask, sid):
            raise AssertionError(f"AddAccessAllowedAceEx failed for {sid_text}")
        rc = advapi32.SetNamedSecurityInfoW(str(path), 1, 0x4, None, None,
                                            acl, None)
        if rc != 0:
            raise AssertionError(
                f"SetNamedSecurityInfoW refused to grant {sid_text} on {path} "
                f"(rc={rc}) -- this host cannot be given the hostile "
                f"precondition this test needs, and must not be reported as one "
                f"that was measured")
    finally:
        kernel32.LocalFree(sid)
        kernel32.LocalFree(descriptor)

def test_registry_location_per_platform() -> None:
    """The registry must not live in a directory whose ACL is somebody else's."""
    default = tui._default_reg_dir()
    if os.name == "nt":
        home = Path.home()
        temp = Path(tempfile.gettempdir()).resolve()
        check(default == home / ".smartcli" / "sessions",
              f"the Windows registry lives under the user profile, not %TEMP% "
              f"({default})")
        check(temp not in default.parents and default != temp,
              f"the Windows registry is not inside the temp directory ({default})")
    else:
        # POSIX was already correct and stays exactly as it was.
        runtime = os.environ.get("XDG_RUNTIME_DIR")
        if runtime:
            check(default == Path(runtime) / "smartcli_tui",
                  f"POSIX XDG_RUNTIME_DIR registry unchanged ({default})")
        elif sys.platform == "darwin":
            check(default == Path.home() / "Library" / "Caches" / "SmartCLI" / "sessions",
                  f"POSIX macOS registry unchanged ({default})")
        else:
            check(default == Path.home() / ".cache" / "smartcli" / "sessions",
                  f"POSIX registry unchanged ({default})")


def test_windows_registry_dacl_is_private() -> None:
    """MEASURE the DACL of the directory the code creates, and of a token file.

    The hostile precondition is CONSTRUCTED here, never inherited. This used to
    take the parent %TEMP%'s word for it -- a fresh directory under the system
    temp directory, whose measured ACL on the author's machine granted Modify
    to seven foreign trustees -- which is a fact about the host, not about the
    code: on a Windows runner whose temp directory is owner-only a fresh
    subdirectory names no foreign trustee at all, and the "before" assertion
    below went red on a commit whose code was fine. So the fixture now grants a
    known foreign principal full control on the registry directory AND on a
    control sibling the code is never pointed at. A pass can then only be
    explained by _ensure_reg_dir replacing the DACL it was handed: not by a
    fixture that was private to begin with, and not by the code having been
    pointed at the other directory.
    """
    if os.name != "nt":
        print("SKIP  registry DACL (Windows only; POSIX mode bits are covered "
              "by test_registry_symlink)")
        return
    missing = [name for name in ("_win_dacl_grants", "_win_apply_dacl",
                                 "_win_secure_registry_dir")
               if not callable(getattr(tui, name, None))]
    missing += [name for name in ("_WIN_DIR_INHERITANCE",)
                if getattr(tui, name, None) is None]
    check(not missing,
          f"tui.py exposes the Windows DACL helpers (missing: {missing})")
    if missing:
        return
    old_dir = tui.REG_DIR
    with tempfile.TemporaryDirectory(prefix="smartcli_dacl_") as tmp:
        root = Path(tmp)
        registry, control = root / "sessions", root / "control"
        registry.mkdir()
        control.mkdir()
        # The hostile grant, on the directory under test and on one the code is
        # never shown. Read back with _win_foreign_grantees, which walks the
        # ACL with its own bindings, so "the grant landed" is a measurement and
        # not a restatement of what this helper was asked to do.
        foreign = _win_pick_foreign_sid()
        _win_grant_foreign(registry, foreign)
        _win_grant_foreign(control, foreign)
        before = _win_foreign_grantees(registry)
        check(foreign in before,
              f"the fixture is hostile by construction, so this test CAN go red: "
              f"{foreign} may read and modify the registry directory before the "
              f"code runs (foreign grantees={sorted(before)})")
        tui.REG_DIR = registry
        try:
            # A refusal from the code under test is a failed claim, not a
            # traceback: the claim is about the end state, and "it gave up" is
            # not the same end state as "the directory is private".
            try:
                tui._ensure_reg_dir()
            except SystemExit as exc:
                check(False, f"_ensure_reg_dir refused instead of making the "
                             f"directory private: {str(exc).strip()[:140]!r}")
            after_dir = _win_foreign_grantees(registry)
            check(not after_dir,
                  f"no foreign principal can read or modify the registry "
                  f"directory after _ensure_reg_dir (before={len(before)}, "
                  f"after={sorted(after_dir)})")
            after_control = _win_foreign_grantees(control)
            check(foreign in after_control,
                  f"the control directory the code never saw is STILL hostile, so "
                  f"the clean result above is about the DACL that was replaced "
                  f"and not about a fixture that was private to begin with "
                  f"(control foreign grantees={sorted(after_control)})")

            try:
                tui._write_reg("daclprobe", {"sid": "daclprobe", "port": 1,
                                             "pid": 1, "token": "t"})
            except SystemExit as exc:
                check(False, f"the capability token write refused: "
                             f"{str(exc).strip()[:140]!r}")
            token_file = tui._reg_path("daclprobe")
            written = token_file.exists()
            check(written, "the token file was written")
            if written:
                after_file = _win_foreign_grantees(token_file)
                check(not after_file,
                      f"no foreign principal can read the capability token file "
                      f"(after={sorted(after_file)})")
            else:
                check(False, "with no token file there is no token DACL to measure")
            check(_win_allowed_sids() <= {
                sid for sid in tui._win_allowed_sid_strings(tui._win_acl_api())},
                "the account running the test is one of the allowed trustees")
        finally:
            tui.REG_DIR = old_dir
            # Nothing is left behind. Unlinking the tree does not undo a DACL,
            # and the ACE granted to `control` is still on it, so it is taken
            # back with the same call that makes a directory private -- even
            # when the checks above failed, which is when an abandoned foreign
            # grant would matter most. Not raised: a teardown error would hide
            # the failure that got us here.
            for leftover in (registry, control):
                try:
                    tui._win_apply_dacl(leftover, tui._WIN_DIR_INHERITANCE)
                except OSError as exc:
                    check(False, f"the access this test granted on "
                                 f"{leftover.name} was taken back ({exc})")


def test_windows_registry_fails_closed() -> None:
    """A DACL that cannot be set, or cannot be proven, must STOP the token write."""
    if os.name != "nt":
        print("SKIP  Windows fail-closed refusal (Windows only)")
        return
    for name in ("_win_apply_dacl", "_win_verify_private", "_win_dacl_grants"):
        if not callable(getattr(tui, name, None)):
            check(False, f"tui.py exposes {name} so the refusal can be exercised")
            return
    old_dir, old_apply, old_grants = tui.REG_DIR, tui._win_apply_dacl, tui._win_dacl_grants

    def refused(fn):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            try:
                fn()
            except SystemExit as exc:
                return True, str(exc), err.getvalue()
        return False, "", err.getvalue()

    with tempfile.TemporaryDirectory(prefix="smartcli_refuse_") as tmp:
        registry = Path(tmp) / "sessions"
        tui.REG_DIR = registry
        try:
            def broken(*_a, **_kw):
                raise OSError("SetNamedSecurityInfoW failed with Win32 error 5")
            tui._win_apply_dacl = broken
            ok, msg, _err = refused(tui._ensure_reg_dir)
            check(ok and "refusing" in msg and str(registry) in msg and "icacls" in msg,
                  f"a DACL that cannot be SET is a refusal naming the path and "
                  f"icacls, not a warning (ok={ok}, msg={msg.strip()[:120]!r})")

            tui._win_apply_dacl = old_apply
            tui._win_dacl_grants = lambda _p: [("S-1-1-0", 0x001F01FF)]
            ok, msg, _err = refused(tui._ensure_reg_dir)
            check(ok and "S-1-1-0" in msg and "Everyone" not in msg,
                  f"a DACL that reads back with a foreign grantee is refused and "
                  f"NAMES it (ok={ok}, msg={msg.strip()[:120]!r})")

            tui._win_dacl_grants = lambda _p: None
            ok, msg, _err = refused(tui._ensure_reg_dir)
            check(ok and "could not be read back" in msg,
                  f"an UNREADABLE DACL is treated as unproven, not as clean "
                  f"(ok={ok}, msg={msg.strip()[:120]!r})")

            tui._win_dacl_grants = old_grants
            tui._ensure_reg_dir()
            tui._win_apply_dacl = broken
            ok, _msg, _err = refused(lambda: tui._write_reg(
                "refused", {"sid": "refused", "port": 1, "pid": 1, "token": "t"}))
            check(ok and not (registry / "refused.json").exists(),
                  "a token whose file DACL fails is refused AND removed, not left "
                  f"on disk (ok={ok}, left={(registry / 'refused.json').exists()})")
        finally:
            tui.REG_DIR, tui._win_apply_dacl, tui._win_dacl_grants = (old_dir, old_apply,
                                                                      old_grants)


def test_stranded_sessions_are_named_not_killed() -> None:
    """Relocation strands old sessions: name them, kill nothing, do not count them."""
    warn = getattr(tui, "_stranded_session_warning", None)
    count = getattr(tui, "_active_session_count", None)
    check(callable(warn) and callable(count),
          "tui.py exposes _stranded_session_warning and _active_session_count")
    if not (callable(warn) and callable(count)):
        return
    old_dir = tui.REG_DIR
    with tempfile.TemporaryDirectory(prefix="smartcli_stranded_") as tmp:
        root = Path(tmp)
        legacy, fresh = root / "smartcli_tui", root / "sessions"
        legacy.mkdir()
        for name, body in (("one.json", {"pid": 4242}), ("two.json", {"pid": 777}),
                           ("three.json", {"nope": 1}), ("ignored.txt", {})):
            (legacy / name).write_text(json.dumps(body), encoding="utf-8")
        fresh.mkdir()
        tui.REG_DIR = fresh
        try:
            message = warn(legacy) or ""
            check(str(legacy) in message and "3" in message and "4242" in message
                  and "777" in message,
                  f"the warning names the old path, the entry count and the "
                  f"recorded pids ({message[:150]!r})")
            check("killed by hand" in message,
                  f"the warning says the pids are the user's to reap "
                  f"({message[:150]!r})")
            check(warn(root / "absent") is None,
                  "an absent old registry produces no warning")
            (legacy / "three.json").unlink()
            (legacy / "two.json").unlink()
            (legacy / "one.json").unlink()
            check(warn(legacy) is None,
                  "an empty old registry produces no warning")

            tui.REG_DIR = legacy
            check(warn(legacy) is None,
                  "no warning when SMARTCLI_TUI_DIR still points at the old path")

            tui.REG_DIR = fresh
            for name in ("a.json", "b.json"):
                (fresh / name).write_text(json.dumps({"pid": 1}), encoding="utf-8")
            check(count() == 2,
                  f"the cap counts the CURRENT registry only (got {count()}, "
                  f"expected 2 -- stranded entries must not consume the limit)")
        finally:
            tui.REG_DIR = old_dir


def test_posix_registry_branch_is_untouched() -> None:
    """The POSIX protections must not have been routed through the Windows code."""
    if os.name == "nt":
        print("SKIP  POSIX registry branch (Windows only)")
        return
    old_dir = tui.REG_DIR
    reached = []

    def tripwire(*_a, **_kw):
        reached.append(True)
        raise AssertionError("the POSIX branch called a Windows ACL helper")

    saved = {name: getattr(tui, name, None) for name in ("_win_secure_registry_dir",)}
    with tempfile.TemporaryDirectory(prefix="smartcli_posix_") as tmp:
        registry = Path(tmp) / "sessions"
        tui.REG_DIR = registry
        try:
            for name in saved:
                if callable(saved[name]):
                    setattr(tui, name, tripwire)
            tui._ensure_reg_dir()
            tui._write_reg("posix", {"sid": "posix", "port": 1, "pid": 1, "token": "t"})
            mode = registry.stat().st_mode & 0o777
            file_mode = tui._reg_path("posix").stat().st_mode & 0o777
            check(not reached and mode == 0o700 and file_mode == 0o600,
                  f"POSIX still creates 0700/0600 with no Windows ACL call "
                  f"(dir={oct(mode)}, file={oct(file_mode)}, reached={reached})")
        finally:
            for name, value in saved.items():
                setattr(tui, name, value)
            tui.REG_DIR = old_dir


def test_child_death_reaches_the_daemon_wire() -> None:
    """The opt-in must actually change what a wait caller is told, and must
    not change anything at all when it is off.

    Two distinct defects are gated here, and neither is a source-text check:

    * UNREACHED. The core's child-death outcome (`readiness.EXITED`) was
      produced by the library and consumed by nobody, so through the CLI and
      the MCP server -- the way an agent actually drives a session -- a child
      that died still cost the full ceiling. The only change that turns this
      red is threading `--detect-child-exit` from `start`/`run` into the
      session and reporting the outcome in the reply.

    * UNENCODABLE. `EXITED` is a deliberate singleton: falsy, identity-only
      equality, and NOT something `json` can write. A reply that passed it
      through would raise inside the daemon's writer, and `index >= 0` on it
      raises too -- so a child dying during `wait-any` would have turned into
      a daemon error, the most expensive outcome available, instead of the
      cheap one this feature exists to provide. `json.dumps` on the real reply
      is the assertion, because that is the call that used to raise.

    A real (unstarted) PtySession is the fixture: it supplies a genuine screen
    model, snapshot and liveness answer, and constructing one spawns no PTY
    and no child process. Only the wait primitive is replaced.
    """
    EXITED = readiness.EXITED
    sess = tui.PtySession(cols=40, rows=6)
    snap = sess.snapshot()

    def reply(action: str, **req):
        body = {"token": "tok", "action": action, **req}
        return tui._handle(sess, body, "tok")

    # (a) OFF BY DEFAULT. Every wait reports the key, and it is false -- so a
    #     caller that never opted in sees a strictly compatible reply.
    for action, req, field in (
        ("wait_regex", {"pattern": "x"}, "matched"),
        ("wait_change", {}, "changed"),
        ("wait_visual_change", {}, "changed"),
        ("wait_any", {"patterns": ["x"]}, "index"),
    ):
        setattr(sess, {"wait_regex": "wait_for", "wait_change": "wait_change",
                       "wait_visual_change": "wait_visual_change",
                       "wait_any": "wait_any"}[action],
                (lambda *a, _f=field, **k: (False, snap)))
        try:
            resp = reply(action, **req)
            encoded = json.dumps(resp)          # the call that used to raise
        finally:
            delattr(sess, {"wait_regex": "wait_for", "wait_change": "wait_change",
                           "wait_visual_change": "wait_visual_change",
                           "wait_any": "wait_any"}[action])
        check(resp.get("exited") is False and resp.get(field) is False
              and resp.get("ok") is True,
              f"{action} on a default session: exited is false and the reply "
              f"encodes ({field}={resp.get(field)!r})")
        check("exited" in encoded,
              f"{action} reply states the exited key even when it is false")

    # (b) ON, and the child is gone. The outcome is named, the primitive's own
    #     value is coerced to whatever that field's wire already calls "no
    #     match", and the whole reply still encodes.
    #
    #     The per-field spelling is the point, not a detail. `wait-any` reports
    #     an INDEX, and `False >= 0` is True in Python, so collapsing EXITED to
    #     False there would have reported `matched=True pattern=0` for a wait
    #     that matched nothing -- a caller would act on a match that never
    #     happened. It must be -1, which is what a wait-any timeout has always
    #     reported. Caught by an end-to-end run, not by this suite: the first
    #     version of this case asserted `index is False` and so pinned the bug.
    cases = (
        ("wait_regex", {"pattern": "x"}, "wait_for", "matched", False),
        ("wait_change", {}, "wait_change", "changed", False),
        ("wait_visual_change", {}, "wait_visual_change", "changed", False),
        ("wait_any", {"patterns": ["x", "y"]}, "wait_any", "index", -1),
    )
    for action, req, method, field, no_match in cases:
        setattr(sess, method, (lambda *a, **k: (EXITED, snap)))
        try:
            resp = reply(action, **req)
            encoded = json.dumps(resp)
        finally:
            delattr(sess, method)
        check(resp.get("exited") is True and resp.get(field) == no_match
              and type(resp.get(field)) is type(no_match),
              f"{action} on a dead child: exited is true, {field} is the "
              f"no-match value {no_match!r} and not merely falsy "
              f"(got {resp.get(field)!r})")
        # The composite field a caller actually branches on. For wait-any this
        # is the assertion that would have caught the False>=-0 bug.
        if field == "index":
            check(resp.get("matched") is False,
                  f"{action} on a dead child: matched is False, not a "
                  f"fictitious pattern 0 (got {resp.get('matched')!r})")
        check(resp.get("ok") is True and '"exited": true' in encoded,
              f"{action} reply encodes with exited=true and is not an error")

    # wait_ready spells the outcome as a REASON string, not the singleton, so
    # it needs its own case: an unknown member of the vocabulary must not be
    # silently reported as a timeout.
    sess.wait_ready = (lambda *a, **k: (readiness.EXITED_REASON, snap))
    try:
        resp = reply("wait_ready", marker="x")
        encoded = json.dumps(resp)
    finally:
        del sess.wait_ready
    check(resp.get("reason") == readiness.EXITED_REASON
          and resp.get("exited") is True,
          "wait_ready reports reason=EXITED (not TIMEOUT) with exited=true")
    check('"exited": true' in encoded, "wait_ready reply encodes with exited=true")

    # The token gate is not a formality: the new field must not be reachable
    # by a peer that cannot authenticate, on the same request shape.
    check(tui._handle(sess, {"action": "wait_regex", "pattern": "x"}, "tok")
          .get("exited") is None,
          "an unauthenticated wait still gets no reply fields at all")


def test_detect_child_exit_is_opt_in() -> None:
    """The flag must be off unless asked for, on every verb that has it.

    A wait that used to return TIMEOUT/false returning EXITED instead is a
    behaviour change for every existing caller, so the default is the load-
    bearing half of this feature. Both halves are gated: the parser default,
    and the assignment into the live session, which is checked by driving the
    real `_run_daemon` up to its accept loop with a stub session (no PTY, no
    child process -- `_serve_forever` is replaced by a sentinel).
    """
    parser = tui.build_parser()
    for argv, verb in ((["start", "--cmd", "x"], "start"),
                       (["run", "--cmd", "x", "--steps", "y"], "run")):
        args = parser.parse_args(argv)
        check(getattr(args, "detect_child_exit") is False,
              f"{verb} does not enable child-death detection by default")
    args = parser.parse_args(["start", "--cmd", "x", "--detect-child-exit"])
    check(args.detect_child_exit is True, "start --detect-child-exit is accepted")

    class _Stop(Exception):
        pass

    class _StubSession:
        """The PtySession surface `_run_daemon` touches, and nothing else."""

        def __init__(self, cols: int, rows: int) -> None:
            self.detect_child_exit = False
            self.started: object = None

        def start(self, cmd) -> None:
            self.started = cmd

        def close(self) -> dict:
            return {}

    # Two lists, because the pair is the whole assertion: what the session
    # looked like when it was CONSTRUCTED (the core's own default, and the
    # proof that the stub is not simply reporting back what it was asked for)
    # and what it looked like at the moment the daemon began SERVING it, which
    # is the only moment the value can matter.
    constructed: list[bool] = []
    served: list[bool] = []
    registered: list[object] = []
    _sid: list[str] = [""]

    def _factory(cols: int, rows: int) -> _StubSession:
        s = _StubSession(cols, rows)
        constructed.append(s.detect_child_exit)
        return s

    def _serve_stub(_srv, sess, _token, _stop_event):
        served.append(sess.detect_child_exit)
        # Read here rather than afterwards: the daemon deletes its own entry
        # on the way out, so a later read would find nothing and prove nothing.
        registered.append(json.loads(tui._reg_path(_sid[0]).read_text("utf-8")))
        raise _Stop

    old_dir = tui.REG_DIR
    old_session = tui.PtySession
    old_serve = tui._serve_forever
    with tempfile.TemporaryDirectory(prefix="smartcli_exit_") as tmp:
        try:
            tui.REG_DIR = Path(tmp)
            tui.PtySession = _factory        # type: ignore[assignment]
            tui._serve_forever = _serve_stub  # type: ignore[assignment]
            for want in (True, False):
                constructed.clear()
                served.clear()
                registered.clear()
                _sid[0] = f"exitprobe{int(want)}"
                try:
                    tui._run_daemon(_sid[0], "prog", 80, 24, "tok",
                                    detect_child_exit=want)
                except _Stop:
                    pass
                # Two observations, and the PAIR is the assertion: the
                # constructor default, which proves the stub is not lying
                # about starting off, and the value the daemon actually
                # installed on the object it went on to serve.
                check(constructed == [False] and served == [want],
                      f"_run_daemon serves a session with detect_child_exit="
                      f"{want} (constructor default={constructed}, "
                      f"served={served})")
                # The registry records it, so `list` can never describe a
                # session differently from the one it is listing.
                check(registered and registered[0].get("detect_child_exit") is want,
                      f"the registry entry records detect_child_exit={want} "
                      f"({registered})")
        finally:
            tui.REG_DIR = old_dir
            tui.PtySession = old_session       # type: ignore[assignment]
            tui._serve_forever = old_serve      # type: ignore[assignment]


def main() -> int:
    test_session_ids()
    test_environment_parser()
    test_session_limit()
    test_terminal_size_limit()
    test_daemon_resize_survives_bad_size()
    test_registry_symlink()
    test_close_keeps_a_live_daemons_entry()
    test_starttime_extraction()
    test_close_is_identity_aware()
    test_registry_location_per_platform()
    test_windows_registry_dacl_is_private()
    test_windows_registry_fails_closed()
    test_stranded_sessions_are_named_not_killed()
    test_posix_registry_branch_is_untouched()
    test_non_dict_request_is_rejected_cleanly()
    test_child_death_reaches_the_daemon_wire()
    test_detect_child_exit_is_opt_in()
    print()
    if failures:
        print(f"{failures} FAILURE(S)")
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
