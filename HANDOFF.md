# SmartCLI — Handoff (承上启下)

*Written 2026-07-08. This is the single document a fresh AI reads first to pick up SmartCLI without re-deriving anything. It records what the project IS, what already WORKS (with the exact commands to see it), the brain (`knowledge/`), the hard-won rules that must never be re-lost, the environment, and the open tasks framed so you can start in one move. Two upstream count corrections are baked in: there are **THREE** skills (not two), and the live `fx` registry has **18** effects (not 19).*

---

## 1. What SmartCLI IS

**Shared core (`smartcli_core/`, DO-NOT-MODIFY).** A pluggable PTY backend + `pyte` screen model + semantic snapshot + readiness sync — modules `pty_backend / screen_model / snapshot / readiness / session`. The deliberate architecture call: the core is a **pluggable PTY layer, NOT tmux-bound**. Target programs may run in Linux containers (tmux there) while local dev runs on Windows (ConPTY via pywinpty). Screen perception uses `pyte` structured-text snapshots (chosen over screenshot/vision on purpose) so one screen model feeds both the agent (perceive, up) and rendering (down). The hard, valuable part is the ACI layer: readiness sync, compression of raw screen to a semantic tree, and action translation (intent → key sequence).

**drive-tui skill (`skills/drive-tui/`).** Teaches an AI to DRIVE interactive terminal programs (REPLs, installers, vim, agent CLIs like kiro-cli, arrow-key menus, y/N prompts, password fields, curses UIs) through a PTY via a **perceive → decide → act → wait → confirm** loop — never blind-`sleep`, always re-snapshot after acting. The surface is a thin CLI `scripts/tui.py` with two modes: **A) persistent session** (a detached localhost-only daemon owns one live program; state survives across shell calls — `start/snapshot/send-text/send-line/keys/wait/wait-regex/alive/close/list`) and **B) one-shot `run`** (a JSON step list against a fresh process). On top sits an importable **pattern library** (`patterns/`) that `classify()`s a screen and `drive()`s it with one of **8 recipes**. Fault-isolated `@register` + pkgutil discovery; recipes fail loud on bad intent.

**cmd-art skill (`skills/cmd-art/`).** Helps a human design CMD/terminal visual effects and ASCII art from a one-line request, via `fx` — a "living-template" engine: an `Effect` ABC + `@register` decorator + pkgutil auto-discovery, so effects, themes, and multi-effect shows all compose. Pure Python stdlib (optional `pyfiglet`/`PIL`), truecolor tuned for Windows Terminal. CLI is `python -m fx <list|show|play|gallery|random|show --seq/--script>`; `play` is **bounded by default** (10s on a TTY), degrades to one plain frame on non-TTY, and always restores the terminal via try/finally. Effects are **pure frame producers** (return one full frame; never print/sleep/touch ANSI modes — the play loop owns the terminal). 8 themes; a legacy `scripts/ascii_fx.py` shim preserves the old surface.

**tui-ui skill (`skills/tui-ui/`).** A web-like terminal UI layout engine + widgets emitting **tmux-safe ANSI frames** (SGR color runs + newlines only — no cursor moves, no alt-screen). You compose a tree of renderables (CSS box model margin→border→padding→content, border-box default; `VStack/HStack/Grid/Page` with `Fr` fractional units); it resolves sizes, composites cell grids, and serializes **once**. Everything is display-cell accurate (CJK/emoji/ZWJ/VS16/flag-pairs via `ui.core.width()`, never `len()`), so columns never desync. Beyond widgets it has a real **ENGINE**: `field.py` (CellField shader — LinearGradient/RadialGlow/Ripple/Plasma + Over/Add/Mask/Translate compositors, ASPECT=2 distance), `raster.py` (sub-cell half/quad/braille pixels), `box_junction.py` (edge-algebra auto-connecting `┼┬┤`), `color_model.py` (honest truecolor→256→16→mono degrade). It produces *frames*; something else owns the terminal (contrast drive-tui). **15 widgets live** (11 core + 4 in `ui/widgets_ext/`: `gradient_rule`, `radial_glow`, `slider_track`, `braille_chart`).

**Knowledge graph (`knowledge/`).** A navigable wiki-link graph — **140 `.md` files**, of which **122 concept/works entries** (120 unique slugs; `tmux-capture-pane` intentionally ×3), plus 7 READMEs, INDEX, and 10 `sources/` research digests. Each note carries an exact formula/sequence/constant, a **Source:**, and double-bracketed cross-links. Core discipline is lane-selection: **replica task → measure ground truth first** (start at `[[hard-lessons]]` + `[[effort-selector]]`); **creative task → compose the four primitives** (start at `[[rendering-model]]`). Integrity as of this handoff: 0 dangling links (all 909 resolve), 0 remaining "(unsourced — verify)" flags.

---

## 2. Current state — DONE & verified (with the exact commands to see it)

Run everything from repo root `D:\Project\SmartCLI` unless a `cd` is shown. Set `PYTHONIOENCODING=utf-8` on Windows first (the CLIs also auto-reconfigure stdout).

**cmd-art — 18 effects, all render.**
```
cd skills\cmd-art
python -m fx list            # 18: banner_scroll, boids, cube, decrypt, donut, fire,
                             # fireworks, gradient_text, image2ascii, life, plasma,
                             # rain, sparkle, sphere, starfield, text3d, tunnel, typewriter
python -m fx gallery         # one frame of each
python -m fx play donut --seconds 5
python -m fx show --seq "donut:fire:3,plasma::3"
```
Themes: mono, fire, ocean, synthwave, viridis, pastel, matrix-green, rainbow. Verified by `python tests\verify_fx.py` — **26/26 pass** (is_animated routing mirrors the CLI).

**effort_selector replica — violet-ripple selector.**
```
python skills\tui-ui\examples\effort_selector.py --once --stage ultracode --frame 1
```
24 KB, composing engine `field.Ripple` with **zero inline ripple math** (the ripple is sampled from the primitive; verified at runtime — `.sample` called, no inline `math.cos`). Measured constants: XDR 8-step violet palette `rgb(62,22,118)→rgb(140,80,240)`, `trackChars` with `┋` (U+2506), triangle cols `[1,10,20,30,40,53]`, `λ=20`, `travel = elapsed_ticks × 0.03`, aspect-corrected distance, SS3 `ESC O C` navigation. (Caveat: real-terminal cadence eyeball still open — see §5.)

**drive-tui — 8 recipes, REPL drive confirmed end-to-end.**
```
python skills\drive-tui\scripts\tui.py start --cmd "python" --cols 80 --rows 24
python skills\drive-tui\scripts\tui.py wait-regex --id <SID> ">>> " --timeout-ms 15000
python skills\drive-tui\scripts\tui.py send-line --id <SID> "print(6*7)"
python skills\drive-tui\scripts\tui.py snapshot --id <SID>
python skills\drive-tui\scripts\tui.py close --id <SID>
```
8 recipes live via `all_patterns()`: repl, menu_select, pager, search_filter, confirm, form, progress, wizard. Python API: `sys.path.insert(0,"skills/drive-tui"); from patterns import classify, explain, all_patterns, get, load_all; from smartcli_core import PtySession`. REPL drive confirmed (`run_line` → `['42']`); fault isolation verified (a crashing recipe module leaves the rest registered); probes `_drive_probe1..5.py` + `probe_pty_fx.py` PASS (`_drive_probe2.py` prints one warning **by design** — it's the fail-soft test).

**Screenshot harness — pyte→PIL→PNG (honestly labelled, not real tmux).**
```
python tools\screenshot\cli.py selftest
python tools\screenshot\perception_matrix.py
python tools\screenshot\tui_ui_smoke.py
python tools\screenshot\sweep.py           # outputs under tools/screenshot/out/
```
`render_bytes_to_screen` bakes the `\n`→`\r\n` CRLF normalization. Every capture carries `shot.py:RENDER_LABEL` = pyte-simulation.

**tui-ui — cell-accurate layout, self_test green.**
```
cd skills\tui-ui
python -m ui widgets                       # 15 widgets
python -m ui gallery --width 100 --height 30
python self_test.py                        # 30 rows × exactly 100 cells, no fr drift
```
`self_test.py` also passes at (40,12),(80,24),(120,40),(200,50): box-drawing present, truecolor SGR present, `width()` edge cases correct, CJK bars land on the same columns as ASCII (wide-char alignment proven).

**AGENTCLI validation harness.**
```
python tools\agentcli\validate_agentcli.py            # local mock, no API keys
python tools\agentcli\validate_agentcli.py --external # probe installed Codex/Aider/OpenCode/Goose
```
Missing external tools = skipped, not failed. Six scenarios: repl/confirm/progress/menu_select/search_filter/subagents.

**Regression set (all exit 0).**
```
python tests\_readme_literal.py    python tests\verify_fx.py
python tests\probe_pty_fx.py       python tests\_drive_probe1..5.py
```
Plus: 3 external-AI fixes (2026-07-07) re-run exit 0 — README literal import-order crash, verify_fx dispatch, repl_session settle-loop (documented in `AUDIT-REPORT.md`; `smartcli_core` NOT touched).

---

## 3. The knowledge graph — what it is, how to use it

`knowledge/` is the project's brain: a wiki-link graph of exact formulas, ANSI sequences, and constants, each note carrying a **Source:** and cross-links. Entry point is **`knowledge/INDEX.md`**. Read it before building anything — it exists so you don't head-canon a formula that's already measured on disk.

**Lane selection (the one discipline that matters):**
- **Replica task** (recreate a real program's look) → *measure ground truth first.* Start at **`[[hard-lessons]]`** (the 10 rules, §4 below) and **`[[effort-selector]]`** (the worked replica). Decompile / drive / capture the real thing before you write render code.
- **Creative task** (design something new) → *compose the four primitives.* Start at **`[[rendering-model]]`**: field shaders (`field.py`), sub-cell raster (`raster.py`), box junctions (`box_junction.py`), honest color degrade (`color_model.py`). Most "new" effects are a composition of these plus a case study in `works/`.

The **Works wing** (`works/`, 27 studied programs — cbonsai, no-more-secrets, sl, asciiquarium, cava, firework-rs, chafa, notcurses, neo …) is the design brain: each has a real source URL and the extracted algorithm. The six newest concept notes distilled from them are the ready building blocks: `effects/procedural-branching` (cbonsai recursion), `effects/decrypt-reveal` (nms 3-phase reveal), `effects/sprite-scroll` (sl/asciiquarium blit), `effects/color-mask-sprites` (parallel glyph/color layers), `effects/particle-system` (firework-rs float physics), `effects/spectrum-bars` (cava log-bins + eighth-blocks). `sources/` holds the 10 raw research digests behind the notes. Honest `*(verify)*` accuracy flags remain on `neo`/`sl`/`notcurses`/`chafa` (tech debt, not defects).

---

## 4. HARD RULES that must never be re-lost

Source of record: `skills/tui-ui/references/HARD-LESSONS.md` (Chinese, 10 rules) ⇄ `[[hard-lessons]]`. These are the distilled record of a **dozen failed iterations** recreating the real /effort-style ultracode animation. The root cause was never coding ability — it was **method: guessing + self-validation instead of looking at reality.** Condensed, each with its WHY:

1. **Measure ground truth, never head-canon.** If the real program exists, decompile for exact constants, drive it with `PtySession`, capture per-cell bytes/colors — and for animation capture *multiple* PNG frames. *WHY: every failed round was built against imagination, not truth.*
2. **Confirm scale AND shape before writing render code.** The `/effort` glow was an 8-row × 88-col rectangle, misjudged as a "1–2 row ripple bar" for a dozen rounds. *WHY: an order-of-magnitude scale error makes all downstream render code wrong; decide 1-D vs 2-D vs radial first.*
3. **Animation needs MULTIPLE frames — one frame can't infer motion.** Flow ≠ diffusion ≠ pulse. Capture continuous frames ~0.1–0.15s apart and measure the moving edge (the real one expanded left-edge col 49→39→27→8, ~31 cols/sec). *WHY: a single frame is a still photo; motion is only visible over time.*
4. **Verify on the REAL run path, never a self-satisfying preview.** pyte static PNG / patched harness ≠ what the user's terminal shows. *WHY: a green preview that isn't the real path is a lie you tell yourself.*
5. **A test-harness monkeypatch hides real crashes.** Patching `es.dist=_dist` made the PNG "pass" while the real script had no `dist` import and crashed `NameError` (black screen). Run the script's OWN full startup (`python script.py`, no patches), capture stderr. *WHY: the patch fills the exact gap that would crash in production.*
6. **`isatty()=False` must NOT skip the animation loop.** Under any PTY (including SmartCLI's own) isatty is often False. isatty should gate **keyboard input only**, never whether animation runs. *WHY: gating the loop on isatty makes the effect vanish precisely when driven by an agent.*
7. **CRLF for terminals — LF alone does not return to column 0.** Convert `\n`→`\r\n` before feeding a terminal/pyte (LNM off by default; the harness already normalizes). *WHY: LF-only output stair-steps diagonally down the screen.*
8. **UTF-8 stdout — Windows non-UTF-8 crashes on non-ASCII glyphs.** `▀`/`⏵`/box-drawing → gbk/cp936 `UnicodeEncodeError`. Do `sys.stdout.reconfigure(encoding='utf-8', errors='replace')` at startup and force UTF-8 reading child output. *WHY: the default Windows code page can't encode the glyphs these effects are made of.*
9. **Navigation = `ESC O C` (SS3 application cursor mode), not `ESC [ C`.** `[[application-cursor-mode]]` ⇄ `[[application-cursor-keys-deckm]]` documents this as *the exact bug that contaminated effort_selector navigation*. *WHY: apps in DECCKM emit SS3 arrows; sending CSI arrows moves nothing.*
10. **You ARE an agent CLI — drive real programs + capture, don't ask/guess.** Use SmartCLI to drive the real target for ground truth AND to drive your own script for its real render + stderr, then diff numerically. Gotcha: if your script enters alt-screen (`?1049h`), pyte captures the empty main screen — slice stdout bytes on HOME (`\x1b[H`) and render the last frame. Don't ask the user "what does it look like" — you can look yourself. *WHY: the user's time is for direction decisions, not observation you're fully equipped to do.*

Reproducible ground-truth archive (INTERNAL-ONLY — gitignored, EXCLUDED from public release for IP reasons): `research/cc-decompiled/` and `research/real-frames/`. The public source of truth for the effort replica is the code itself (`skills/tui-ui/examples/effort_selector.py` + `ui/field.py::Ripple`).

---

## 5. Environment (how to run things)

- **OS/host:** Windows 11 Pro (10.0.26200) + MSYS2 bash + PowerShell. **NO tmux, NO WSL distro** — tmux cannot run locally; `skills/cmd-art/tmux/*.sh` can't be exercised here. Git-bash / MSYS2 tooling at `D:/Software/Git`.
- **Runtimes:** Python **3.14.6**, Node 24.16. `pyte` + `pywinpty` pip-installed and importable. Caveat: `import pyte` works but `pyte.__version__` does NOT exist — don't rely on it.
- **PTY backend rule:** on Windows drive PTYs via **pywinpty (ConPTY)**, not tmux; keep the backend pluggable so Linux/mac use pexpect/posix pty. ANSI truecolor works in Windows Terminal without tmux.
- **ConPTY caveats (baked into drive-tui SKILL.md):** (1) *startup quiet-gap* — the child's banner can land ~3s after spawn (Python REPL) while the first byte is ~20ms; use a strict `wait-regex` with a generous timeout (e.g. 15000ms) for the FIRST prompt, NOT bare `wait`/`wait_ready` (it may declare STABLE on a still-blank screen). (2) *raw Ctrl-C does NOT reliably interrupt* a line-mode child under ConPTY — recover by `close` + `start` a fresh session (C-c works on POSIX).
- **Encoding:** set `PYTHONIOENCODING=utf-8` on Windows so box/CJK glyphs encode (rule 8).
- **Codex subagent dispatcher is QUOTA-EXHAUSTED / DEAD.** The gateway (`192.168.11.4:8990`) kept 429/502-failing during workflows; the effort_selector port and primitives 2–4 had to be hand-finished when the port agent stalled on it. **Treat codex as unavailable — do live research via built-in WebSearch / WebFetch.** (`codex-subagent-dispatch.md` documents the intended flow and its own "falls back to own WebSearch" clause.)
- **Parallelism / standing preference:** unlimited token budget → default to concurrent ultracode/multi-agent workflows with adversarial verify passes (`ultracode-standing-preference.md`).

**Key file locations:**
- Skills: `skills/{cmd-art,drive-tui,tui-ui}/SKILL.md`
- Must-read before any replica: `skills/tui-ui/references/HARD-LESSONS.md` (+ `references/RENDERING-MODEL.md`)
- Worked replica: `skills/tui-ui/examples/effort_selector.py`
- Ground-truth archive (INTERNAL-ONLY, gitignored / excluded from release): `research/cc-decompiled/`, `research/real-frames/`
- Knowledge graph root: `knowledge/INDEX.md`
- Docs: root `README.md`, `README-USAGE.md`; audit `AUDIT-REPORT.md`; agentcli `AGENTCLI-VALIDATION.md`; research archive `research/README.md`
- Memory: `C:/Users/dwgx1/.claude/projects/D--Project-SmartCLI/memory/` (MEMORY.md index + nodes)

---

## 6. OPEN TASKS (ready-to-run framing)

1. **Finalize effort_selector polish — the one truly-open replica item.** The `travel` parameter is the perennial trap: keep it **small (~λ×1..1.6, breathing)** so the ripple stays localized on the ultracode/max side; a large travel washes the whole panel purple (the frame the user rejected). Label distances from origin: ultracode 4, max 14, xhigh 25, high 34, medium 45, low 53 — keep travel < ~26 so low/medium/high/xhigh stay clean dim-gray. Verified in pyte; **eyeball the animation cadence in a REAL Windows Terminal** (rule 4 — a prior version's marker drifted in cmd.exe). Ready run: `python skills\tui-ui\examples\effort_selector.py` (interactive) and step frames with `--once --frame N`.
2. **POSIX-verify drive-tui.** All verification is Windows/ConPTY. The POSIX daemon (`start_new_session`) and `C-c` interrupt path are coded but machine-unverified here. Run the drive-tui CLI + probes on a Linux/mac box and confirm `close`+interrupt behavior; the tmux launchers (`skills/cmd-art/tmux/*.sh`) also need a real tmux host.
3. **Build new works using the learned techniques.** The six new concept notes are ready building blocks — e.g. a no-more-secrets **decrypt** effect (`[[decrypt-reveal]]`, `rand()%5000` per-cell timer, distance-driven churn), **cava eighth-block spectrum bars** (`[[spectrum-bars]]`, log-bins + gravity smoothing), **braille smooth graphs** (`raster.py` braille sub-cell), particle **fireworks** (`[[particle-system]]` float physics). Compose the four primitives; cite the `works/` case study. Add each as a new `fx` effect (pure frame producer) or tui-ui widget, and verify with the screenshot harness + on the real run path.
4. **Wire knowledge into skills further.** The 3 SKILLs now link `knowledge/INDEX.md` (replica vs creative lanes). Deepen recipe↔`tui-patterns/` and effect↔`effects/` cross-links as new works land; keep the count/claim drift at zero (the last audit fixed 11→14 widgets, then a braille line-chart widget took it 14→15; 19→18 effects).
5. **Author the remaining tech-debt items** as new works are studied: resolve the `*(verify)*` accuracy flags on `neo`/`sl`/`notcurses`/`chafa` by re-fetching their real constants.
6. **Re-fund or replace codex, or keep relying on WebSearch.** The dispatcher is dead (§5). Either restore the gateway quota or continue using built-in WebSearch/WebFetch for live research — do not block on codex.
7. **Standing re-verify-after-workflows:** confirm the 3 external fixes stay exit-0 after any Smoke-phase workflow that edits fx effects or recipe `matches()` (`external-ai-fixes.md`).

Non-issues, do not "fix": drive-tui's `description` has an unquoted `Keywords: TUI` colon that a strict YAML parser trips on but the shipping skill loader accepts (leave it or quote it — behavior-neutral); `_drive_probe2.py`'s one warning is by design; the screenshot harness labelling itself pyte-simulation is correct honesty.

---

## CONTINUATION PROMPT (paste to next AI)

```
You are the next AI taking over SmartCLI at D:\Project\SmartCLI on Windows 11.
Read D:\Project\SmartCLI\HANDOFF.md and knowledge\INDEX.md before doing anything else.

STANDING DIRECTIVES (non-negotiable):
- Token budget is UNLIMITED. Optimize for MAX QUALITY, never for brevity or cost.
- Default to concurrent ULTRACODE / multi-agent workflows for any non-trivial task,
  each with an adversarial verify pass. Parallelize independent work.
- Quality only goes UP, never down. Never regress a working artifact to "simplify."
- VERIFY ON THE REAL RUN PATH. A green preview or a monkeypatched harness is not proof.
  Run the script's own full startup (python script.py, no patches), capture stderr,
  and open the result in a REAL terminal to show the user.
- CONSULT knowledge\INDEX.md FIRST. The exact formulas, ANSI sequences, and constants
  are already measured on disk. Do not head-canon anything that a note already states.
- smartcli_core\ is DO-NOT-MODIFY.

WHAT SMARTCLI IS:
Three Agent Skills over one pluggable PTY+pyte core (smartcli_core\ = pty_backend/
screen_model/snapshot/readiness/session; NOT tmux-bound — pluggable so Windows uses
ConPTY/pywinpty and Linux/mac use posix pty). The skills:
  - drive-tui  : DRIVE interactive TUIs via perceive->decide->act->wait->confirm,
                 never blind-sleep. CLI scripts/tui.py (persistent daemon + one-shot run)
                 + 8 importable recipes (repl, menu_select, pager, search_filter,
                 confirm, form, progress, wizard).
  - cmd-art    : DESIGN terminal visuals via `python -m fx` — 18 effects, 8 themes,
                 pure frame-producer Effect ABC + @register auto-discovery.
  - tui-ui     : web-like cell-accurate layout engine emitting tmux-safe ANSI frames
                 (SGR + newlines only). 15 widgets + ENGINE (field/raster/box_junction/
                 color_model). Produces frames; something else owns the terminal.
The BRAIN is knowledge\ (140 md files, 122 concept/works entries, 0 dangling links):
a wiki-link graph of formulas+sources+cross-links. The LESSONS are in
skills\tui-ui\references\HARD-LESSONS.md ⇄ [[hard-lessons]].

WORKING METHOD (this is how the dozen failed rounds were finally beaten):
1. Measure ground truth — decompile / drive the real program with PtySession / capture
   per-cell bytes+colors. For animation capture MULTIPLE frames ~0.1-0.15s apart and
   measure the moving edge over time. Never build against imagination.
2. Confirm SCALE and SHAPE before writing render code (1-D vs 2-D vs radial; count rows
   and washed column spans). The /effort glow was an 8x88 rectangle misread as a 1-2 row
   bar for a dozen rounds.
3. You ARE an agent CLI: use SmartCLI's own PTY to drive BOTH the real target (for ground
   truth) AND your own script (for its real render + stderr), then diff numerically.
   If your script enters alt-screen (?1049h), pyte sees the empty main screen — slice
   stdout on HOME (\x1b[H) and render the last frame.
4. Don't ask the user "what does it look like" — look yourself, then show them.
Hard mechanics that bite on Windows: CRLF (\n -> \r\n) before feeding a terminal/pyte;
sys.stdout.reconfigure(encoding='utf-8', errors='replace') at startup; isatty()=False
must gate keyboard input ONLY, never the animation loop; TUI navigation is ESC O C
(SS3 application-cursor mode), not ESC [ C.

ENVIRONMENT: Windows 11, Python 3.14.6 + pyte + pywinpty (pyte.__version__ does not exist).
NO tmux, NO WSL locally. Git-bash at D:/Software/Git. Set PYTHONIOENCODING=utf-8.
ConPTY: first prompt can lag ~3s — use strict wait-regex w/ 15000ms timeout, not bare
wait; raw Ctrl-C is unreliable on ConPTY — recover with close+start.
The codex subagent dispatcher (192.168.11.4:8990) is QUOTA-EXHAUSTED / DEAD — do all live
research with built-in WebSearch / WebFetch, do not block on codex.

OPEN OBJECTIVES (each can only be improved, start immediately):
1. Finalize effort_selector polish: eyeball its animation cadence in a REAL Windows
   Terminal. Keep the field.Ripple `travel` SMALL (~lambda x1..1.6, breathing) so the
   ripple stays localized on the ultracode/max side; travel < ~26 keeps low/medium/high/
   xhigh clean dim-gray. Label distances: ultracode 4, max 14, xhigh 25, high 34,
   medium 45, low 53. Run: python skills\tui-ui\examples\effort_selector.py
   (interactive) and step with --once --frame N. It is bit-exact in pyte; the only gap
   is the real-terminal eyeball.
2. POSIX-verify drive-tui on a Linux/mac host: the daemon (start_new_session) and C-c
   interrupt path are coded but unverified off Windows. Also exercise the tmux launchers
   (skills\cmd-art\tmux\*.sh) on a real tmux host.
3. Build NEW works by composing the four engine primitives + a works\ case study — e.g.
   no-more-secrets decrypt ([[decrypt-reveal]], rand()%5000 per-cell timer), cava
   eighth-block spectrum bars ([[spectrum-bars]], log-bins + gravity smoothing), braille
   smooth graphs (raster.py braille sub-cell), firework-rs particle fireworks
   ([[particle-system]] float physics). Add each as a pure-frame fx effect or tui-ui
   widget; verify with the screenshot harness AND on the real run path.
4. Deepen the knowledge<->skills wiring (recipe<->tui-patterns, effect<->effects notes);
   keep count/claim drift at zero (widgets=15, effects=18).
5. Resolve the *(verify)* accuracy flags on neo/sl/notcurses/chafa by re-fetching real
   constants as you study them.
6. Rely on WebSearch/WebFetch for research (codex is dead); optionally restore its quota.

VERIFY WHAT YOU SHIP (all should exit 0):
  cd skills\cmd-art && python -m fx list && python -m fx gallery
  python skills\tui-ui\examples\effort_selector.py --once --stage ultracode --frame 1
  python skills\drive-tui\scripts\tui.py start --cmd "python" --cols 80 --rows 24
    -> wait-regex --id <SID> ">>> " --timeout-ms 15000 -> send-line -> snapshot -> close
  cd skills\tui-ui && python -m ui widgets && python self_test.py
  python tools\screenshot\cli.py selftest
  python tests\verify_fx.py && python tests\_readme_literal.py && python tests\probe_pty_fx.py
Then open the visual result in a real Windows Terminal and show the user before calling
anything done.
```


