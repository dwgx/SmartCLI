# Matrix digital rain

Independent vertical columns of glyphs, each with a bright falling "head" and a fading tail; glyphs are random and periodically re-randomized, respawning at the top after a random delay.

## Formula / params
- Each column falls independently at its own speed.
- The head is brightest; the tail fades to black over N cells.
- After a column exits, it respawns at the top following a random delay.
- Glyphs are chosen at random and periodically re-randomized (canonically mirrored Katakana plus Chicago-typeface characters).
- Ramp (monochrome): `@` / `#` (head) -> `+` / `=` -> `:` / `.` -> ` `.

## Source
Source: https://en.wikipedia.org/wiki/Digital_rain
Source: https://github.com/Rezmason/matrix
Source: https://elgoog.im/assets/p/matrix/shaders/glsl/rainPass.raindrop.frag.glsl

## See also
- [[ascii-luminance-ramp]]
