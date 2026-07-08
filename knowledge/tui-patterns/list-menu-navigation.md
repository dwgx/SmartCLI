# Pattern A — List / Menu Navigation

Recognize a chooser (vim, k9s, lazygit, ncurses menus) as stacked rows of similar structure with exactly one row visually distinguished, and drive it by verified single-step moves to the target index, then Enter.

### Recognition
The distinguished row is marked by one of:
- **reverse video** (SGR 7): selected row cells have `reverse=true` (fg/bg swapped) — most common in ncurses/tview (k9s, lazygit panels).
- **background color highlight** across full width.
- **bold** (SGR 1) on the selected row.
- a **caret/pointer glyph** at the left edge: `>`, `❯`, `›`, `*`, `→` in col 0-2.

Cursor is often parked on the highlighted row (tview/ncurses hide it). Not an editable field — a chooser. lazygit: bordered panels, the focused panel has a colored/bold border + one highlighted line. k9s: table with a reverse-video current row + top command bar.

Detector: the row whose attribute run (reverse OR distinct bg OR bold) spans most of the line width and is unique among siblings, OR the row starting with a pointer glyph = current selection. Track its index across snapshots.

### Drive
- Down `\x1b[B` (fallback `\x1bOB`, or vim `j` 0x6a); Up `\x1b[A` (fallback `\x1bOA`, or vim `k` 0x6b).
- Page: PageDown `\x1b[6~`, PageUp `\x1b[5~`; or Ctrl-D/Ctrl-U in vim-like.
- Jump: `g`/`G`, or Home `\x1b[H` / End `\x1b[F`.
- Confirm: Enter `\r`.
- To reach row N: read current index from snapshot, send Down/Up the delta, re-snapshot to confirm the highlight moved by 1 each time. Do NOT fire all keys blindly — wrap-around and filtered lists change the count (see [[verify-movement-step-by-step]]).

### Done
Highlighted-row index equals target (verified) → then Enter. After Enter the list disappears / new screen loads / value echoes / detail view opens. If the same list+selection persists, the item may be a submenu header (re-classify) or the app needs a different activate key.

**Source:** https://invisible-island.net/xterm/ctlseqs/ctlseqs.html (key sequences); recognition heuristics are primary/synthesized from the project TUI-patterns research digest (`research/R4-tui-patterns.md`).

**See also:** [[key-encoding-reference]], [[application-cursor-mode]], [[verify-movement-step-by-step]], [[cursor-row-binding]], [[fuzzy-search-filter]]
