/* SmartCLI showcase — DRIVE-TUI toy: a faithful, drivable Claude Code
 * slash-command menu (nested). Data + labels are taken from the real Claude
 * Code CLI source (commands/, ModelPicker, Config). You navigate it the way an
 * AI drives a TUI through SmartCLI: perceive the screen, press keys, descend
 * into submenus, read the result. Pure client-side JS, no dependencies.
 *
 * Keys: Up/Down (or j/k) move with wrap; Enter or Right opens a submenu / runs
 * a leaf; Left or Escape goes back; 1-9 jump; also fully clickable.
 */
(function () {
  "use strict";

const MENU = {
  title: "Type a command",
  items: [
    {
      cmd: "/model",
      desc: "Set the AI model for Claude Code (currently Opus 4.8 (1M context))",
      children: {
        title: "Select model",
        subtitle: "Switch between Claude models. Your pick becomes the default for new sessions. For other/previous model names, specify with --model.",
        foot: "Enter to set as default · s to use this session only · Esc to cancel",
        items: [
          {
            label: "1. Default (recommended) ✔",
            desc: "Use the default model (currently Opus 4.8 (1M context)) · $5/$25 per Mtok",
            effort: "● High effort (default)",
            result: "Kept model as Opus 4.8 (1M context) (default)"
          },
          {
            label: "2. Opus",
            desc: "Opus 4.8 with 1M context · Best for everyday, complex tasks · $5/$25 per Mtok",
            effort: "● High effort (default)",
            result: "Set model to Opus 4.8 (1M context)"
          },
          {
            label: "3. Fable",
            desc: "Fable 5 · Most capable for your hardest and longest-running tasks · $10/$50 per Mtok",
            effort: "● High effort (default)",
            result: "Set model to Fable 5"
          },
          {
            label: "4. Sonnet",
            desc: "Sonnet 5 · Efficient for routine tasks · $3/$15 $2/$10 per Mtok · promo through Aug 31",
            effort: "● High effort (default)",
            result: "Set model to Sonnet 5"
          },
          {
            label: "5. Sonnet 5 (1M context)",
            desc: "Sonnet 5 for long sessions · $3/$15 $2/$10 per Mtok · promo through Aug 31",
            effort: "● High effort (default)",
            result: "Set model to Sonnet 5 (1M context)"
          },
          {
            label: "6. Haiku",
            desc: "Haiku 4.5 · Fastest for quick answers · $1/$5 per Mtok",
            effort: "● High effort (default)",
            result: "Set model to Haiku 4.5"
          }
        ]
      }
    },
    {
      cmd: "/config",
      desc: "Open config panel",
      children: {
        title: "Settings",
        subtitle: "Toggle with Enter, adjust enums with ←/→. Changes save immediately.",
        items: [
          { label: "Auto-compact", desc: "Automatically summarize the conversation when context fills up", value: "On", result: "Auto-compact: Off" },
          { label: "Show tips", desc: "Show tips in the spinner while Claude works", value: "On", result: "Show tips: Off" },
          { label: "Reduce motion", desc: "Minimize animations across the UI", value: "Off", result: "Reduce motion: On" },
          { label: "Thinking mode", desc: "Let Claude think before responding", value: "On", result: "Thinking mode: Off" },
          { label: "Prompt suggestions", desc: "Suggest prompts as you type", value: "On", result: "Prompt suggestions: Off" },
          { label: "Rewind code (checkpoints)", desc: "Snapshot file state so you can restore earlier points", value: "On", result: "Rewind code (checkpoints): Off" },
          { label: "Verbose output", desc: "Show full command output without truncation", value: "Off", result: "Verbose output: On" },
          { label: "Terminal progress bar", desc: "Show a progress bar in the terminal", value: "On", result: "Terminal progress bar: Off" },
          { label: "Show turn duration", desc: "Display how long each turn took", value: "Off", result: "Show turn duration: On" },
          {
            label: "Default permission mode",
            desc: "Which permission mode new sessions start in",
            value: "default",
            options: ["default", "plan", "acceptEdits"],
            result: "Default permission mode: plan"
          },
          {
            label: "Editor mode",
            desc: "Text editing keybindings in the prompt",
            value: "normal",
            options: ["normal", "vim"],
            result: "Editor mode: vim"
          },
          {
            label: "Theme",
            desc: "Color theme (opens theme picker)",
            value: "dark",
            result: "Opening theme picker…"
          }
        ]
      }
    },
    {
      cmd: "/theme",
      desc: "Change the theme",
      children: {
        title: "Select theme",
        subtitle: "Choose how Claude Code renders colors in your terminal.",
        items: [
          { label: "Auto (match terminal)", desc: "Follow your terminal's light/dark setting", result: "✓ Theme set to Auto (match terminal)" },
          { label: "Dark mode", desc: "Dark background theme", result: "✓ Theme set to Dark mode" },
          { label: "Light mode", desc: "Light background theme", result: "✓ Theme set to Light mode" },
          { label: "Dark mode (colorblind-friendly)", desc: "Daltonized dark theme", result: "✓ Theme set to Dark mode (colorblind-friendly)" },
          { label: "Light mode (colorblind-friendly)", desc: "Daltonized light theme", result: "✓ Theme set to Light mode (colorblind-friendly)" },
          { label: "Dark mode (ANSI colors only)", desc: "Uses only your terminal's 16 ANSI colors", result: "✓ Theme set to Dark mode (ANSI colors only)" },
          { label: "Light mode (ANSI colors only)", desc: "Uses only your terminal's 16 ANSI colors", result: "✓ Theme set to Light mode (ANSI colors only)" }
        ]
      }
    },
    {
      cmd: "/permissions",
      desc: "Manage allow & deny tool permission rules",
      children: {
        title: "Permission mode",
        subtitle: "Cycle modes anytime with Shift+Tab.",
        items: [
          { label: "Default", desc: "Ask before running tools that change files or run commands", result: "⏵ Permission mode: Default" },
          { label: "Plan Mode", desc: "Research and plan only — Claude won't edit or run until you approve", result: "⏸ Permission mode: Plan Mode" },
          { label: "Accept edits", desc: "Auto-accept file edits in the working directory", result: "⏵⏵ Permission mode: Accept edits" },
          { label: "Bypass Permissions", desc: "Don't ask for approval before potentially dangerous actions", result: "⏵⏵ WARNING: Claude Code running in Bypass Permissions mode\nYou accept all responsibility for actions taken." }
        ]
      }
    },
    {
      cmd: "/help",
      desc: "Show help and available commands",
      result: "Claude Code — common commands:\n/model  Set the AI model    /config  Open config panel\n/clear  Clear conversation  /cost    Show session cost\n/review Review a PR         /init    Initialize CLAUDE.md\nRun /help <command> for details."
    },
    {
      cmd: "/clear",
      desc: "Clear conversation history and free up context",
      result: "✓ Conversation history cleared. Context freed."
    },
    {
      cmd: "/compact",
      desc: "Clear conversation history but keep a summary in context. Optional: /compact [instructions for summarization]",
      result: "✓ Compacted conversation. Summary kept in context."
    },
    {
      cmd: "/cost",
      desc: "Show the total cost and duration of the current session",
      result: "Total cost:            $0.4127\nTotal duration (API):  2m 18.3s\nTotal duration (wall): 14m 6s\nTotal code changes:    212 lines added, 47 lines removed"
    },
    {
      cmd: "/context",
      desc: "Visualize current context usage as a colored grid",
      result: "Context: 48,120 / 200,000 tokens (24%)\nSystem 6.2k · Tools 11.4k · Messages 30.5k · Free 151.9k"
    },
    {
      cmd: "/review",
      desc: "Review a pull request",
      result: "Opening PR review… paste a PR number or URL to review."
    },
    {
      cmd: "/init",
      desc: "Initialize a new CLAUDE.md file with codebase documentation",
      result: "Analyzing your codebase…\n✓ Created CLAUDE.md with project overview and conventions."
    },
    {
      cmd: "/status",
      desc: "Show Claude Code status including version, model, account, API connectivity, and tool statuses",
      result: "Claude Code v2.x\nModel: Sonnet 4.6   Account: you@anthropic.com\nAPI: connected      MCP servers: 2 connected"
    },
    {
      cmd: "/memory",
      desc: "Edit Claude memory files",
      result: "Opening CLAUDE.md in your editor…"
    },
    {
      cmd: "/agents",
      desc: "Manage agent configurations",
      result: "3 agents configured: general-purpose, code-reviewer, researcher."
    },
    {
      cmd: "/mcp",
      desc: "Manage MCP servers",
      result: "MCP servers:\n✓ codegraph (connected)   ✓ playwright (connected)"
    },
    {
      cmd: "/vim",
      desc: "Toggle between Vim and Normal editing modes",
      result: "✓ Editor mode: vim (-- NORMAL --)"
    },
    {
      cmd: "/resume",
      desc: "Resume a previous conversation",
      result: "Select a conversation to resume… (↑/↓ to browse)"
    },
    {
      cmd: "/usage",
      desc: "Show plan usage limits",
      result: "Plan usage: 62% of weekly limit\nResets in 3 days."
    },
    {
      cmd: "/export",
      desc: "Export the current conversation to a file or clipboard",
      result: "✓ Conversation exported to conversation.md"
    },
    {
      cmd: "/doctor",
      desc: "Diagnose and verify your Claude Code installation and settings",
      result: "✓ Installation OK\n✓ Settings valid\n✓ Auth valid   ✓ Network reachable"
    }
  ]
};
  function esc(s) {
    return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  function initCCMenu() {
    var root = document.getElementById("drive-menu");
    var cap = document.getElementById("drive-log");
    if (!root) return;

    // navigation stack: each frame = { node, sel }. node is a MENU-like object
    // with .items (and optional .title/.subtitle). Leaf selection shows result.
    var stack = [{ node: MENU, sel: 0 }];
    var resultView = null;   // {text, warn} when showing a leaf result

    function top() { return stack[stack.length - 1]; }
    function items() { return top().node.items; }
    function cur() { return items()[top().sel]; }

    function setCap(html) { if (cap) cap.innerHTML = html; }


    function render() {
      var node = top().node, sel = top().sel, its = node.items;
      var html = "";
      if (resultView) {
        // a leaf result panel
        var t = esc(resultView.text);
        if (resultView.warn) t = t.replace(/(WARNING[^\n]*)/, '<span class="cc-warn">$1</span>');
        html += '<div class="cc-title">' + esc(resultView.title) + '</div>';
        html += '<div class="cc-result">' + t + '</div>';
        html += '<div class="cc-foot">Enter or Esc · back to menu</div>';
        root.innerHTML = html;
        return;
      }
      // title (root shows "Type a command"; submenus show their title + subtitle)
      html += '<div class="cc-title">' + esc(node.title || "Type a command") + '</div>';
      if (node.subtitle) html += '<div class="cc-sub">' + esc(node.subtitle) + '</div>';
      html += '<div class="cc-rows">';
      // window the list so it fits the fixed stage (max ~7 rows visible)
      var MAXV = 7, start = 0;
      if (its.length > MAXV) {
        start = Math.min(Math.max(0, sel - 3), its.length - MAXV);
      }
      for (var i = start; i < Math.min(its.length, start + MAXV); i++) {
        var it = its[i], on = i === sel;
        var isCmd = !!it.cmd;
        html += '<div class="cc-row' + (on ? ' sel' : '') + '" data-i="' + i + '">';
        html += '<span class="cc-mk">' + (on ? "❯" : " ") + '</span>';
        if (isCmd) html += '<span class="cc-cmd">' + esc(it.cmd) + '</span>';
        else html += '<span class="cc-label">' + esc(it.label) + '</span>';
        html += '<span class="cc-desc">' + esc(it.desc || "") + '</span>';
        if (it.value != null) html += '<span class="cc-val">' + esc(it.value) + '</span>';
        if (it.children) html += '<span class="cc-caret">›</span>';
        html += '</div>';
      }
      html += '</div>';
      // effort line for the focused model row (ModelPicker special case)
      var c = its[sel];
      if (c && c.effort) html += '<div class="cc-effort">' + esc(c.effort) + ' ←/→ to adjust</div>';
      // footer hint — use the submenu's real footer text when provided
      var atRoot = stack.length === 1;
      if (node.foot) {
        html += '<div class="cc-foot">' + esc(node.foot) + '</div>';
      } else {
        html += '<div class="cc-foot">↑↓ navigate · '
          + (c && c.children ? 'Enter/→ open' : 'Enter select')
          + (atRoot ? '' : ' · Esc/← back') + '</div>';
      }
      root.innerHTML = html;
    }


    function move(d) {
      if (resultView) return;
      var n = items().length;
      top().sel = (top().sel + d + n) % n;
      render();
    }
    function open() {
      if (resultView) { back(); return; }
      var it = cur();
      if (it.children) {                     // descend into submenu
        stack.push({ node: it.children, sel: 0 });
        render();
        setCap("act → opened <b>" + esc(it.cmd || it.label) + "</b> submenu");
      } else if (it.result != null) {        // run a leaf -> result panel
        resultView = { title: it.cmd || it.label,
                       text: it.result, warn: /WARNING/.test(it.result) };
        render();
        setCap("confirm → ran <b>" + esc(it.cmd || it.label) + "</b> ✓");
      }
    }
    function back() {
      if (resultView) { resultView = null; render();
        setCap("perceive → back to <b>" + esc(top().node.title || "commands") + "</b>"); return; }
      if (stack.length > 1) { stack.pop(); render();
        setCap("act → back to <b>" + esc(top().node.title || "commands") + "</b>"); }
    }
    // ModelPicker ←/→ effort adjust — real Claude Code symbols + labels
    // (○ Low · ◐ Medium · ● High · ◉ Max). "High" is the default.
    var EFFORTS = [
      { sym: "○", name: "Low" }, { sym: "◐", name: "Medium" },
      { sym: "●", name: "High" }, { sym: "◉", name: "Max" }
    ];
    function adjustEffort(d) {
      var it = cur();
      if (resultView || !it || !it.effort) return;
      var m = it.effort.match(/(Low|Medium|High|Max)/);
      var idx = m ? EFFORTS.map(function (e) { return e.name; }).indexOf(m[1]) : 2;
      idx = Math.max(0, Math.min(EFFORTS.length - 1, idx + d));
      var e = EFFORTS[idx];
      it.effort = e.sym + " " + e.name + " effort" + (e.name === "High" ? " (default)" : "");
      render();
      setCap("act → effort <b>" + e.name + "</b> (←/→ to adjust)");
    }

    root.addEventListener("keydown", function (e) {
      var k = e.key;
      if (k === "ArrowDown" || k === "j") { move(1); e.preventDefault(); }
      else if (k === "ArrowUp" || k === "k") { move(-1); e.preventDefault(); }
      else if (k === "Enter" || k === "ArrowRight") { open(); e.preventDefault(); }
      else if (k === "ArrowLeft" || k === "Escape") { back(); e.preventDefault(); }
      else if (/^[1-9]$/.test(k)) {
        if (!resultView) { var i = +k - 1; if (i < items().length) { top().sel = i; render(); } }
        e.preventDefault();
      }
      // left/right also adjust effort if the row supports it (models)
      if ((k === "ArrowLeft" || k === "ArrowRight") && !resultView && cur() && cur().effort) {
        adjustEffort(k === "ArrowRight" ? 1 : -1);
      }
    });
    root.addEventListener("click", function (e) {
      var row = e.target.closest ? e.target.closest(".cc-row") : null;
      if (!row) { if (resultView) back(); return; }
      var i = +row.getAttribute("data-i");
      if (i === top().sel) open(); else { top().sel = i; render(); }
    });
    root.addEventListener("focus", function () {
      setCap("focused — <b>↑↓</b> navigate, <b>Enter/→</b> open, <b>Esc/←</b> back");
    });

    render();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initCCMenu);
  } else { initCCMenu(); }
})();
