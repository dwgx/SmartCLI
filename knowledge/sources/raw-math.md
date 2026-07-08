# ANSI/ASCII Effect Math — Authoritative Raw Findings

Every fact below carries a source URL. Formulas quoted verbatim from the cited
source where possible. Gathered 2026-07-08 via direct WebFetch/curl on canonical
pages (codex live-search dispatcher was quota-exhausted: HTTP 403 "预扣费额度失败",
so fell back to WebFetch + raw curl per fallback instructions).

Verbatim-quoted source files also cached locally during research:
- Perlin improved noise Java: /tmp/perlin.html
- DOOM PSX fire flames.html: /tmp/flames.html

---

## 1. Andy Sloane donut.c — spinning ASCII torus

Source: https://www.a1k0n.net/2011/07/20/donut-math.html

Torus = circle of radius R1 centered at (R2,0,0), swept about y-axis by phi,
then whole donut rotated about x-axis by A and about z-axis by B.

Constants (verbatim):
```c
const float R1 = 1;
const float R2 = 2;
const float K2 = 5;                                  // viewer-to-donut distance
const float K1 = screen_width*K2*3/(8*(R1+R2));      // projection scale / FOV
const float theta_spacing = 0.07;                    // tube angle step, 0..2pi
const float phi_spacing   = 0.02;                    // revolve step, 0..2pi
```

Cross-section circle before revolving:
```c
float circlex = R2 + R1*costheta;
float circley = R1*sintheta;
```

Full rotated 3D point (verbatim):
```c
float x = circlex*(cosB*cosphi + sinA*sinB*sinphi) - circley*cosA*sinB;
float y = circlex*(sinB*cosphi - sinA*cosB*sinphi) + circley*cosA*cosB;
float z = K2 + cosA*circlex*sinphi + circley*sinA;
float ooz = 1/z;                                     // "one over z"
```

Perspective projection (x',y') = (K1*x/(K2+z), K1*y/(K2+z)); in code with ooz,
y negated because screen y points down:
```c
int xp = (int)(screen_width/2  + K1*ooz*x);
int yp = (int)(screen_height/2 - K1*ooz*y);
```

Z-buffer stores 1/z (background init 0 = infinite depth); draw only if nearer:
```c
if (ooz > zbuffer[xp][yp]) { zbuffer[xp][yp] = ooz; ... }
```

Luminance = surface normal (rotated (cos theta, sin theta, 0)) dotted with light
direction (0,1,-1), i.e. L = N.y - N.z (verbatim):
```c
float L = cosphi*costheta*sinB - cosA*costheta*sinphi -
          sinA*sintheta + cosB*(cosA*sintheta - costheta*sinA*sinphi);
```
L ranges -sqrt(2)..+sqrt(2). Plot only when L > 0 (surface faces viewer).

Character ramp (12 chars, dim->bright) and index (verbatim):
```c
int luminance_index = L*8;                 // 8*sqrt(2) = 11.3 -> index 0..11
output[xp][yp] = ".,-~:;=!*#$@"[luminance_index];
```

---

## 2. Rotating 3D cube / wireframe

Source (basic 3D rotation matrices): https://en.wikipedia.org/wiki/Rotation_matrix
Source (perspective divide): https://en.wikipedia.org/wiki/3D_projection

Basic rotation matrices for column vectors R*v (right-hand rule, positive theta
CCW when axis points toward observer):

Rx(t):
```
[ 1    0       0    ]
[ 0  cos t  -sin t  ]
[ 0  sin t   cos t  ]
```
Ry(t):
```
[  cos t   0   sin t ]
[   0      1    0    ]
[ -sin t   0   cos t ]      # note: -sin is bottom-left for Ry
```
Rz(t):
```
[ cos t  -sin t   0 ]
[ sin t   cos t   0 ]
[   0       0     1 ]
```

Perspective projection (from 3D projection article, "B_x = A_x (B_z/A_z)"):
screen_x = (x/z)*focal + cx ; screen_y = (y/z)*focal + cy. Draw the 12 cube
edges as lines (Bresenham) between projected vertices.
Bresenham line algorithm source: https://en.wikipedia.org/wiki/Bresenham%27s_line_algorithm

---

## 3. 3D starfield (fly-through)

Source (projection math): https://en.wikipedia.org/wiki/3D_projection
(Article confirms perspective divide "B_x = A_x (B_z/A_z)" and "distant objects
appear smaller than nearer objects"; per-frame motion/respawn/brightness are the
standard starfield demo conventions layered on top of that projection.)

Each star (x,y,z). Per frame:
```
z -= speed
if z <= 0:  x = rand(-w,w); y = rand(-h,h); z = max_depth   # respawn far
sx = (x / z) * scale + center_x
sy = (y / z) * scale + center_y
k  = 1 - z / max_depth        # 0 far .. 1 near
brightness = k * 255 ; size = k * max_size
```
ASCII ramp by depth: nearest -> "@" / "*", mid -> "+" / ".", far -> " ".

---

## 4. Tunnel effect (precomputed distance/angle tables)

Source: https://lodev.org/cgtutor/tunnel.html

Per-pixel lookup tables (ratio = 32.0), verbatim:
```c
distance = int(ratio * texHeight /
    sqrt((x - w/2.0)*(x - w/2.0) + (y - h/2.0)*(y - h/2.0))) % texHeight;
angle = (unsigned int)(0.5 * texWidth * atan2(y - h/2.0, x - w/2.0) / 3.1416);
distanceTable[y][x] = distance;
angleTable[y][x]    = angle;
```

Per-frame animation shifts (verbatim):
```c
int shiftX = int(texWidth  * 1.0  * animation);   // forward/back speed
int shiftY = int(texHeight * 0.25 * animation);   // rotation speed
```

Texture lookup (verbatim, split):
```c
texture[(unsigned int)(distanceTable[y][x] + shiftX) % texWidth]
       [(unsigned int)(angleTable[y][x]    + shiftY) % texHeight];
```
Unsigned modulo wraps; texWidth/texHeight should be powers of two.

---

## 5. Plasma effect (sum of sines)

Source: https://lodev.org/cgtutor/plasma.html

Each sine term stays in 0..256 range as `128 + 128*sin(...)`. Sum N terms, divide
by N to renormalize to 0..255, store in plasma[y][x]. Four-sine plasma (verbatim
terms, then `/ 4`):
```c
128.0 + (128.0 * sin(x / 16.0))
128.0 + (128.0 * sin(y / 8.0))
128.0 + (128.0 * sin((x + y) / 16.0))
128.0 + (128.0 * sin(sqrt(double(x * x + y * y)) / 8.0))
// color = (sum of the four) / 4
```
Two-sine variant divides by 2. Distance-to-center term:
`128.0 * sin(sqrt((x-w/2.0)^2 + (y-h/2.0)^2) / 8.0)`.

Palette animation (verbatim): compute plasma buffer once, animate by rotating
palette index:
```c
paletteShift = int(getTime() / 10.0);
buffer[y][x] = palette[(plasma[y][x] + paletteShift) % 256];
```
Palette built continuous (HSVtoRGB over hue, or tileable sine ramps) so rotation
is seamless. ASCII ramp: map 0..255 to " .:-=+*#%@".

---

## 6. Demoscene fire — two canonical algorithms

### 6a. Lode Vandevenne fire (cooling-buffer kernel)
Source: https://lodev.org/cgtutor/fire.html

Seed bottom row with fresh random values every frame (verbatim):
```c
for(int x = 0; x < w; x++) fire[h-1][x] = abs(32768 + rand()) % 256;
```

Propagation/cooling kernel — sum of 3 pixels directly below + 1 pixel two rows
below, times 32 over 129 (effective divisor ~4.0155 > 4 so fire cools/rises),
verbatim:
```c
fire[y][x] =
  ((fire[(y+1)%h][(x-1+w)%w]
  + fire[(y+1)%h][(x)%w]
  + fire[(y+1)%h][(x+1)%w]
  + fire[(y+2)%h][(x)%w]) * 32) / 129;
```
Divisor rule (verbatim intent): divide by 4 -> fire rises forever; by 5 -> dies
too fast; *16/65 = /4.0625; *4/17 = /4.25. Higher divisor -> lower flames.
No subtractive -1 term in this version; cooling is entirely the >4 divisor.

Palette build (verbatim), hue red->yellow, lightness ramps:
```c
color = HSLtoRGB(ColorHSL(x / 3, 255, std::min(255, x * 2)));
palette[x] = RGBtoINT(color);
buffer[y][x] = palette[fire[y][x]];
```

### 6b. DOOM PSX fire (Fabien Sanglard)
Source: https://fabiensanglard.net/doom_fire_psx/index.html
Canonical code: https://github.com/fabiensanglard/DoomFirePSX/blob/master/flames.html

Dimensions: FIRE_WIDTH = 320, FIRE_HEIGHT = 168. 37-color palette (index 0..36),
black -> red -> orange -> yellow -> white (verbatim rgb triplets):
```
0x07,0x07,0x07  0x1F,0x07,0x07  0x2F,0x0F,0x07  0x47,0x0F,0x07  0x57,0x17,0x07
0x67,0x1F,0x07  0x77,0x1F,0x07  0x8F,0x27,0x07  0x9F,0x2F,0x07  0xAF,0x3F,0x07
0xBF,0x47,0x07  0xC7,0x47,0x07  0xDF,0x4F,0x07  0xDF,0x57,0x07  0xDF,0x57,0x07
0xD7,0x5F,0x07  0xD7,0x5F,0x07  0xD7,0x67,0x0F  0xCF,0x6F,0x0F  0xCF,0x77,0x0F
0xCF,0x7F,0x0F  0xCF,0x87,0x17  0xC7,0x87,0x17  0xC7,0x8F,0x17  0xC7,0x97,0x1F
0xBF,0x9F,0x1F  0xBF,0x9F,0x1F  0xBF,0xA7,0x27  0xBF,0xA7,0x27  0xBF,0xAF,0x2F
0xB7,0xAF,0x2F  0xB7,0xB7,0x2F  0xB7,0xB7,0x37  0xCF,0xCF,0x6F  0xDF,0xDF,0x9F
0xEF,0xEF,0xC7  0xFF,0xFF,0xFF
```

Init: whole buffer 0; bottom row = 36 (verbatim):
```js
firePixels[(FIRE_HEIGHT-1)*FIRE_WIDTH + i] = 36;
```

spreadFire + doFire (verbatim):
```js
function spreadFire(src) {
    var pixel = firePixels[src];
    if (pixel == 0) {
        firePixels[src - FIRE_WIDTH] = 0;
    } else {
        var randIdx = Math.round(Math.random() * 3.0);   // & 3 commented out
        var dst = src - randIdx + 1;
        firePixels[dst - FIRE_WIDTH] = pixel - (randIdx & 1);
    }
}
function doFire() {
    for (x = 0; x < FIRE_WIDTH; x++)
        for (y = 1; y < FIRE_HEIGHT; y++)
            spreadFire(y * FIRE_WIDTH + x);
}
```
The random `randIdx` gives horizontal wind drift (dst offset) and the `-(randIdx&1)`
gives stochastic cooling/decay. ASCII ramp for fire index: " .:*oO&8#@".

---

## 7. Conway's Game of Life — B3/S23

Source: https://en.wikipedia.org/wiki/Conway%27s_Game_of_Life

8-cell Moore neighbourhood. Four rules (verbatim):
1. "Any live cell with fewer than two live neighbours dies, as if by underpopulation."
2. "Any live cell with two or three live neighbours lives on to the next generation."
3. "Any live cell with more than three live neighbours dies, as if by overpopulation."
4. "Any dead cell with exactly three live neighbours becomes a live cell, as if by reproduction."

Rulestring B3/S23: dead cell born with exactly 3 neighbours; live cell survives
with 2 or 3. ASCII: live = '#'/'O', dead = ' '/'.'.

---

## 8. Matrix digital rain

Source (concept): https://en.wikipedia.org/wiki/Digital_rain
Source (canonical modern implementation): https://github.com/Rezmason/matrix
Rezmason raindrop shader (per-column brightness/head): https://elgoog.im/assets/p/matrix/shaders/glsl/rainPass.raindrop.frag.glsl

Algorithm: independent columns, each with a "head" (drop) position falling at a
per-column speed. Head cell is brightest (near white/bright green); cells above
fade toward dark green then black over a tail length. When head passes the bottom
it respawns at top after a random delay. Glyphs are random and periodically
re-randomized. Rezmason shader note (verbatim): glyphs "that share a column are
lit simultaneously, and are brighter toward the bottom ... those bright areas are
truncated into raindrops." Movie glyphs are mirrored Katakana + a few Susan Kare
Chicago-typeface characters (per project docs). ASCII/monochrome ramp by tail age:
'@'/'#' (head) -> '+'/'=' -> ':'/'.' -> ' '.

---

## 9. Mandelbrot set — escape-time algorithm

Source: https://en.wikipedia.org/wiki/Plotting_algorithms_for_the_Mandelbrot_set

z_{n+1} = z_n^2 + c, z_0 = 0, c = mapped pixel coordinate. Real/imag expansion
of z^2 + c (verbatim expressions):
```
xtemp := x*x - y*y + x0     // Re(z^2 + c)
y     := 2*x*y + y0         // Im(z^2 + c)
x     := xtemp
```
Escape when x*x + y*y > 4 (radius 2). Loop guard: `while (x*x + y*y <= 4 AND
iteration < max_iteration)`; max_iteration := 1000. Color = palette[iteration].
Map iteration count to ASCII ramp " .:-=+*#%@" (0 iters -> space, max -> '@' for
in-set). X range approx (-2.00, 0.47), Y range (-1.12, 1.12).

---

## 10. Julia set

Source: https://en.wikipedia.org/wiki/Plotting_algorithms_for_the_Mandelbrot_set
(same escape-time iteration; Julia symmetry noted: "Julia sets have symmetry
around the origin.")

Same z^2 + c iteration and same x*x + y*y > 4 escape test, but c is a FIXED
constant for the whole image and z_0 = the pixel coordinate (opposite of
Mandelbrot). Popular constant: c = -0.7 + 0.27015i. Also c = -0.8 + 0.156i,
c = 0.285 + 0.01i, c = -0.4 + 0.6i. Same iteration-count -> ASCII ramp mapping.

---

## 11. Perlin improved noise (Ken Perlin, 2002)

Source: https://cs.nyu.edu/~perlin/noise/
(mrl.cs.nyu.edu redirects/cert-mismatches to cs.nyu.edu; SIGGRAPH 2002 "Improving
Noise".) Full Java reference implementation, verbatim:

```java
static double fade(double t) { return t * t * t * (t * (t * 6 - 15) + 10); }
static double lerp(double t, double a, double b) { return a + t * (b - a); }
static double grad(int hash, double x, double y, double z) {
   int h = hash & 15;                      // CONVERT LO 4 BITS OF HASH CODE
   double u = h<8 ? x : y,                  // INTO 12 GRADIENT DIRECTIONS.
          v = h<4 ? y : h==12||h==14 ? x : z;
   return ((h&1) == 0 ? u : -u) + ((h&2) == 0 ? v : -v);
}
static public double noise(double x, double y, double z) {
   int X = (int)Math.floor(x) & 255,       // FIND UNIT CUBE THAT CONTAINS POINT
       Y = (int)Math.floor(y) & 255,
       Z = (int)Math.floor(z) & 255;
   x -= Math.floor(x); y -= Math.floor(y); z -= Math.floor(z);  // RELATIVE X,Y,Z
   double u = fade(x), v = fade(y), w = fade(z);                // FADE CURVES
   int A = p[X  ]+Y, AA = p[A]+Z, AB = p[A+1]+Z,   // HASH 8 CUBE CORNERS
       B = p[X+1]+Y, BA = p[B]+Z, BB = p[B+1]+Z;
   return lerp(w, lerp(v, lerp(u, grad(p[AA  ], x  , y  , z   ),
                                  grad(p[BA  ], x-1, y  , z   )),
                          lerp(u, grad(p[AB  ], x  , y-1, z   ),
                                  grad(p[BB  ], x-1, y-1, z   ))),
                  lerp(v, lerp(u, grad(p[AA+1], x  , y  , z-1 ),
                                  grad(p[BA+1], x-1, y  , z-1 )),
                          lerp(u, grad(p[AB+1], x  , y-1, z-1 ),
                                  grad(p[BB+1], x-1, y-1, z-1 ))));
}
```

Permutation table (verbatim, 256 values; doubled to 512 to avoid overflow):
```java
static final int p[] = new int[512], permutation[] = { 151,160,137,91,90,15,
131,13,201,95,96,53,194,233,7,225,140,36,103,30,69,142,8,99,37,240,21,10,23,
190,6,148,247,120,234,75,0,26,197,62,94,252,219,203,117,35,11,32,57,177,33,
88,237,149,56,87,174,20,125,136,171,168,68,175,74,165,71,134,139,48,27,166,
77,146,158,231,83,111,229,122,60,211,133,230,220,105,92,41,55,46,245,40,244,
102,143,54,65,25,63,161,1,216,80,73,209,76,132,187,208,89,18,169,200,196,
135,130,116,188,159,86,164,100,109,198,173,186,3,64,52,217,226,250,124,123,
5,202,38,147,118,126,255,82,85,212,207,206,59,227,47,16,58,17,182,189,28,42,
223,183,170,213,119,248,152,2,44,154,163,70,221,153,101,155,167,43,172,9,
129,22,39,253,19,98,108,110,79,113,224,232,178,185,112,104,218,246,97,228,
251,34,242,193,238,210,144,12,191,179,162,241,81,51,145,235,249,14,239,107,
49,192,214,31,181,199,106,157,184,84,204,176,115,121,50,45,127,4,150,254,
138,236,205,93,222,114,67,29,24,72,243,141,128,195,78,66,215,61,156,180 };
static { for (int i=0; i < 256 ; i++) p[256+i] = p[i] = permutation[i]; }
```

Output range approx -1..+1; map to 0..1 via (n+1)/2, then to ASCII ramp
" .:-=+*#%@". Value noise = same lattice + fade + lerp, but corners store random
scalar values (not gradients) interpolated directly.

---

## 12. Boids (Craig Reynolds, 1987)

Source: https://www.red3d.com/cwr/boids/
Original paper: Reynolds, C. (1987) "Flocks, Herds, and Schools: A Distributed
Behavioral Model", SIGGRAPH '87. https://www.red3d.com/cwr/papers/1987/boids.html

Three steering rules (verbatim), each over local flockmates only:
- Separation: "steer to avoid crowding local flockmates"
- Alignment:  "steer towards the average heading of local flockmates"
- Cohesion:   "steer to move toward the average position of local flockmates"

Local neighbourhood defined (verbatim) by "a distance (measured from the center
of the boid) and an angle, measured from the boid's direction of flight." Boids
outside are ignored.

Standard vector implementation (per neighbour set N within radius):
```
cohesion   = (avg_position(N) - self.pos) * w_cohesion
alignment  = (avg_velocity(N) - self.vel) * w_alignment
separation = sum( self.pos - other.pos  for other in N if dist<sep_radius ) * w_sep
self.vel  += cohesion + alignment + separation
self.vel   = clamp(self.vel, max_speed)
self.pos  += self.vel
```
Typical weights w_sep > w_align ~ w_cohesion; separation uses a smaller radius
than alignment/cohesion. Result is emergent flocking.
