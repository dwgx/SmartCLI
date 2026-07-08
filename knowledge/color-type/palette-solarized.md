# Palette: Solarized

Ethan Schoonover's 16-color precision palette with balanced lightness relationships for light/dark backgrounds.

Exact hex (16):
- base03 `#002b36`, base02 `#073642`, base01 `#586e75`, base00 `#657b83`
- base0 `#839496`, base1 `#93a1a1`, base2 `#eee8d5`, base3 `#fdf6e3`
- yellow `#b58900`, orange `#cb4b16`, red `#dc322f`, magenta `#d33682`
- violet `#6c71c4`, blue `#268bd2`, cyan `#2aa198`, green `#859900`

## Usage
The eight `base*` tones form a monotone lightness ramp; the trick is they swap roles between themes. **Dark:** background `base03`, highlights `base02`, body text `base0`, emphasized `base1`. **Light:** background `base3`, highlights `base2`, body `base00`, emphasized `base01`. The 8 accent hues (yellow→green) stay fixed across both themes — pick accents by role, backgrounds by theme. Because lightness relationships are balanced, do NOT interpolate across `base*` for a gradient; use them as discrete UI tones and reserve [[color-interpolation]] for the accent hues.

**Source:** https://ethanschoonover.com/solarized/

**See also:** [[palette-viridis]], [[palette-synthwave84]], [[256-color-cube]]
