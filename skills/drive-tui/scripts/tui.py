#!/usr/bin/env python3
"""tui.py -- thin CLI over smartcli_core for driving interactive TUI programs.

Two modes:

* Persistent session (default): ``start`` spawns a detached per-session daemon
  that owns a live PtySession; ``send-*`` / ``keys`` / ``wait`` / ``snapshot``
  connect to it over a localhost-only TCP socket so state survives across shell
  invocations. This is the perceive->decide->act loop from the shell.

* One-shot script (``run``): execute a JSON list of steps against a freshly
  spawned program in a single process and print snapshots. No daemon needed.


The wait family (``wait``, ``wait-regex``, ``wait-change``,
``wait-visual-change``, ``wait-any``) can optionally END when the child process
dies instead of sitting out the remaining timeout: ``start --detect-child-exit``
and ``run --detect-child-exit``, both off by default, both exactly today's
behaviour when off. On, a wait that ended on a dead child reports
``exited: true`` (``wait`` reports ``reason=EXITED``).

The daemon binds 127.0.0.1 only; it is local process control, no network surface.
"""

from __future__ import annotations

import argparse
import hmac
import json
import os
import queue
import re
import secrets
import select
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

# --- locate smartcli_core wherever this skill folder ended up ----------------
# Package import serves the wheel/entrypoint path; the fallback preserves direct
# execution from a source checkout or standalone copied skill.
try:
    from . import smartcli_bootstrap
except ImportError:  # pragma: no cover - exercised by direct script probes
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import smartcli_bootstrap  # type: ignore[no-redef]  # noqa: E402

smartcli_bootstrap.locate_core()

from smartcli_core import PtySession  # noqa: E402
from smartcli_core.readiness import EXITED, EXITED_REASON  # noqa: E402


def _default_reg_dir() -> Path:
    """Return a per-user registry location, never a shared fixed /tmp path."""
    if os.name == "nt":
        # NOT the temp directory. A POSIX mode bit is inert on Windows, so the
        # only thing protecting this file is the ACL of whatever directory it
        # is born in -- and an ACL is inherited, not chosen. Measured on the
        # dev host with icacls: a registry directory created fresh under %TEMP%
        # carried ten trustees, seven of them granted Modify, one of them a
        # local agent-sandbox group. The user profile is the one parent whose
        # SDDL is written to be owner-only (SYSTEM/Administrators/owner, all
        # inheritable); _ensure_reg_dir then replaces even that inheritance
        # with an explicit DACL and reads it back.
        return Path.home() / ".smartcli" / "sessions"
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
    if runtime_dir:
        return Path(runtime_dir) / "smartcli_tui"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Caches" / "SmartCLI" / "sessions"
    return Path.home() / ".cache" / "smartcli" / "sessions"


REG_DIR = Path(os.environ.get("SMARTCLI_TUI_DIR") or _default_reg_dir())
HOST = "127.0.0.1"
DEFAULT_MAX_SESSIONS = 8
MAX_COLS = 1000
MAX_ROWS = 500
MAX_CELLS = 100_000

# --- A04-S3 service budgets (design values, not measurements) ---------------
# A single "read everything that is there" call is what let an idle daemon
# discover 271 KB of unparsed output at its first client contact and what let a
# request-triggered pump swallow a whole backlog at once. These bound one service
# turn; production defaults can be revised from a local measurement, and the
# values are deliberately small enough to test.
IO_TURN_BYTES = int(os.environ.get("SMARTCLI_IO_TURN_BYTES", "65536"))
#: Fast verbs answered inside one poll gap, so a flood of quick requests cannot
#: consume the whole gap and starve the transport.
JOBS_PER_TURN = int(os.environ.get("SMARTCLI_JOBS_PER_TURN", "4"))
# --- A05 admission caps ------------------------------------------------------
# The reader count and the job queue were bounded by a literal `64` that only ever
# FILTERED a list after the fact: an accepted connection had already cost a thread,
# and an authenticated request had already cost a queue slot, before the number was
# consulted. These are admission limits instead -- a caller that arrives over the
# cap is REFUSED with a reason it can read, and nothing is ever dropped silently.
#: Live connection-reader threads one session will carry.
MAX_READERS = max(1, int(os.environ.get("SMARTCLI_MAX_READERS", "64")))
#: Authenticated requests queued for the single worker before arrivals are refused.
#: The floor of 1 matters: a cap of 0 would refuse every caller including the one
#: that would close the session.
MAX_JOBS = max(1, int(os.environ.get("SMARTCLI_MAX_JOBS", "64")))
# --- S6 reply progress -------------------------------------------------------
#: Bytes one spawn generation may spend RESENDING a device reply the transport
#: would not accept. 0 = off (the pre-S6 behaviour: one attempt per observation,
#: the remainder reported and left unwritten). Opt-in by design, and the daemon is
#: the only caller that sets it on a session.
REPLY_RETRY_BYTES = int(os.environ.get("SMARTCLI_REPLY_RETRY_BYTES", "0"))
_SID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
_ENV_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# --- registry: one JSON file per session id --------------------------------

def _validate_sid(sid: str) -> str:
    """Reject path-like or unbounded session ids before touching the filesystem."""
    if not isinstance(sid, str) or not _SID_RE.fullmatch(sid):
        raise SystemExit(
            "error: session id must be 1-64 characters using only letters, "
            "digits, '.', '_' or '-', and must start with a letter or digit"
        )
    return sid


def _reg_path(sid: str) -> Path:
    sid = _validate_sid(sid)
    return REG_DIR / f"{sid}.json"


def _max_sessions() -> int:
    raw = os.environ.get("SMARTCLI_MAX_SESSIONS", str(DEFAULT_MAX_SESSIONS))
    try:
        value = int(raw)
    except ValueError as exc:
        raise SystemExit("error: SMARTCLI_MAX_SESSIONS must be an integer") from exc
    if not 1 <= value <= 128:
        raise SystemExit("error: SMARTCLI_MAX_SESSIONS must be between 1 and 128")
    return value


#: Environment variables the CLI itself reads. `--env` may not set any of them:
#: they are the control plane, not payload for the driven child.
_RESERVED_ENV_PREFIXES = ("SMARTCLI_TUI_",)
_RESERVED_ENV_KEYS = frozenset({
    "SMARTCLI_ROOT",           # smartcli_bootstrap uses it to locate the core
    "SMARTCLI_MAX_SESSIONS",   # the session cap
    "SMARTCLI_AUTO_INSTALL",   # doctor's dependency installer
})


def _parse_env_items(items: list[str]) -> dict[str, str]:
    """Parse repeated KEY=VALUE values without invoking a shell."""
    result: dict[str, str] = {}
    for item in items:
        key, sep, value = item.partition("=")
        if not sep or not _ENV_KEY_RE.fullmatch(key):
            raise SystemExit(f"error: invalid --env {item!r}; expected KEY=VALUE")
        # Compare UPPERCASED, unconditionally. Windows environment names are
        # case-insensitive and CPython upcases them on assignment (os.py's
        # `encodekey` under `if name == 'nt'` returns `encode(key).upper()`), so an
        # exact-case check let `--env smartcli_tui_token=...` through and
        # `os.environ.update()` then installed it AS SMARTCLI_TUI_TOKEN — handing
        # the driven child the capability that line ~854 deliberately pops so it
        # cannot control its own daemon. Uppercasing everywhere costs nothing on
        # POSIX and closes the bypass on the historical primary dev target.
        upper = key.upper()
        if upper.startswith(_RESERVED_ENV_PREFIXES) or upper in _RESERVED_ENV_KEYS:
            raise SystemExit(f"error: --env may not override SmartCLI control variable {key!r}")
        result[key] = value
    return result


def _validate_size(cols: int, rows: int) -> tuple[int, int]:
    if cols < 1 or rows < 1:
        raise SystemExit("error: terminal dimensions must be positive")
    if cols > MAX_COLS or rows > MAX_ROWS or cols * rows > MAX_CELLS:
        raise SystemExit(
            f"error: terminal is too large ({cols}x{rows}); limits are "
            f"{MAX_COLS} columns, {MAX_ROWS} rows and {MAX_CELLS} cells"
        )
    return cols, rows


# --- Windows registry privacy -------------------------------------------------
# The POSIX protections in _ensure_reg_dir are inert on Windows: `0o600` passed
# to `os.open` buys no permission there, and the one `chmod` in the module is
# POSIX-only. What actually decides access is the ACL -- and the ACL a new
# directory is born with is INHERITED from its parent, not chosen by us. That
# inheritance is precisely what made the old location unsafe, so the fix is to
# stop inheriting: an explicit DACL naming exactly three trustees (this account,
# NT AUTHORITY\SYSTEM, BUILTIN\Administrators), applied, then READ BACK.
#
# Every ctypes entry point below declares argtypes AND restype. Without them
# ctypes truncates handles and pointers to 32 bits on x64 and these APIs answer
# plausibly wrong instead of raising -- the dangerous direction, because the
# answer is the security verdict. TRUSTEE/EXPLICIT_ACCESS are not used:
# SetEntriesInAclW returned ERROR_INVALID_PARAMETER (87) for every documented
# grfAccessMode/grfInheritance/TRUSTEE_TYPE combination on the dev host, while
# building the identical DACL by hand with InitializeAcl +
# AddAccessAllowedAceEx and handing it to SetNamedSecurityInfoW produced
# exactly the three ACEs below (verified with icacls).

_WIN_SE_FILE_OBJECT = 1
_WIN_DACL_SECURITY_INFORMATION = 0x00000004
_WIN_PROTECTED_DACL_SECURITY_INFORMATION = 0x80000000
# FILE_ALL_ACCESS: STANDARD_RIGHTS_REQUIRED plus every specific right on an
# NTFS file or directory -- a superset of DELETE, READ_CONTROL, WRITE_DAC,
# WRITE_OWNER and SYNCHRONIZE, so holding it means holding the registry.
_WIN_FILE_ALL_ACCESS = 0x001F01FF
_WIN_ACL_REVISION = 2
_WIN_TOKEN_QUERY = 0x0008
_WIN_TOKEN_USER_CLASS = 1
#: ACE inheritance flags used when the DACL is applied. The DIRECTORY
#: propagates its three ACEs to everything created inside it, so a registry
#: file cannot pick up a trustee we did not name -- inheriting from the parent
#: is the very behaviour that caused the exposure, and here the parent is ours.
_WIN_DIR_INHERITANCE = 0x01 | 0x02  # OBJECT_INHERIT_ACE | CONTAINER_INHERIT_ACE
_WIN_FILE_INHERITANCE = 0x00  # a file has no children to inherit to
#: Any of these bits in a grant means the trustee can do something here.
#: FILE_ALL_ACCESS already covers SYNCHRONIZE and every standard right, so a
#: grant that misses this mask grants nothing worth stealing.
_WIN_SENSITIVE_MASK = (0x001F01FF | 0x01000000  # FILE_ALL_ACCESS | ACCESS_SYSTEM_SECURITY
                       | 0x02000000            # MAXIMUM_ALLOWED
                       | 0xF0000000)           # GENERIC_* bits, mapped or not
_WIN_ALLOWED_SIDS = ("S-1-5-18", "S-1-5-32-544")  # NT AUTHORITY\SYSTEM, BUILTIN\Administrators
_WIN_ACE_ALLOWED = 0x00
#: ACE types that GRANT access, from the Win32 ACE-type table (Ace Strings,
#: microsoft.com/en-us/windows/win32/win32/secauthz/ace-strings.md, SDDL "XA"):
#: 0x00 allow, 0x04 allow-compound, 0x05 allow-object, 0x09 allow-callback,
#: 0x0B allow-callback-object. The set is written out in full and matched
#: FIRST, because this is a privacy check: a type missing from it is a grant we
#: failed to account for, and the answer to that is a refusal, not a pass. It
#: used to be the other way round -- a type was treated as inert unless it was
#: recognised as a grant -- and 0x09 landed in the wrong list, so a DACL whose
#: foreign grant was ACCESS_ALLOWED_CALLBACK_ACE (WRITE_DAC, WRITE_OWNER,
#: DELETE for a stranger) verified PRIVATE. 0x0B being absent is what showed
#: 0x09 was a slip rather than a policy.
_WIN_ACE_GRANTING = frozenset({0x00, 0x04, 0x05, 0x09, 0x0B})
#: Types that can only take access away or only record it: 0x01 deny, 0x02 audit,
#: 0x03 alarm, 0x06 deny-object, 0x07 audit-object, 0x08 alarm-object, and the
#: callback flavours of the same -- 0x0A deny-callback, 0x0C audit-callback,
#: 0x0D alarm-callback. Parsed past, never counted as grants. 0x0E
#: (SYSTEM_MANDATORY_LABEL) and 0x10 (SYSTEM_RESOURCE_ATTRIBUTE) are
#: deliberately absent: they are SACL entries, not DACL ACEs, so seeing one in a
#: DACL means this walk is reading something it does not understand.
_WIN_ACE_NON_GRANTING = frozenset({0x01, 0x02, 0x03, 0x06, 0x07, 0x08,
                                    0x0A, 0x0C, 0x0D})
_WIN_ACL_SIZE_INFO_CLASS = 2
_WIN_REFUSAL = (
    "error: refusing to write a session capability token: the {what} at {path} "
    "could not be proven private to this user ({detail}).\n"
    "  SmartCLI sets an explicit Windows DACL there -- this account, "
    "NT AUTHORITY\\SYSTEM and BUILTIN\\Administrators, full control, nothing "
    "else -- and then reads it back before writing. Anything else that can "
    "read this directory can drive a live child process, so an unproven DACL "
    "is treated as a permissive one.\n"
    '  Check:  icacls "{path}"\n'
    "  It must list exactly those three trustees. If sandbox software, group "
    "policy or an endpoint agent re-applies an ACL to a directory we create, "
    "point SMARTCLI_TUI_DIR at a directory it leaves alone, remove the extra "
    "trustees, or run as an account that can set the DACL, then retry."
)
_WIN_ACL_API: dict[str, Any] | None = None


def _win_acl_api() -> dict[str, Any]:
    """Bind (once) the Windows entry points used to set and read back a DACL."""
    global _WIN_ACL_API
    if _WIN_ACL_API is not None:
        return _WIN_ACL_API
    import ctypes

    dword = ctypes.c_ulong
    handle = ctypes.c_void_p
    # ctypes.windll only exists on Windows; it is touched here, inside a function
    # no POSIX path ever calls, so the module still imports everywhere else.
    advapi32 = ctypes.windll.advapi32
    kernel32 = ctypes.windll.kernel32

    kernel32.GetCurrentProcess.argtypes = []
    kernel32.GetCurrentProcess.restype = handle
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    # CloseHandle, not LocalFree: a token handle is a kernel handle, and freeing
    # one as if it were heap memory corrupts the heap (observed as an access
    # violation, then 0xC0000374, in the process that did it).
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel32.CloseHandle.restype = ctypes.c_int
    advapi32.OpenProcessToken.argtypes = [handle, dword, ctypes.POINTER(handle)]
    advapi32.OpenProcessToken.restype = ctypes.c_int
    advapi32.GetTokenInformation.argtypes = [handle, ctypes.c_int, ctypes.c_void_p,
                                              dword, ctypes.POINTER(dword)]
    advapi32.GetTokenInformation.restype = ctypes.c_int
    advapi32.ConvertSidToStringSidW.argtypes = [ctypes.c_void_p,
                                                ctypes.POINTER(ctypes.c_wchar_p)]
    advapi32.ConvertSidToStringSidW.restype = ctypes.c_int
    advapi32.ConvertStringSidToSidW.argtypes = [ctypes.c_wchar_p,
                                                ctypes.POINTER(ctypes.c_void_p)]
    advapi32.ConvertStringSidToSidW.restype = ctypes.c_int
    advapi32.GetLengthSid.argtypes = [ctypes.c_void_p]
    advapi32.GetLengthSid.restype = dword
    advapi32.InitializeAcl.argtypes = [ctypes.c_void_p, dword, dword]
    advapi32.InitializeAcl.restype = ctypes.c_int
    advapi32.AddAccessAllowedAceEx.argtypes = [ctypes.c_void_p, dword, dword, dword,
                                               ctypes.c_void_p]
    advapi32.AddAccessAllowedAceEx.restype = ctypes.c_int
    advapi32.SetNamedSecurityInfoW.argtypes = [ctypes.c_wchar_p, ctypes.c_int, dword,
                                               ctypes.c_void_p, ctypes.c_void_p,
                                               ctypes.c_void_p, ctypes.c_void_p]
    advapi32.SetNamedSecurityInfoW.restype = dword
    advapi32.GetNamedSecurityInfoW.argtypes = [ctypes.c_wchar_p, ctypes.c_int, dword,
                                               ctypes.c_void_p, ctypes.c_void_p,
                                               ctypes.POINTER(ctypes.c_void_p),
                                               ctypes.c_void_p,
                                               ctypes.POINTER(ctypes.c_void_p)]
    advapi32.GetNamedSecurityInfoW.restype = dword
    advapi32.GetAclInformation.argtypes = [ctypes.c_void_p, ctypes.c_void_p, dword,
                                           ctypes.c_int]
    advapi32.GetAclInformation.restype = ctypes.c_int
    advapi32.GetAce.argtypes = [ctypes.c_void_p, dword, ctypes.POINTER(ctypes.c_void_p)]
    advapi32.GetAce.restype = ctypes.c_int

    class SidAndAttributes(ctypes.Structure):
        _fields_ = [("Sid", ctypes.c_void_p), ("Attributes", dword)]

    class TokenUser(ctypes.Structure):
        _fields_ = [("User", SidAndAttributes)]

    class AceHeader(ctypes.Structure):
        _fields_ = [("AceType", ctypes.c_ubyte), ("AceSize", ctypes.c_ubyte),
                    ("AceFlags", ctypes.c_ubyte)]

    class AccessAllowedAce(ctypes.Structure):
        # ACCESS_ALLOWED_ACE: header, access mask, then the SID inline. The SID
        # STARTS at the mask's end, which is why the read-back below walks
        # pointers instead of trusting a fixed-size struct copy.
        _fields_ = [("Header", AceHeader), ("Mask", dword), ("SidStart", dword)]

    class AclSizeInformation(ctypes.Structure):
        _fields_ = [("AceCount", dword), ("AclBytesInUse", dword),
                    ("AclBytesFree", dword)]

    _WIN_ACL_API = {
        "ctypes": ctypes, "dword": dword, "advapi32": advapi32, "kernel32": kernel32,
        "TokenUser": TokenUser, "AceHeader": AceHeader,
        "AccessAllowedAce": AccessAllowedAce, "AclSizeInformation": AclSizeInformation,
    }
    return _WIN_ACL_API


def _win_sid_string(api: dict[str, Any], sid: Any) -> str:
    """Render a PSID as an SID string (``S-1-5-21-...``)."""
    ctypes = api["ctypes"]
    text = ctypes.c_wchar_p()
    if not api["advapi32"].ConvertSidToStringSidW(sid, ctypes.byref(text)):
        raise OSError("ConvertSidToStringSidW failed")
    try:
        value = text.value
    finally:
        api["kernel32"].LocalFree(text)
    if not value:
        raise OSError("ConvertSidToStringSidW produced an empty SID")
    return value


def _win_current_user_sid(api: dict[str, Any]) -> str:
    """The SID of the account this process runs as, from its own token."""
    ctypes, advapi32, dword = api["ctypes"], api["advapi32"], api["dword"]
    token = ctypes.c_void_p()
    if not advapi32.OpenProcessToken(api["kernel32"].GetCurrentProcess(),
                                      _WIN_TOKEN_QUERY, ctypes.byref(token)):
        raise OSError("OpenProcessToken failed: this process cannot read its own token")
    try:
        needed = dword(0)
        advapi32.GetTokenInformation(token, _WIN_TOKEN_USER_CLASS, None, 0,
                                     ctypes.byref(needed))
        if not needed.value:
            raise OSError("GetTokenInformation reported a zero-sized TOKEN_USER")
        buf = ctypes.create_string_buffer(needed.value)
        if not advapi32.GetTokenInformation(token, _WIN_TOKEN_USER_CLASS, buf,
                                            needed, ctypes.byref(needed)):
            raise OSError("GetTokenInformation failed for TOKEN_USER")
        user = ctypes.cast(buf, ctypes.POINTER(api["TokenUser"])).contents.User
        return _win_sid_string(api, user.Sid)
    finally:
        api["kernel32"].CloseHandle(token)


def _win_allowed_sid_strings(api: dict[str, Any]) -> tuple[str, ...]:
    """The only trustees the registry DACL may name: me, SYSTEM, Administrators."""
    return (_win_current_user_sid(api),) + _WIN_ALLOWED_SIDS


def _win_apply_dacl(path: Path, inheritance: int) -> None:
    """Replace ``path``'s DACL with full control for exactly the allowed SIDs.

    The DACL is set PROTECTED so no ACE is pushed down onto the object from its
    parent, and the directory's ACEs are inheritable so that what lands inside
    it is derived from this list rather than from a token default nobody chose.
    """
    api = _win_acl_api()
    ctypes, advapi32, kernel32 = api["ctypes"], api["advapi32"], api["kernel32"]
    sids: list[Any] = []
    try:
        size = 8  # the ACL header
        for text in _win_allowed_sid_strings(api):
            sid = ctypes.c_void_p()
            if not advapi32.ConvertStringSidToSidW(text, ctypes.byref(sid)):
                raise OSError(f"ConvertStringSidToSidW failed for {text}")
            sids.append(sid)
            size += 8 + advapi32.GetLengthSid(sid)
        acl_buf = ctypes.create_string_buffer(size)
        acl = ctypes.cast(acl_buf, ctypes.c_void_p)
        if not advapi32.InitializeAcl(acl, size, _WIN_ACL_REVISION):
            raise OSError(f"InitializeAcl failed for a {size}-byte ACL")
        for sid in sids:
            if not advapi32.AddAccessAllowedAceEx(
                    acl, _WIN_ACL_REVISION, inheritance, _WIN_FILE_ALL_ACCESS, sid):
                raise OSError("AddAccessAllowedAceEx failed")
        rc = advapi32.SetNamedSecurityInfoW(
            str(path), _WIN_SE_FILE_OBJECT,
            _WIN_DACL_SECURITY_INFORMATION | _WIN_PROTECTED_DACL_SECURITY_INFORMATION,
            None, None, acl, None)
        if rc != 0:
            raise OSError(f"SetNamedSecurityInfoW failed with Win32 error {rc}")
    finally:
        for sid in sids:
            kernel32.LocalFree(sid)


def _win_dacl_grants(path: Path) -> list[tuple[str, int]] | None:
    """Every ACE on ``path`` that GRANTS something, as (SID string, mask).

    The classification is fail-closed and it is the reason this function can
    return None: an ACE is counted only if it is a plain ACCESS_ALLOWED_ACE,
    skipped only if it is a type that provably cannot grant
    (``_WIN_ACE_NON_GRANTING``), and ANY other type -- a compound/object/callback
    grant, or a value nobody enumerated -- ends the walk in a refusal. An
    unenumerated type is never read as "harmless".

    None means the DACL could not be read, or held something this build will not
    vouch for. A NULL DACL -- the one state that grants everyone everything -- is
    reported as None too, because "could not establish" and "wide open" both
    have to end in a refusal.
    """
    api = _win_acl_api()
    ctypes, advapi32 = api["ctypes"], api["advapi32"]
    acl, descriptor = ctypes.c_void_p(), ctypes.c_void_p()
    rc = advapi32.GetNamedSecurityInfoW(
        str(path), _WIN_SE_FILE_OBJECT, _WIN_DACL_SECURITY_INFORMATION,
        None, None, ctypes.byref(acl), None, ctypes.byref(descriptor))
    if rc != 0:
        return None
    try:
        if not acl:
            return None  # NULL DACL: full access for everyone, including us
        info = api["AclSizeInformation"]()
        if not advapi32.GetAclInformation(acl, ctypes.byref(info), ctypes.sizeof(info),
                                          _WIN_ACL_SIZE_INFO_CLASS):
            return None
        grants: list[tuple[str, int]] = []
        sid_offset = api["AccessAllowedAce"].SidStart.offset
        for index in range(info.AceCount):
            ace = ctypes.c_void_p()
            if not advapi32.GetAce(acl, index, ctypes.byref(ace)):
                return None
            body = ctypes.cast(ace, ctypes.POINTER(api["AccessAllowedAce"])).contents
            ace_type = body.Header.AceType
            if ace_type in _WIN_ACE_GRANTING:
                if ace_type != _WIN_ACE_ALLOWED:
                    # A compound, object or callback grant puts flags and GUIDs
                    # (and, for a compound ACE, a second SID) between the mask
                    # and the trustee, so this parser would read the wrong
                    # bytes as a SID. It is a GRANT, so it cannot be waved past
                    # as inert: the honest answer is that we cannot say what it
                    # hands out, and the DACL was supposed to hold three plain
                    # ACEs and nothing else.
                    return None
                sid = ctypes.c_void_p(ctypes.addressof(body) + sid_offset)
                try:
                    grants.append((_win_sid_string(api, sid), body.Mask))
                except OSError:
                    return None
            elif ace_type not in _WIN_ACE_NON_GRANTING:
                # An ACE type nobody enumerated -- a future type, or a SACL
                # entry in a DACL. Its posture is the same as a grant we cannot
                # read: refuse, rather than let an unenumerated value decide
                # that a stranger may rewrite the DACL.
                return None
        return grants
    finally:
        api["kernel32"].LocalFree(descriptor)


def _win_verify_private(path: Path, what: str) -> None:
    """Refuse unless ``path``'s DACL is provably {me, SYSTEM, Administrators}."""
    api = _win_acl_api()
    allowed = _win_allowed_sid_strings(api)
    grants = _win_dacl_grants(path)
    if grants is None:
        raise SystemExit(_WIN_REFUSAL.format(
            what=what, path=path,
            detail="its DACL could not be read back, or holds an ACE this build "
                   "will not read as a plain grant — a compound, object or "
                   "callback ACE (types 0x04/0x05/0x09/0x0B), or a type this "
                   "build does not enumerate — and it cannot be shown that none "
                   "of them names another trustee"))
    foreign = [(sid, mask) for sid, mask in grants
               if sid not in allowed and (mask & _WIN_SENSITIVE_MASK)]
    if foreign:
        raise SystemExit(_WIN_REFUSAL.format(
            what=what, path=path,
            detail=f"{len(foreign)} other trustee(s) can read or modify it: "
                   + ", ".join(sorted({sid for sid, _ in foreign}))))
    missing = [sid for sid in allowed if not any(g == sid for g, _ in grants)]
    if missing:
        raise SystemExit(_WIN_REFUSAL.format(
            what=what, path=path,
            detail="the DACL grants nothing to " + ", ".join(missing)))


def _win_secure_registry_dir(path: Path) -> None:
    """Make ``path`` private on Windows, or refuse to go on writing a token."""
    try:
        _win_apply_dacl(path, _WIN_DIR_INHERITANCE)
    except OSError as exc:
        raise SystemExit(_WIN_REFUSAL.format(
            what="session registry directory", path=path, detail=exc)) from exc
    _win_verify_private(path, "session registry directory")


def _win_discard_unprovable_file(path: Path) -> None:
    """Remove a registry file whose DACL could not be made private.

    A token left behind under a DACL we could not prove is worse than no token:
    the write is reported as refused, so nothing points at the file, and it sits
    on disk holding a capability for a live child process. Deleting is the only
    outcome that leaves nothing to be found later.
    """
    try:
        path.unlink()
    except OSError:
        pass


def _win_secure_registry_file(path: Path) -> None:
    """Same DACL on a registry file, AND the same read-back -- then it is done.

    The directory's ACEs are inheritable, so this file is already readable only
    by the three allowed trustees; setting them explicitly means that guarantee
    is a fact about this call rather than a consequence of a parent's flags.

    Applying is not enough, and the asymmetry was the defect: the DIRECTORY was
    applied and then verified, while the FILE -- the object that actually holds
    the capability token -- was only applied. So a DACL re-applied by sandbox
    software, group policy or an endpoint agent between the apply and the next
    use went unchallenged on the one file whose contents are the secret, and
    `_ensure_reg_dir`'s per-write check only ever re-examined the directory.
    Both are verified now, on the same fail-closed terms, and the file is
    removed rather than left behind if either half cannot be established.
    """
    try:
        _win_apply_dacl(path, _WIN_FILE_INHERITANCE)
    except OSError as exc:
        _win_discard_unprovable_file(path)
        raise SystemExit(_WIN_REFUSAL.format(
            what="session registry file", path=path, detail=exc)) from exc
    try:
        _win_verify_private(path, "session registry file")
    except SystemExit:
        _win_discard_unprovable_file(path)
        raise


def _legacy_windows_reg_dir() -> Path | None:
    """The pre-relocation Windows registry directory, or None off Windows.

    Kept so sessions left there can be NAMED rather than silently abandoned:
    relocating the registry makes every session the previous version started
    unreachable by both `close` and `list`, and their pids -- the only handle
    left on their child processes -- go with them.
    """
    if os.name != "nt":
        return None
    return Path(tempfile.gettempdir()) / "smartcli_tui"


def _stranded_session_warning(legacy: Path | None = None) -> str | None:
    """Describe sessions stranded in the old registry, or None if there are none.

    Nothing is moved and nothing is killed. A pid read out of another version's
    file is not this program's to act on, and silently killing a process it
    merely believes it once started is a far worse failure than a session the
    user has to reap by hand.

    The message therefore also says what ENDS the notice, which is the only
    dismissal path there is: this program never deletes that directory (there is
    no `shutil` import anywhere in this module), so without naming it the user
    is left with a warning on every command forever and no statement that
    anything can clear it. Removal is the user's own action, to be taken once
    they have dealt with the pids; the entries are recounted on every command,
    so an emptied directory silences it.
    """
    if legacy is None:
        legacy = _legacy_windows_reg_dir()
    if legacy is None:
        return None
    if os.path.normcase(os.path.abspath(legacy)) == os.path.normcase(os.path.abspath(REG_DIR)):
        return None  # SMARTCLI_TUI_DIR still points at the old location; nothing moved
    try:
        entries = sorted(legacy.glob("*.json"))
    except OSError:
        return None
    if not entries:
        return None
    pids = []
    for entry in entries:
        try:
            pids.append(int(json.loads(entry.read_text(encoding="utf-8")).get("pid") or 0))
        except (OSError, ValueError, AttributeError):
            pids.append(0)
    known = ", ".join(str(p) for p in pids if p > 0) or "not recorded"
    return (f"warning: {len(entries)} SmartCLI session(s) from a previous version are "
            f"still recorded in {legacy}, which this version no longer uses. They are "
            f"unreachable from `close` and `list`, and their pids ({known}) must be "
            f"killed by hand -- nothing is killed for you. They do not count against "
            f"the session limit, which starts fresh in {REG_DIR}. This notice repeats "
            f"on every command until that directory is gone, because nothing here "
            f"deletes it: once you have dealt with those pids, remove {legacy} (or "
            f"its *.json entries) yourself and it will not come back.")


def _ensure_reg_dir() -> None:
    """Create the registry directory and refuse any endpoint we cannot prove safe.

    POSIX: 0700, and refused if it is a symlink or owned by another user.
    Windows: an explicit DACL naming three trustees, applied and then read back.
    Neither platform continues if its own protection cannot be established --
    an unproven registry directory is treated as a permissive one, because the
    file inside it is the capability token for a live child process.
    """
    REG_DIR.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        _win_secure_registry_dir(REG_DIR)
        return
    try:
        info = REG_DIR.lstat()
    except OSError as exc:
        raise SystemExit(f"error: cannot inspect session registry {REG_DIR}: {exc}") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise SystemExit(f"error: session registry is not a real directory: {REG_DIR}")
    if info.st_uid != os.getuid():
        raise SystemExit(f"error: session registry is not owned by this user: {REG_DIR}")
    try:
        os.chmod(REG_DIR, 0o700)
    except OSError as exc:
        raise SystemExit(f"error: cannot secure session registry {REG_DIR}: {exc}") from exc


def _active_session_count() -> int:
    """Sessions counted against the cap: the CURRENT registry only.

    A relocated registry starts with an empty cap even though sessions recorded
    under the old path may still be running -- their pids are stranded in files
    this version cannot see, so charging them against the limit would report a
    full host that has nothing running.
    """
    return sum(1 for _ in REG_DIR.glob("*.json"))


def _write_reg(sid: str, info: dict) -> None:
    # The reg file holds the per-session capability token, so it must not be
    # readable by anyone else. On POSIX create the dir 0700 and the file 0600 (a
    # shared /tmp is multi-user); on Windows the mode bits are inert, so the
    # directory's DACL is what protects it and the file's is set explicitly too.
    _ensure_reg_dir()
    p = _reg_path(sid)
    # O_EXCL prevents a duplicate/racing daemon from replacing another
    # session's capability file. On POSIX, create it as 0600 from the start.
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if os.name != "nt":
        flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(str(p), flags, 0o600)
    else:
        flags |= getattr(os, "O_NOINHERIT", 0) | getattr(os, "O_BINARY", 0)
        fd = os.open(str(p), flags, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(info))
    if os.name == "nt":
        # Written and closed first: an ACL applied to a still-open handle would
        # only cover the fd, not the name other processes resolve.
        _win_secure_registry_file(p)


def _read_reg(sid: str) -> dict:
    p = _reg_path(sid)
    if not p.exists():
        raise SystemExit(f"error: no such session '{sid}' (looked in {p})")
    return json.loads(p.read_text(encoding="utf-8"))


# --- IPC: newline-delimited JSON request/response over a TCP socket ----------

def _send_request(port: int, req: dict, timeout: float = 30.0) -> dict:
    with socket.create_connection((HOST, port), timeout=timeout) as sock:
        sock.settimeout(timeout)
        sock.sendall((json.dumps(req) + "\n").encode("utf-8"))
        buf = bytearray()
        while b"\n" not in buf:
            chunk = sock.recv(65536)
            if not chunk:
                break
            buf.extend(chunk)
    line = bytes(buf).split(b"\n", 1)[0]
    if not line:
        raise SystemExit("error: empty response from session daemon")
    return json.loads(line.decode("utf-8"))


def _call(sid: str, req: dict, timeout: float = 30.0) -> dict:
    """Send one request to the session daemon.

    ``timeout`` is the socket timeout. For blocking waits the daemon does not
    reply until the wait finishes, so callers pass a socket timeout derived
    from the wait's own timeout (see cmd_wait/cmd_wait_regex) — otherwise a
    long wait would trip the default socket timeout and crash the client while
    the daemon kept running.
    """
    info = _read_reg(sid)
    # Auto-include the per-session capability token so only the creator (who can
    # read the per-user reg file) can drive the session. Callers never pass it.
    token = info.get("token")
    if token is not None and "token" not in req:
        req = {**req, "token": token}
    try:
        resp = _send_request(int(info["port"]), req, timeout=timeout)
    except (TimeoutError, ConnectionRefusedError, ConnectionResetError, OSError) as exc:
        raise SystemExit(
            f"error: session '{sid}' is not reachable (stale entry? {exc}). "
            f"Close the session (CLI: close --id {sid}; MCP: the close tool) "
            "to clean up the stale entry."
        ) from exc
    if resp.get("error"):
        raise SystemExit(f"error: {resp['error']}")
    return resp


# --- daemon: owns the live PtySession, serves requests on a socket ----------

def _io_block(sess) -> dict | None:
    """The runtime's io evidence, or None when this session cannot produce it.

    A04-S3: produced by the runtime (``basis_origin=runtime``) and only forwarded
    by the daemon and its CLI/MCP wrappers. An older session object without the
    method gets no ``io`` key at all -- never a synthesized one, because a claim
    that looks measured but was invented is worse than an absent field.
    """
    fn = getattr(sess, "io_block", None)
    if fn is None:
        return None
    try:
        return fn()
    except Exception:
        return None


def _snapshot_response(sess: PtySession, snap, **fields) -> dict:
    """Build one consistent text/JSON/hash response for every observing verb."""
    content_hash = sess.model.content_hash()
    visual_hash = sess.model.visual_hash()
    structured = json.loads(snap.to_json())
    structured["hash"] = content_hash
    structured["visual_hash"] = visual_hash
    io_block = _io_block(sess)
    if io_block is not None:
        # What the runtime knows about the transport -- cut, watermarks, and what is
        # still pending -- so a caller can tell "quiet" from "not read yet".
        structured["io"] = io_block
    return {
        "ok": True,
        "alive": sess.is_alive(),

        # Whether a full-screen program owns the screen changes what the next
        # action MEANS (does `q` quit or type a letter?), so it travels with every
        # observation rather than only inside the JSON payload.
        "alt_screen": sess.model.alt_screen,
        "text": snap.to_text(),
        "json": json.dumps(structured, ensure_ascii=False),
        "hash": content_hash,
        "visual_hash": visual_hash,
        **({"io": io_block} if io_block is not None else {}),
        **fields,
    }


def _exited(value: Any) -> bool:
    """Did this wait end because the child DIED, rather than on its own terms?

    Two shapes reach here, because the core spells the outcome two ways: the
    three boolean waits and ``wait_any`` return :data:`EXITED`, the singleton
    whose ``__bool__`` is False and whose ``__eq__`` is identity-only so it
    cannot be confused with a timeout, while ``wait_ready`` returns the string
    :data:`EXITED_REASON` to sit inside its existing MARKER/STABLE/TIMEOUT
    vocabulary. Both mean the same thing and both are worth naming on the wire.

    Only ever true when the session was started with ``--detect-child-exit``;
    the core cannot produce the outcome without an ``alive_fn``.
    """
    return value is EXITED or value == EXITED_REASON


def _wire_wait_value(value: Any, no_match: Any) -> Any:
    """The JSON-encodable form of a wait primitive's return value.

    ``EXITED`` is a deliberate singleton and ``json`` cannot encode it: passing
    it through would raise inside the reply writer, and ``index >= 0`` on it
    raises too, so a child dying mid-``wait-any`` would have surfaced as a
    daemon error rather than as a wait outcome.

    ``no_match`` is passed by the CALL SITE rather than defaulted here, because
    the wire already has a distinct spelling of "this wait did not match" per
    field and guessing one for all of them is a live bug, not a style question:
    ``wait-any`` reports an index, and ``False >= 0`` is ``True`` in Python, so
    collapsing ``EXITED`` to ``False`` there would have told the caller pattern
    0 matched. It is ``-1``, which is what a ``wait-any`` timeout has always
    reported, so ``matched`` then computes to ``False`` on its own.

    The distinction is not lost by the coercion: it travels in ``exited``,
    which is strictly more information than the caller's old ``matched=false``,
    because that value cannot say WHY the wait ended.

    With child-death detection off, the default, nothing here changes a value:
    the wait returned a real bool/int and it is written exactly as before.
    """
    return no_match if value is EXITED else value


def _token_ok(req: dict, expected_token: str) -> bool:
    """Constant-time capability check. ONE implementation, two call sites.

    The reader thread calls this so an unauthenticated request never reaches the
    worker queue; `_handle` calls it again because it is the authoritative gate for
    any direct caller. Two copies of this logic would be a way for them to drift.
    """
    supplied = req.get("token")
    return (isinstance(supplied, str)
            and hmac.compare_digest(supplied, expected_token))


def _handle(sess: PtySession, req: dict, expected_token: str,
            on_poll: Callable[[], None] | None = None) -> dict:
    """Dispatch one request against the live session. Returns a JSON-able dict.

    Every request MUST carry a ``token`` field matching the per-session
    capability token minted at ``start``. Missing/wrong tokens are rejected
    with a constant-time compare before any action is performed, so an
    unauthenticated local process on the loopback port cannot inject keystrokes,
    read the screen, or close the session.
    """
    # Kept here as well as on the reader thread. The reader rejects unauthenticated
    # requests before they can occupy the worker queue, but this check stays as the
    # authoritative one: _handle must be safe to call directly (tests do), and a
    # single guard that some future caller can bypass is how auth holes appear.
    if not _token_ok(req, expected_token):
        return {"ok": False, "error": "auth: bad or missing token"}

    action = req.get("action")

    if action == "snapshot":
        sess.pump()
        snap = sess.snapshot()
        return _snapshot_response(sess, snap)

    if action == "send_text":
        sess.send_text(req.get("text", ""))
        return {"ok": True}

    if action == "send_line":
        sess.send_line(req.get("text", ""))
        return {"ok": True}

    if action == "send_keys":
        sess.send_keys(list(req.get("keys", [])))
        return {"ok": True}

    # Every wait below reports `exited`, and it is `false` unless the session was
    # started with --detect-child-exit, so a caller that never asked for the
    # distinction pays one boolean it already had the information about.
    if action == "wait_ready":
        reason, snap = sess.wait_ready(
            marker=req.get("marker"),
            max_wait_ms=int(req.get("max_wait_ms", 10000)),
            quiet_ms=int(req.get("quiet_ms", 200)),
            on_poll=on_poll,
        )
        # `reason` is already a string, so it crosses the wire unchanged; the
        # new vocabulary member rides alongside it rather than inside it.
        return _snapshot_response(sess, snap, reason=reason,
                                  exited=_exited(reason))

    if action == "wait_regex":
        matched, snap = sess.wait_for(
            req["pattern"], timeout_ms=int(req.get("timeout_ms", 10000)),
            on_poll=on_poll)
        return _snapshot_response(sess, snap,
                                  matched=_wire_wait_value(matched, False),
                                  exited=_exited(matched))

    if action == "wait_change":
        changed, snap = sess.wait_change(
            baseline_hash=req.get("baseline_hash"),
            timeout_ms=int(req.get("timeout_ms", 10000)),
            on_poll=on_poll)
        return _snapshot_response(sess, snap,
                                  changed=_wire_wait_value(changed, False),
                                  exited=_exited(changed))

    if action == "wait_visual_change":
        changed, snap = sess.wait_visual_change(
            baseline_hash=req.get("baseline_hash"),
            timeout_ms=int(req.get("timeout_ms", 10000)),
            on_poll=on_poll)
        return _snapshot_response(sess, snap,
                                  changed=_wire_wait_value(changed, False),
                                  exited=_exited(changed))

    if action == "wait_any":
        index, snap = sess.wait_any(
            list(req.get("patterns", [])),
            timeout_ms=int(req.get("timeout_ms", 10000)),
            on_poll=on_poll)
        # `exited` is decided from the RAW value, before coercion: the singleton
        # IS the identification, so testing the coerced False would report "did
        # not exit" on the one reply that exists because it did. The coercion is
        # still required and is not cosmetic -- `index >= 0` raises on the
        # singleton, and an exception here is caught as a daemon error, turning
        # the outcome this feature exists to make cheap into the most expensive
        # one available.
        exited = _exited(index)
        index = _wire_wait_value(index, -1)
        return _snapshot_response(sess, snap, index=index, matched=index >= 0,
                                  exited=exited)

    if action == "alive":
        sess.pump()
        return {"ok": True, "alive": sess.is_alive()}

    if action == "resize":
        # _validate_size raises SystemExit for CLI callers; SystemExit is a
        # BaseException, so it would sail through the per-connection
        # `except Exception` guard and tear down the daemon + live session.
        # Convert it to an error response here instead.
        try:
            cols, rows = _validate_size(int(req["cols"]), int(req["rows"]))
        except SystemExit as exc:
            # Strip _validate_size's own "error: " prefix. Every other daemon
            # reply stores a bare message and lets _call add the prefix once for
            # the CLI caller, so keeping it here produced "error: error: ...".
            msg = str(exc)
            return {"ok": False, "error": msg[len("error: "):]
                    if msg.startswith("error: ") else msg}
        sess.resize(cols, rows)
        return {"ok": True}

    if action == "close":
        # A04-S4: answer with what was actually CONFIRMED. The session's close is
        # bounded (each backend confirms within a fixed window) and the state
        # travels back so a caller can distinguish "requested" from "gone"; a
        # close that could not be confirmed is still a shutdown, never a claimed
        # success. The teardown in _run_daemon is idempotent.
        return {"ok": True, "_shutdown": True, "close": sess.close()}

    return {"ok": False, "error": f"unknown action '{action}'"}


#: Everything up to and including the token check is UNAUTHENTICATED, so it runs on
#: a short budget. 2s is generous for loopback — even the 4 MiB cap below transfers
#: in milliseconds — and it is re-armed against a FIXED deadline so a peer dribbling
#: bytes cannot renew its welcome.
PRE_AUTH_TIMEOUT = 2.0
#: Total patience for writing ONE authenticated reply, unchanged from the pre-A06
#: value. A06 is not fixed by lowering this ceiling -- that would take replies away
#: from healthy-but-slow callers -- so a peer that IS reading keeps exactly the
#: window it always had, and the bound that matters is the stall window below.
POST_AUTH_TIMEOUT = float(os.environ.get("SMARTCLI_REPLY_TIMEOUT_MS", "60000")) / 1000.0
#: A06: seconds the send may make NO progress -- the peer accepts not one byte --
#: before it is abandoned. A peer that stops reading releases the session's only
#: worker inside this window instead of holding it for the whole ceiling; a peer
#: that is merely SLOW renews the window on every accepted byte, so slow is never
#: mistaken for stalled. 2 s is ~100x the transfer time of a loopback reply (a
#: 500 KB snapshot completes in milliseconds against a reading peer). 0 disables
#: the bound, leaving only the ceiling.
REPLY_STALL_SECONDS = float(os.environ.get("SMARTCLI_REPLY_STALL_SECONDS", "2.0"))
#: Refusals are written from the ACCEPT loop, so they get a much shorter deadline:
#: a courtesy reply must never be the thing that delays the next accept.
REFUSAL_DEADLINE = 0.5
#: Cap the pre-newline buffer: an unauthenticated peer must not be able to exhaust
#: memory by streaming bytes with no newline. Far above any legitimate request.
MAX_REQ = 4 * 1024 * 1024


def _read_request(conn: socket.socket) -> dict:
    """Read one newline-terminated JSON object. Raises on anything malformed.

    Runs on the READER thread, never on the worker, because this is the
    unauthenticated part: a peer that connects and never sends a newline must not
    be able to stall anyone else. It used to run inline in the accept loop, which
    made the read timeout itself the denial-of-service primitive rather than the
    mitigation.
    """
    conn.settimeout(PRE_AUTH_TIMEOUT)
    buf = bytearray()
    deadline = time.monotonic() + PRE_AUTH_TIMEOUT
    while b"\n" not in buf:
        left = deadline - time.monotonic()
        if left <= 0:
            raise TimeoutError("pre-auth read budget exhausted")
        conn.settimeout(left)
        chunk = conn.recv(65536)
        if not chunk:
            break
        buf.extend(chunk)
        if len(buf) > MAX_REQ:
            raise ValueError("request exceeds max size")
    if not buf:
        raise ValueError("empty request")
    req = json.loads(bytes(buf).split(b"\n", 1)[0].decode("utf-8"))
    # Enforce the SHAPE before anything touches it. A non-dict payload
    # (`[1,2,3]`, `"hi"`, `null`) used to reach _handle and die on `req.get(...)`
    # with AttributeError, which fell through to the generic handler and replied
    # with an interpreter exception — no `ok` field, unlike every other reply on
    # this socket, to a peer that had not authenticated.
    if not isinstance(req, dict):
        raise ValueError("request must be a JSON object")
    return req


def _reply(conn: socket.socket, payload: dict, deadline: float | None = None,
           stall: float | None = None) -> dict:
    """Send one newline-terminated JSON reply, bounded by a stall AND a ceiling (A06).

    ``sendall`` on a blocking socket returns only once every byte is in the peer's
    buffer, so a peer that stopped reading held the session's only worker for the
    whole post-auth timeout -- and with it every other caller of that session.

    The bound that fixes that is the STALL window (``stall``, default
    :data:`REPLY_STALL_SECONDS`): the send is abandoned once the peer has accepted
    nothing for that long. ``deadline`` (default :data:`POST_AUTH_TIMEOUT`) stays
    the total ceiling it always was, and because progress RENEWS the stall window, a
    slow-but-reading peer keeps the patience it always had -- only a peer that has
    genuinely stopped is cut off. A stall window of 0 disables the no-progress
    bound and leaves the ceiling alone.

    Whatever was accepted goes to the peer, and the outcome is RETURNED
    (``sent``/``bytes``/``total_bytes``/``reason``/``deadline_s``/``stall_s``)
    instead of raising or blocking. The caller closes the connection, which the
    stranded peer observes as an empty response rather than as silence.

    A dead or stalled peer is an outcome, not an exception: nothing here raises for
    it. The connection is left non-blocking and is not reused -- every call site
    closes it immediately afterwards.
    """
    budget = POST_AUTH_TIMEOUT if deadline is None else deadline
    stall_limit = REPLY_STALL_SECONDS if stall is None else stall
    data = (json.dumps(payload) + "\n").encode("utf-8")
    now = time.monotonic()
    end = now + max(budget, 0.0)
    #: Renewed on every accepted byte; ``inf`` when the window is disabled.
    progress_until = now + stall_limit if stall_limit > 0 else float("inf")
    sent = 0
    reason: str | None = None
    try:
        conn.setblocking(False)
        while sent < len(data):
            now = time.monotonic()
            if now >= end:
                reason = f"deadline: {sent}/{len(data)} bytes in {budget:.3f}s"
                break
            if now >= progress_until:
                reason = (f"stalled: peer accepted nothing for {stall_limit:.3f}s "
                          f"({sent}/{len(data)} bytes)")
                break
            try:
                count = conn.send(data[sent:])
            except BlockingIOError:
                # Spurious wakeups are allowed: the loop re-checks both bounds and
                # retries the SAME suffix, so a partial reply is never restarted.
                select.select([], [conn], [],
                              min(end - now, progress_until - now, 0.05))
                continue
            except InterruptedError:
                continue
            if count <= 0:
                reason = f"peer closed after {sent}/{len(data)} bytes"
                break
            sent += count
            if stall_limit > 0:
                progress_until = time.monotonic() + stall_limit
    except OSError as exc:
        reason = f"{type(exc).__name__}: {exc} ({sent}/{len(data)} bytes)"
    if reason is None and sent < len(data):      # cannot happen; never claim success
        reason = f"peer stopped reading: {sent}/{len(data)} bytes"
    return {"sent": reason is None, "bytes": sent, "total_bytes": len(data),
            "deadline_s": budget, "stall_s": stall_limit, "reason": reason}


def _serve_forever(srv: socket.socket, sess, token: str,
                   stop: threading.Event) -> None:
    """Serve requests until a `close` arrives, the child dies, or `stop` is set.

    CONCURRENCY MODEL, and why it is this one
    -----------------------------------------
    Three roles, deliberately separated:

      accept thread (here)  accept a connection, hand it to a reader. Never blocks
                            on a peer, so no client can delay another's ACCEPT.
      reader thread (per    do the UNAUTHENTICATED work — read the line, parse it,
      connection)           check the token — then enqueue the authenticated job.
                            One silent peer burns only its own 2s budget.
      worker thread (one)   the ONLY thread that touches `sess`.

    The single worker is not timidity, it is required. `PtySession` is not
    thread-safe in three concrete ways, all of which corrupt perception SILENTLY
    rather than raising:

      * `ScreenModel.visual_hash()` recomputes only the rows pyte marks dirty and
        then CLEARS `screen.dirty`. Two callers racing means one of them clears
        rows the other has not consumed yet, so a real screen change is lost — the
        exact blindness this project exists to remove.
      * `PtySession.pump()` is read-modify-write: `read_nonblocking` -> `feed` ->
        `drain_replies` -> `write`. Interleaving two of those reorders the bytes
        fed to the emulator and can interleave two DSR-CPR answers on the wire.
      * `PtySession.resize()` mutates `cols`, `rows`, the backend, the pyte screen
        and `_blank_hash` as four separate steps; observing it midway yields a
        screen whose dimensions disagree with its buffer.

    Putting a lock around the session instead would serialise the expensive part
    anyway AND let a `wait-regex --timeout-ms 60000` hold the lock for its entire
    timeout, which is most of what this daemon does. Hence: fast verbs and long
    waits are separated below rather than fighting over a mutex.

    HONEST LIMIT: a long `wait*` occupies the worker, so a second LONG wait queues
    behind the first. That is inherent to one PTY child having one screen, and it
    is not what the head-of-line defect was about — what mattered was that an
    unauthenticated stranger, or an unrelated fast verb, could be blocked. Fast
    verbs are answered during a long wait via the interleave hook; see
    `_WORKER_FAST_VERBS`.
    """
    jobs: queue.Queue = queue.Queue()
    #: A05: the check-and-enqueue for the job cap must be atomic, or two readers
    #: could both see room for one and admit one each. It is held for a qsize()
    #: and a put_nowait() only -- never across a reply to a peer, which is the
    #: very thing A06 bounds.
    admission = threading.Lock()
    shutdown = threading.Event()

    #: Verbs answered DURING a long wait, via the readiness poll hook. They are all
    #: cheap and non-blocking, so servicing them in a poll gap costs the wait one
    #: extra sub-millisecond step.
    #:
    #: The exclusions are the load-bearing part of this set:
    #:   * every `wait_*` verb — a second wait entered from the first one's poll gap
    #:     would reenter the session and could recurse without bound;
    #:   * `close` — it tears down the session the wait is still using;
    #:   * `resize` — it is cheap, but `PtySession.resize` re-dimensions the pyte
    #:     screen, which necessarily changes the content hash. A caller blocked in
    #:     `wait_change` would then read "the screen changed" and conclude its own
    #:     keystroke had landed, when all that happened was a concurrent resize.
    #:     Answering it a few milliseconds later, in queue order, costs nothing and
    #:     keeps the change primitives honest.
    INTERLEAVE_OK = frozenset({
        "snapshot", "alive", "list", "send_text", "send_line", "send_keys",
    })

    def _drain_interleavable() -> None:
        """Run pending fast verbs. Called from the WAITING thread's poll gap.

        This is what makes the fix real rather than a relocation of the queue. The
        worker owns the session, so a long `wait-regex` would otherwise hold it for
        its entire timeout and a concurrent `snapshot` would sit behind it —
        exactly the head-of-line symptom, just moved one layer in. Because the hook
        fires on the worker's own thread, the single-threaded-session invariant is
        preserved: nothing else ever touches `sess`.

        Requests that are NOT interleavable are put back for normal ordering.
        """
        deferred = []
        served = 0
        try:
            service_io()
            while served < JOBS_PER_TURN:
                try:
                    item = jobs.get_nowait()
                except queue.Empty:
                    break
                if item is None:          # shutdown sentinel: preserve it
                    deferred.append(item)
                    shutdown.set()
                    break
                conn, req = item
                if req.get("action") in INTERLEAVE_OK:
                    try:
                        _reply(conn, _handle(sess, req, token))
                    except Exception as exc:  # noqa: BLE001
                        _reply(conn, {"ok": False,
                                      "error": f"{type(exc).__name__}: {exc}"})
                    finally:
                        try:
                            conn.close()
                        except OSError:
                            pass
                    jobs.task_done()
                    served += 1
                else:
                    deferred.append(item)
                    jobs.task_done()
        finally:
            for item in deferred:
                jobs.put(item)

    #: Does this session declare the budgeted-read profile? Decided ONCE, from the
    #: session's own state, never by calling and catching TypeError: a TypeError
    #: raised *inside* pump would then be mistaken for a signature mismatch and
    #: swallow a real failure (or read the transport twice).
    budgeted = isinstance(getattr(sess, "io_turn_bytes", None), int)
    #: Does this session carry the S6 reply ledger? Same rule, decided the same
    #: way: a pre-S6 session object (a caller's own, an older table) is serviced
    #: without it, and one that has it decides internally whether it retries.
    resumable = callable(getattr(sess, "retry_pending_reply", None))

    def service_io() -> None:
        """One bounded I/O turn owned by the worker thread (A04-S3).

        The worker is the only writer of the screen model, so it is also the only
        place I/O may advance. Byte-bounded and never recursive: a turn cannot run
        another wait, so no request can be delayed by more than one budget.
        """
        try:
            if budgeted:
                sess.pump(max_bytes=IO_TURN_BYTES)
            else:
                sess.pump()          # a session that predates the budget profile
        except Exception:
            # A read error must not kill the daemon: the io block reports it.
            pass
        if resumable:
            # S6: this turn is the "later turn" a reply the transport refused gets
            # to make progress on, so a child blocked on its device answer does not
            # stay blocked because the one attempt happened to land on a full
            # buffer. The session decides whether it has budget; a session without
            # it is a no-op call. Separate from the read above so a failed read
            # cannot swallow the resume -- the two failures are unrelated.
            try:
                sess.retry_pending_reply()
            except Exception:
                pass

    def worker() -> None:
        while not shutdown.is_set():
            try:
                item = jobs.get(timeout=0.2)
            except queue.Empty:
                # Idle: keep the child alive and its queries answered even when no
                # client is asking anything (the X3 stall was exactly this path).
                service_io()
                continue
            if item is None:
                break
            # Busy: one bounded turn per iteration, so a continuously non-empty
            # request queue cannot starve the transport either.
            service_io()
            conn, req = item
            try:
                resp = _handle(sess, req, token,
                               on_poll=_drain_interleavable)
                if resp.get("_shutdown"):
                    shutdown.set()
                _reply(conn, resp)
            except Exception as exc:  # never let one request kill the daemon
                _reply(conn, {"ok": False,
                              "error": f"{type(exc).__name__}: {exc}"})
            finally:
                try:
                    conn.close()
                except OSError:
                    pass
                jobs.task_done()

    def reader(conn: socket.socket) -> None:
        """Unauthenticated work happens HERE, off the accept path."""
        try:
            req = _read_request(conn)
        except (TimeoutError, OSError, ValueError, UnicodeDecodeError) as exc:
            _reply(conn, {"ok": False, "error": f"bad request: {type(exc).__name__}"})
            try:
                conn.close()
            except OSError:
                pass
            return
        except Exception as exc:  # noqa: BLE001 - a reply is better than a silent drop
            _reply(conn, {"ok": False, "error": f"{type(exc).__name__}: {exc}"})
            try:
                conn.close()
            except OSError:
                pass
            return
        # Authenticate BEFORE the request can occupy the worker queue, so an
        # unauthenticated peer cannot make the owner wait behind it.
        if not _token_ok(req, token):
            _reply(conn, {"ok": False, "error": "unauthorized"})
            try:
                conn.close()
            except OSError:
                pass
            return
        with admission:
            if jobs.qsize() >= MAX_JOBS:
                full = True
            else:
                full = False
                jobs.put_nowait((conn, req))
        if full:
            # A05: refuse at ADMISSION, visibly. The alternative -- accepting it and
            # letting the caller believe its work is queued -- is how a "cap" turns
            # into an unbounded amount of work the daemon is carrying. The reply is
            # written OUTSIDE the lock and on the refusal deadline, so a peer that
            # does not read it cannot slow the next reader down.
            _reply(conn, {"ok": False, "reason": "too_many_jobs",
                          "error": f"too many requests already queued ({MAX_JOBS}); "
                                   "retry shortly"},
                   deadline=REFUSAL_DEADLINE)
            try:
                conn.close()
            except OSError:
                pass

    wt = threading.Thread(target=worker, name="session-worker", daemon=True)
    wt.start()
    readers: list[threading.Thread] = []
    try:
        srv.settimeout(0.2)
        while not shutdown.is_set() and not stop.is_set():
            try:
                conn, _ = srv.accept()
            except (TimeoutError, OSError):
                readers = [t for t in readers if t.is_alive()]
                continue
            # A05: prune first, then decide -- the cap counts LIVE readers, and the
            # old code only ever filtered this list after a thread had already been
            # created. Over the cap the connection is refused here, before it costs
            # a thread, and the caller is told why instead of being left to time out.
            readers = [t for t in readers if t.is_alive()]
            if len(readers) >= MAX_READERS:
                _reply(conn, {"ok": False, "reason": "too_many_readers",
                              "error": f"too many connections in flight ({MAX_READERS}); "
                                       "retry shortly"},
                       deadline=REFUSAL_DEADLINE)
                try:
                    conn.close()
                except OSError:
                    pass
                continue
            t = threading.Thread(target=reader, args=(conn,),
                                 name="conn-reader", daemon=True)
            t.start()
            readers.append(t)
    finally:
        shutdown.set()
        jobs.put(None)
        wt.join(timeout=5.0)


def _run_daemon(
    sid: str,
    cmd,
    cols: int,
    rows: int,
    token: str,
    cwd: str | None = None,
    child_env: dict[str, str] | None = None,
    detect_child_exit: bool = False,
) -> None:
    """Serve one PtySession on a localhost socket until told to close or child dies."""
    _validate_size(cols, rows)
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((HOST, 0))
    srv.listen(8)
    port = srv.getsockname()[1]

    if cwd:
        os.chdir(cwd)
    if child_env:
        os.environ.update(child_env)

    sess = PtySession(cols=cols, rows=rows)
    # A04-S3: this session's own waits read through the same byte budget as the
    # worker's service turns, so a long wait cannot drain an unbounded backlog.
    sess.io_turn_bytes = IO_TURN_BYTES
    # S6: and its device replies get a bounded retry budget, spent across the
    # daemon's own I/O turns. Both are set before start(), which is what resets the
    # per-generation counters they feed.
    sess.reply_retry_bytes = REPLY_RETRY_BYTES
    # OPT-IN, and off unless `start --detect-child-exit` said so. The core's
    # default is False and its waits only gain a liveness predicate when this
    # attribute is set, so a session started the ordinary way sits out its
    # ceiling exactly as it always has -- a wait that used to return
    # TIMEOUT/false still does. Set on the session rather than per wait call
    # because the flag is a property of how this session was started, and
    # because the core already resolved the same question in exactly this shape.
    sess.detect_child_exit = detect_child_exit
    sess.start(cmd)
    _write_reg(sid, {"sid": sid, "port": port, "pid": os.getpid(),
                     # The pid alone cannot identify a process: it is unique
                     # only while the process lives, so a recycled pid both
                     # fakes a live daemon and hides a dead one. The creation
                     # time is the standard companion to the pid, and
                     # close requires the two to agree before it believes
                     # either. Written before the token-bearing file exists,
                     # so an entry without it is a legacy entry (below).
                     "pid_born": _proc_identity(os.getpid()),
                     "cmd": cmd, "cols": cols, "rows": rows,
                     "cwd": cwd or os.getcwd(),
                     "env_keys": sorted((child_env or {}).keys()),
                     "detect_child_exit": bool(detect_child_exit),
                     "token": token, "started": time.time()})
    try:
        _serve_forever(srv, sess, token, threading.Event())
    finally:
        sess.close()
        srv.close()
        try:
            _reg_path(sid).unlink()
        except OSError:
            pass


# --- one-shot script mode: run steps against a fresh program ----------------

def _run_steps(cmd, steps, cols: int, rows: int,
               detect_child_exit: bool = False) -> int:
    """Execute a JSON step list against a freshly spawned program; print snapshots."""
    _validate_size(cols, rows)
    def emit(label, snap, extra=""):
        print(f"===== {label}{(' ' + extra) if extra else ''} =====")
        print(snap.to_text())
        print()

    with PtySession(cols=cols, rows=rows) as sess:
        # Same opt-in, same default, and the same reason: `run` is a shipped
        # verb with the same five waits, so leaving the flag off it alone would
        # make it the one place a caller cannot ask. Its output is printed
        # rather than JSON-encoded, so the EXITED singleton renders as the
        # readable `reason=EXITED` / `matched=EXITED` rather than needing the
        # coercion the daemon's wire format requires.
        sess.detect_child_exit = detect_child_exit
        sess.start(cmd)
        for i, step in enumerate(steps):
            act = step.get("action")
            if act == "send_text":
                sess.send_text(step.get("text", ""))
            elif act == "send_line":
                sess.send_line(step.get("text", ""))
            elif act == "send_keys":
                sess.send_keys(list(step.get("keys", [])))
            elif act == "wait_ready":
                reason, snap = sess.wait_ready(
                    marker=step.get("marker"),
                    max_wait_ms=int(step.get("max_wait_ms", 10000)))
                emit(f"step{i}:wait_ready", snap, f"reason={reason} alive={sess.is_alive()}")
            elif act in ("wait_regex", "wait_for"):
                matched, snap = sess.wait_for(
                    step["pattern"], timeout_ms=int(step.get("timeout_ms", 10000)))
                emit(f"step{i}:wait_regex", snap, f"matched={matched} alive={sess.is_alive()}")
            elif act == "wait_any":
                index, snap = sess.wait_any(
                    list(step.get("patterns", [])),
                    timeout_ms=int(step.get("timeout_ms", 10000)))
                emit(f"step{i}:wait_any", snap, f"index={index} alive={sess.is_alive()}")
            elif act == "wait_change":
                changed, snap = sess.wait_change(
                    baseline_hash=step.get("baseline_hash"),
                    timeout_ms=int(step.get("timeout_ms", 10000)))
                emit(f"step{i}:wait_change", snap, f"changed={changed} alive={sess.is_alive()}")
            elif act == "wait_visual_change":
                changed, snap = sess.wait_visual_change(
                    baseline_hash=step.get("baseline_hash"),
                    timeout_ms=int(step.get("timeout_ms", 10000)))
                emit(
                    f"step{i}:wait_visual_change",
                    snap,
                    f"changed={changed} alive={sess.is_alive()}",
                )
            elif act == "snapshot":
                sess.pump()
                emit(f"step{i}:snapshot", sess.snapshot(), f"alive={sess.is_alive()}")
            else:
                print(f"error: unknown step action '{act}' at index {i}", file=sys.stderr)
                return 2
    return 0


# --- command handlers -------------------------------------------------------

def _print_snap(resp: dict, as_json: bool) -> None:
    if as_json:
        print(resp.get("json", "{}"))
    else:
        print(resp.get("text", ""))


def cmd_start(args) -> int:
    _validate_size(args.cols, args.rows)
    sid = args.id or f"s{os.getpid()}_{int(time.time() * 1000) % 100000}"
    _validate_sid(sid)
    if _reg_path(sid).exists():
        raise SystemExit(f"error: session '{sid}' already exists")
    _ensure_reg_dir()
    active_count = _active_session_count()
    max_sessions = _max_sessions()
    if active_count >= max_sessions:
        raise SystemExit(
            f"error: session limit reached ({active_count}/{max_sessions}); "
            "close an existing session or raise SMARTCLI_MAX_SESSIONS")
    cwd = _resolve_cwd(args.cwd)
    child_env = _parse_env_items(list(args.env or []))
    # Mint a per-session capability token: only holders of this token (the
    # creator, who can read the per-user reg file where it is persisted) may
    # drive the loopback daemon. Passed to the daemon via an ENV VAR, NOT argv —
    # argv is world-visible in `ps`/Task Manager, so a token on the command line
    # would leak to any local user. The daemon writes it into the (0600) reg file
    # so client subcommands can auto-load it.
    token = secrets.token_hex(16)
    # Re-exec this module as a detached daemon process.
    daemon = [sys.executable, os.path.abspath(__file__), "_daemon",
              "--id", sid, "--cmd", args.cmd,
              "--cols", str(args.cols), "--rows", str(args.rows)]
    if args.detect_child_exit:
        # On argv, like --cwd: it is configuration, not a capability, and the
        # capability token deliberately is not (that stays in the env var, for
        # the reason spelled out above).
        daemon += ["--detect-child-exit"]
    if cwd:
        daemon += ["--cwd", cwd]
    daemon_env = {
        **os.environ,
        "SMARTCLI_TUI_TOKEN": token,
        "SMARTCLI_TUI_CHILD_ENV": json.dumps(child_env),
    }
    popen_kwargs = dict(close_fds=True, stdin=subprocess.DEVNULL,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                        env=daemon_env)
    if os.name == "nt":
        # CREATE_NO_WINDOW (0x08000000) | CREATE_NEW_PROCESS_GROUP.
        # We use CREATE_NO_WINDOW rather than the old DETACHED_PROCESS (0x08):
        # DETACHED_PROCESS only means "don't inherit the parent console" — it does
        # NOT stop a console window from being created, so when winpty/ConPTY
        # allocates its pseudo-console to spawn the target program, a conhost
        # window can flash up and STEAL FOCUS from whatever the user is doing.
        # CREATE_NO_WINDOW explicitly runs the console child with no window, which
        # is the correct "silent, never grab focus" disposition and still gives a
        # fully detached process (its own group, no inherited console, DEVNULL io).
        popen_kwargs["creationflags"] = (
            subprocess.CREATE_NEW_PROCESS_GROUP | 0x08000000  # CREATE_NO_WINDOW
        )
    else:
        # Detach from the launching shell's session so a SIGHUP on shell exit
        # (or Ctrl-C to the process group) does not kill the daemon — this is
        # what makes "state survives across separate shell calls" hold on POSIX.
        popen_kwargs["start_new_session"] = True
    subprocess.Popen(daemon, **popen_kwargs)
    # Wait for the daemon to register + bind.
    deadline = time.time() + 10.0
    while time.time() < deadline:
        if _reg_path(sid).exists():
            break
        time.sleep(0.05)
    else:
        raise SystemExit("error: session daemon did not start in time")
    if args.json:
        print(json.dumps({"ok": True, "sid": sid}))
    else:
        print(sid)
    return 0


def cmd_snapshot(args) -> int:
    resp = _call(args.id, {"action": "snapshot"})
    print(
        f"# hash={resp.get('hash')} visual_hash={resp.get('visual_hash')} "
        f"alive={resp.get('alive')} alt_screen={resp.get('alt_screen')}",
        file=sys.stderr,
    )
    _print_snap(resp, args.json)
    return 0


def _resolve_send_text(args) -> str:
    """Text for send-text/send-line: from stdin if --stdin, else the argument.

    stdin is the path-conversion-safe channel: Git Bash / MSYS rewrites a leading
    '/' in a native argv (so '/model' arrives as 'D:/Software/Git/model'), but it
    never touches piped stdin. A trailing newline from the pipe is stripped.
    """
    if getattr(args, "stdin", False):
        return sys.stdin.read().rstrip("\r\n")
    if args.text is None:
        raise SystemExit("error: give TEXT, or pass --stdin to read it from a pipe "
                         "(use --stdin for slash-commands like /model on Git Bash)")
    return args.text


def cmd_send_text(args) -> int:
    _call(args.id, {"action": "send_text", "text": _resolve_send_text(args)})
    return 0


def cmd_send_line(args) -> int:
    _call(args.id, {"action": "send_line", "text": _resolve_send_text(args)})
    return 0


def cmd_keys(args) -> int:
    _call(args.id, {"action": "send_keys", "keys": args.keys})
    return 0


def cmd_wait(args) -> int:
    resp = _call(args.id, {"action": "wait_ready", "marker": args.marker,
                           "max_wait_ms": args.timeout_ms},
                 timeout=args.timeout_ms / 1000.0 + 15.0)
    # Outcome on stderr, screen on stdout: the convention every wait verb here
    # already follows, and the only place `exited` is visible from the CLI --
    # `--json` prints the Snapshot payload, not the reply envelope, so a field
    # that lives only in the envelope would be unreachable from this surface.
    print(f"# reason={resp.get('reason')} exited={resp.get('exited')} "
          f"alive={resp.get('alive')}", file=sys.stderr)
    _print_snap(resp, args.json)
    return 0


def cmd_wait_regex(args) -> int:
    resp = _call(args.id, {"action": "wait_regex", "pattern": args.pattern,
                           "timeout_ms": args.timeout_ms},
                 timeout=args.timeout_ms / 1000.0 + 15.0)
    print(f"# matched={resp.get('matched')} exited={resp.get('exited')} "
          f"alive={resp.get('alive')}", file=sys.stderr)
    _print_snap(resp, args.json)
    return 0


def cmd_wait_change(args) -> int:
    req = {"action": "wait_change", "timeout_ms": args.timeout_ms}
    if args.baseline_hash is not None:
        req["baseline_hash"] = args.baseline_hash
    resp = _call(args.id, req, timeout=args.timeout_ms / 1000.0 + 15.0)
    print(f"# changed={resp.get('changed')} exited={resp.get('exited')} "
          f"hash={resp.get('hash')} alive={resp.get('alive')}", file=sys.stderr)
    _print_snap(resp, args.json)
    return 0


def cmd_wait_visual_change(args) -> int:
    req = {"action": "wait_visual_change", "timeout_ms": args.timeout_ms}
    if args.baseline_hash is not None:
        req["baseline_hash"] = args.baseline_hash
    resp = _call(args.id, req, timeout=args.timeout_ms / 1000.0 + 15.0)
    print(
        f"# changed={resp.get('changed')} exited={resp.get('exited')} "
        f"visual_hash={resp.get('visual_hash')} alive={resp.get('alive')}",
        file=sys.stderr,
    )
    _print_snap(resp, args.json)
    return 0


def cmd_wait_any(args) -> int:
    # Patterns via repeated --pattern, or one-per-line on stdin (--stdin) so MSYS
    # Git-bash path-conversion can't mangle a regex like "/foo" into "D:/.../foo".
    patterns = list(args.pattern or [])
    if args.stdin:
        patterns += [ln for ln in sys.stdin.read().splitlines() if ln]
    if not patterns:
        print("error: wait-any needs at least one --pattern (or --stdin)",
              file=sys.stderr)
        return 2
    resp = _call(args.id, {"action": "wait_any", "patterns": patterns,
                           "timeout_ms": args.timeout_ms},
                 timeout=args.timeout_ms / 1000.0 + 15.0)
    idx = resp.get("index", -1)
    hit = patterns[idx] if idx is not None and idx >= 0 else None
    print(f"# index={idx} matched={resp.get('matched')} pattern={hit!r} "
          f"exited={resp.get('exited')} alive={resp.get('alive')}",
          file=sys.stderr)
    _print_snap(resp, args.json)
    return 0


def cmd_alive(args) -> int:
    resp = _call(args.id, {"action": "alive"})
    print("alive" if resp.get("alive") else "dead")
    return 0 if resp.get("alive") else 1


def cmd_resize(args) -> int:
    # The daemon owns validation: it converts _validate_size's SystemExit into
    # an error REPLY so an out-of-range size cannot tear down a live session.
    # _call then turns that reply back into SystemExit for the CLI caller, which
    # is the shared convention for every verb here — so a rejected size exits
    # non-zero with the daemon's message and never reaches the lines below.
    resp = _call(args.id, {"action": "resize", "cols": args.cols, "rows": args.rows})
    if args.json:
        print(json.dumps({"ok": True, "sid": args.id,
                          "cols": args.cols, "rows": args.rows}))
    else:
        print(f"resized {args.id} to {args.cols}x{args.rows}")
    return 0


def _parse_proc_stat_starttime(text: str) -> int | None:
    """Pull field 22 (``starttime``) out of a ``/proc/<pid>/stat`` body.

    Pure on purpose: the field layout is the only part that is easy to get
    wrong, so it is exercised against fixed samples in the deterministic gate
    rather than needing a live process. Field 2 is the executable name in
    parentheses and may itself contain spaces and parentheses, so the name is
    skipped by scanning past the LAST ')' instead of splitting the whole line;
    what follows starts at field 3, which puts ``starttime`` at index 19.
    """
    cut = text.rfind(")")
    if cut < 0:
        return None
    fields = text[cut + 1:].split()
    if len(fields) < 20:  # 50 fields follow the name; 19 of them precede starttime
        return None
    try:
        return int(fields[19])
    except ValueError:
        return None


_WIN_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_WIN_STILL_ACTIVE = 259
#: Toolhelp snapshot flag: the process list. (The alternative, EnumProcesses,
#: is not exported by kernel32 on every host -- measured here, where it resolves
#: only from psapi.dll -- so the enumeration uses the API kernel32 does have.)
_WIN_TH32CS_SNAPPROCESS = 0x00000002
_WIN_INVALID_HANDLE_VALUE = -1
_WIN_PROC_API: dict[str, Any] | None = None


def _win_proc_api() -> dict[str, Any]:
    """Bind (once) the kernel32 entry points the pid probes below call.

    Same rule, same reason, and the same singleton as `_win_acl_api` above:
    `ctypes.windll.kernel32` is one process-wide object, so these probes and the
    DACL bindings are looking at the same function objects, and an undeclared
    entry point does not fail loudly. With no `restype`, ctypes returns a
    default `c_int`, which truncates a 64-bit HANDLE to 32 bits and yields a
    plausible wrong answer -- the wrong answer being the process identity the
    security verdict is made of. `argtypes` matters just as much: without them
    a `DWORD` pid or a `BOOL` flag can be passed as anything at all.
    """
    global _WIN_PROC_API
    if _WIN_PROC_API is not None:
        return _WIN_PROC_API
    import ctypes

    dword = ctypes.c_ulong
    handle = ctypes.c_void_p
    filetime = ctypes.POINTER(ctypes.c_ulonglong)

    class ProcessEntry32W(ctypes.Structure):
        # PROCESSENTRY32W. The trailing name buffer is MAX_PATH WCHARs; nothing
        # here reads it, but the struct has to be the real size or the kernel
        # writes past the end of what was allocated for it.
        _fields_ = [("dwSize", dword), ("cntUsage", dword),
                    ("th32ProcessID", dword), ("th32DefaultHeapID", handle),
                    ("th32ModuleID", dword), ("cntThreads", dword),
                    ("th32ParentProcessID", dword), ("pcPriClassBase", ctypes.c_long),
                    ("dwFlags", dword), ("szExeFile", ctypes.c_wchar * 260)]

    kernel32 = ctypes.windll.kernel32
    kernel32.OpenProcess.argtypes = [dword, ctypes.c_int, dword]
    kernel32.OpenProcess.restype = handle
    kernel32.GetProcessTimes.argtypes = [handle, filetime, filetime, filetime,
                                         filetime]
    kernel32.GetProcessTimes.restype = ctypes.c_int
    kernel32.GetExitCodeProcess.argtypes = [handle, ctypes.POINTER(dword)]
    kernel32.GetExitCodeProcess.restype = ctypes.c_int
    kernel32.CreateToolhelp32Snapshot.argtypes = [dword, dword]
    kernel32.CreateToolhelp32Snapshot.restype = handle
    kernel32.Process32FirstW.argtypes = [handle, ctypes.POINTER(ProcessEntry32W)]
    kernel32.Process32FirstW.restype = ctypes.c_int
    kernel32.Process32NextW.argtypes = [handle, ctypes.POINTER(ProcessEntry32W)]
    kernel32.Process32NextW.restype = ctypes.c_int
    # CloseHandle, not LocalFree: a process handle is a kernel handle. Declared
    # here as well as in _win_acl_api so neither module's correctness depends on
    # having called the other first; the two declarations are identical.
    kernel32.CloseHandle.argtypes = [handle]
    kernel32.CloseHandle.restype = ctypes.c_int
    _WIN_PROC_API = {"ctypes": ctypes, "dword": dword, "kernel32": kernel32,
                     "ProcessEntry32W": ProcessEntry32W}
    return _WIN_PROC_API


def _proc_identity(pid: int) -> str | None:
    """A creation-time identity for ``pid``, or None if the OS will not say.

    A pid names a *slot*, not a process: once the owner exits the slot is
    reusable, so "is this pid alive" answers a question about the slot. Pairing
    the pid with the time its process was created names the process instead,
    and that pairing stays meaningful after the pid is recycled. On Windows
    this comes from ``GetProcessTimes`` through the same
    ``PROCESS_QUERY_LIMITED_INFORMATION`` handle ``_pid_is_alive`` already
    opens -- same bindings, same kind of handle, so the liveness probe and the
    identity probe are answered by the kernel about the very same object rather
    than by two independent races.
    On Linux it is field 22 of ``/proc/<pid>/stat``, which counts CLOCK TICKS
    since boot and is therefore only tick-granular: two processes born inside
    the same tick return the same value, and the process-table search in
    ``_live_pid_with_identity`` can reach either of them first. Such a collision
    can only ever cost a false REFUSAL -- the search may name the colliding
    sibling instead of the recorded daemon, and ``close`` then keeps an entry it
    could have cleaned -- and never a false "gone", because the recorded
    daemon's own value is present for exactly as long as the daemon lives.
    macOS exposes no cheap creation time for another process at all, so it
    reports None, ``start`` records ``pid_born: null`` and every ``close`` on
    that platform takes the legacy pid-only test (see ``_daemon_liveness``).
    """
    if pid <= 0:
        return None
    if os.name == "nt":
        api = _win_proc_api()
        ctypes, kernel32 = api["ctypes"], api["kernel32"]
        handle = kernel32.OpenProcess(_WIN_PROCESS_QUERY_LIMITED_INFORMATION, 0, pid)
        if not handle:
            return None
        try:
            creation, exit_, kernel, user = (ctypes.c_ulonglong() for _ in range(4))
            if not kernel32.GetProcessTimes(handle, ctypes.byref(creation),
                                            ctypes.byref(exit_), ctypes.byref(kernel),
                                            ctypes.byref(user)):
                return None
            # FILETIME: 100ns ticks since 1601 — opaque, monotonic per machine,
            # and only ever compared against another value from this same host.
            return f"win:{creation.value}"
        finally:
            kernel32.CloseHandle(handle)
    if not os.path.isdir("/proc"):
        return None
    try:
        text = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    ticks = _parse_proc_stat_starttime(text)
    return None if ticks is None else f"proc:{ticks}"



def _pid_is_alive(pid: int) -> bool:
    """Is a process with this pid still running?

    Used before deleting a registry entry, because that file is the ONLY store of
    the session's capability token AND its daemon pid: deleting it while the
    daemon lives leaves a PTY child that cannot be reached by protocol and cannot
    be found for a manual kill, while `list` cheerfully reports zero sessions.
    """
    if pid <= 0:
        return False
    if os.name == "nt":
        # No signal 0 on Windows; ask the OS for a handle to the pid instead.
        api = _win_proc_api()
        ctypes, dword, kernel32 = api["ctypes"], api["dword"], api["kernel32"]
        handle = kernel32.OpenProcess(_WIN_PROCESS_QUERY_LIMITED_INFORMATION, 0, pid)
        if not handle:
            return False
        try:
            code = dword()
            if kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return code.value == _WIN_STILL_ACTIVE
            return True  # handle opened but status unreadable: assume alive
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists, owned by someone else
    return True


def _enumerable_pids() -> list[int] | None:
    """Every pid this platform lets us enumerate, or None if it cannot be done.

    None is a refusal, not an empty list, and the difference is the whole point:
    an enumeration that could not be completed must never be reported as "no
    process is alive", because the caller decides whether to delete the only
    record of a live child's pid from it.
    """
    if os.name == "nt":
        api = _win_proc_api()
        ctypes, kernel32 = api["ctypes"], api["kernel32"]
        entry = api["ProcessEntry32W"]()
        entry.dwSize = ctypes.sizeof(entry)
        snapshot = kernel32.CreateToolhelp32Snapshot(_WIN_TH32CS_SNAPPROCESS, 0)
        # INVALID_HANDLE_VALUE (-1) and NULL (0) are both "no snapshot"; the
        # handle is 64-bit, so it is compared as the int ctypes hands back.
        if not snapshot or snapshot == _WIN_INVALID_HANDLE_VALUE:
            return None
        try:
            if not kernel32.Process32FirstW(snapshot, ctypes.byref(entry)):
                # ERROR_NO_MORE_FILES would mean an empty process table, which
                # cannot happen while this process is running; anything else
                # means the walk did not start, and a walk that did not start
                # has told us nothing.
                return None
            pids = [int(entry.th32ProcessID)]
            while kernel32.Process32NextW(snapshot, ctypes.byref(entry)):
                pids.append(int(entry.th32ProcessID))
            return pids
        finally:
            kernel32.CloseHandle(snapshot)
    if os.path.isdir("/proc"):
        try:
            return [int(name) for name in os.listdir("/proc") if name.isdigit()]
        except OSError:
            return None
    return None


def _live_pid_with_identity(recorded: object) -> tuple[int | None, bool]:
    """A live pid created at ``recorded``, and whether the search was complete.

    The creation time names a process where a pid names a slot, so this asks the
    one question a dead pid cannot answer about itself: does anything at all
    still carry the identity this entry recorded? A complete search that finds
    nothing is positive evidence the recorded daemon is gone; an incomplete one
    is not evidence of anything and is reported as such by ``False``.

    Incomplete also covers a search that read NO identities at all. A host that
    will not report a creation time for a single process -- this one included,
    which the kernel always permits -- cannot distinguish "the daemon is gone"
    from "I was unable to look", and the unlink must not be decided on the
    second reading.
    """
    if not isinstance(recorded, str) or not recorded:
        return None, True
    pids = _enumerable_pids()
    if pids is None:
        return None, False
    readable = 0
    for candidate in pids:
        identity = _proc_identity(candidate)
        if identity is None:
            continue
        readable += 1
        if identity == recorded:
            return candidate, True
    return None, readable > 0


def _daemon_liveness(info: dict) -> tuple[bool, str, bool]:
    """Is the daemon named by this registry entry still running?

    Returns ``(alive, reason, legacy)``. The registry file is the ONLY store of
    the token and the pid, so the verdict has to be evidence, never a guess:
    the entry is cleanable only when the OS positively says the recorded daemon
    is gone. Everything short of that — a pid that answers, a pid whose
    creation time contradicts the recorded one, a creation time the OS refuses
    to hand over, an enumeration that could not be completed — is reported
    ALIVE, because the two failure directions are not symmetric: a false "still
    running" costs the caller one ``--force``, while a false "dead" orphans a
    live PTY child that nothing can reach.

    The identity is a GATE, not a diagnostic, and it is the creation time that
    does the gating, in both directions:

    * a live pid whose creation time does not match the recorded one has been
      recycled, so the recorded daemon is not the thing answering;
    * a DEAD pid is not accepted on its own when the entry records a creation
      time. A dead pid says the slot is free, and says nothing about the daemon;
      the creation time is the daemon's name, and if some process still carries
      it then the recorded daemon is running whatever pid the entry now holds.
      That second half is what a pid-only check cannot do, and it is why
      overwriting just ``pid`` in a live entry no longer deletes the file.

    What it is NOT: proof of ownership. Anything that can write the registry
    file can write a ``pid_born`` naming nothing that is alive, or omit it, and
    can simply delete the file outright — so this closes a consistency hole, not
    an authorization one. See SECURITY.md, which says so in the same words.
    Two limits belong to the platform rather than to the host, and both end in
    the same kind of answer. macOS cannot report a creation time for another
    process, so ``start`` records ``pid_born: null`` there and an entry that
    carries one cannot have been written on that host; it also cannot be
    checked there, so it is kept and refused until ``--force`` — permanently,
    not until the host recovers. Entries the program wrote itself take the
    legacy pid-only branch instead, and are still cleaned up when the pid is
    gone. The other is the granularity ``_proc_identity`` documents: Linux
    measures the value in clock ticks, so it can be shared with a process born
    in the same tick, which costs a refusal and never a wrong "gone".

    ``legacy`` marks the one case that cannot be decided by identity at all —
    an entry written by a tui.py older than the identity field. Those fall back
    to the pid-only test this function has always used and say so, rather than
    inventing an identity for a process that was never asked for one.
    """
    pid = int(info.get("pid") or 0)
    if pid <= 0:
        return False, f"the entry records no daemon pid (pid={pid})", False
    recorded = info.get("pid_born")
    if not _pid_is_alive(pid):
        if recorded:
            twin, complete = _live_pid_with_identity(recorded)
            if twin is not None:
                return True, (f"pid {pid} is gone, but pid {twin} is running with "
                              f"the creation time {recorded} this entry records, "
                              f"so the recorded daemon is alive under a pid this "
                              f"entry no longer holds: the pid field is stale or "
                              f"was altered, and the entry is kept"), False
            if not complete:
                return True, (f"pid {pid} is gone, but this host could not be "
                              f"asked whether any process still carries the "
                              f"recorded creation time {recorded}, so that could "
                              f"not be ruled out"), False
        # A pid that is gone, with nothing alive under the recorded creation
        # time (or none recorded): either the daemon exited, or the slot was
        # recycled and the replacement has already exited too.
        return False, f"pid {pid} is not running", False
    if not recorded:
        return True, (f"pid {pid} is running, but this entry predates the "
                      f"creation-time field, so the check is the weaker "
                      f"pid-only one"), True
    actual = _proc_identity(pid)
    if actual is None:
        # Fail closed: the OS would not tell us who owns this pid.
        return True, (f"pid {pid} is running but its creation time is "
                      f"unreadable, so its identity could not be confirmed"), False
    if actual != recorded:
        # The pid slot has been reused by some other process. The recorded
        # daemon is then not the thing answering, and whether it exited
        # cleanly is unknowable from here — so refuse, and let --force decide.
        return True, (f"pid {pid} is running but was created at {actual}, not "
                      f"the recorded {recorded}: the pid was recycled, so what "
                      f"the recorded daemon did is unknown"), False
    return True, (f"pid {pid} is running and its creation time {actual} "
                  f"matches the recorded one"), False


def cmd_close(args) -> int:
    try:
        _call(args.id, {"action": "close"})
    except SystemExit:
        # The documented stale-entry cleanup path must actually remove the file —
        # but ONLY once the daemon is known to be gone. A failed request is not
        # proof of death: a timeout can mean the daemon is merely busy (its accept
        # loop is serial), and unlinking then destroys the token and the pid that
        # are the only ways left to reach or kill it, while `list` reports zero.
        info = {}
        try:
            info = _read_reg(args.id)
        except SystemExit:
            pass  # entry already gone; nothing to clean up
        alive, why, legacy = _daemon_liveness(info)
        if alive and not getattr(args, "force", False):
            # A "kill pid N" is only advice the reader can follow when the OS
            # still answers for N. The entry's own pid is precisely the field a
            # stale or altered entry gets wrong, and when the recorded creation
            # time is what kept the entry, the reason above already names the
            # live pid instead.
            kill_hint = ""
            recorded_pid = int(info.get("pid") or 0)
            if recorded_pid > 0 and _pid_is_alive(recorded_pid):
                kill_hint = f" or kill pid {recorded_pid} and re-run"
            print(f"error: session '{args.id}' did not answer, but its daemon "
                  f"is still running — {why} — so the registry entry was KEPT: "
                  f"deleting it would orphan the child and lose the token. "
                  f"Retry{kill_hint}, or pass --force.",
                  file=sys.stderr)
            return 1
        if legacy:
            print(f"warning: session '{args.id}' carries no recorded daemon "
                  f"creation time, so its liveness check was the weaker "
                  f"pid-only one; a recycled pid would read as this daemon. "
                  f"Start a new session to get an identity-checked entry.",
                  file=sys.stderr)
        try:
            _reg_path(args.id).unlink()
        except OSError:
            pass
    if args.json:
        print(json.dumps({"ok": True, "sid": args.id, "closed": True}))
    else:
        print(f"closed {args.id}")
    return 0


def cmd_list(args) -> int:
    sessions = []
    for p in sorted(REG_DIR.glob("*.json")) if REG_DIR.exists() else []:
        try:
            info = json.loads(p.read_text(encoding="utf-8"))
            sessions.append({
                "sid": info["sid"],
                "port": int(info["port"]),
                "pid": int(info["pid"]),
                "cmd": info["cmd"],
                "cols": int(info.get("cols", 0)),
                "rows": int(info.get("rows", 0)),
                "cwd": info.get("cwd"),
                "started": info.get("started"),
            })
        except Exception:
            continue
    if args.json:
        print(json.dumps({"ok": True, "sessions": sessions}))
    else:
        for info in sessions:
            print(
                f"{info['sid']}\tport={info['port']}\tpid={info['pid']}\t"
                f"cmd={info['cmd']}\tcwd={info['cwd']}"
            )
    return 0


def cmd_run(args) -> int:
    steps = json.loads(Path(args.steps).read_text(encoding="utf-8"))
    if not isinstance(steps, list):
        raise SystemExit("error: steps file must contain a JSON list")
    cwd = _resolve_cwd(args.cwd)
    child_env = _parse_env_items(list(args.env or []))
    old_cwd = os.getcwd()
    old_env = {key: os.environ.get(key) for key in child_env}
    try:
        if cwd:
            os.chdir(cwd)
        os.environ.update(child_env)
        return _run_steps(args.cmd, steps, args.cols, args.rows,
                          args.detect_child_exit)
    finally:
        os.chdir(old_cwd)
        for key, previous in old_env.items():
            if previous is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = previous


def _resolve_cwd(value: str | None) -> str | None:
    if not value:
        return None
    cwd = str(Path(value).expanduser().resolve())
    if not Path(cwd).is_dir():
        raise SystemExit(f"error: --cwd is not a directory: {cwd}")
    return cwd


def cmd__daemon(args) -> int:
    # The token arrives via env (SMARTCLI_TUI_TOKEN), not argv, so it never shows
    # up in `ps`/Task Manager. Fall back to --token only for backward compat.
    token = os.environ.get("SMARTCLI_TUI_TOKEN") or getattr(args, "token", None)
    if not token:
        raise SystemExit("error: daemon started without a token")
    try:
        child_env = json.loads(os.environ.pop("SMARTCLI_TUI_CHILD_ENV", "{}"))
    except json.JSONDecodeError as exc:
        raise SystemExit("error: invalid internal child environment payload") from exc
    # The controlled process must not inherit the capability used to control its
    # daemon. Remove it before PtySession spawns the target.
    os.environ.pop("SMARTCLI_TUI_TOKEN", None)
    _run_daemon(args.id, args.cmd, args.cols, args.rows, token, args.cwd,
                child_env, args.detect_child_exit)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="tui.py",
        description="Drive interactive TUI programs via smartcli_core.")
    p.add_argument("--install-deps", action="store_true",
                   help="pip-install any missing runtime deps (pyte/pywinpty) "
                        "now, then continue; otherwise missing deps are only "
                        "reported. Same as SMARTCLI_AUTO_INSTALL=1.")
    sub = p.add_subparsers(
        dest="command", required=True,
        # Hand-maintained: argparse would otherwise list `_daemon` too, which is
        # internal. ADD NEW VERBS HERE as well as registering the subparser —
        # `resize` was invisible in --help for exactly that reason.
        metavar="{start,snapshot,send-text,send-line,keys,wait,wait-regex,"
                "wait-change,wait-visual-change,wait-any,alive,resize,close,"
                "list,run,doctor}")

    sp = sub.add_parser("start", help="spawn a program in a detached persistent session")
    sp.add_argument("--cmd", required=True, help="command line to spawn, e.g. \"python\"")
    sp.add_argument("--id", help="session id (default: auto-generated)")
    sp.add_argument("--cols", type=int, default=100)
    sp.add_argument("--rows", type=int, default=30)
    sp.add_argument("--cwd", help="working directory for the target program")
    sp.add_argument("--env", action="append", default=[], metavar="KEY=VALUE",
                    help="environment variable for the target (repeatable)")
    sp.add_argument("--detect-child-exit", dest="detect_child_exit",
                    action="store_true",
                    help="make this session's waits END when the child dies, "
                         "instead of sitting out the remaining timeout. Off by "
                         "default, and off means unchanged: a wait that used to "
                         "return TIMEOUT/false still does. When on, a wait that "
                         "ended on a dead child reports exited=true (wait: "
                         "reason=EXITED), so 'the program died' is "
                         "distinguishable from 'the program was quiet'")
    sp.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    sp.set_defaults(func=cmd_start)

    sp = sub.add_parser("snapshot", help="print a semantic snapshot of the session")
    sp.add_argument("--id", required=True)
    sp.add_argument("--json", action="store_true", help="emit Snapshot.to_json() instead of to_text()")
    sp.set_defaults(func=cmd_snapshot)

    sp = sub.add_parser("send-text", help="type literal text (no Enter). "
                        "Use --stdin for text with a leading '/' (see note below).")
    sp.add_argument("--id", required=True)
    sp.add_argument("text", nargs="?",
                    help="text to type; omit and pass --stdin to read from stdin")
    sp.add_argument("--stdin", action="store_true",
                    help="read the text from stdin instead of the argument. "
                         "REQUIRED for slash-commands like /model on Git Bash / "
                         "MSYS, where a leading '/' in an argv is rewritten to a "
                         "Windows path (e.g. '/model' -> 'D:/Software/Git/model') "
                         "before Python sees it. Piping via stdin bypasses that.")
    sp.set_defaults(func=cmd_send_text)

    sp = sub.add_parser("send-line", help="type text followed by Enter. "
                        "Use --stdin for text with a leading '/' (see note below).")
    sp.add_argument("--id", required=True)
    sp.add_argument("text", nargs="?",
                    help="text to type; omit and pass --stdin to read from stdin")
    sp.add_argument("--stdin", action="store_true",
                    help="read the text from stdin instead of the argument. "
                         "REQUIRED for slash-commands like /model on Git Bash / "
                         "MSYS, where a leading '/' in an argv is rewritten to a "
                         "Windows path before Python sees it. Piping bypasses that.")
    sp.set_defaults(func=cmd_send_line)

    sp = sub.add_parser("keys", help="send key tokens, e.g. Down Down Enter, C-c, M-x")
    sp.add_argument("--id", required=True)
    sp.add_argument("keys", nargs="+")
    sp.set_defaults(func=cmd_keys)

    sp = sub.add_parser("wait", help="wait for a regex marker OR screen stability, then snapshot")
    sp.add_argument("--id", required=True)
    sp.add_argument("--marker", help="regex to wait for (optional; omit to wait for stability)")
    sp.add_argument("--timeout-ms", dest="timeout_ms", type=int, default=10000)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_wait)

    sp = sub.add_parser("wait-regex", help="wait strictly for a regex to appear, then snapshot")
    sp.add_argument("--id", required=True)
    sp.add_argument("pattern")
    sp.add_argument("--timeout-ms", dest="timeout_ms", type=int, default=10000)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_wait_regex)

    sp = sub.add_parser("wait-change",
                        help="wait until the screen content changes (from a baseline "
                             "hash, or from now), then snapshot — the precise "
                             "'did my action land?' primitive")
    sp.add_argument("--id", required=True)
    sp.add_argument("--baseline-hash", dest="baseline_hash", type=int, default=None,
                    help="hash to wait to change away from (default: the screen now). "
                         "Pass the 'hash' from a prior snapshot/wait-change.")
    sp.add_argument("--timeout-ms", dest="timeout_ms", type=int, default=10000)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_wait_change)

    sp = sub.add_parser(
        "wait-visual-change",
        help="wait for text, styling, selection or cursor state to change",
    )
    sp.add_argument("--id", required=True)
    sp.add_argument("--baseline-hash", dest="baseline_hash", type=int, default=None,
                    help="visual_hash from a prior snapshot (default: current state)")
    sp.add_argument("--timeout-ms", dest="timeout_ms", type=int, default=10000)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_wait_visual_change)

    sp = sub.add_parser("wait-any",
                        help="wait for ANY of several regexes (pexpect expect([...]) "
                             "style); reports WHICH matched first, then snapshot")
    sp.add_argument("--id", required=True)
    sp.add_argument("--pattern", action="append",
                    help="a regex to race (repeat for several; earliest in the "
                         "list wins a same-poll tie)")
    sp.add_argument("--stdin", action="store_true",
                    help="also read patterns one-per-line from stdin (MSYS "
                         "path-conversion-safe for regexes containing slashes)")
    sp.add_argument("--timeout-ms", dest="timeout_ms", type=int, default=10000)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_wait_any)

    sp = sub.add_parser("alive", help="check whether the child process is still running")
    sp.add_argument("--id", required=True)
    sp.set_defaults(func=cmd_alive)

    sp = sub.add_parser("resize", help="change the terminal size of a live session")
    sp.add_argument("--id", required=True)
    sp.add_argument("--cols", required=True, type=int)
    sp.add_argument("--rows", required=True, type=int)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_resize)

    sp = sub.add_parser("close", help="terminate the session and its daemon")
    sp.add_argument("--id", required=True)
    sp.add_argument("--json", action="store_true")
    sp.add_argument("--force", action="store_true",
                    help="delete the registry entry even though the daemon may "
                         "still be running — it deletes whenever the recorded "
                         "daemon cannot be shown to be gone: a live daemon, a "
                         "pid slot that has been recycled, an identity the OS "
                         "will not report, a host that could not be enumerated "
                         "for a process carrying the recorded creation time, or "
                         "a legacy entry with no creation time recorded. Nor "
                         "is the token unique on Linux: it counts clock ticks "
                         "since boot, so a process born in the same tick "
                         "carries the same value and can be taken for the "
                         "daemon. The creation time is a consistency check on "
                         "the entry, not proof of who wrote it: anything able "
                         "to write the registry file can write a "
                         "self-consistent pair, or "
                         "delete the file outright. --force loses the token and "
                         "the pid, so the child becomes unreachable; kill the "
                         "pid yourself first")
    sp.set_defaults(func=cmd_close)

    sp = sub.add_parser("list", help="list active sessions")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_list)

    sp = sub.add_parser("run", help="one-shot: run a JSON step list against a fresh program")
    sp.add_argument("--cmd", required=True)
    sp.add_argument("--steps", required=True, help="path to a JSON file: a list of step objects")
    sp.add_argument("--cols", type=int, default=100)
    sp.add_argument("--rows", type=int, default=30)
    sp.add_argument("--cwd", help="working directory for the target program")
    sp.add_argument("--env", action="append", default=[], metavar="KEY=VALUE",
                    help="environment variable for the target (repeatable)")
    sp.add_argument("--detect-child-exit", dest="detect_child_exit",
                    action="store_true",
                    help="same opt-in as `start`: a step that waits ends when "
                         "the child dies rather than burning its timeout "
                         "(printed as reason=EXITED / matched=EXITED)")
    sp.set_defaults(func=cmd_run)

    sp = sub.add_parser("doctor", help="report smartcli_core location + dependency status")
    sp.set_defaults(func=cmd_doctor)

    # No help= on purpose: parsers without help are omitted from --help, which
    # keeps this internal re-exec verb out of the public command list.
    sp = sub.add_parser("_daemon")
    sp.add_argument("--id", required=True)
    sp.add_argument("--cmd", required=True)
    # token now arrives via the SMARTCLI_TUI_TOKEN env var (not argv, which leaks
    # in ps). Kept optional for backward compat only.
    sp.add_argument("--token", default=None)
    sp.add_argument("--cols", type=int, default=100)
    sp.add_argument("--rows", type=int, default=30)
    sp.add_argument("--cwd", default=None)
    # Internal re-exec argument, set only by `cmd_start` when the caller passed
    # --detect-child-exit. SUPPRESS because this parser is already out of --help
    # and the public spelling of the option belongs to `start`.
    sp.add_argument("--detect-child-exit", dest="detect_child_exit",
                    action="store_true", help=argparse.SUPPRESS)
    sp.set_defaults(func=cmd__daemon)

    return p


def cmd_doctor(args) -> int:
    """Print where smartcli_core resolved from and whether deps are present."""
    try:
        where = smartcli_bootstrap.locate_core()
    except ImportError as exc:
        print(f"smartcli_core: NOT FOUND\n  {exc}")
        return 1
    print(f"smartcli_core: {where or 'installed (pip)'}")
    missing = smartcli_bootstrap._missing_deps()
    if missing:
        print(f"missing deps: {', '.join(missing)}")
        print(f"  install: {smartcli_bootstrap._install_cmd(missing)}")
        return 1
    print("dependencies: all present")
    return 0


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    # Relocating the registry strands sessions the previous version started:
    # they are unreachable by `close` and `list`, and their pids -- the only
    # handle left on their child processes -- went with them. Name them once, on
    # stderr, and kill nothing. `_daemon` is excluded because it is our own
    # detached child, whose stderr nobody reads.
    if getattr(args, "command", None) != "_daemon":
        stranded = _stranded_session_warning()
        if stranded:
            print(stranded, file=sys.stderr)
    # Offer to install missing runtime deps before doing work that needs them.
    # 'doctor' reports on its own; '_daemon' inherits the parent's environment.
    if getattr(args, "command", None) not in ("doctor", "_daemon"):
        smartcli_bootstrap.ensure_deps(
            auto_install=True if getattr(args, "install_deps", False) else None)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
