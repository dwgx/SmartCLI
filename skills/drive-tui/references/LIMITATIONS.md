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

### 2026-07-13 · POSIX `terminate()` left a zombie child (was known-#6)
- **Symptom:** on Linux, after `close()`/`terminate()` the child stayed as a
  `<defunct>` (zombie) process — `SIGTERM` was sent but nothing reaped it.
- **Root cause:** `PosixPtyBackend.terminate()` called `os.kill(SIGTERM)` and
  `os.close(fd)` but never `os.waitpid()`, so the kernel kept the exit status.
- **Fix:** `terminate()` now polls `waitpid(WNOHANG)` up to ~1s, then falls back
  to `SIGKILL` + a blocking `waitpid`, reaping in all paths.
- **Verified:** real Debian 13 over SSH — `tests/_sandbox_posix_backend.py` went
  from `[KNOWN] zombie (state=Z)` to `[OK] no zombie … gone/reaped`. Windows
  drive-probe suite 1–6 + tui_cli still green (POSIX-only change).

### 2026-07-13 · Arrow keys ignored by curses/DECCKM apps (was known-#5)
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

### #3 · `content_hash` is blind to selection-only cursor movement
- Stability detection hashes plain text, not cursor/attributes, so a menu where
  only the highlighted row moves (no text change) can read as `STABLE` too soon.
- **Why not "fixed":** including attributes/cursor in the hash causes the
  opposite failure — false *unstable* on blink/reverse churn, which is worse.
  Design tradeoff. Workaround: after an arrow key, use a short `wait` then
  re-`snapshot` and compare the `selected` span, not bare stability.

### ConPTY (Windows) startup quiet-gap & Ctrl-C
- First prompt can land ~3s after spawn; use `wait-regex` with a 15s timeout for
  the FIRST prompt, never bare `wait`. Raw Ctrl-C is unreliable under ConPTY —
  recover with `close` + fresh `start`. (POSIX Ctrl-C works.)

### Environment notes
- POSIX backend verified on Debian 13 / Python 3.13 (2026-07-13) via an isolated
  SSH sandbox (venv + copied `smartcli_core`). macOS not yet verified — BSD pty
  EOF is handled (`not chunk`) but untested on a real mac.
- tmux launcher scripts (`skills/cmd-art/tmux/*.sh`) not verified on a real tmux
  host.

