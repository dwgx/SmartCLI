# sl — the steam-locomotive sprite scroller

Runs a full ASCII steam train across the screen when you mistype `ls`. A minimal, canonical sprite-scroll animation.

**Source:** https://github.com/mtoyoda/sl — constants verified against `sl.c` (v5.03) + `sl.h` (v5.02) (2026-07-08).

## How it works
- The train is stored as multi-line ASCII frames in string arrays; three engines (D51, C51, SL-logo) each with **6 animation patterns**.
- Main loop `for (x = COLS-1; ; --x)` decrements x by 1 per frame from the right edge, redraws via a custom blit (`mvaddch` cell-by-cell, skipping chars scrolled off the left), then `refresh()` + `usleep(40000)` (**40 ms/frame, ~25 fps**).
- Wheels/exhaust cycle by modulo on x: `d51[(D51LENGTH + x) % D51PATTERNS]` (6 patterns); the logo cycles every 3 columns (`/3`), the waving man every 12 (`/12 % 2`).
- Traps `SIGINT` with `signal(SIGINT, SIG_IGN)` so `^C` won't kill it.
- Exact dims (`sl.h`): D51 = 10 rows × len 83 × 6 patterns; C51 = 11 × 87 × 6; LOGO = 6 × 84 × 6 (no CARLENGTH/COALLENGTH macros — car/coal are string-literal art).

## What to borrow
- The **sprite-scroll** primitive: a static glyph block blitted at a moving `(x, y)` with a small frame cycle for sub-animation (wheels, exhaust). This is the simplest entity type in a scene renderer.

## See also
- [[sprite-scroll]]
- [[cell-grid-model]]
