# Flicker-Free Rendering

**Statement:** Draw each frame by building one full frame string and writing it once over a home-positioned (not cleared-between) screen, so the terminal never shows a blank intermediate state.

**Real recipe / sequences:**
```
startup:  enter alt screen (\e[?1049h) if wanted; hide cursor (\e[?25l);
          set NOWRAP; CLEAR once (\e[2J); query size.
each frame: build entire frame in memory, then HOME (\e[H) + write whole string once.
          Prefer \e[H (home + overwrite) over \e[2J every frame (2J-per-frame can flash).
exit:     show cursor (\e[?25h); leave alt screen (\e[?1049l); reset (\e[0m).
```
Supporting techniques:
- Double-buffer everything: compute the full next frame, then swap / write once.
- z-buffer for 3D (donut/sphere): init to 0 each frame; keep fragment with largest ooz = 1/z.
- Emit a color escape only when it changes between adjacent cells (SGR run-length) to shrink output.
- Frame pacing: target ~30-60 fps; sleep = frame_period - work_time. Precompute sin/cos and distance/angle tables for trig-heavy effects.

Verified in project code (cmd-art core.py play): enters alt screen, hides cursor, NOWRAP, CLEAR once, HOME+redraw each frame; finally restores RESET/WRAP/SHOW/ALT_LEAVE.

**Source:** https://www.a1k0n.net/2011/07/20/donut-math.html (framebuffer-cleared-each-frame + write-once discipline; cross-cutting gotchas 2 & 8 in project research R2; alt-screen/cursor sequences per xterm ctlseqs https://invisible-island.net/xterm/ctlseqs/ctlseqs.html )

**See also:** [[cell-grid-model]], [[cursor-and-screen-control]], [[tmux-alternate-screen]], [[ansi-sgr-color]], [[resize-sigwinch-handling]]
