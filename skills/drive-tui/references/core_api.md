# smartcli_core API — reference (read only when you need field-level detail)

The skill's CLI (`scripts/tui.py`) covers the common loop. Read this only when you need to script directly against `smartcli_core` in Python or need exact field semantics.

## PtySession (`smartcli_core.session`)
Constructor: `PtySession(cols=80, rows=24, backend=None)`. Picks `WinptyBackend` on Windows, `PosixPtyBackend` elsewhere.

- `start(cmd)` — spawn; `cmd` may be a string (`"python"`) or an argv list.
- `close()` — terminate the child; idempotent. Also works as a context manager.
- `is_alive() -> bool`.
- `resize(cols, rows)` — resize PTY + screen together.
- `pump() -> bytes` — read whatever is available and feed the screen. Call once more after the child dies to drain the final output.
- `send_text(str)` — type literally, no newline.
- `send_line(str)` — type + Enter (`\r`).
- `send_keys(list[str])` — key tokens (see below).
- `snapshot() -> Snapshot`.
- `wait_ready(marker=None, quiet_ms=200, max_wait_ms=10000, min_wait_ms=50, ...) -> (reason, Snapshot)` — reason in `MARKER`/`STABLE`/`TIMEOUT`. Races marker vs. stability. Can return `STABLE` on a still-blank screen during a startup quiet-gap — prefer `wait_for` for a known first prompt.
- `wait_for(pattern, timeout_ms=10000, ...) -> (matched, Snapshot)` — strict regex wait; does NOT short-circuit on stability. Snapshot is always the current screen, even on timeout.
- `wait_stable(...) -> bool`.

## Key tokens (`send_keys` / the `keys` subcommand)
Names: `Enter Return Tab BackTab Space Backspace Delete Escape Esc Up Down Left Right Home End PageUp PageDown Insert F1`–`F12`.
Combos: `C-x`/`^X` → Ctrl (Ctrl-A = 0x01). `M-x` → ESC prefix (Alt). Unknown tokens are sent as literal UTF-8.
Escape sequences are normal-mode xterm/VT100. Application-cursor-keys mode (`\x1b[?1h`) expects `\x1bOA` for Up — not auto-detected.

## Snapshot (`smartcli_core.snapshot`)
Fields: `size (rows,cols)`, `lines`, `cursor (row,col)`, `cursor_hidden`, `selected_line`, `selected` (a `Span`), `selected_reason`, `status_bar`, `status_bar_row`, `title`, `menu_items` (list of `Span`), `errors` (list of `(row,text,reason)`), `screen_reverse`.
- `selected_line` / `selected`: widest highlighted (reverse-video or non-default-bg) span, else the cursor line. This is the menu-selection signal.
- `menu_items`: every highlighted span in reading order — the choices in a menu.
- `errors`: lines with red fg (`reason="red_fg"`) or matching `error|failed|traceback|exception` (`reason="keyword"`).
- `to_text() -> str`: header line + row-numbered body (`*` on selected rows, blank runs collapsed to `...`).
- `to_json(indent=None) -> str`: full structure; empty/None fields omitted.

`Span`: `row, col_start, col_end (exclusive), text`.

## Readiness (`smartcli_core.readiness`)
Three signals combined: transport quiescence, pyte content-hash stability (cursor/attr changes excluded), and regex marker. Every wait has a hard `max_wait`/`timeout` ceiling so spinners return the last screen instead of hanging. `min_wait_ms` guards the stale-screen race right after sending input.

## Backends (`smartcli_core.pty_backend`)
`get_default_backend()` → `WinptyBackend` (pywinpty/ConPTY, daemon reader thread → queue) on win32, else `PosixPtyBackend` (pty.fork + select). Both normalize reads to bytes and feed one long-lived `pyte.ByteStream`.

## Platform notes verified on this host (Windows 11, Python 3.14.6, pyte 3.0.5, pywinpty 3.0.5)
- ConPTY first byte ~20ms after spawn, but a program's own banner can lag seconds (Python REPL banner ~3s). Use `wait_for(<prompt>)` with a generous timeout for the first prompt.
- Raw Ctrl-C (0x03) does NOT reliably interrupt a line-mode child under ConPTY. If `C-c` doesn't work, `close` and restart the session. POSIX signals work normally.
- `send_line` uses `\r`. Raw-mode apps needing `\n` should use `send_text("...\n")`.
- `$`-anchored regex matches against the whole screen text; prefer loose markers or pass multiline flags when scripting directly.

## See also (knowledge graph)
Sourced concept notes for the mechanisms above live in `D:/Project/SmartCLI/knowledge/`
(hub: `knowledge/tui-patterns/README.md`, index: `knowledge/INDEX.md`):
- Readiness / snapshots: [[quiescence-detection]] · [[snapshot-stability-hash]] · [[screen-snapshot-capture]] · [[alternate-screen-detection]]
- Keys & cursor modes: [[key-encoding-reference]] · [[application-cursor-mode]] ⇄ [[application-cursor-keys-deckm]]
- Backends / PTY: [[pywinpty]] · [[node-pty-windows-conpty]] · [[pty-vs-pipe]] · [[crlf-termios]] · [[isatty-branching]]
- The 8 recipes: [[list-menu-navigation]] · [[fuzzy-search-filter]] · [[pager-navigation]] · [[confirm-yes-no-dialog]] · [[progress-spinner-waiting]] · [[form-field-input]] · [[repl-session]] · [[wizard-installer-flow]]
