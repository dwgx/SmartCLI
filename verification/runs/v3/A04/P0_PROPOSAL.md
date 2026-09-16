# A04 P0 — capability and resource proposal (S1 and the slices that depend on it)

Owner authorization: **approved by the Owner on 2026-09-16** ("全力发挥去做吧…全部做完收尾就push 打tag"),
which covers this proposal, the slice sequence S1→S6, the release documentation and the tag. New
threads are still listed separately (only S4 may need one, and it will not be created without a
further explicit word).

Base: `D:\Project\SmartCLI` at HEAD `701e61f` **plus the uncommitted T05/T04/T03 overlay**
(`snapshot.py 3b6e10af…`, `screen_model.py 242ba383…`, `pty_backend.py 93bb587d…`, three new test files).

## 1. Interface decision (S1)

Chosen route: **private capability on the built-in backends, one optional public kwarg on the
existing entry point.** No new API family.

| symbol | kind | contract |
|---|---|---|
| `PtyBackend` (ABC) | unchanged | third-party backends keep implementing only `spawn`/`read_nonblocking`/`write`/`resize`/`is_alive`/`terminate` |
| `supports_read_budget(backend) -> bool` | new module function | true only for backends that declare `READ_BUDGET_CAPABLE = True`; the session never probes by calling and catching `TypeError` |
| `PosixPtyBackend._read_budgeted(max_bytes) -> bytes` | new private | `select` then at most `max_bytes` bytes; `b""` when not readable; EOF/error recorded in status, never raised as a silent empty read |
| `WinptyBackend._read_budgeted(max_bytes) -> bytes` | new private | pops already-decoded chunks, accumulates at most `max_bytes`, keeps the unreturned **suffix** in `_carry` (accounted, never dropped) |
| `<backend>.read_status() -> dict` | new, both built-ins | `readable_now` (bool/None), `eof`, `error`, `queued_payload_bytes`, `reader_held_payload_bytes`, `generation` |
| `PtySession.pump(max_bytes=None)` | additive kwarg | `None` = byte-for-byte today's behaviour; an int requires a budget-capable backend, else `ReadBudgetUnsupported` is raised **before** any read |
| `PtySession.io_state() -> dict` | new | the additive `io` block: `generation`, `read_offset`, `fed_offset`, `pending{known_payload_bytes, readable_now, parser_incomplete, reply_bytes, upstream}`, `local_cut`, `representation`, `stream_error`, `basis_origin` |
| `ReadBudgetUnsupported(RuntimeError)` | new exception | raised when a budget is requested from a backend that cannot honour it |

Rules kept from the v3 design: offsets count **bytes delivered to the session** in one generation
(`0 ≤ fed_offset ≤ read_offset`); `budget_limited` when a turn consumes exactly its budget (a later
real emptiness check is what may say `drained`); unknown counts are `null`, never `0`; the Windows
representation string is `conpty_reconstructed_utf8` and its `upstream` is always `unknown`; nothing
about `_CSI_CAP`, the SGR downgrade rules or the T03 write contract changes.

## 2. Budget symbols and first values

`B_read` single-read ceiling · `B_turn` bytes fed per turn · `B_reply` reply slot · `B_queue` Windows
payload cap · `N_items` item cap · `J_fast` fast verbs per turn · `J_scan` queue scans per turn ·
`T_soft` checkpoint interval.

S1 introduces the mechanism with **defaults off** (the daemon does not pass a budget yet) and test-only
small values (`B_read = 4`, `B_turn = 8`) so the bounds are reached inside a few iterations. Production
defaults are decided in S3 from a local measurement, not from the X2/X3 numbers, and not asserted in
this slice.

## 3. Files (physical count)

S1 = **6 files**: `smartcli_core/pty_backend.py`, `smartcli_core/session.py`, their two vendor twins,
`tests/test_a04_read_budget.py`, `tests/run_all.py`. S2 (+6), S2p (+4), S3 (+5), S4 (+7), S5 (+4),
S6 (+5) follow `A04_PRODUCTION.md` §8. `tests/run_all.py` is shared: each slice adds only its own
registration line and never reorders or relaxes existing entries.

## 4. Rollback

Slices are additive and default-off: with `max_bytes=None` every path is the pre-change path, so
reverting a slice's file pair restores previous behaviour. Per the v3 ruling, the *dependency* order is
respected: S2 depends on S1, S5 on S4 — they are reverted in reverse order, never piecemeal. The live
worktree is never `reset`/`stash`ed; all red/green work happens in an isolated copy under the RUN dir.

## 5. Explicitly not in S1

Daemon service turns (S3), readiness cut (S2), close protocol (S4), Windows cap (S5), reply progress
(S6), release docs (S7). A05 (`tui.py` reader "cap" that is only a filter) and A06 (`_reply`'s 60 s
worker stall, unbounded `jobs`/`readers`) stay open and are named as such in every receipt.
