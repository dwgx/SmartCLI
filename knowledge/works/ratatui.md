# Ratatui — constraint-solved layout + double-buffer diff

A Rust immediate-mode TUI framework. Two ideas worth stealing: a constraint solver for layout, and a double-buffered cell diff for flicker-free rendering.

**Source:** https://github.com/ratatui/ratatui

## How it works
- **Layout:** `Layout.direction.constraints([Length | Percentage | Ratio | Min | Max | Fill]).split(rect)`. Constraints are solved by the **Cassowary** constraint solver, which finds a best fit when constraints conflict. Leftover space goes to the last region unless there's a trailing `Min(0)`. `Flex` (Start / End / Center / SpaceBetween / SpaceAround) plus `.spacing()` controls distribution.
- **Immediate mode:** a `Cell` stores its symbol string and style separately. Two `Buffer`s are kept; each frame diffs current vs previous and emits **only changed cells**, then swaps. Because the buffer is shared, render order equals z-order (later draws overwrite).

## What to borrow
- Constraint-based split (`Length/Percentage/Ratio/Min/Max/Fill` → solver) as a layout primitive, complementary to Textual's box model.
- The double-buffer, cell-diff render loop — the concrete mechanism behind [[flicker-free-rendering]]: never repaint unchanged cells.

## See also
- [[flicker-free-rendering]]
- [[box-model-on-cell-grid]]
- [[fractional-space-distribution]]
- [[rendering-model]]
