# Terminal Cell Aspect Ratio

**Statement:** Terminal cells are roughly twice as tall as they are wide (~2:1 height:width), so circular and 3D shapes must be aspect-corrected or they render squashed.

**Real params / correction:**
```
Cell aspect ratio ~ 2:1 (height:width).
Fixes for round/3D shapes:
  - halve Y, OR multiply x-scale by ~2, OR use different Kx/Ky projection scales.
  - donut.c already bakes this in via distinct horizontal/vertical projection constants
    (original 80x22 donut used Kx=30, Ky=15).
  - Euclidean path length in animation engines often DOUBLES the row delta to compensate
    (cells ~2x tall) — e.g. TTE Motion/Path length calc.
Sphere, tunnel, plasma need explicit aspect correction (scale y or fov) or they look squashed.
```

**Source:** https://www.a1k0n.net/2011/07/20/donut-math.html (projection scale from screen size; aspect note is cross-cutting gotcha 1 in project research R2, and the row-delta-doubling appears in TTE Motion, research R1 PART C)

**See also:** [[sub-cell-resolution]], [[cell-grid-model]], [[cell-width-measurement]], [[box-model-on-cell-grid]]
