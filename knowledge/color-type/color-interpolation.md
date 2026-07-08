# Color Interpolation & sRGB Gamma

Blend between colors by interpolating each channel linearly; for perceptually correct blends, convert sRGB to linear light first.

- Per-channel linear interpolation: `c = c0 + t*(c1 - c0)`.
- Multi-stop gradient: find the interval containing `x`, then local `t = (x - x0)/(x1 - x0)`.
- sRGB → linear: `linear = s <= 0.04045 ? s/12.92 : ((s+0.055)/1.055)^2.4`.
- linear → sRGB: `s = lin <= 0.0031308 ? 12.92*lin : 1.055*lin^(1/2.4) - 0.055`.
- Gamma matters: interpolating in sRGB space directly (without linearization) shifts midpoint brightness.

**Source:** https://www.w3.org/TR/css-color-4/#color-conversion-code and https://fgiesen.wordpress.com/2012/08/15/linear-interpolation-past-present-and-future/

**See also:** [[hsv-cycling-lolcat]], [[palette-viridis]], [[truecolor-24bit]]
