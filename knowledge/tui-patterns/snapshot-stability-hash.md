# Snapshot Stability Hash

Hash the visible grid so you can tell when the screen has stopped changing; exclude the cursor blink phase or a blinking cursor prevents the screen from ever settling.

```
cell_hash   = hash(char, fg, bg, bold, reverse, underline, cursor_here?)
screen_hash = hash(rows, cols, active_buffer, cursor_x, cursor_y,
                   cursor_visible, all cell_hashes)
stable if screen_hash == previous for stable_ms
```

Exclude the cursor **blink phase** from the hash, else a blinking cursor makes `screen_hash` oscillate and stability is never reached. This hash is the change-detector that feeds the stability half of quiescence.

**Source:** primary/synthesized — hash composition is engineering guidance distilled in the project TUI-patterns research digest (`research/R4-tui-patterns.md`). The cursor-blink exclusion is a measured failure mode, not an external spec.

**See also:** [[quiescence-detection]], [[screen-snapshot-capture]], [[done-signal-layering]]
