/* SmartCLI showcase — click-to-zoom lightbox.
 * Self-contained: injects its own CSS, wires every gallery <img>/<video> so a
 * click opens an enlarged copy centred over a dimmed backdrop. No dependencies.
 *   - click a thumbnail  -> open (img shows full-res; video clones + autoplays)
 *   - click backdrop / press Esc / click the ✕ -> close
 *   - the caption from the figure's <figcaption> rides along under the media
 *   - accessible: role=dialog, focus trap to the close button, Esc, aria-labels
 * Warm palette matches the page (coral #cc785c on near-black #0d0c0a).
 */
(function () {
  "use strict";

  // Only media inside a showcase gallery is zoomable — not the hero terminal,
  // logos, or nav. These are the two gallery containers plus their hero figures.
  var SELECTOR =
    ".gif-hero img, .gif-hero video, .gifs img, .gifs video";

  function injectCss() {
    if (document.getElementById("lb-style")) return;
    var css =
      ".lb-zoomable{cursor:zoom-in}" +
      ".lb-overlay{position:fixed;inset:0;z-index:1000;display:flex;" +
        "align-items:center;justify-content:center;flex-direction:column;" +
        "gap:14px;padding:4vmin;background:rgba(9,8,7,.82);" +
        "backdrop-filter:blur(6px);-webkit-backdrop-filter:blur(6px);" +
        "opacity:0;transition:opacity .18s ease;cursor:zoom-out}" +
      ".lb-overlay.on{opacity:1}" +
      ".lb-stage{max-width:min(1100px,94vw);max-height:82vh;" +
        "border-radius:12px;overflow:hidden;border:1px solid #3a352e;" +
        "background:#0d0c0a;box-shadow:0 24px 80px rgba(0,0,0,.6);" +
        "transform:scale(.96);transition:transform .18s ease;cursor:default}" +
      ".lb-overlay.on .lb-stage{transform:scale(1)}" +
      ".lb-stage img,.lb-stage video{display:block;max-width:min(1100px,94vw);" +
        "max-height:82vh;width:auto;height:auto;object-fit:contain}" +
      ".lb-cap{font-family:var(--mono,ui-monospace,monospace);font-size:13px;" +
        "color:#d8d4cc;text-align:center;max-width:min(1100px,94vw);" +
        "line-height:1.5;text-shadow:0 1px 2px rgba(0,0,0,.5)}" +
      ".lb-cap b{color:#cc785c;font-weight:500}" +
      ".lb-close{position:absolute;top:max(3vmin,14px);right:max(3vmin,18px);" +
        "width:40px;height:40px;border-radius:50%;border:1px solid #4a443b;" +
        "background:#1c1a17;color:#faf9f5;font-size:20px;line-height:1;" +
        "cursor:pointer;display:flex;align-items:center;justify-content:center;" +
        "transition:background .12s ease,border-color .12s ease}" +
      ".lb-close:hover{background:#cc785c;border-color:#cc785c}" +
      ".lb-close:focus-visible{outline:2px solid #cc785c;outline-offset:2px}" +
      "@media(prefers-reduced-motion:reduce){" +
        ".lb-overlay,.lb-overlay .lb-stage{transition:none}}";
    var el = document.createElement("style");
    el.id = "lb-style";
    el.textContent = css;
    document.head.appendChild(el);
  }

  var overlay = null, lastFocus = null;

  function close() {
    if (!overlay) return;
    var ov = overlay;
    overlay = null;
    ov.classList.remove("on");
    document.removeEventListener("keydown", onKey);
    document.body.style.overflow = "";
    var done = function () { if (ov.parentNode) ov.parentNode.removeChild(ov); };
    ov.addEventListener("transitionend", done, { once: true });
    setTimeout(done, 260); // fallback if transitionend never fires
    if (lastFocus && lastFocus.focus) lastFocus.focus();
  }

  function onKey(e) {
    if (e.key === "Escape") { e.preventDefault(); close(); }
  }

  function open(media) {
    if (overlay) return;
    lastFocus = document.activeElement;
    injectCss();

    overlay = document.createElement("div");
    overlay.className = "lb-overlay";
    overlay.setAttribute("role", "dialog");
    overlay.setAttribute("aria-modal", "true");

    var stage = document.createElement("div");
    stage.className = "lb-stage";

    var big;
    if (media.tagName === "VIDEO") {
      // Clone so the page copy keeps playing; enlarge + autoplay muted-loop.
      big = media.cloneNode(true);
      big.removeAttribute("width");
      big.removeAttribute("height");
      big.muted = true;
      big.loop = true;
      big.autoplay = true;
      big.setAttribute("playsinline", "");
      big.controls = true; // give the user scrubbing at full size
      var p = big.play && big.play();
      if (p && p.catch) p.catch(function () {});
    } else {
      big = document.createElement("img");
      big.src = media.currentSrc || media.src;
      big.alt = media.alt || "";
    }
    stage.appendChild(big);
    overlay.appendChild(stage);

    // caption from the enclosing <figure>
    var fig = media.closest("figure");
    var cap = fig && fig.querySelector("figcaption");
    if (cap) {
      var c = document.createElement("div");
      c.className = "lb-cap";
      c.innerHTML = cap.innerHTML;
      overlay.appendChild(c);
      overlay.setAttribute("aria-label", cap.textContent.trim());
    } else if (media.alt) {
      overlay.setAttribute("aria-label", media.alt);
    }

    var btn = document.createElement("button");
    btn.className = "lb-close";
    btn.type = "button";
    btn.setAttribute("aria-label", "Close");
    btn.innerHTML = "&#10005;"; // ✕
    btn.addEventListener("click", close);
    overlay.appendChild(btn);

    // click the backdrop (but not the media/caption) closes
    overlay.addEventListener("click", function (e) {
      if (e.target === overlay) close();
    });
    stage.addEventListener("click", function (e) { e.stopPropagation(); });

    document.body.appendChild(overlay);
    document.body.style.overflow = "hidden";
    document.addEventListener("keydown", onKey);
    // trigger the transition on the next frame
    requestAnimationFrame(function () {
      requestAnimationFrame(function () { overlay.classList.add("on"); });
    });
    btn.focus();
  }

  function wire() {
    injectCss();
    var nodes = document.querySelectorAll(SELECTOR);
    [].forEach.call(nodes, function (m) {
      if (m.dataset.lbWired) return;
      // skip a fallback <img> nested inside a <video> — the <video> is wired.
      if (m.tagName === "IMG" && m.closest("video")) return;
      m.dataset.lbWired = "1";
      m.classList.add("lb-zoomable");
      m.setAttribute("tabindex", "0");
      m.setAttribute("role", "button");
      if (!m.getAttribute("aria-label")) {
        var fig = m.closest("figure");
        var cap = fig && fig.querySelector("figcaption");
        m.setAttribute("aria-label",
          "Enlarge: " + (m.alt || (cap && cap.textContent.trim()) || "media"));
      }
      m.addEventListener("click", function () { open(m); });
      m.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); open(m); }
      });
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", wire);
  } else {
    wire();
  }
})();
