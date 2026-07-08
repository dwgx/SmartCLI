# yazi — async-off-render-thread with discardable tasks

A Rust terminal file manager whose architecture is the reference for keeping a TUI responsive: do all heavy work off the render thread, and make in-flight work discardable.

**Source:** https://github.com/sxyazi/yazi

## How it works
- **Two-tier async scheduler:** 10 macro workers + 5 micro workers across 3 priority levels, running off the render thread.
- **Chunked loading:** directories load in chunks so a huge folder never blocks the UI.
- **Discardable in-flight tasks:** tasks can be abandoned via Tokio `abort` plus an atomic per-line `ticket` — when you scroll away, stale work is dropped instead of finishing pointlessly.
- **Render batching** coalesces updates.
- **Bounded highlighting:** syntax highlighting is limited to the visible window.
- **Image preview:** a two-pass cached scheme that locks stdout only *after* the data is prepared, plus partial-erase-then-redraw to avoid flicker.

## What to borrow
- The **async-off-render-thread + discardable-ticket** model for previews and highlighting — the pattern for a responsive TUI that does expensive work: never block the render loop, and cancel work the user has scrolled past.
- Lock stdout only after data is ready; visible-window-bounded work.

## See also
- [[progress-spinner-waiting]]
- [[flicker-free-rendering]]
- [[quiescence-detection]]
