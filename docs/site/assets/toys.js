/* SmartCLI showcase — interactive playground toys.
 * Three live, pokeable demos that mirror what the skills actually do:
 *   1. cmd-art: a canvas effect engine (rain / plasma / life), pure frame producer
 *   2. drive-tui: a menu you drive with real arrow keys, with a perceive log
 *   3. tui-ui: sub-cell-precision bars + braille sparkline, driven by a slider
 * No dependencies. Warm palette to match the page.
 */
(function () {
  "use strict";
  var COR = "#cc785c", TEAL = "#5db8a6", AMB = "#e8a55a", GRN = "#5db872",
      DIM = "#6b675f", INK = "#0d0c0a";

  // ============ TOY 1: cmd-art canvas effects ============
  function initFx() {
    var cv = document.getElementById("fx-canvas");
    if (!cv) return;
    var ctx = cv.getContext("2d");
    // Size the backing store to the ACTUAL displayed box (× devicePixelRatio) so
    // the monospace grid is crisp and never stretched — the earlier fixed
    // 380×220 store scaled to 100% width, distorting glyph spacing.
    // W,H = css pixels; cols,rows = grid; cellW,cellH = EXACT per-cell size so
    // cols*cellW == W and rows*cellH == H — no leftover strip on the right/bottom
    // (that leftover INK strip was the "black corner").
    var W, H, cols, rows, cellW, cellH, CELL = 12;
    function resize() {
      var dpr = window.devicePixelRatio || 1;
      var r = cv.getBoundingClientRect();
      var cssW = Math.max(200, Math.round(r.width));
      var cssH = Math.max(120, Math.round(r.height));
      cv.width = Math.round(cssW * dpr);
      cv.height = Math.round(cssH * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      W = cssW; H = cssH;
      cols = Math.max(1, Math.round(W / CELL));
      rows = Math.max(1, Math.round(H / CELL));
      cellW = W / cols;   // fractional — tiles the FULL width, no remainder
      cellH = H / rows;   // tiles the FULL height
    }
    resize();
    var mode = "rain", t = 0;
    var drops = [], grid = [], heat = [], stars = [];

    function reset() {
      drops = []; for (var i = 0; i < cols; i++) drops[i] = Math.random() * rows;
      grid = []; for (var y = 0; y < rows; y++) { grid[y] = []; for (var x = 0; x < cols; x++) grid[y][x] = Math.random() < 0.28 ? 1 : 0; }
      heat = []; for (var hy = 0; hy <= rows; hy++) { heat[hy] = []; for (var hx = 0; hx < cols; hx++) heat[hy][hx] = 0; }
      stars = []; for (var s = 0; s < Math.max(40, cols * 2); s++) stars.push({ a: Math.random() * 6.28, r: Math.random(), z: Math.random() });
    }
    reset();
    var FIRE_RAMP = "  ..::-=+*#%@";  // cool -> hot glyphs
    var FIRE_COL = [[24,23,21],[90,20,0],[160,45,0],[220,90,0],[240,150,30],[255,220,120]];

    var GLYPH = "01ｱｲｳｴｵｶｷ<>[]{}#$%&*+=".split("");
    // Perf guards: cap to ~30fps, and only run while the canvas is on-screen and
    // the tab is visible. Without these the loop burns a core forever (even in a
    // background tab or scrolled far away) — the kind of thing that overheats
    // phones and slow laptops.
    var FRAME_MS = 1000 / 30;
    var lastDraw = 0;
    var onScreen = true, tabVisible = !document.hidden, running = false, raf = 0;
    function frame(now) {
      raf = 0;
      if (!onScreen || !tabVisible) { running = false; return; }  // pause: no rAF re-arm
      raf = requestAnimationFrame(frame);
      if (now - lastDraw < FRAME_MS) return;   // throttle to ~30fps
      lastDraw = now;
      draw();
    }
    function ensureRunning() {
      if (running || !onScreen || !tabVisible) return;
      running = true; lastDraw = 0; raf = requestAnimationFrame(frame);
    }
    function draw() {
      ctx.fillStyle = INK; ctx.fillRect(0, 0, W, H);
      ctx.font = Math.round(cellH * 0.9) + "px 'JetBrains Mono',monospace";
      var baseY = cellH * 0.78;   // text baseline within a cell
      t += 1;
      if (mode === "rain") {
        for (var x = 0; x < cols; x++) {
          var y = drops[x];
          for (var k = 0; k < 10; k++) {
            var yy = Math.floor(y) - k; if (yy < 0 || yy >= rows) continue;
            var a = k === 0 ? 1 : Math.max(0, 0.7 - k * 0.08);
            ctx.fillStyle = k === 0 ? "rgba(230,230,220," + a + ")"
              : "rgba(93,184,166," + a + ")";
            ctx.fillText(GLYPH[(x * 7 + yy + t) % GLYPH.length], x * cellW, yy * cellH + baseY);
          }
          drops[x] += 0.5; if (drops[x] - 10 > rows) drops[x] = -Math.random() * 8;
        }
      } else if (mode === "plasma") {
        // full-bleed: fill each cell's rectangle with its colour (no black gaps,
        // no leftover edge) — matches the real fx plasma (bg-coloured cells).
        for (var yy2 = 0; yy2 < rows; yy2++) for (var xx = 0; xx < cols; xx++) {
          var v = Math.sin(xx * 0.4 + t * 0.05) + Math.sin(yy2 * 0.5 + t * 0.04)
            + Math.sin((xx + yy2) * 0.3 + t * 0.03);
          var n = (v + 3) / 6; // 0..1
          var r = Math.floor(120 + 135 * Math.sin(n * 6.28));
          var g = Math.floor(90 + 100 * Math.sin(n * 6.28 + 2));
          var b = Math.floor(90 + 90 * Math.sin(n * 6.28 + 4));
          ctx.fillStyle = "rgb(" + r + "," + g + "," + b + ")";
          // +1 px overlap so sub-pixel fractional cells leave no seam
          ctx.fillRect(Math.floor(xx * cellW), Math.floor(yy2 * cellH),
                       Math.ceil(cellW) + 1, Math.ceil(cellH) + 1);
        }
      } else if (mode === "fire") {
        for (var fx = 0; fx < cols; fx++) heat[rows][fx] = Math.random() < 0.85 ? 1 : 0.3;
        for (var fy = 0; fy < rows; fy++) for (var fx2 = 0; fx2 < cols; fx2++) {
          var below = heat[fy + 1][fx2] || 0;
          var bl = heat[fy + 1][(fx2 - 1 + cols) % cols] || 0;
          var br = heat[fy + 1][(fx2 + 1) % cols] || 0;
          var h = (below * 2 + bl + br) / 4 - 0.045 - Math.random() * 0.02;
          heat[fy][fx2] = h < 0 ? 0 : h;
          if (h > 0.04) {
            var ci = Math.min(FIRE_COL.length - 1, Math.floor(h * FIRE_COL.length));
            var c = FIRE_COL[ci];
            ctx.fillStyle = "rgb(" + c[0] + "," + c[1] + "," + c[2] + ")";
            var gi = Math.min(FIRE_RAMP.length - 1, Math.floor(h * FIRE_RAMP.length));
            ctx.fillText(FIRE_RAMP[gi], fx2 * cellW, fy * cellH + baseY);
          }
        }
      } else if (mode === "starfield") {
        var cx = W / 2, cy = H / 2;
        for (var si = 0; si < stars.length; si++) {
          var st = stars[si];
          st.z -= 0.012; if (st.z <= 0.02) { st.z = 1; st.a = Math.random() * 6.28; st.r = Math.random(); }
          var rad = (1 - st.z) * (W * 0.6) * st.r;
          var px = cx + Math.cos(st.a) * rad, py = cy + Math.sin(st.a) * rad;
          if (px < 0 || px >= W || py < 0 || py >= H) continue;
          var br2 = 1 - st.z;
          var g2 = Math.floor(150 + 105 * br2);
          ctx.fillStyle = "rgba(" + g2 + "," + (180 + Math.floor(75 * br2)) + "," + (200 + Math.floor(55 * br2)) + "," + (0.3 + 0.7 * br2) + ")";
          ctx.fillText(br2 > 0.7 ? "*" : br2 > 0.4 ? "+" : ".", px, py);
        }
      } else { // life
        if (t % 6 === 0) step();
        for (var y2 = 0; y2 < rows; y2++) for (var x2 = 0; x2 < cols; x2++) {
          if (grid[y2][x2]) {
            ctx.fillStyle = TEAL;
            ctx.fillText("●", x2 * cellW, y2 * cellH + baseY);
          }
        }
      }
    }
    function step() {
      var ng = [];
      for (var y = 0; y < rows; y++) { ng[y] = []; for (var x = 0; x < cols; x++) {
        var n = 0;
        for (var dy = -1; dy <= 1; dy++) for (var dx = -1; dx <= 1; dx++) {
          if (!dx && !dy) continue;
          var ny = (y + dy + rows) % rows, nx = (x + dx + cols) % cols;
          n += grid[ny][nx];
        }
        ng[y][x] = grid[y][x] ? (n === 2 || n === 3 ? 1 : 0) : (n === 3 ? 1 : 0);
      } }
      grid = ng;
    }

    // Respect prefers-reduced-motion: draw a single static frame, never loop.
    if (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      draw();
    } else {
      // pause when scrolled out of view
      if ("IntersectionObserver" in window) {
        new IntersectionObserver(function (es) {
          onScreen = es[0].isIntersecting;
          if (onScreen) ensureRunning();
        }, { threshold: 0.01 }).observe(cv);
      }
      // pause when the tab is hidden
      document.addEventListener("visibilitychange", function () {
        tabVisible = !document.hidden;
        if (tabVisible) ensureRunning();
      });
      ensureRunning();
    }

    var tabs = document.getElementById("fx-tabs");
    tabs.addEventListener("click", function (e) {
      if (e.target.tagName !== "BUTTON") return;
      mode = e.target.getAttribute("data-fx");
      [].forEach.call(tabs.children, function (b) { b.classList.remove("on"); });
      e.target.classList.add("on");
      reset();  // fresh state for life/fire/starfield
      ensureRunning();
    });
  }

  // ============ TOY 2: drive-tui menu ============
  window._initDrive = function () {
    var menu = document.getElementById("drive-menu");
    var log = document.getElementById("drive-log");
    if (!menu) return;
    var rows = [].slice.call(menu.querySelectorAll(".mrow"));
    var labels = rows.map(function (r) { return r.textContent.trim(); });
    var sel = 0;
    // Only the changed word (wrapped in <b>) animates — the CSS wordPop keyframe
    // fires whenever the <b> element is re-created here. Static text stays put.
    var lastHtml = "";
    function setLog(html) {
      if (html === lastHtml) return;
      lastHtml = html;
      log.innerHTML = html;
    }
    function render() {
      rows.forEach(function (r, i) {
        r.classList.toggle("sel", i === sel);
        r.classList.remove("done");
      });
      setLog("perceive → the highlighted row is <b>" + labels[sel] + "</b>");
    }
    function move(d) {
      sel = (sel + d + rows.length) % rows.length;
      rows.forEach(function (r, i) { r.classList.toggle("sel", i === sel); r.classList.remove("done"); });
      setLog("act → sent <b>" + (d < 0 ? "Up" : "Down")
        + "</b> · highlight on <b>" + labels[sel] + "</b>");
    }
    function commit() {
      rows[sel].classList.add("done");
      setLog("confirm → deploying to <b>" + labels[sel] + "</b> ✓");
    }
    render();
    menu.addEventListener("keydown", function (e) {
      if (e.key === "ArrowDown") { move(1); e.preventDefault(); }
      else if (e.key === "ArrowUp") { move(-1); e.preventDefault(); }
      else if (e.key === "Enter") { commit(); e.preventDefault(); }
    });
    rows.forEach(function (r, i) {
      r.addEventListener("click", function () { sel = i; render(); commit(); });
    });
    menu.addEventListener("focus", function () {
      setLog("focused — press <b>↑ ↓</b> then <b>Enter</b>");
    });
  };

  // ============ TOY 3: tui-ui sub-cell widgets ============
  window._initWidgets = function () {
    var slider = document.getElementById("w-slider");
    if (!slider) return;
    var fillEl = document.getElementById("w-fill");
    var thumbEl = document.getElementById("w-thumb");
    var barEl = document.getElementById("w-bar");
    var pctEl = document.getElementById("w-pct");
    var meterEl = document.getElementById("w-meter");
    var sparkEl = document.getElementById("w-spark");
    var value = 62;
    var EIGHTHS = [" ", "▏", "▎", "▍", "▌", "▋", "▊", "▉", "█"];
    var BRAILLE = ["⣀", "⣤", "⣶", "⣿", "⠛", "⠶", "⣄", "⡀"];
    var WIDTH = 22;

    function bar(pct) {
      var cells = pct / 100 * WIDTH;
      var full = Math.floor(cells);
      var rem = Math.round((cells - full) * 8);
      var s = "";
      for (var i = 0; i < full; i++) s += "█";
      if (rem > 0 && full < WIDTH) { s += EIGHTHS[rem]; full++; }
      for (var j = full; j < WIDTH; j++) s += " ";
      return s;
    }
    function meter(pct) {
      var n = Math.round(pct / 100 * 20);
      var s = "";
      for (var i = 0; i < 20; i++) s += i < n ? "▄" : "·";
      return s;
    }
    function spark(seed) {
      // a smooth-ish braille sparkline that shifts with the value
      var s = "";
      for (var i = 0; i < 18; i++) {
        var v = Math.sin(i * 0.6 + seed * 0.08) * 0.5 + 0.5;
        s += "⠀⣀⣄⣤⣦⣶⣷⣿".charAt(Math.floor(v * 7));
      }
      return s;
    }
    function update() {
      var p = Math.round(value);
      fillEl.style.width = p + "%";
      thumbEl.style.left = p + "%";
      barEl.textContent = bar(p);
      pctEl.textContent = p + "%";
      meterEl.textContent = meter(p);
      sparkEl.textContent = spark(p);
      slider.setAttribute("aria-valuenow", p);
      pctEl.style.color = p > 85 ? "#e06c60" : p > 60 ? AMB : GRN;
    }

    // custom pointer-driven slider (no native <input>)
    function setFromClientX(clientX) {
      var r = slider.getBoundingClientRect();
      value = Math.max(0, Math.min(100, (clientX - r.left) / r.width * 100));
      update();
    }
    var dragging = false;
    slider.addEventListener("pointerdown", function (e) {
      dragging = true; slider.classList.add("drag");
      slider.setPointerCapture(e.pointerId);
      setFromClientX(e.clientX); e.preventDefault();
    });
    slider.addEventListener("pointermove", function (e) {
      if (dragging) setFromClientX(e.clientX);
    });
    function endDrag() { dragging = false; slider.classList.remove("drag"); }
    slider.addEventListener("pointerup", endDrag);
    slider.addEventListener("pointercancel", endDrag);
    slider.addEventListener("keydown", function (e) {
      if (e.key === "ArrowRight" || e.key === "ArrowUp") { value = Math.min(100, value + 2); update(); e.preventDefault(); }
      else if (e.key === "ArrowLeft" || e.key === "ArrowDown") { value = Math.max(0, value - 2); update(); e.preventDefault(); }
      else if (e.key === "Home") { value = 0; update(); e.preventDefault(); }
      else if (e.key === "End") { value = 100; update(); e.preventDefault(); }
    });
    update();
  };

  // TOYS-CONTINUE
  window.addEventListener("DOMContentLoaded", function () {
    initFx();
    if (window._initDrive) window._initDrive();
    if (window._initWidgets) window._initWidgets();
  });
})();
