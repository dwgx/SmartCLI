# drive-tui — Known limitations & fix log

A living log the AI reads and appends to (see SKILL.md → "Known limitations &
self-improvement"). Read this FIRST when a program misbehaves — the cause may
already be here. When you fix something, add a dated entry: symptom, root cause,
fix, and **exactly how you verified it on the real run path**.

Rules for entries: measure ground truth (don't guess), verify by driving the
real program (not a mock), and if you touched `smartcli_core` note the
regression run (drive-probes + `_sandbox_posix_backend.py` on Linux).

---

## Fixed & verified

### 2026-08-09 · One connection could stall the daemon for every other caller
- **Shipped in v0.2.3** (2026-08-09).
- **Symptom:** any local process — with no credential at all — could connect to the
  session port, send bytes with no newline, and block every other caller. With
  `listen(8)`, nine such connections denied service for ~18s at a time, repeatable.
- **Root cause:** the accept loop was serial and the UNAUTHENTICATED transport read ran
  inline on it. An earlier fix split the read budget (2s pre-auth / 60s post-auth),
  cutting the worst case from 540s to 18s — a 30x mitigation that left the primitive
  intact, because the loop was still serial.
- **Fix:** three roles. The accept thread only accepts; a per-connection reader does the
  unauthenticated work (read, parse, check the token) so one silent peer burns only its
  own 2s; and a SINGLE worker thread is the only thread that ever touches the session.
  That last part is required, not caution — `visual_hash()` clears `screen.dirty` as a
  side effect, `pump()` is read-modify-write, and `resize()` mutates four fields in
  sequence, so two threads in the session corrupt perception silently.
- **Plus a second layer:** a long `wait*` occupied the worker, so a concurrent
  `snapshot` waited behind it (8s, measured) — the same block one layer in. The core's
  wait loops now take an optional poll hook, called in the idle gap ON THE WAITING
  THREAD, so fast verbs are answered without a second thread touching the session.
- **Verified:** `tests/test_daemon_concurrency.py` drives the real accept loop against a
  fake session (no PTY): 9 silent peers → authenticated request served in 0.00s;
  `snapshot` during a long wait → 0.04s; 200 KB request still succeeds; auth still
  enforced; session access provably single-threaded. Mutation-verified three ways
  (serial inline → 10.06s FAIL; no poll hook → 8.00s FAIL; handling on the reader
  thread → FAIL). On a live PTY: `snapshot` in 0.13s during a 20s `wait-regex`, zero
  leaked sessions. run_all 44/44; CI green on all 11 jobs including the three-OS
  real-PTY smoke.

### 2026-08-09 · A second `close` is idempotent only after the daemon has exited (the _mcp_probe flake)
- **Not a defect — the consequence of a deliberate fix.** `close` returns as soon as the
  daemon has SENT its reply; the daemon then exits through its own `finally`. A second
  `close` landing inside that window finds the request failing while the pid is still
  alive, and correctly REFUSES (see the 2026-08-07 entry above — deleting the entry there
  would destroy the token and pid that are the only handles left on a live child).
- **If you script a retry, poll.** Call `close` again on a bounded loop until it reports
  ok, rather than asserting the second call succeeds immediately. `tests/_mcp_probe.py`
  does exactly this; its assertion used to require `ok` unconditionally and was the
  load-dependent flake that failed 2 of 5 full-suite runs and one CI leg on macOS.
- **Resolved 2026-08-09.** Mutation-verified that the polled version still fails if
  `close` never becomes idempotent, and 5/5 under four CPU burners with zero leaks.

### 2026-08-07 · `close` after a timeout deleted a LIVE daemon's registry entry, and `list` then confirmed a lie
- **Symptom:** `close --id <SID>` printed `closed <sid>`, exited 0, and `list` reported
  zero sessions — while the daemon was still running and still owned a PTY child.
- **Root cause:** `_call` turns *any* transport failure, including a plain timeout,
  into a `SystemExit` whose message tells the operator to run `close` "to clean up the
  stale entry", and `cmd_close` then unlinked the registry file unconditionally. But
  the daemon's accept loop is **serial**, so a busy daemon looks exactly like a dead
  one at the socket. That file is the only store of both the capability token and the
  pid, so the deletion left a live daemon unreachable by protocol (token gone) and
  unfindable for a manual kill (pid gone). The red-line check every session is
  supposed to run — `list` → zero leaked sessions — would have confirmed a lie.
- **Fix:** death must be proven before deletion. `_pid_is_alive()` uses
  `os.kill(pid, 0)` on POSIX (`ProcessLookupError` = gone, `PermissionError` = exists
  but foreign) and `OpenProcess` + `GetExitCodeProcess` on Windows, where signal 0
  does not exist. On a failed request with a live pid, `close` **refuses**, exits 1,
  and prints the pid so you can act. `--force` overrides it.
- **What this means for you when it fires:** a refusing `close` is not a bug. Retry
  the verb (the daemon was probably just busy serving another connection), or kill the
  printed pid and re-run. Reach for `--force` only when you have confirmed the process
  is gone, because it restores the old data-loss behaviour by design.
- **Verified:** without spawning a PTY — a registry entry whose pid is the live test
  process and whose port nothing listens on. Pre-fix, `cmd_close` printed
  "closed livepid", returned 0, and unlinked the file while that pid was alive. Locked
  by `test_close_keeps_a_live_daemons_entry` in `tests/test_drive_security.py` (live
  pid → entry kept, rc!=0; absent pid → removed, rc==0; `--force` → removed anyway).
  Mutation-verified: restoring the unconditional unlink fails that check.

### 2026-08-07 · `--env` could re-inject the session token on Windows (case-sensitive guard)
- **Symptom:** on Windows, `--env smartcli_tui_token=stolen` was accepted and the
  driven child received `SMARTCLI_TUI_TOKEN` — the capability the daemon deliberately
  pops so a child cannot control its own session.
- **Root cause:** the guard was `key.startswith("SMARTCLI_TUI_")`, an exact-case
  check. Windows environment names are case-insensitive and CPython upcases keys on
  assignment (`os.py`: under `if name == 'nt'`, `encodekey` returns
  `encode(key).upper()`), so a lowercase spelling passed validation and
  `os.environ.update()` installed it under the reserved name anyway. Measured
  pre-fix: `smartcli_tui_token`, `SmartCli_Tui_Token`, `SMARTCLI_ROOT` and
  `SMARTCLI_MAX_SESSIONS` all ACCEPTED.
- **Fix:** compare uppercased unconditionally (free on POSIX, closes the bypass on the
  historical primary dev target), with the deny-list widened to the other variables
  this CLI reads: `SMARTCLI_ROOT`, `SMARTCLI_MAX_SESSIONS`, `SMARTCLI_AUTO_INSTALL`.
  Your own names are unaffected — a test asserts `SMARTCLI_USER_THING` still passes.
- **Verified:** `tests/test_drive_security.py`; mutation-verified — restoring the
  case-sensitive guard fails 7 checks. Same commit also rejects a non-dict JSON
  request before dispatch (`[1,2,3]` used to return an `AttributeError` string, with
  no `ok` field, to a peer that had not authenticated).

### 2026-08-06 · pyte had no alternate-screen buffer, so full-screen programs corrupted the primary screen
- **Symptom:** pyte implements no alternate-screen mode at all (1049/1047/47 just set an
  unknown bit), so `vim`/`less`/`htop` — every full-screen program this skill exists to
  drive — painted their alternate screen on top of the main one, and on exit the main
  screen was never restored. An agent read a merged, impossible screen with nothing
  reporting a problem.
- **Fix:** implemented per xterm and verified against tmux: 1049 saves the cursor and
  clears the alt buffer on entry, restores both on exit; 47/1047 switch without the
  cursor save; the cursor is deliberately NOT homed on entry. Private mode 1048
  (cursor save/restore only) is also supported, with a weaker evidence level: xterm
  defines it, but neither tmux nor GNU screen implements it, so there is no ground
  truth to check it against. The state now reaches every surface an agent reads —
  `ScreenModel.alt_screen`, `Snapshot.alt_screen`, the `to_text()` header (leads the
  flags, inserted before `selected`/`status`/`errors`), the JSON `hints`, and every
  drive-tui daemon reply — rather than only being reachable by poking the pyte object.
- **Verified:** six alt-screen cases diffed against a real terminal — four vs a tmux
  pane in `_diff_tmux_pyte.py`, plus two in the three-way `_diff_two_refs.py` against
  tmux AND GNU screen (with `altscreen on`, which GNU screen defaults off) — and a
  further 26 alt-screen assertions locked deterministically in
  `test_terminal_fidelity.py`. Keep those two numbers apart: only the six were
  compared against a real terminal, and the 26 are in-memory. On a live PTY: driving
  real `less` reports `alt_screen=True` in the header while inside it and `False`
  after quitting. (This entry originally said "sixteen ... diffed against a real tmux
  pane", copied from HANDOFF without counting; a review caught it. Count with
  `grep -c '"alt screen' tests/_diff_*.py`.)

### 2026-07-19 · Selection-only and cursor-only changes were invisible (formerly a "Still open" entry)
- **Symptom:** after an arrow key, a menu could move its selection using only
  reverse video/background attributes while its text stayed identical;
  text-only `wait_change` correctly remained stable but offered no alternative.
- **Fix:** added a separate `visual_hash` over cells, attributes, and cursor state,
  plus `wait_visual_change` in the core, daemon, CLI, one-shot steps, and MCP.
  Text readiness deliberately keeps its old content-only hash so blink/cosmetic
  churn cannot make output streams permanently unstable.
- **Verified:** `tests/test_visual_change.py` locks reverse-video, cursor-only,
  and unchanged-text behavior in memory; the macOS CLI and MCP real-PTY probes
  remain green with zero leaked sessions.

### 2026-07-13 · POSIX `terminate()` left a zombie child (formerly a "Still open" entry)
- **Symptom:** on Linux, after `close()`/`terminate()` the child stayed as a
  `<defunct>` (zombie) process — `SIGTERM` was sent but nothing reaped it.
- **Root cause:** `PosixPtyBackend.terminate()` called `os.kill(SIGTERM)` and
  `os.close(fd)` but never `os.waitpid()`, so the kernel kept the exit status.
- **Fix:** `terminate()` now polls `waitpid(WNOHANG)` up to ~1s, then falls back
  to `SIGKILL` + a blocking `waitpid`, reaping in all paths.
- **Verified:** real Debian 13 over SSH — `tests/_sandbox_posix_backend.py` went
  from `[KNOWN] zombie (state=Z)` to `[OK] no zombie … gone/reaped`. Windows
  drive-probe suite 1–6 + tui_cli still green (POSIX-only change).

### 2026-07-13 · Arrow keys ignored by curses/DECCKM apps (formerly a "Still open" entry)
- **Symptom:** sending `keys Up`/`Down` to a full-screen curses program moved
  nothing — the app never saw an arrow key.
- **Root cause:** we always emitted CSI arrows (`ESC [ A`). Apps that enable
  DECCKM (application cursor keys, `ESC[?1h` — what `curses.keypad(True)` does)
  expect SS3 (`ESC O A`); CSI is not recognised in that mode.
- **Fix:** `send_keys` now reads the live cursor-key mode via
  `ScreenModel.app_cursor` (pyte records DECCKM as mode value `32`) and emits SS3
  for cursor/nav keys when it's on, CSI otherwise. Fully automatic — callers
  still just send `keys Up`. `_resolve_key(token, app_cursor=…)` + `KEY_MAP_SS3`.
- **Verified:** real Debian 13 ncurses probe — `curses.keypad(True)` app read our
  adaptive `Up` as `KEY_UP` (`[PASS] #5 FIXED`); pyte reported `DECCKM=on` from
  the live screen. Windows default path unchanged (CSI when no DECCKM), Ctrl-C
  and all drive-probes unaffected.

---

## Still open (with reasons)

### A second LONG wait queues behind the first (inherent, not a defect)
- One session owns one PTY child, so it has one screen. Two concurrent `wait*` verbs on
  the same session have no meaningful independent answer, and the single session worker
  runs them in arrival order.
- **Fast verbs are NOT affected** — `snapshot`, `alive`, `list`, `send-text`,
  `send-line`, `keys` are answered *during* a long wait (measured on a live PTY: 0.13s
  while a 20s `wait-regex` was in flight). `resize` is deliberately excluded: it
  re-dimensions the pyte screen and therefore changes the content hash, so answering it
  mid-wait would make a caller blocked in `wait-change` read "the screen changed" and
  conclude its own keystroke had landed.
- If you need two independent waits, use two sessions.

### ConPTY (Windows) startup quiet-gap & Ctrl-C
- First prompt can land ~3s after spawn; use `wait-regex` with a 15s timeout for
  the FIRST prompt, never bare `wait`. Raw Ctrl-C is unreliable under ConPTY —
  recover with `close` + fresh `start`. (POSIX Ctrl-C works.)

### Environment notes
- POSIX backend verified on Debian 13 / Python 3.13 (2026-07-13) and macOS on
  Apple Silicon / Python 3.14 (2026-07-19). The BSD PTY EOF path, persistent
  CLI, MCP adapter, resize, REPL drive, and zombie-free close all passed.
- tmux launcher scripts (`skills/cmd-art/tmux/*.sh`) VERIFIED 2026-07-27 on real
  tmux 3.6b (macOS): `tests/_tmux_launcher_probe.py` drove both scripts through
  all five states — 18/18. It found a real bug (`fx-popup` leaked tmux's raw
  "no current client" with exit 1 when no client was attached); now guarded.
- The core detects pyte's capabilities at import time (`_PYTE_HAS_ALT`,
  `_PYTE_DCH_HANDLES_WIDE` in `smartcli_core/screen_model.py`) instead of pinning
  a version range. So behaviour can change from a `pip install -U pyte` alone,
  with no SmartCLI code change: once pyte ships its own alternate-screen support
  or wide-glyph-aware DCH, this core's override switches off automatically. If a
  screen or a delete-characters case looks wrong after a dependency upgrade,
  check the installed pyte version and these two flags before assuming a
  regression here.

## Service, budgets and close (A04, 0.3.0)

- **The daemon services the session on its own.** Every worker iteration spends one byte-bounded I/O
  turn, so a child keeps running (and its device queries keep being answered) even when no client
  asks anything. Measured: `ESC[6n` answered 0.169 s after the child sent it with no polling, and a
  256 KiB fixture completed unprompted; with the turn removed the same fixture stalls at 12 288 B.
- **A timeout is not an answer.** `io.local_cut` distinguishes `drained` from `budget_limited`,
  `unknown` and `error`, and `pending` carries `null` (not `0`) when a transport cannot count. A
  `STABLE` verdict requires `drained`; a caller that ignores `io` is back to guessing.
- **Windows is not wire-byte-exact.** ConPTY composes the stream it delivers (a 1 MiB burst arrived
  as ~12 KB), so `representation=conpty_reconstructed_utf8` and `source_wire_exact=false`. The
  payload cap bounds what this runtime has received -- it does not bound ConPTY, and it does not
  apply backpressure to the child.
- **Close is confirmed or admitted.** `close_unconfirmed` with `last_progress` is a real answer; a
  returned native call is never treated as an exit. The three liveness gaps that used to follow this
  sentence are closed (`tests/test_liveness_gaps.py`): an owed device reply is RESUMED on a later I/O
  turn from a ledger that re-sends only bytes the transport reported as NOT accepted, bounded by
  `SMARTCLI_REPLY_RETRY_BYTES` per spawn generation — **off by default**, so with it unset the pre-S6
  behaviour stands (one attempt per observation, the remainder reported and left unwritten, and bytes
  whose landing the transport cannot report never re-sent); the daemon's reader and job caps are now
  ADMISSION limits (`SMARTCLI_MAX_READERS` / `SMARTCLI_MAX_JOBS`, default 64 each) that refuse with
  `reason: too_many_readers` / `too_many_jobs` before a thread or a queue slot is spent, instead of
  filtering a list after the fact; and `_reply` sends non-blocking under its 60 s ceiling plus a
  no-progress stall window (`SMARTCLI_REPLY_STALL_SECONDS`, default 2 s), so a peer that stops reading
  releases the worker inside that window while a slow-but-reading peer keeps the patience it always
  had. **Still open:** `pump(max_bytes=...)` can hang once the reader pauses (see the OPEN section
  below; issue #15). Two residual bounds worth knowing: the caps bound ADMISSION, so a queue already
  admitted and re-queued by the interleave path can transiently exceed `MAX_JOBS` (refused work is
  never silently dropped, and admitted work still runs); and a peer that keeps making token progress
  can still hold the worker up to the 60 s ceiling, which is deliberate — that is the patience a
  healthy caller had before A06.

## Write-path scheduling edges (N2, 2026-09-16)

Three edges the 256 KiB real-pty test never reached were reachable on a real daemon, and all three
were defects in `PosixPtyBackend.write` / the reply path:

- **A trickling writer ran past the deadline.** The offset advances on every call, so a loop that
  checks its deadline only in the EAGAIN/EINTR/zero-progress branches never reached the check: 64
  one-byte calls completed past a deadline that expired after the third and still reported success.
  The deadline is now re-checked before EVERY write. A completed write is still never downgraded.
- **A `select.select` failure lost the receipt.** The exception propagated raw, so a caller could not
  tell whether 0 or 4095 bytes had landed; EINTR was not retried at all. Waiting is now bounded and
  converts: a signal retries the SAME suffix (never a re-send from zero, which would duplicate bytes),
  any other error reports the earned prefix as `IncompleteWrite(offset, total, reason)`.
- **A reply that could not be written was invisible.** A bare `except: pass` swallowed it, so a child
  blocked on a device query looked like a child that ignored the input. It is now reported as
  `io.pending.reply_error` with the known prefix subtracted from `reply_bytes`, attempted once (a
  blind whole-payload retry would duplicate a partial reply), and cleared by the next healthy write.

Verification: `tests/test_partial_write_edges.py` (7 cases, injected `os.write`/`select`/clock, no PTY)
failed 5/7 before the change and passes after; the real-pty test still delivers 262 144 B exactly once
(sha256 match, 32 writability waits). The wait count is scheduling-dependent -- 32/35/44 across
identical runs -- so never read it as a fixed property of the transport.

## OPEN: `pump(max_bytes=)` can hang when the reader reaches its high water (found 2026-09-16)

On the real ConPTY transport, a client that asks for a byte budget can wait forever once the reader
pauses at the payload high water: the client waits for its full `max_bytes`, the reader stops filling
at the high water, and the reader only resumes when the client drains -- which a client waiting for a
budget it can never get never does. Measured: `pump(max_bytes=64 KiB)` with
`SMARTCLI_WINPTY_HIGH_BYTES=131072`/`LOW=32768` and a child writing 256 KiB **never returned**
(faulthandler dump inside `WinptyBackend._read_budgeted`); with the default 4 MiB high water the same
run behaves, because a normal burst never reaches the pause. A control (`read_status()` called once
while the child writes) returns in 0.00 s, so the io-evidence path is not the stall.

Tracked as <https://github.com/dwgx/SmartCLI/issues/15>; repro in
`D:\\Project\\SmartCLI-v3-runs\\A04\\s5-highwater\\`. **Until it is fixed: do not pass `max_bytes` to
`pump()` on Windows, and do not lower the high water** -- an unbudgeted `pump()` takes whatever is
ready and cannot enter the wait. Fix direction: return what is available after a bounded wait, and
wake the reader when the client drains below the low water.

## Environment facts found while verifying (2026-09-16, Windows 11 + ConPTY)

- **A Git-for-Windows vim and this box's `less` never switch to the alternate screen** under ConPTY.
  `esc[?1049h` decoded out of a synthetic stream still sets `alt_screen=True`, so the model is fine:
  the programs simply never enter it here. Checks that demand `alt_screen is True` fail for the
  environment, so `examples/drive_vim.py` and `tests/_mcp_probe.py` now assert that the model AGREES
  with what the program did (entered it -> True, never entered it -> False). Where a program does
  enter the alternate screen, a False reading still fails.
- **`tests/_tmux_launcher_probe.py` SKIPs on Windows** -- there is no `termios`/`pty` at all, so the
  probe cannot run; it now says so instead of failing the aggregator. Run it on a POSIX host with tmux
  to get the 18/18 verification the script needs.
- **pywinpty `shlex.split`s a string command.** `session.start(r'"C:\Program Files\...\vim.exe" -u NONE')`
  never starts (the error is `The command was not found or was not executable: C:\Program`). Pass an
  ARGV LIST instead: `session.start([vim, "-u", "NONE", ...])`.
