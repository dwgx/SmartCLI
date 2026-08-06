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
