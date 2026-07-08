# Plasma (sum of sines)

A smooth, animated color field made by summing several sine functions of pixel position, then scrolling a color palette rather than recomputing the field.

## Formula / params
- Four sine terms per pixel:
  - `128 + 128*sin(x/16)`
  - `128 + 128*sin(y/8)`
  - `128 + 128*sin((x+y)/16)`
  - `128 + 128*sin(sqrt(x^2 + y^2)/8)`
- Sum the four, then divide by 4 -> value in 0..255.
- Animate the palette only: `paletteShift = int(getTime()/10)`; `buffer = palette[(plasma + paletteShift) % 256]`.
- Ramp: ` .:-=+*#%@`.

## Source
Source: https://lodev.org/cgtutor/plasma.html

## See also
- [[tunnel]]
- [[ascii-luminance-ramp]]
