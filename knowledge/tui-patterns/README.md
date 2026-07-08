# TUI Interaction Patterns

Reusable paradigms for driving interactive terminal programs through a PTY while observing a rendered screen snapshot (the terminal grid: char + fg/bg/bold/reverse/underline attrs + cursor row/col + active buffer). Guiding principle across every entry: the highest-confidence "done" is process-exit / shell-prompt-return; snapshot heuristics are confidence signals layered on top, and recognition binds to cursor row + cell attributes rather than raw text.

Mined from `research/R4-tui-patterns.md` (live web research + WebFetch of the fzf man page and xterm ctlseqs, cross-checked against manpages).

## Foundations
- [[screen-snapshot-capture]] — turn a PTY byte stream into an observable cell grid via a headless emulator.
- [[emulator-libraries]] — pyte / pexpect / node-pty / @xterm/headless / vt10x / tmux / screen, per stack.
- [[tmux-capture-pane]] — get SGR-annotated, already-rendered panes without embedding a VT emulator.
- [[alternate-screen-detection]] — the alt-screen enter sequence is the strongest "a full-screen TUI launched" signal.
- [[application-cursor-mode]] — DECCKM: if arrows do nothing, resend them as SS3.
- [[key-encoding-reference]] — exact bytes to WRITE for every key; Enter = CR `\r`, not LF.
- [[quiescence-detection]] — decide when output has "settled" from idle + stability + no partial escape.
- [[snapshot-stability-hash]] — hash the grid to detect change; exclude cursor blink or it never settles.

## Cross-cutting principles
- [[cursor-row-binding]] — trust prompt strings only when the cursor is on/after that row.
- [[verify-movement-step-by-step]] — re-snapshot after each arrow; never fire N keys blindly.
- [[done-signal-layering]] — process-exit is ground truth; completion words and stability are weaker signals.

## Interaction patterns
- [[list-menu-navigation]] — Pattern A: one visually-distinguished row; move by verified single steps, then Enter.
- [[fuzzy-search-filter]] — Pattern B: fzf-style; type to narrow `X/Y`, verify pointer, Enter.
- [[pager-navigation]] — Pattern C: less/man/more; page to `(END)` or send `q`.
- [[confirm-yes-no-dialog]] — Pattern D: infer default from capitalization; retry with the full word.
- [[progress-spinner-waiting]] — Pattern E: recognize from successive snapshots; usually send nothing.
- [[form-field-input]] — Pattern F: dialog/whiptail forms driven as a focus → fill → Tab → OK state machine.
- [[repl-session]] — Pattern G: match primary prompt on the cursor row; handle continuation prompts.
- [[wizard-installer-flow]] — Pattern H: classify each step, drive it, confirm the screen materially changed.
