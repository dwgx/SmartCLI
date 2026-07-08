# Image → ANSI Half-Block (chafa)

Render an image in a terminal at double vertical resolution by mapping two stacked pixels into one character cell.

- One cell = two vertical pixels: foreground = top pixel, background = bottom pixel.
- Print `▀` U+2580 UPPER HALF BLOCK; the fg fills the top half, bg the bottom half, doubling vertical resolution.
- Minimal half-block mode: `chafa --symbols vhalf`.
- Symbol classes available: half / hhalf / vhalf, sextant, quad, block, braille, ascii, wide. Sextants (U+1FB00 block) subdivide the cell more finely.

**Source:** https://hpjansson.org/chafa/ , https://hpjansson.org/chafa/man/ , https://github.com/hpjansson/chafa

**See also:** [[truecolor-24bit]], [[box-drawing]], [[wcwidth-east-asian-width]]
