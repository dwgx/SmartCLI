# R2 — Math / 3D Animation Techniques for ASCII/ANSI Terminals

> **Archived first-pass research** — superseded by [`../knowledge/sources/`](../knowledge/sources/); folded into [`../knowledge/effects/`](../knowledge/effects/README.md). See [`README.md`](README.md). Kept for provenance.


Raw research findings with exact formulas, constants, ASCII ramps and source URLs.
Compiled 2026-07-07 from 4 parallel codex web-search runs + direct WebFetch cross-check of a1k0n.net.

Standard grayscale ASCII ramp used throughout (dark to bright, 10 chars):
`" .:-=+*#%@"`
Donut uses its own 12-char ramp: `.,-~:;=!*#$@`

---

## 1. Spinning ASCII Donut / Torus (Andy Sloane donut.c)

Source (VERIFIED via direct fetch): https://www.a1k0n.net/2011/07/20/donut-math.html
Original obfuscated donut.c (2006).

### Constants
```
R1 = 1        // tube (cross-section circle) radius
R2 = 2        // distance from center of torus to center of tube
K2 = 5        // viewer distance (added to z)
K1 = screen_width * K2 * 3 / (8 * (R1 + R2))   // projection scale derived from screen size
theta_spacing = 0.07   // step for theta (around tube cross-section)
phi_spacing   = 0.02   // step for phi (around torus center)
ramp = ".,-~:;=!*#$@"   // 12 chars, dim -> bright
```
Original 80x22 donut.c effectively used center (40,12), Kx=30, Ky=15, K2=5.

### Parameters
- theta in [0, 2pi): sweeps the tube cross-section circle (radius R1, centered at (R2,0,0))
- phi   in [0, 2pi): revolves that circle around the torus center axis
- A = rotation about X axis, B = rotation about Z axis (the two animated spin angles)

### Base circle (before revolution), centered at (R2,0,0):
```
(R2 + R1*cos(theta), R1*sin(theta), 0)
```
Helper terms: `circlex = R2 + R1*cos(theta)`, `circley = R1*sin(theta)`

### Full 3D world coordinates after rotation by A (x-axis) and B (z-axis):
```
x = circlex*(cos(B)*cos(phi) + sin(A)*sin(B)*sin(phi)) - circley*cos(A)*sin(B)
y = circlex*(sin(B)*cos(phi) - sin(A)*cos(B)*sin(phi)) + circley*cos(A)*cos(B)
z = K2 + cos(A)*circlex*sin(phi) + circley*sin(A)
```
(z already includes the K2 viewer-distance offset.)

### Projection (one-over-z):
```
ooz = 1 / z                                  // "one over z"; larger ooz = closer
xp = (int)(screen_width/2  + K1*ooz*x)
yp = (int)(screen_height/2 - K1*ooz*y)       // y negated: up in 3D = down on screen
```
General projection eqn: `(x', y') = (K1*x/(K2+z), K1*y/(K2+z))`

### Luminance (surface normal dot light direction L=(0,1,-1), i.e. Ny - Nz):
Surface normal before rotation = (cos(theta), sin(theta), 0), rotated same as position.
```
L = cos(phi)*cos(theta)*sin(B)
    - cos(A)*cos(theta)*sin(phi)
    - sin(A)*sin(theta)
    + cos(B)*(cos(A)*sin(theta) - cos(theta)*sin(A)*sin(phi))
```
L ranges from -sqrt(2) to +sqrt(2). If L <= 0 the surface faces away -> skip.

### Character mapping + z-buffer:
```
if L > 0:
    if ooz > zbuffer[xp][yp]:               // depth test (bigger ooz wins)
        zbuffer[xp][yp] = ooz
        luminance_index = clamp(floor(L*8), 0, 11)   // 8*sqrt(2) ~= 11.3 -> 12-char ramp
        output[xp][yp] = ".,-~:;=!*#$@"[luminance_index]
```
zbuffer initialized to 0. Framebuffer cleared to spaces each frame.

### Animation:
```
A += 0.04    // per frame
B += 0.02
```

---

## 2. Rotating Sphere with Lambert Shading

Sources: https://en.wikipedia.org/wiki/Sphere , https://en.wikipedia.org/wiki/Lambertian_reflectance , https://en.wikipedia.org/wiki/Rotation_matrix

### Parametric sphere, radius r, centered at origin:
```
u in [0, pi]    (polar), v in [0, 2pi) (azimuth)
p = ( r*sin(u)*cos(v),  r*sin(u)*sin(v),  r*cos(u) )
```
Surface normal (origin-centered sphere): `N = p / r = normalize(p)`

### Rotation matrices (column-vector convention, R = Rz(g)*Ry(b)*Rx(a)):
```
Rx(a) = [1 0 0; 0 cos(a) -sin(a); 0 sin(a) cos(a)]
Ry(b) = [cos(b) 0 sin(b); 0 1 0; -sin(b) 0 cos(b)]
Rz(c) = [cos(c) -sin(c) 0; sin(c) cos(c) 0; 0 0 1]
```
```
p_rot = R * p
N_rot = R * N        // already unit length for pure rotation
```

### Projection:
```
z_view = p_rot.z + distance
ooz = 1 / z_view
xp = cx + fov * p_rot.x / z_view
yp = cy - fov * p_rot.y / z_view
```

### Lambert diffuse shading:
```
Ldir = normalize((lx, ly, lz))
diffuse = max(0, dot(N_rot, Ldir))
ramp = " .:-=+*#%@"
idx = clamp(floor(diffuse * (len(ramp)-1)), 0, len(ramp)-1)
char = ramp[idx]
```
z-buffer same as donut (keep nearest by ooz). Animate alpha+=0.03, beta+=0.02, gamma+=0.01.

Implementation note: iterate u,v finely enough (step ~0.02-0.05) that projected points fill each cell; the z-buffer resolves overlap. Correct for terminal cell aspect (~2:1 height:width) by scaling y or fov.

---

## 3. Rotating Cube / Wireframe

Sources: rotation matrices (above), https://en.wikipedia.org/wiki/Bresenham%27s_line_algorithm

### 8 vertices (side 2s, e.g. s=1):
```
v0=(-s,-s,-s) v1=(s,-s,-s) v2=(s,s,-s) v3=(-s,s,-s)
v4=(-s,-s,s)  v5=(s,-s,s)  v6=(s,s,s)  v7=(-s,s,s)
```
### 12 edges:
```
(0,1)(1,2)(2,3)(3,0)   // back face
(4,5)(5,6)(6,7)(7,4)   // front face
(0,4)(1,5)(2,6)(3,7)   // connectors
```
### Transform + project (same R matrices as sphere):
```
p_rot = R * vertex
z_view = p_rot.z + distance         // distance ~4
xp = cx + p_rot.x * fov / z_view
yp = cy - p_rot.y * fov / z_view
fov = min(width, height) * 0.8
```
### Bresenham line between projected vertices:
```
dx =  abs(x1-x0);  sx = x0<x1 ? 1 : -1
dy = -abs(y1-y0);  sy = y0<y1 ? 1 : -1
err = dx + dy
loop:
  plot(x0,y0)
  if x0==x1 and y0==y1: break
  e2 = 2*err
  if e2 >= dy: err += dy; x0 += sx
  if e2 <= dx: err += dx; y0 += sy
```
Shading: fixed edge char '#', vertices '@'; OR per-edge depth shade
`t = clamp(1-(avgDepth-near)/(far-near),0,1)` -> ramp `.:-=+*#%@`.
Animate alpha+=0.03, beta+=0.04, gamma+=0.02.

---

## 4. 3D Tunnel Effect

Source: Lode Vandevenne, https://lodev.org/cgtutor/tunnel.html

### Constants:
```
texWidth = 256, texHeight = 256, ratio = 32.0, pi = 3.14159265358979
```
### Precomputed per-pixel tables (center cx,cy):
```
dx = x - cx;  dy = y - cy;  r = sqrt(dx*dx + dy*dy)
distanceTable[y][x] = int(ratio * texHeight / r) % texHeight
angleTable[y][x]    = (unsigned)(0.5 * texWidth * atan2(dy, dx) / pi)
```
### Per frame (animation = time in seconds):
```
shiftDistance = int(texHeight * 1.0  * animation)
shiftAngle    = int(texWidth  * 0.25 * animation)
v = (distanceTable[y][x] + shiftDistance) & (texHeight-1)   // &(size-1) if power of two, else %
u = (angleTable[y][x]    + shiftAngle)    & (texWidth-1)
texel = texture[v][u]
```
### ASCII depth/fog shading:
```
depth = distanceTable[y][x] / (texHeight-1.0)
charIndex = clamp(int((1.0 - depth) * (rampLen-1)), 0, rampLen-1)
ch = " .:-=+*#%@"[charIndex]
// with texture: final = texelBrightness/255 * (1-depth)
```
For terminal without a texture, use a checkerboard/XOR texture: `texture[v][u] = ((u^v) & 8) ? light : dark` or `((u>>4)^(v>>4))&1`.

---

## 5. Perspective Starfield

Sources: https://slicker.me/javascript/starfield_flythrough.htm , https://ogldev.org/www/tutorial12/tutorial12.html

### Star state + constants:
```
star.x in [-800,800], star.y in [-600,600], star.z in [1,1000]
maxZ = 1000.0, focalLength = 128.0
```
### Update + respawn:
```
star.z -= speed
if star.z <= 1.0:
    star.x = rand(-800,800); star.y = rand(-600,600); star.z = maxZ
```
### Perspective projection:
```
k = focalLength / star.z
sx = centerX + star.x * k
sy = centerY + star.y * k
```
### Brightness by depth -> ASCII:
```
brightness = clamp(1 - star.z/maxZ, 0, 1)
ramp = " .+*#"; idx = int(brightness*(len(ramp)-1)); ch = ramp[idx]
```
Threshold variant:
```
z/maxZ >= 0.80 -> '.'   >=0.55 -> '+'   >=0.30 -> '*'   >=0.10 -> '#'   else '@'
```
Motion trails: draw Bresenham line from old projection (oldZ) to new (newZ), brightness from newZ.

---

## 6. Plasma Effect (sum of sines)

Source: Lode Vandevenne, https://lodev.org/cgtutor/plasma.html

### Lode's static 4-sine:
```
color = ( (128+128*sin(x/16.0)) + (128+128*sin(y/8.0))
        + (128+128*sin((x+y)/16.0)) + (128+128*sin(sqrt(x*x+y*y)/8.0)) ) / 4
```
### Animated (t = time):
```
s = sin(x/16.0 + t) + sin(y/8.0 + t) + sin((x+y)/16.0 + t) + sin(sqrt(x*x+y*y)/8.0 + t)
// each sine in [-1,1] -> s in [-4,4]
n = (s + 4.0) / 8.0           // normalize to [0,1]
```
### ASCII / palette:
```
ramp = " .:-=+*#%@"; idx = int(n*(len(ramp)-1)); ch = ramp[idx]
// palette cycling: paletteIndex = (baseIndex + int(t*32.0)) % 256
```
Color: map n to an HSV hue or a red-green-blue sine palette:
`r=128+127*sin(n*PI), g=128+127*sin(n*PI+2), b=128+127*sin(n*PI+4)`.

---

## 7. Fire Effect (cellular cooling buffer)

Source: Lode Vandevenne, https://lodev.org/cgtutor/fire.html

### Buffer fire[h][w], heat 0..255. Seed bottom row each frame:
```
fire[h-1][x] = random(0, 255)
```
### Lode's exact propagation kernel (4 cells below) + cooling:
```
sum = fire[(y+1)%h][(x-1+w)%w] + fire[(y+1)%h][x]
    + fire[(y+1)%h][(x+1)%w] + fire[(y+2)%h][x]
fire[y][x] = (sum * 32) / 129          // divide by 4.03125: average * (128/129) cooling
```
### Simpler additive-decay variant:
```
avg = (belowLeft + below + belowRight + below2) / 4
newVal = max(0, avg - decay)           // decay=1 tall, 2 medium, 3-4 short flames
```
### ASCII + ANSI color:
```
ramp = " .:-=+*#%@"
idx = clamp(fire[y][x]*rampLen/256, 0, rampLen-1)
heat<32 -> black/dim; <80 -> red(31); <140 -> bright red(91); <200 -> yellow(33); else white(97)
```

---

## 8. Conway's Game of Life

Sources: https://conwaylife.com/ , https://conwaylife.com/wiki/Tutorials/Rules

### Moore 8-neighbor count:
```
N = grid[y-1][x-1]+grid[y-1][x]+grid[y-1][x+1]
  + grid[y][x-1]              +grid[y][x+1]
  + grid[y+1][x-1]+grid[y+1][x]+grid[y+1][x+1]
```
Border: dead border (out=0) OR toroidal wrap `grid[(y+dy+h)%h][(x+dx+w)%w]`.

### Transition (B3/S23):
```
next[y][x] = 1  if N==3 OR (grid[y][x]==1 AND N==2)
           = 0  otherwise
```
Double-buffer: compute all next[] from grid[], then swap. Render dead=' ', alive='#' or '█'.

---

## 9. Mandelbrot Set Zoom

Sources: https://en.wikipedia.org/wiki/Plotting_algorithms_for_the_Mandelbrot_set , https://www.linas.org/art-gallery/escape/smooth.html

### Iteration: z0=0, z_{n+1}=z_n^2+c, escape |z|>2 (zx^2+zy^2>4):
```
zx' = zx*zx - zy*zy + cx
zy' = 2*zx*zy + cy
```
### Screen -> complex mapping (center, scale):
```
cx = centerX + (px - w/2) * scale / w
cy = centerY + (py - h/2) * scale / w     // or - for math-up Y
```
### Zoom animation:
```
scale(t) = initialScale * zoomFactor^t     // 0<zoomFactor<1 to zoom in, e.g. 3.0*0.97^t
centerX = -0.743643887037151, centerY = 0.131825904205330   // classic seahorse point
```
### ASCII mapping:
```
ramp = " .:-=+*#%@"; R = len(ramp)-1
if n == max_iter: ch = ' '                 // inside set
else: ch = ramp[floor((n/max_iter)^0.5 * R)]   // sqrt gives nicer distribution
```
### Smooth coloring (optional, reduces banding):
```
mu = n + 1 - log(log(sqrt(zx*zx+zy*zy)))/log(2)
v = clamp(mu/max_iter,0,1); ch = ramp[floor(v*R)]
```

---

## 10. Julia Set (animated)

Source: https://en.wikipedia.org/wiki/Julia_set

Same iteration as Mandelbrot but z0 = pixel coordinate, c = fixed constant.
```
zx = centerX + (px - w/2)*scale/w
zy = centerY - (py - h/2)*scale/w
```
Static example: c = -0.7 + 0.27015i.
### Animate c around a circle:
```
cx = 0.7885 * cos(t)
cy = 0.7885 * sin(t)
t = frameIndex * 0.03
```
ASCII ramp identical to Mandelbrot; interior (n==max_iter) -> ' '.

---

## 11. Perlin / Value Noise Fields

Sources: https://cs.nyu.edu/~perlin/noise/ , https://developer.nvidia.com/gpugems (ch5) , https://www.scratchapixel.com/lessons/procedural-generation-virtual-worlds/perlin-noise-part-2/perlin-noise.html

### Fade (improved Perlin) + lerp:
```
fade(t) = 6t^5 - 15t^4 + 10t^3
lerp(a,b,t) = a + t*(b-a)
```
### Value noise (lattice of random values V(i,j) in [0,1]):
```
x0=floor(x); y0=floor(y); tx=x-x0; ty=y-y0
u=fade(tx); v=fade(ty)
a=V(x0,y0); b=V(x1,y0); c=V(x0,y1); d=V(x1,y1)
noise = lerp( lerp(a,b,u), lerp(c,d,u), v )    // in [0,1]
```
### Classic Perlin gradient noise:
Gradient table (2D): (1,0)(-1,0)(0,1)(0,-1)(1,1)(-1,1)(1,-1)(-1,-1), diagonals /sqrt(2).
```
d00=(tx,ty) d10=(tx-1,ty) d01=(tx,ty-1) d11=(tx-1,ty-1)
n00=dot(G(x0,y0),d00) ... n11=dot(G(x1,y1),d11)
u=fade(tx); v=fade(ty)
perlin = lerp( lerp(n00,n10,u), lerp(n01,n11,u), v )   // in ~[-1,1]
display = 0.5*perlin + 0.5
```
### fBm / octaves:
```
persistence=0.5, lacunarity=2.0, octaves=4..8
sum=0; amp=1; freq=base; norm=0
for k in octaves:
    sum += amp*noise(x*freq, y*freq); norm += amp
    amp *= 0.5; freq *= 2.0
fbm = sum/norm                          // [0,1] if noise is [0,1]
```
Animate: scroll `noise(x+sx*t, y+sy*t)` or use 3D noise with z=t.
ASCII: `ch = " .:-=+*#%@"[floor(clamp(v,0,1)*(len-1))]`.

---

## 12. Boids Flocking (Craig Reynolds)

Sources: https://www.red3d.com/cwr/boids/ , https://www.red3d.com/cwr/papers/1987/boids.html , https://www.kfish.org/boids/pseudocode.html

### State per boid: position p_i, velocity v_i, acceleration a_i.
### Terminal-friendly constants:
```
R_sep=2.0, R_neigh=8.0 (cells)
W_sep=1.50, W_coh=0.010 (Parker /100), W_align=0.125 (Parker /8)
V_max=1.0, A_max=0.08, epsilon=1e-6
```
### Neighbor sets: N_i = {j: d_ij<R_neigh}, N_sep = {j: d_ij<R_sep}.
### Three rules:
```
Separation: F_sep = sum_{j in N_sep} (p_i - p_j)/(d_ij^2 + eps)
Cohesion:   center = mean(p_j over N_i);  F_coh = center - p_i    (0 if N_i empty)
Alignment:  avgVel = mean(v_j over N_i);  F_align = avgVel - v_i  (0 if N_i empty)
```
### Combine + integrate:
```
a_i = W_sep*F_sep + W_coh*F_coh + W_align*F_align
if |a_i|>A_max: a_i = normalize(a_i)*A_max
v_i += a_i;  if |v_i|>V_max: v_i = normalize(v_i)*V_max
p_i += v_i
```
Parker classic constants: F_coh=(center-p)/100, F_align=(avgVel-v)/8, if dist<100: F_sep-=(p_j-p_i), V_max=10.
### Render glyph by heading:
```
angle = atan2(v.y, v.x)
chars = [">","\\","v","/","<","\\","^","/"]
glyph = chars[round(angle/(2*pi)*8) mod 8]
```
Add edge wrap or steer-back-from-border to keep flock on screen.

---

## 13. Particle System with Gravity

Source: Reeves particle systems https://dl.acm.org/doi/10.1145/357318.357320

### State: p=(x,y), v=(vx,vy), age, life. Terminal y is DOWN so gravity positive.
```
g = 30.0 cells/s^2, dt = 1/60
```
### Semi-implicit Euler (stable):
```
v.y += g*dt
p   += v*dt
age += dt
```
### Respawn:
```
if age>=life or p.y>=screen_height:
    p = emitter + rand_offset
    v.x = rand(-8,8); v.y = rand(-20,-5)
    age = 0; life = rand(0.6, 2.0)
```
### Age -> brightness -> ASCII:
```
t = clamp(age/life,0,1); brightness = 1-t
ch = " .:-=+*#%@"[floor(brightness*9)]   // spawn '@' -> death ' '
```
Truecolor spark: `r=255, g=round(64+191*brightness), b=round(32*brightness)`.

---

## 14. Matrix Digital Rain

Source: https://en.wikipedia.org/wiki/Digital_rain , ANSI: https://tforgione.fr/posts/ansi-escape-codes/

### Per-column state:
```
x=col index; head_y (float); speed=rand(0.25,1.25); L=rand_int(8,30); delay; chars[y]
charset = "ABC...Z0-9@#$%&*+-=/\|[]{}<>"  (+ half-width katakana ｱｲｳ... if font supports)
```
### Update per frame:
```
if delay>0: delay-=1; skip
head_y += speed
```
### For each visible row y:
```
dist = head_y - y                 // visible if 0 <= dist <= L
brightness = clamp(1 - dist/L, 0, 1)
if floor(head_y)==y: brightness=1; color = bright white/green (head)
if rand()<0.02 or chars[y] empty: chars[y]=random_choice(charset)   // mutation
```
### Clear tail + reset:
```
tail_y = floor(head_y - L - 1); if in range: draw ' ' at (x,tail_y)
if head_y - L > screen_height:
    head_y = -rand_int(0,screen_height); speed=rand(0.25,1.25)
    L=rand_int(8,30); delay=rand_int(0,120); clear column
```
### Truecolor gradient (green, gamma 1.7):
```
b = clamp(1-dist/L,0,1); q = b^1.7
r=0; g=round(32+223*q); blue=round(8+72*q)
// dist=0 -> rgb(0,255,80); dist=L/2 -> ~rgb(0,101,30); dist=L -> rgb(0,32,8)
head = "\x1b[38;2;220;255;220m"; trail = "\x1b[38;2;{r};{g};{blue}m"
```
### 256-color gradient (xterm cube code = 16 + 36*R + 6*G + B, R,G,B in 0..5):
```
b=clamp(1-dist/L,0,1); G=clamp(1+round(4*b),1,5); code=16+6*G
// b~0->22 dark green ... b~1->46 bright green
trail="\x1b[38;5;{code}m"; head="\x1b[38;5;255m"; reset="\x1b[0m"
```

---

## Cross-cutting implementation gotchas

1. Terminal cell aspect ratio is ~2:1 (height:width). For circular/3D shapes, halve Y or multiply x-scale by ~2 (donut projection already uses different Kx/Ky). Sphere/tunnel/plasma need aspect correction or they look squashed.
2. Double-buffer everything; build a full frame string and write once. Use `\x1b[H` (cursor home) or `\x1b[2J` between frames; hide cursor `\x1b[?25l`, restore `\x1b[?25h` on exit.
3. z-buffer (donut/sphere) initialized to 0 each frame; keep the fragment with the largest ooz=1/z.
4. Fractals: precompute the ramp; escape test uses zx^2+zy^2>4 (avoid sqrt in the loop). Deep zoom eventually needs higher precision than float64.
5. Perlin needs a permutation table (Ken Perlin's 256-entry doubled table) for reproducible hashing; value noise can use a cheap hash of integer coords.
6. Fire/plasma/tunnel: precompute the distance/angle tables once (they don't change), only the shift offsets change per frame.
7. ANSI color: emit color escape only when it changes between adjacent cells to cut output size dramatically. Always reset `\x1b[0m` at line/frame end.
8. Frame pacing: target ~30-60 fps; sleep = frame_period - work_time. Trig-heavy effects (donut, plasma) benefit from precomputed sin/cos tables.
9. Windows terminals: enable virtual-terminal processing (ENABLE_VIRTUAL_TERMINAL_PROCESSING) so ANSI escapes work in classic conhost; Windows Terminal handles them natively.
