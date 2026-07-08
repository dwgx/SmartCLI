# Bubble Tea + Lip Gloss — Elm-loop TUI + text-block layout

Go's Elm-architecture TUI framework (Bubble Tea) paired with its styling/layout library (Lip Gloss). Reference for a single-consumer event loop and value-type text-block composition.

**Source:** https://github.com/charmbracelet/bubbletea , https://github.com/charmbracelet/lipgloss

## How it works
- **Event loop (Bubble Tea):** an Elm loop — many producers feed one `chan Msg`, a single consumer processes them. The `cursedRenderer` double-buffers and diffs, tracks dirty lines, flushes at 60 Hz, and uses **DEC-2026 synchronized output** to eliminate tearing.
- **Layout (Lip Gloss):** `Style` is a **value type** — fluent setters copy, so styles compose without shared mutation. `JoinHorizontal/Vertical(pos, ...)` glue text blocks (`pos` is a float alignment on the cross axis); `Place/PlaceHorizontal/PlaceVertical` position a block in a larger space. `Width/Height/Size` are ANSI- and Unicode-aware. Layers: `NewLayer().X().Y().Z()` + `compositor.Compose`.
- **Keys:** canonical modifier order `ctrl, alt, shift, meta, hyper, super`; a `Key{Text, Mod, Code, ShiftedCode, BaseCode, IsRepeat}` struct.

## What to borrow
- Single-consumer event loop: many producers → one channel → one consumer is the clean concurrency model for a TUI.
- **DEC-2026 synchronized output** to kill tearing on repaint ([[flicker-free-rendering]]).
- Lip Gloss `Join`/`Place` + value-type `Style` for composing text blocks — the align-and-place algebra for splash/banner layout.

## See also
- [[flicker-free-rendering]]
- [[box-model-on-cell-grid]]
- [[box-drawing-glyphs]]
- [[rendering-model]]
