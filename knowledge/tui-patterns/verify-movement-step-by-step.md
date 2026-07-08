# Verify Movement Step-by-Step

Never fire N arrow keys blindly in a list/menu; wrap-around, live-filtering, and variable row heights make blind counts wrong. Re-snapshot after each key.

- Read the current selection index from the snapshot.
- Send one Down/Up, then re-snapshot and confirm the highlight moved by exactly 1.
- Repeat until the highlighted-row index equals the target index; only then Enter.

Why blind counts fail: wrap-around (moving past the last row jumps to the first), live-filtered lists change the row count as you type, and variable row heights break a naive "send delta keys" plan.

**Source:** primary/synthesized — cross-cutting engineering principle distilled in the project TUI-patterns research digest (`research/R4-tui-patterns.md`); it is [[hard-lessons]] rule 8 (self-verify by driving your own output) applied to input.

**See also:** [[list-menu-navigation]], [[fuzzy-search-filter]], [[wizard-installer-flow]], [[cursor-row-binding]]
