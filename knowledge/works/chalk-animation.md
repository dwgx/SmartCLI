# chalk-animation — in-place animated text effects

A JS library of animated text effects (rainbow, pulse, glitch, radar, neon, karaoke). Its exact in-place redraw escape and per-frame formulas are directly reimplementable.

**Source:** https://github.com/bokub/chalk-animation (verified: `index.js`)

## How it works
- **Redraw:** a frame counter increments each render; redraw is `\x1b[<lines>F \x1b[G \x1b[2K` (cursor up N lines, go to column 1, erase line) then reprint. Loop via `setTimeout(delay / speed)`.
- **Effect math:**
  - *rainbow* — `hue = 5 * frame`, a 2-stop HSV long-spin.
  - *pulse* — 120-frame cycle red↔white with a reverse-after-hold.
  - *glitch* — modulo-sum blanking plus random character corruption.
  - *radar* — grayscale sweep, `depth = len * 0.2`, `shade = (depth - pos) * step`.
  - *neon* — parity flip between dim and bold magenta.
  - *karaoke* — left→right amber fill with a 10-frame lead-in.
- **Default delays (ms):** rainbow 15, pulse 16, glitch 55, radar 50, neon 500, karaoke 50.

## What to borrow
- The exact in-place line-overwrite escape `\x1b[nF\x1b[G\x1b[2K` — the minimal, portable way to animate a fixed block without a full clear (relates to [[flicker-free-rendering]]).
- The per-frame formulas are drop-in effect kernels; rainbow is a variant of [[hsv-cycling-lolcat]].

## See also
- [[hsv-cycling-lolcat]]
- [[color-interpolation]]
- [[flicker-free-rendering]]
