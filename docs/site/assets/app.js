/* SmartCLI showcase — live, randomized hero terminal.
 *
 * Each visit picks a random scenario (a different model driving a different
 * agent CLI on a different task) and animates it: the human's prompt is typed,
 * then drive-tui's perceive -> act -> wait -> confirm beats reveal one line at a
 * time, then it loops to a fresh scenario. No build step, no dependencies.
 * Colors mirror the Anthropic warm-editorial page palette.
 */
(function () {
  "use strict";

  // palette (kept in sync with the page CSS variables)
  var C = {
    cor: "#cc785c", teal: "#5db8a6", amb: "#e8a55a", grn: "#5db872",
    dim: "#8e8b82", fg: "#faf9f5"
  };

  // Line helper: [text, color, bold]
  function L(t, c, b) { return { t: t, c: c || C.fg, b: !!b }; }

  // A box row of fixed interior width so borders always align.
  function boxTop(w) { return "  ╭" + rep("─", w) + "╮"; }
  function boxBot(w) { return "  ╰" + rep("─", w) + "╯"; }
  function boxRow(left, w, right) {
    right = right || "";
    var pad = Math.max(0, w - left.length - right.length);
    var inner = (left + rep(" ", pad) + right).slice(0, w);
    return "  │" + inner + "│";
  }
  function rep(s, n) { var o = ""; for (var i = 0; i < n; i++) o += s; return o; }

  // ---- SCENARIOS: real + plausible model x CLI x task combos --------------
  // Each scenario follows the same perceive/act/confirm shape captured from
  // real drive-tui runs; CLI/model names are neutral placeholders.
  var SCENARIOS = [
    {
      model: "Fable 5", cli: "agent",
      prompt: "drive an agent CLI, say hi, switch to the lowest tier",
      beats: [
        { cap: "perceive — a semantic snapshot of the live screen", lines: [
          L("[screen 30x100] cursor=r25c6  title=\"agent\"  [stable]", C.dim),
          L(boxTop(30), C.cor),
          L(boxRow("  Agent Build Beta  0.2.99", 30), C.teal),
          L(boxRow("  New worktree", 30, "ctrl+w  "), C.fg),
          L(boxRow("  Resume session", 30, "ctrl+s  "), C.fg),
          L(boxBot(30), C.cor),
          L("  ❯ _", C.teal),
          L("  Fable 5 (high) · always-approve", C.cor)
        ]},
        { cap: "act — type 你好 and read the reply", lines: [
          L("  ❯ 你好                              9:36 AM", C.teal, true),
          L("  ◆ Thought for 0.1s", C.dim),
          L("  你好！我是助手，可以帮你处理开发任务。", C.fg),
          L("  Worked for 2.0s.", C.dim)
        ]},
        { cap: "act — arrow keys navigate the /model picker", lines: [
          L("    High Effort (active)   extensive reasoning", C.dim),
          L("    Medium Effort          balanced", C.dim),
          L("  ❯ Low Effort            quick, fast", C.teal, true),
          L("", C.fg),
          L("  keys: Down Down → highlight moved to Low  ✓", C.grn)
        ]},
        { cap: "confirm — the tier actually changed", lines: [
          L("  ❯ 你好                              9:38 AM", C.teal, true),
          L("  你好！有什么需要帮忙的吗？", C.fg),
          L("  Worked for 1.5s.", C.dim),
          L("", C.fg),
          L("  Fable 5 (low) · always-approve        ✓", C.grn, true)
        ]}
      ]
    },
    {
      model: "Codex (GPT-5.6)", cli: "codex",
      prompt: "open codex, review the staged diff",
      beats: [
        { cap: "perceive — the codex TUI, YOLO mode", lines: [
          L("╭─────────────────────────────╮", C.cor),
          L("│ >_ OpenAI Codex (v0.144.1)   │", C.teal),
          L("│ model: gpt-5.6-sol ultra     │", C.fg),
          L("│ permissions: YOLO mode       │", C.amb),
          L("╰─────────────────────────────╯", C.cor),
          L("  › review the staged diff", C.teal)
        ]},
        { cap: "act — send the command, wait for review", lines: [
          L("  ◆ reading 6 files, 214 lines…", C.dim),
          L("  › src/auth.py:42  possible None deref", C.fg),
          L("  › tests/  no coverage for the new path", C.fg),
          L("  ◆ 3 findings, 1 high", C.amb)
        ]},
        { cap: "confirm — findings captured, screen stable", lines: [
          L("  review complete · 3 findings", C.fg),
          L("  1 high · 2 medium                     ✓", C.grn, true),
          L("", C.fg),
          L("  gpt-5.6-sol ultra · D:\\Project", C.cor)
        ]}
      ]
    },
    {
      model: "Claude (Sonnet)", cli: "kiro-cli",
      prompt: "open kiro-cli, log in with the arrow menu",
      beats: [
        { cap: "perceive — a y/N arrow menu", lines: [
          L("  You are not logged in. Login now?", C.fg),
          L("  ❯ Yes", C.teal, true),
          L("    No", C.dim)
        ]},
        { cap: "act — Down arrow moves the highlight", lines: [
          L("  You are not logged in. Login now?", C.fg),
          L("    Yes", C.dim),
          L("  ❯ No", C.teal, true),
          L("", C.fg),
          L("  keys: Down → highlight moved  ✓", C.grn)
        ]},
        { cap: "confirm — perceived and driven like a human", lines: [
          L("  the arrow key landed. CSI vs SS3", C.fg),
          L("  handled. no blind sleep, ever.        ✓", C.grn, true),
          L("", C.fg),
          L("  perceive → decide → act → wait → confirm", C.cor, true)
        ]}
      ]
    }
  ];

  // ---- animation engine ---------------------------------------------------
  function esc(s) {
    return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  function pickScenario() {
    return SCENARIOS[Math.floor(Math.random() * SCENARIOS.length)];
  }

  function run(root) {
    var titleEl = root.querySelector(".lt-title");
    var promptEl = root.querySelector(".lt-prompt");
    var capEl = root.querySelector(".lt-cap");
    var bodyEl = root.querySelector(".lt-body");
    var cancelled = false;

    function sleep(ms) {
      return new Promise(function (res) {
        var id = setTimeout(res, ms);
        root._timers.push(id);
      });
    }

    async function typeText(el, text, cps) {
      el.textContent = "";
      for (var i = 0; i < text.length && !cancelled; i++) {
        el.textContent += text[i];
        await sleep(1000 / cps + Math.random() * 22);
      }
    }

    async function revealLines(lines) {
      bodyEl.innerHTML = "";
      for (var i = 0; i < lines.length && !cancelled; i++) {
        var ln = lines[i];
        var span = document.createElement("div");
        span.className = "lt-line";
        span.style.color = ln.c;
        if (ln.b) span.style.fontWeight = "500";
        span.innerHTML = ln.t ? esc(ln.t) : "&nbsp;";
        span.style.opacity = "0";
        bodyEl.appendChild(span);
        // small enter transition
        await sleep(10);
        span.style.transition = "opacity .25s ease";
        span.style.opacity = "1";
        await sleep(190);
      }
    }

    async function loop() {
      while (!cancelled) {
        var sc = pickScenario();
        titleEl.textContent = sc.model + "  ·  driving " + sc.cli;
        // type the human's prompt
        promptEl.parentNode.style.opacity = "1";
        await typeText(promptEl, sc.prompt, 34);
        await sleep(650);
        // play beats
        for (var b = 0; b < sc.beats.length && !cancelled; b++) {
          capEl.textContent = "▸ " + sc.beats[b].cap;
          capEl.style.opacity = "0";
          await sleep(40);
          capEl.style.transition = "opacity .3s ease";
          capEl.style.opacity = "1";
          await revealLines(sc.beats[b].lines);
          await sleep(1050);
        }
        await sleep(900);
        // fade out before the next scenario
        bodyEl.style.transition = "opacity .4s ease";
        bodyEl.style.opacity = "0";
        capEl.style.opacity = "0";
        await sleep(430);
        bodyEl.style.opacity = "1";
      }
    }

    root._cancel = function () { cancelled = true; };
    loop();
  }

  function mount() {
    var root = document.getElementById("live-term");
    if (!root) return;
    root._timers = [];
    // reduced motion: leave the static SVG fallback in place
    if (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      return;
    }
    // swap the <noscript> SVG for the live terminal chrome
    root.innerHTML =
      '<div class="lt-bar">' +
        '<span class="lt-dot d1"></span><span class="lt-dot d2"></span>' +
        '<span class="lt-dot d3"></span>' +
        '<span class="lt-title">SmartCLI · drive-tui</span></div>' +
      '<div class="lt-screen">' +
        '<div class="lt-cmd"><span class="lt-p">ai&gt;</span> ' +
          '<span class="lt-prompt"></span><span class="lt-cursor">▋</span></div>' +
        '<div class="lt-cap"></div>' +
        '<div class="lt-body"></div>' +
      '</div>';
    run(root);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", mount);
  } else {
    mount();
  }
})();

