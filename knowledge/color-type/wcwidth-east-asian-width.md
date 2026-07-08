# wcwidth / East Asian Width

Compute the terminal column width of a Unicode code point (Kuhn's `wcwidth.c`, informed by UAX #11 East Asian Width).

Width **0** (zero-width):
- Categories Mn + Me + Cf (excluding U+00AD soft hyphen), plus U+1160..U+11FF (Hangul Jamo medial/final) and U+200B.
- Combining table starts at U+0300..U+036F; includes variation selectors U+FE00..U+FE0F and U+FEFF.

Width **-1** (non-printable): `ucs < 32 || (ucs >= 0x7f && ucs < 0xa0)`.

Width **2** (wide) — requires `ucs >= 0x1100` and one of:
- 0x1100..0x115F, 0x2329/0x232A, 0x2E80..0xA4CF (excluding 0x303F), 0xAC00..0xD7A3,
  0xF900..0xFAFF, 0xFE10..0xFE19, 0xFE30..0xFE6F, 0xFF00..0xFF60, 0xFFE0..0xFFE6,
  0x20000..0x2FFFD, 0x30000..0x3FFFD.

Everything else is width 1.

**Source:** https://www.cl.cam.ac.uk/~mgk25/ucs/wcwidth.c and https://www.unicode.org/reports/tr11/

**See also:** [[image-to-ansi-halfblock]], [[box-drawing]], [[figlet-flf-spec]]
