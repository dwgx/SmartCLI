# RUN/T03/last.md — no false success on a short PTY write

Worker: session `01a0a700`. Repo `D:\Project\SmartCLI` at HEAD `701e61f` (uncommitted working tree).

## Status: IMPLEMENTED, injected-OS and real-PTY evidence

`PosixPtyBackend.write` called `os.write(self._fd, data)` once and discarded the return value, on a
non-blocking fd. The kit's oracle measured the consequence before this round: a 14-byte payload was
reported as sent after **2 bytes** with **1** call. After this round the same oracle reports
`received_bytes 14/14`, sha256 match, `calls 5`, `waits 1`.

**Escalated to E4 on 2026-09-16** (Owner-supplied Docker, `python:3.13-slim`, real `pty.fork()`):
`T03/posix/test_posix_write.py` writes **one call of 262 144 bytes** through the production method to
a raw-mode child that reports its own length + sha256:

| component | write_seconds | writability waits | child report | verdict |
|---|---|---|---|---|
| candidate (this round) | 0.003 | **44** | 262 144 bytes, sha256 match | **PASS** |
| old single-`os.write` (mutated copy) | 0.000 | 0 | **no report at all** (child hung on the short write) | **FAIL** |

The kernel forced 44 waits, so this is the short-write path exercised on a real transport, not a
stand-in. Artifact: `T03/posix-real-pty.json`; child referee: `T03/posix/child_receiver.py`.

## Exact scope (as delivered)

| file | change | sha256 (first 16) |
|---|---|---|
| `smartcli_core/pty_backend.py` | `IncompleteWrite(OSError)` + bounded `write` loop (`write_timeout = 5.0`, memoryview offset, EAGAIN wait, EINTR retry, zero-progress guard) | `93bb587ddfd69f3d` |
| `skills/drive-tui/_vendor/smartcli_core/pty_backend.py` | byte-identical twin (single-file copy) | `93bb587ddfd69f3d` |
| `tests/test_partial_write_regression.py` | new: 12 tests | `d7e9d14772d5afb6` |
| `tests/run_all.py` | registration line | `6403122433939712` |

Contract kept: `write(data: bytes) -> None` still returns normally only when every byte was accepted;
otherwise it raises. `IncompleteWrite` subclasses `OSError`, so existing `except OSError` handlers keep
working, and it carries `written_bytes`, `total_bytes`, `reason`. It is deliberately **not** exported
from `smartcli_core/__init__.py`: that would be a public-API change, which needs its own proposal.
`written_bytes` stays `None` when the transport cannot report progress; it is never padded with `0`.

The daemon path needs no change to stop lying: `tui._handle` already turns a raised exception into
`{"ok": false, "error": …}`, so a partial write becomes a visible failure rather than a success.

## Commands and results (first run, no rerun)

| command | exit | result |
|---|---|---|
| `python -B tests/test_partial_write_regression.py` | 0 | Ran 12 tests, OK |
| `conformance.py --case input --consent-execute-reviewed-code` | 0 | 14/14 bytes, sha256 `f0a3febf…` both sides, calls 5, waits 1 |
| `python -B tools/sync_vendor.py --check` | 0 | in sync |
| `conformance.py --case all --consent-execute-reviewed-code` | 0 | screen/sgr/input/wait/reject all PASS (`all_selected_pass: true`) |

## Four-stage mutation proof (isolated copy `RUN/T03/validation/repo`)

| stage | component | result |
|---|---|---|
| 1 original | `write` restored to a single `os.write` with the return value discarded | **FAILED (failures=10)**, e.g. `b'A\xe4' != b'A\xe4\xb8\xad\x00B\r\n\xe4\xbf\x9d\xe5\xad\x98'` — 2 of 14 bytes, call reported success |
| 2 candidate | live `pty_backend.py` | Ran 12 tests, **OK** |
| 3 bug restored | single `os.write` again | **FAILED (failures=10)** |
| 4 restored | live `pty_backend.py` | Ran 12 tests, **OK** |

Test file bytes identical in every stage (`sha256 d7e9d14772d5afb6…`). The first mutation attempt
matched the **abstract** `write()` signature and silently left the fix in place; the harness's own
post-conditions caught it and the anchor was moved behind `write_timeout` (recorded because a mutation
that "survives" by not applying is exactly the failure mode the brief warns about). Logs:
`stage{1..4}-*.log`; mutation: `../mutate.py t03-single-write`.

## Controls pinned

Short writes; EAGAIN; EINTR; per-byte writes; zero progress; deadline via a fake clock (bounded loop,
no spin); partial then EPIPE (prefix reported, origin kept); EBADF; empty payload (no transport call);
repeat after a failure (not sticky); completion not undone by a later deadline; `write` before `spawn`.

## The eight contract classes (docs/A01_MINIMAL.md §6)

short write ✔ · EAGAIN ✔ · EINTR ✔ · zero progress ✔ · timeout ✔ · partial-then-failure ✔ ·
final byte vs. deadline race ✔ · repeat call after an error ✔

## NOT_RUN

* `posix_pty` — `NO_POSIX_HOST_OR_NO_EXPLICIT_PTY_APPROVAL`. This host has no POSIX shell and the
  Docker daemon is stopped; starting it is a separate, heavier decision. **No real PTY byte-exact
  claim is made**: the evidence is `E3 + injected os.write/select/time` against the production method.
* Cross-session partial-write receipts (CLI/MCP surfacing of `written_bytes`) — a separate increment,
  not started.
* **Commit: NOT_CREATED. Push: NOT_REQUESTED.**
