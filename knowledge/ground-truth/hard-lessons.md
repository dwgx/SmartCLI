# Hard Lessons — Replicating Real TUI Effects (pointer)

**Statement:** Ten blood-earned rules for faithfully replicating a *real, existing* TUI/CLI effect (a screenshot, an animation, another CLI's UI). Read before any replica task. Every rule maps to a real, expensive failure during the `/effort` ultracode reconstruction.

This is a **pointer** into a load-bearing skill document — the full text lives with the tui-ui skill. Summary of the ten rules:

1. **If ground truth exists, get it first — no head-canon.** Decompile for exact constants, drive the real program and capture per-cell bytes/colors, screenshot animations to frames. Build against reality, not imagination.
2. **Confirm scale before form.** An 8-row × 88-col rectangle was mistaken for a 1–2 row bar for a dozen rounds. Measure boundaries (which rows, which columns) before writing any renderer.
3. **Animation needs multiple frames.** One frame can't distinguish flow vs. diffusion vs. pulse. Capture continuous frames (every 0.1–0.15 s) and measure a quantity over time.
4. **Verify on the real run path, not "looks about right."** A pyte static PNG or hand-patched harness is not what the user's terminal shows.
5. **Test-harness monkeypatches hide real crashes.** Injecting a dependency the script itself lacks fakes success; run the script's own full startup path.
6. **Don't downgrade an interactive TUI just because `isatty()==False`.** Under a PTY, isatty is often False; it should gate *keyboard input*, not the animation loop.
7. **Terminal newlines must be CRLF.** LF alone moves down without returning to column 0; normalize `\n` → `\r\n`.
8. **Self-verify by driving your own output with SmartCLI.** Drive the real target for ground truth, drive your own script for its real render + stderr, diff numerically. Watch for alt-screen (`?1049h`) hiding output in the main buffer.
9. **Windows non-UTF-8 stdout crashes on non-ASCII glyphs.** `sys.stdout.reconfigure(encoding='utf-8', errors='replace')`.
10. **Don't ask the user "what does it look like" — you can look yourself.** You have drive + capture + render abilities; use them.

**The standard replica workflow:** get ground truth → measure scale & form → extract exact params (palette, coords, speeds — quantified) → build against truth → verify on the real run path → confirm in a real terminal (CRLF, isatty, UTF-8). Only when ground truth matches item-by-item is it "correct."

**Source:** Load-bearing project document (unsourced / primary): `skills/tui-ui/references/HARD-LESSONS.md`. Worked case: [[effort-selector]] and the verified replica `skills/tui-ui/examples/effort_selector.py`.

**See also:** [[effort-selector]], [[rendering-model]], [[verify-movement-step-by-step]], [[done-signal-layering]], [[screen-snapshot-capture]], [[quiescence-detection]], [[application-cursor-mode]]
