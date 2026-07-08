# Cursor-Row Binding

Bind recognition to the cursor row + cell attributes, not pure text matching: prompt strings (`>`, `:`, `...`, `[y/N]`) also appear in scrollback and echoed input.

- Only trust a prompt/marker string when the cursor is on or after that row AND the screen is quiescent.
- Pure text matching misclassifies scrollback and echoed input (output may itself contain `>>>`, `...`, `>`).
- In REPLs this is mandatory: match prompt regexes on the CURSOR ROW (see [[repl-session]]).
- Regex over the raw stream is a fast side-channel only; the grid must be built by a real VT parser (see [[screen-snapshot-capture]]).

This is the single highest-leverage recognition rule across every interaction pattern.

**Source:** primary/synthesized — cross-cutting engineering principle distilled in the project TUI-patterns research digest (`research/R4-tui-patterns.md`); grounds on terminal cursor-position semantics (xterm ctlseqs CPR / cursor reporting).

**See also:** [[repl-session]], [[list-menu-navigation]], [[done-signal-layering]], [[screen-snapshot-capture]]
