# Donut (rotating ASCII torus)

A spinning torus rendered to ASCII by sampling `(theta, phi)` surface points, rotating by angles A/B, projecting with a z-buffer, and picking a glyph from surface luminance.

## Formula / params
- Constants: `R1=1` (tube radius), `R2=2` (center radius), `K2=5` (viewer distance), `K1 = screen_width*K2*3 / (8*(R1+R2))` (scale so torus fills ~3/8 of width).
- Step sizes: `theta += 0.07`, `phi += 0.02`.
- Circle point before rotation: `circlex = R2 + R1*costheta`, `circley = R1*sintheta`.
- Rotated 3D point (A = x-axis spin, B = z-axis spin):
  - `x = circlex*(cosB*cosphi + sinA*sinB*sinphi) - circley*cosA*sinB`
  - `y = circlex*(sinB*cosphi - sinA*cosB*sinphi) + circley*cosA*cosB`
  - `z = K2 + cosA*circlex*sinphi + circley*sinA`
- Projection: `xp = w/2 + K1*(1/z)*x`, `yp = h/2 - K1*(1/z)*y`.
- Z-buffer: store `ooz = 1/z`; draw only if `ooz > zbuffer[xp][yp]`.
- Luminance: `L = cosphi*costheta*sinB - cosA*costheta*sinphi - sinA*sintheta + cosB*(cosA*sintheta - costheta*sinA*sinphi)`; plot only when `L > 0`.
- Ramp: `".,-~:;=!*#$@"` (12 chars); index `= L*8` giving 0..11 (since `8*sqrt(2) ~= 11.3`).

## Source
Source: https://www.a1k0n.net/2011/07/20/donut-math.html

## See also
- [[perspective-projection]]
- [[rotation-matrix]]
- [[ascii-luminance-ramp]]
