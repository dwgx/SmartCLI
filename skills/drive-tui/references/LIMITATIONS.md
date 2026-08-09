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

### One unauthenticated connection can stall the daemon (bounded, not fixed)
- The accept loop is serial (`conn, _ = srv.accept()`, no threading), so a local peer
  that connects and never sends a newline blocks every other caller — including you —
  for the length of its read budget. The budget is split (2s pre-auth, re-armed against
  a fixed deadline so dribbled bytes cannot renew it; 60s post-auth for an
  authenticated reply), which took nine held connections from a measured 540s down to
  18s. **That is a 30× reduction, not a fix**: an attacker who keeps reconnecting still
  degrades service.
- **Why it stops there:** per-connection threading is the real answer and
  `PtySession` is not thread-safe, so it is a concurrency-model change rather than a
  patch. Tracked as **A0-DAEMON-CONCURRENCY** in `NEXT-STEPS.md`, including the trap in
  the simpler design — a lock plus per-connection threads would let a blocking `wait*`
  verb hold the lock for its entire timeout, which is most of what this daemon does.
- **Practical impact while it stands:** a verb that times out does not prove the daemon
  died (see the `close` entry above). Retry before concluding anything.

### `_mcp_probe` has a load-dependent flake (deliberately not hidden)
- **Symptom:** `tests/_mcp_probe.py` failed in 2 of 5 full-suite `run_all.py` runs on
  2026-08-07, and did **not** reproduce in 3 back-to-back serial runs of
  `_tui_cli_probe` + `_mcp_probe`. It passes standalone.
- **Suspected cause:** the probe was modified in that same session (it gained a second
  session and a second leak poll), so this session's own work is the likely origin, not
  a product defect. That is a hypothesis, not a finding.
- **Why no `rerun=True`:** hiding it would destroy the evidence. `run_all.py` now
  retains child output and prints the last 40 lines on failure, so the next occurrence
  reports the probe's own FAIL line. **If you see it, capture that output before doing
  anything else** — it is the diagnosis this entry is waiting on.

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
