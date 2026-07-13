# SmartCLI — Handoff (承上启下)

*Written 2026-07-08, last updated **2026-07-13**. This is the single document a fresh AI reads first to pick up SmartCLI without re-deriving anything. It records the **current release state**, what the project IS, what already WORKS (with the exact commands to see it), the brain (`knowledge/`), the hard-won rules that must never be re-lost, the environment, and the open tasks framed so you can start in one move. Baked-in truths (re-verified against code 2026-07-13): there are **THREE** skills, the live `fx` registry has **19** effects (a 3D `solarsystem` orrery was added), and `tui-ui` has **15** widgets. **Read §7 (2026-07-13 session) first for the most recent work — website, POSIX real-Linux fixes, and the launch plan.***

---

## 0. Release & current state (v0.1.2) — READ THIS FIRST

SmartCLI is **published and public** as of 2026-07-12. This section is the authoritative current-state record; anything older in this doc that contradicts it is stale.

**Where it lives:**
- **PyPI:** `pip install smartcli-toolkit` → https://pypi.org/project/smartcli-toolkit/ . The dist name is **`smartcli-toolkit`**; the **import package stays `smartcli_core`** (`from smartcli_core import PtySession`).
- **GitHub:** public repo **github.com/dwgx/SmartCLI**, branch `main`, tags **v0.1.0 / v0.1.1 / v0.1.2** each with a matching GitHub Release.
- **Claude plugin marketplace:** `.claude-plugin/marketplace.json` is present → users run **`/plugin marketplace add dwgx/SmartCLI`**.
- **skillhu.bz:** all 3 skills published — skillhu.bz/skill/cmd-art, skillhu.bz/skill/drive-tui, skillhu.bz/skill/tui-ui.

**Version consistency (VERSION = 0.1.2, verified 2026-07-12 across):** `pyproject.toml`, `smartcli_core/__init__.py` `__version__`, `skills/cmd-art/fx/__init__.py` `__version__`, all 3 `skills/*/SKILL.md` `version:` fields, and `.claude-plugin/marketplace.json` plugin version. **When you bump the version, all six must move together.**

**CI / publishing:**
- `.github/workflows/ci.yml` — **Windows-only** CI on the deterministic tests.
- `.github/workflows/publish.yml` — PyPI **Trusted Publishing (OIDC)**, tag-push triggered. ✅ **NOW WORKING (verified 2026-07-13):** the one-time setup is done — a Trusted Publisher is registered on PyPI (owner `dwgx`, **repo `SmartCLI`** — the GitHub repo name, NOT the PyPI dist name; that mismatch was the original `invalid-publisher` bug) and the `pypi` GitHub Environment exists. A `workflow_dispatch` run (29245353129) completed green: the OIDC handshake succeeded and the publish step ran against `upload.pypi.org` (0.1.2 files were `skip-existing`-skipped as already present). So **tag-push auto-publish now works**: bump the version everywhere, `git tag vX.Y.Z && git push origin vX.Y.Z`. `skip-existing:true` is set so a re-run on an existing version is a no-op, not an error. (Historical: v0.1.0/0.1.1/0.1.2 were originally uploaded **manually with `twine --disable-progress-bar`** because OIDC was not yet configured — no longer necessary.)

**Live counts (re-verified against code 2026-07-13):** cmd-art **19 effects / 8 themes** (solarsystem was added 2026-07-13, after the v0.1.2 tag — that is why older lines say 18); drive-tui **8 recipes**; tui-ui **15 widgets** (11 core + 4 in `ui/widgets_ext/`, incl. `braille_chart.py`); knowledge **122-note graph** (**140 `.md` files**). Any doc that still says **18 effects** or **14 widgets** is STALE — `python -m fx list` prints 19, `python -m ui widgets` prints 15.

**Security note:** a PyPI API token's plaintext appeared in a prior session's chat. The owner chose **not** to revoke it. Recommended action still stands: revoke it and rely on the OIDC publish workflow (after the one-time Trusted-Publisher setup above).

**Excluded from release (keep excluded):** `research/cc-decompiled/` and `research/real-frames/` are gitignored (0 tracked files, verified) and carry the project's internal reverse-engineering assets. All provenance wording in *shipping* files was neutralized per the owner's decision. Do **not** re-expose these dirs or reintroduce fresh provenance wording.

---

## 1. What SmartCLI IS

**Shared core (`smartcli_core/`).** A pluggable PTY backend + `pyte` screen model + semantic snapshot + readiness sync — modules `pty_backend / screen_model / snapshot / readiness / session`. **⚠️ POLICY: DO-NOT-MODIFY except with real-run-path verification + independent adversarial review + no regression across the full recipe suite.** (It was DO-NOT-MODIFY outright; in v0.1.1/v0.1.2 it was deliberately modified under this exception with user authorization — see §2 core fixes #1/#2/#4.) The deliberate architecture call: the core is a **pluggable PTY layer, NOT tmux-bound**. Target programs may run in Linux containers (tmux there) while local dev runs on Windows (ConPTY via pywinpty). Screen perception uses `pyte` structured-text snapshots (chosen over screenshot/vision on purpose) so one screen model feeds both the agent (perceive, up) and rendering (down). The hard, valuable part is the ACI layer: readiness sync, compression of raw screen to a semantic tree, and action translation (intent → key sequence).

**drive-tui skill (`skills/drive-tui/`).** Teaches an AI to DRIVE interactive terminal programs (REPLs, installers, vim, agent CLIs like kiro-cli, arrow-key menus, y/N prompts, password fields, curses UIs) through a PTY via a **perceive → decide → act → wait → confirm** loop — never blind-`sleep`, always re-snapshot after acting. The surface is a thin CLI `scripts/tui.py` with two modes: **A) persistent session** (a detached localhost-only daemon owns one live program; state survives across shell calls — `start/snapshot/send-text/send-line/keys/wait/wait-regex/alive/close/list`) and **B) one-shot `run`** (a JSON step list against a fresh process). On top sits an importable **pattern library** (`patterns/`) that `classify()`s a screen and `drive()`s it with one of **8 recipes**. Fault-isolated `@register` + pkgutil discovery; recipes fail loud on bad intent.

**cmd-art skill (`skills/cmd-art/`).** Helps a human design CMD/terminal visual effects and ASCII art from a one-line request, via `fx` — a "living-template" engine: an `Effect` ABC + `@register` decorator + pkgutil auto-discovery, so effects, themes, and multi-effect shows all compose. Pure Python stdlib (optional `pyfiglet`/`PIL`), truecolor tuned for Windows Terminal. CLI is `python -m fx <list|show|play|gallery|random|show --seq/--script>`; `play` is **bounded by default** (10s on a TTY), degrades to one plain frame on non-TTY, and always restores the terminal via try/finally. Effects are **pure frame producers** (return one full frame; never print/sleep/touch ANSI modes — the play loop owns the terminal). 8 themes; a legacy `scripts/ascii_fx.py` shim preserves the old surface.

**tui-ui skill (`skills/tui-ui/`).** A web-like terminal UI layout engine + widgets emitting **tmux-safe ANSI frames** (SGR color runs + newlines only — no cursor moves, no alt-screen). You compose a tree of renderables (CSS box model margin→border→padding→content, border-box default; `VStack/HStack/Grid/Page` with `Fr` fractional units); it resolves sizes, composites cell grids, and serializes **once**. Everything is display-cell accurate (CJK/emoji/ZWJ/VS16/flag-pairs via `ui.core.width()`, never `len()`), so columns never desync. Beyond widgets it has a real **ENGINE**: `field.py` (CellField shader — LinearGradient/RadialGlow/Ripple/Plasma + Over/Add/Mask/Translate compositors, ASPECT=2 distance), `raster.py` (sub-cell half/quad/braille pixels), `box_junction.py` (edge-algebra auto-connecting `┼┬┤`), `color_model.py` (honest truecolor→256→16→mono degrade). It produces *frames*; something else owns the terminal (contrast drive-tui). **15 widgets live** (11 core + 4 in `ui/widgets_ext/`: `gradient_rule`, `radial_glow`, `slider_track`, `braille_chart`).

**Knowledge graph (`knowledge/`).** A navigable wiki-link graph — **140 `.md` files**, of which **122 concept/works entries** (120 unique slugs; `tmux-capture-pane` intentionally ×3), plus 7 READMEs, INDEX, and 10 `sources/` research digests. Each note carries an exact formula/sequence/constant, a **Source:**, and double-bracketed cross-links. Core discipline is lane-selection: **replica task → measure ground truth first** (start at `[[hard-lessons]]` + `[[effort-selector]]`); **creative task → compose the four primitives** (start at `[[rendering-model]]`). Integrity (re-checked 2026-07-13): 0 dangling links (every `[[slug]]` resolves; the only bracketed non-links are the literal `[[filename-slug]]`/`[[links]]`/`[[see also]]` syntax examples in the section READMEs). A handful of digest-level uncertainties are still honestly marked `*(verify)*` in `INDEX.md` (neo/sl/notcurses/chafa) — see §3 for the correct status.

---

## 2. Current state — DONE & verified (with the exact commands to see it)

Run everything from repo root `D:\Project\SmartCLI` unless a `cd` is shown. Set `PYTHONIOENCODING=utf-8` on Windows first (the CLIs also auto-reconfigure stdout).

**cmd-art — 19 effects, all render.**
```
cd skills\cmd-art
python -m fx list            # 19: banner_scroll, boids, cube, decrypt, donut, fire,
                             # fireworks, gradient_text, image2ascii, life, plasma,
                             # rain, solarsystem, sparkle, sphere, starfield, text3d,
                             # tunnel, typewriter
python -m fx gallery         # one frame of each
python -m fx play donut --seconds 5
python -m fx show --seq "donut:fire:3,plasma::3"
```
Themes: mono, fire, ocean, synthwave, viridis, pastel, matrix-green, rainbow. Verified by `python tests\verify_fx.py` — **27/27 pass** (19 effects + 8 fixed checks; is_animated routing mirrors the CLI).

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
8 recipes live via `all_patterns()`: repl, menu_select, pager, search_filter, confirm, form, progress, wizard. Python API: `sys.path.insert(0,"skills/drive-tui"); from patterns import classify, explain, all_patterns, get, load_all; from smartcli_core import PtySession`. REPL drive confirmed (`run_line` → `['42']`); fault isolation verified (a crashing recipe module leaves the rest registered); probes `_drive_probe1..6.py` + `probe_pty_fx.py` PASS (`_drive_probe2.py` prints one warning **by design** — it's the fail-soft test). **New in v0.1.2:** `_drive_probe6.py` drives the **pager / form / wizard** recipes LIVE (against `tests/_pager_app.py` / `_form_app.py` / `_wizard_app.py`) — those three were never driven end-to-end before; `_tui_cli_probe.py` drives the drive-tui CLI + token-auth surface.

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

**v0.1.1 / v0.1.2 workstream — core & robustness fixes (authorized modification of `smartcli_core`, with independent adversarial verification).**

*Core fixes (all verified on the real run path + adversarial review; the core exception in §1 applies):*
- **FIXED #1 — false-STABLE on a blank startup screen.** `wait_ready` / `wait_until_stable` could declare STABLE on a never-painted blank screen during a ConPTY startup quiet-gap. Added an optional **`blank_hash` gate** (default `None` = byte-identical old behavior); `PtySession` passes its blank baseline so a still-blank screen is not treated as ready.
- **FIXED #2 — quickstart marker could never match.** The docstring example marker `>>> $` can never match pyte's space-padded lines; examples now use the **unanchored `>>> `**.
- **FIXED #4 — stale EOF on backend reuse.** `WinptyBackend.spawn` now **resets `queue` / `_eof` / `_reader`** so a re-used backend cannot inherit a stale EOF sentinel.
- **FIXED #5 (2026-07-13, verified on real Linux) — arrows now adaptive.** Was: arrows always emitted CSI (`ESC[A`), never SS3, so curses/DECCKM apps ignored them. Now `send_keys` reads the live screen's cursor-key mode (`ScreenModel.app_cursor` — pyte records DECCKM as mode value `32`) and emits SS3 (`ESC O A`) to application-cursor apps, CSI otherwise. Verified on Debian 13 ncurses (a `keypad(True)` probe read our `Up` as `KEY_UP`); Windows default path unchanged.
- **FIXED #6 (2026-07-13, verified on real Linux) — POSIX `terminate()` reaps the child.** Was: `SIGTERM` with no `waitpid`, leaving a `<defunct>` zombie. Now polls `waitpid(WNOHANG)` ~1s, `SIGKILL` fallback, blocking reap. Verified on Debian 13 (`_sandbox_posix_backend.py`: `[KNOWN] zombie` → `[OK] reaped`).
- **NOT fixed (recorded as known, with reasons):** **#3** `content_hash` is blind to selection-only cursor movement (design tradeoff — fixing it risks false-*unstable*).

*Skill-code degenerate-input fixes (all with regression locks in `tests/test_degenerate_inputs.py`):* `field.Ripple` (wavelength 0 / falloff 0 / empty palette), `SliderTrack` (empty positions list), `BrailleChart` (non-finite series), and `fx` **Param int coerce** (zero-padded `08`/`010` and `+`/`-` signed based literals now parse; clean error otherwise).

**Regression set (all exit 0).** Unified runner: `python tests\run_all.py`.
```
# deterministic / mutation-verified suite (all GENUINE, not false-green):
python tests\test_readiness.py          # virtual-clock unit tests + blank-gate locks (#1)
python tests\test_degenerate_inputs.py  # the degenerate-input regression locks above
python tests\test_fx_contract.py        # 19 effects x sizes, exact frame contract (enumerates all_effects())
python tests\_drive_probe6.py           # pager/form/wizard driven LIVE
python tests\_tui_cli_probe.py          # drive-tui CLI + token-auth
python skills\tui-ui\ui\box_junction.py # box_junction _selftest (module-level)
# standing regression gate (must stay exit-0):
python tests\verify_fx.py               # 27/27 (19 effects + 8 fixed checks); known random-seconds flake — rerun once
python tests\_readme_literal.py         python tests\probe_pty_fx.py
```
Plus: 3 external-AI fixes (2026-07-07) still exit 0 — README literal import-order crash, verify_fx dispatch, repl_session settle-loop (documented in `AUDIT-REPORT.md`; those did NOT touch `smartcli_core` — the authorized core changes above came later, in v0.1.1/v0.1.2).

---

## 3. The knowledge graph — what it is, how to use it

`knowledge/` is the project's brain: a wiki-link graph of exact formulas, ANSI sequences, and constants, each note carrying a **Source:** and cross-links. Entry point is **`knowledge/INDEX.md`**. Read it before building anything — it exists so you don't head-canon a formula that's already measured on disk.

**Lane selection (the one discipline that matters):**
- **Replica task** (recreate a real program's look) → *measure ground truth first.* Start at **`[[hard-lessons]]`** (the 10 rules, §4 below) and **`[[effort-selector]]`** (the worked replica). Decompile / drive / capture the real thing before you write render code.
- **Creative task** (design something new) → *compose the four primitives.* Start at **`[[rendering-model]]`**: field shaders (`field.py`), sub-cell raster (`raster.py`), box junctions (`box_junction.py`), honest color degrade (`color_model.py`). Most "new" effects are a composition of these plus a case study in `works/`.

The **Works wing** (`works/`, 27 studied programs — cbonsai, no-more-secrets, sl, asciiquarium, cava, firework-rs, chafa, notcurses, neo …) is the design brain: each has a real source URL and the extracted algorithm. The six newest concept notes distilled from them are the ready building blocks: `effects/procedural-branching` (cbonsai recursion), `effects/decrypt-reveal` (nms 3-phase reveal), `effects/sprite-scroll` (sl/asciiquarium blit), `effects/color-mask-sprites` (parallel glyph/color layers), `effects/particle-system` (firework-rs float physics), `effects/spectrum-bars` (cava log-bins + eighth-blocks). `sources/` holds the 10 raw research digests behind the notes. The `neo`/`sl`/`notcurses`/`chafa` notes carry **digest-level `*(verify)*` flags** that `INDEX.md` states honestly (README-level color math, un-re-fetched constants, `ncpile_rasterize` quantization, chafa's cost function) — these are the remaining source-confirmation gaps, not errors. Treat them as "usable, but re-fetch the primary source before quoting an exact constant." (Earlier drafts of this handoff claimed the flags were all resolved; that was wrong — `INDEX.md` is the accurate record.)

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

## 6. OPEN TASKS — "reach A-grade" gaps (benchmarked vs pexpect / conch / Textual / TTE / terminal-bench)

Ranked by impact/effort. The v0.1.2 release, the deterministic/mutation-verified test suite, and the core #1/#2/#4 fixes are DONE — these are what's left.

1. **[DONE 2026-07-13] Ship a `py.typed` marker in `smartcli_core`.** Added + `[tool.setuptools.package-data]`; verified present inside the built wheel. Not version-bumped/published yet.
2. **[S] Add a Linux CI matrix** running the deterministic tests + `tests/_sandbox_posix_backend.py`. The POSIX pty backend is now **verified on real Debian 13** (2026-07-13, via an SSH sandbox — #5/#6 fixed there), but CI is still Windows-only; a Linux job would keep it green automatically instead of relying on a manual SSH run.
3. **[M] MCP-server wrapper over the drive-tui daemon's verb surface** (`start/snapshot/send-*/keys/wait*/alive/close/list`). Biggest adoption lever — usable by any MCP client.
4. **[S] Pattern-list / multi-marker wait** (pexpect-style wait-any that returns *which* marker matched).
5. **[M] Golden-frame snapshot regression test for tui-ui** — commit a baseline frame and diff, like `pytest-textual-snapshot`.
6. **[M] Shared `easing.py` + `Gradient(stops, steps, direction)` builder for cmd-art** to de-duplicate effect math.
7. **[S-M] Ship `spectrum-bars` + `cbonsai` effects** — the knowledge notes `[[spectrum-bars]]` / `[[procedural-branching]]` are ready building blocks. Add each as a pure-frame `fx` effect; verify with `test_fx_contract.py` + on the real run path.
8. **[L] Docs site + contributor onramp:** mkdocs-material site, `CONTRIBUTING.md`, pytest/coverage badge.

**Discoverability (0 stars today):** record a demo GIF/asciinema for the README top (asciinema + agg, or termsvg), then Show HN / r/commandline / `awesome-claude-code` + `awesome-cli-apps` PRs. A calibrated `/deep-research` prompt list exists (anchors: conch, terminal-bench, plotille, TTE, PyPI trusted publishing) — worth saving as `RESEARCH-PROMPTS.md`.

**One-time release chore (blocks tag-push auto-publish):** complete the PyPI Trusted-Publisher setup + `pypi` GitHub Environment described in §0 so `publish.yml` works; until then keep releasing manually with `twine --disable-progress-bar`.

**Still-open replica polish (unchanged from earlier rounds):** eyeball `effort_selector.py`'s animation cadence in a REAL Windows Terminal. Keep `field.Ripple` `travel` **small (~λ×1..1.6, breathing)** so the ripple stays localized on the ultracode/max side; `travel < ~26` keeps low/medium/high/xhigh clean dim-gray. Label distances: ultracode 4, max 14, xhigh 25, high 34, medium 45, low 53. It's bit-exact in pyte; the only gap is the real-terminal eyeball. **drive-tui is now POSIX-verified** (2026-07-13, Debian 13 over SSH: spawn/read/write/resize, DECCKM SS3 arrows, and zombie-free terminate all pass `tests/_sandbox_posix_backend.py`). **macOS: the POSIX backend core is now verified** (2026-07-13, GitHub Actions `macos-latest`: `tests/_sandbox_posix_backend.py` PASSed spawn/read/drive/resize + #6 zombie-free reap on the BSD pty path). The interactive curses DECCKM/SS3-arrow probe is SKIPPED on CI runners (no controllable terminal) — it still wants one real-Mac run over SSH (see `docs/MACOS-VERIFY.md`). Still unverified: the tmux launchers `skills/cmd-art/tmux/*.sh` (need a real tmux host).

**Standing re-verify-after-workflows:** confirm the 3 external fixes + full `tests/run_all.py` stay exit-0 after any workflow that edits fx effects or recipe `matches()` (`external-ai-fixes.md`).

Non-issues, do not "fix": drive-tui's `description` has an unquoted `Keywords: TUI` colon that a strict YAML parser trips on but the shipping skill loader accepts (leave it or quote it — behavior-neutral); `_drive_probe2.py`'s one warning is by design; the screenshot harness labelling itself pyte-simulation is correct honesty; `verify_fx.py`'s random-seconds flake — rerun once.

**Publish-tooling reality (not the project's fault):** LobeHub / agentskillhub publish CLIs have real bugs (`spawn 'start' ENOENT` / IPv6-only callback / server 401) — those channels could NOT be published to. skillhu.bz and PyPI/GitHub succeeded.

---

## 7. 2026-07-13 SESSION — what this long session did (承上启下)

A single long session. The §7 work below was on `main`, pushed, and gate-green at
the time it was written. **A LATER session (2026-07-13) added more work that may be
uncommitted/unpushed when you read this** — the drive-tui `/model` `--stdin` fix, a
docs-site video/lightbox overhaul, and a doc-accuracy pass. **Always run `git status`
+ `git log origin/main..HEAD` first** rather than trusting this line. Ordered by durability.

### 7a. Core POSIX fixes — VERIFIED ON REAL LINUX (the highest-value work)
Two issues that were "known but unverifiable on Windows" (#5/#6) were reproduced,
fixed, and re-verified on a real Debian 13 box over SSH (`ssh dwgx-home-cloud`,
Python 3.13), using an **isolated sandbox** (venv + copied `smartcli_core`):
- **#6 zombie reap** (`smartcli_core/pty_backend.py` `PosixPtyBackend.terminate`):
  was SIGTERM with no `waitpid` → `<defunct>` zombie. Now polls `waitpid(WNOHANG)`
  ~1s, SIGKILL fallback, **bounded** post-SIGKILL reap (no infinite block on
  D-state children — adversarial-review fix A1).
- **#5 adaptive arrows** (`session.py` `KEY_MAP_SS3` + `_resolve_key(app_cursor=)`
  + `send_keys`; `screen_model.py` `app_cursor` prop reading pyte DECCKM = mode
  `1<<5`): arrows now emit SS3 (`ESC O A`) when the app enabled DECCKM, CSI else.
  A real ncurses `keypad(True)` probe read our `Up` as `KEY_UP`.
- Verify script: `tests/_sandbox_posix_backend.py` (run it on any POSIX host).
  Windows path unchanged (CSI when no DECCKM); full drive-probe + tui_cli green;
  vendored copy re-synced. HANDOFF §2 #5/#6 now marked FIXED.
- **macOS POSIX backend core: VERIFIED** (2026-07-13, CI `macos-latest` — BSD pty
  spawn/read/drive/resize + zombie-free reap PASS). The curses DECCKM/SS3 probe is
  SKIPPED on CI (no controllable terminal); one real-Mac SSH run still wanted (see
  `docs/MACOS-VERIFY.md`). **STILL UNVERIFIED:** real tmux. Do NOT claim it.

### 7b. Drop-in self-configuration
`smartcli_core` is now vendored into `skills/drive-tui/_vendor/` (kept
byte-identical by `tools/sync_vendor.py` + `tests/test_vendor_sync.py`), so a lone
drive-tui folder is self-contained. `skills/drive-tui/scripts/smartcli_bootstrap.py`
locates the core robustly ($SMARTCLI_ROOT → walk-up → _vendor → pip). New
`tui.py doctor` subcommand + `--install-deps`. `.claude-plugin/plugin.json` +
`INSTALL.md` added. Also: daemon launch switched `DETACHED_PROCESS` →
`CREATE_NO_WINDOW` so it **no longer steals focus** on Windows.

### 7c. py.typed — DONE
`smartcli_core/py.typed` + `[tool.setuptools.package-data]`; verified inside the
built wheel. NOT version-bumped/published (bump all six sites together at release).

### 7d. Showcase website — `docs/site/`, live at https://dwgx.github.io/SmartCLI/
Anthropic warm-editorial aesthetic (cream `#faf9f5` + coral `#cc785c` + serif
display; the palette + fonts were researched from Anthropic's real brand tokens —
the earlier synthwave version was rejected by the owner). Hand-written single page,
no framework. Has: a JS live-terminal hero that types a **randomized** model×CLI
scenario each load (`assets/app.js`); an interactive **playground** (`assets/toys.js`)
— canvas fx (rain/fire/plasma/stars/life, perf-guarded: 30fps cap + pause when
off-screen/tab-hidden + reduced-motion), a **custom slider** (not native), and a
**DRIVE-TUI toy** (`assets/ccmenu.js`) that is a faithful nested reproduction of the
REAL Claude Code 2.1.207 `/model` menu (captured by driving the actual CLI), with
fixed-size frame + cached selection; a "Driving a real TUI" GIF gallery; a
seamless-loop fx GIF gallery; custom themed scrollbar; OpenGraph/Twitter cards.
**Full 5-language localization**: `index.zh-Hans/zh-Hant/ja/ko.html` + a nav
switcher (translated by a workflow, structure-preserving). Deploy is automatic via
`.github/workflows/pages.yml` on push to `docs/site/**`.

### 7e. Real-TUI proof GIFs (the launch assets)
Driven for real in a **throwaway Docker container** on the Linux box (Docker
29.6.1 available; `docker run` a debian:trixie-slim, drive, `docker rm` — host
untouched), captured to color GIFs via `tests/_demo_lazygit.py` /
`tests/_demo_drive.py` + `tools/make_lazygit_gif.py` (takes `--src/--out/--cols/
--rows`): **lazygit** (hero), **htop**, **ncdu**, **nano**. In `showcase/` +
`docs/site/assets/drive-*.gif`. `_demo_drive.py` is reusable — add a target to its
`SCRIPTS` dict.

### 7f. Launch plan + self-improvement mechanism
- **Two-phase launch plan** in `NEXT-STEPS.md §C` (seed → ignite, 3 audiences).
  **Ready-to-paste copy** for every channel in `docs/LAUNCH-COPY.md` (Show HN,
  Reddit, X, awesome-list PRs, skill-community) — numbers fact-checked. C1 (proof
  reel) + C3 (SEO/OG/repo-homepage) DONE by AI. **C2/C4/C5 are HUMAN-post steps**
  (open the PRs, post to HN/Reddit/X) — copy is written, owner posts on their timing.
- **`skills/drive-tui/references/LIMITATIONS.md`** — a living log the AI reads first
  and appends to; SKILL.md documents the self-improvement loop (reproduce →
  research → verify on the REAL path → record → continue).
- **Competitive reality (from deep research):** the "pyte semantic snapshot + wait
  for stable" pattern is now a CROWDED category (pilotty, ht, termscope, termwright,
  conch, virtui). SmartCLI's genuinely defensible edges are **native Windows+POSIX
  in one library** and **adaptive DECCKM arrows** — NOT "semantic not vision" (that's
  table stakes now). Lead with the Windows-parity + input-correctness angle, not the
  screen-model angle, on HN. 1Panel was REJECTED as a demo (it's a web panel, not a
  TUI). Full research in the launch-copy positioning section.

### 7g. Also done
Fuzz sandbox (`tests/_sandbox_fuzz_core.py`, zero-process) found + fixed real
pyte-crash edges in the perception chain (see §2). CLAUDE.md at repo root has the
**spawn red-line** (2026-07-13 incident: dense concurrent PTY spawns can overload
the machine — verify serially, never fan out real processes).

### NEXT STEPS for the next AI
1. **More real-TUI proof GIFs** (owner wants "震撼"): `nmtui` (network wizard form),
   `vim`, `aptitude`, or drive a real agent CLI (grok/codex) — back to the "AI drives
   AI" narrative. Use `tests/_demo_drive.py` + a throwaway container. Verify serially.
2. **Owner-gated launch**: C2 awesome-list PRs, C4 Show HN/Reddit/X, C5 skill
   community — copy is in `docs/LAUNCH-COPY.md`; the owner posts.
3. **macOS / tmux verification** if a host becomes available (the only unverified
   platforms; would let us drop the caveats).
4. **Optional**: MCP-server wrapper over the drive-tui daemon (biggest adoption
   lever per §6/competitive research); Linux CI leg running `_sandbox_posix_backend.py`.

**Sandbox note:** the Docker demo container is torn down at session end; recreate
per §7e when needed. SSH target is `dwgx-home-cloud` (Debian 13). Never fan out
concurrent real-PTY spawns (CLAUDE.md red-line).

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
- smartcli_core\ is DO-NOT-MODIFY *except* with real-run-path verification + independent
  adversarial review + no regression across the full recipe suite (this is how the
  v0.1.1/v0.1.2 core fixes #1/#2/#4 were made). Never touch it casually.

WHAT SMARTCLI IS:
Three Agent Skills over one pluggable PTY+pyte core (smartcli_core\ = pty_backend/
screen_model/snapshot/readiness/session; NOT tmux-bound — pluggable so Windows uses
ConPTY/pywinpty and Linux/mac use posix pty). The skills:
  - drive-tui  : DRIVE interactive TUIs via perceive->decide->act->wait->confirm,
                 never blind-sleep. CLI scripts/tui.py (persistent daemon + one-shot run)
                 + 8 importable recipes (repl, menu_select, pager, search_filter,
                 confirm, form, progress, wizard).
  - cmd-art    : DESIGN terminal visuals via `python -m fx` — 19 effects, 8 themes,
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

RELEASE STATE (2026-07-12): v0.1.2 is PUBLIC. PyPI `pip install smartcli-toolkit`
(import stays smartcli_core); GitHub github.com/dwgx/SmartCLI (tags v0.1.0/0.1.1/0.1.2 +
Releases); 3 skills on skillhu.bz; `/plugin marketplace add dwgx/SmartCLI`. VERSION 0.1.2
must stay consistent across pyproject / smartcli_core __init__ / fx __init__ / 3 SKILL.md /
marketplace.json. publish.yml (OIDC) NEEDS one-time PyPI Trusted-Publisher + `pypi` GitHub
Environment setup before tag-push auto-publish works; until then release manually with
`python -m twine upload --disable-progress-bar`. cc-decompiled/ stays gitignored/excluded.

OPEN OBJECTIVES — "reach A-grade" gaps (ranked by impact/effort; start immediately):
1. [DONE 2026-07-13] py.typed marker shipped in smartcli_core (verified in the wheel).
2. [S] Add a Linux CI matrix for the deterministic tests + _sandbox_posix_backend.py.
   POSIX backend now VERIFIED on real Debian 13 (2026-07-13, #5/#6 fixed); CI still
   Windows-only, so a Linux job would keep it green automatically.
3. [M] MCP-server wrapper over the drive-tui daemon verb surface — biggest adoption lever.
4. [S] Pattern-list / multi-marker wait (pexpect-style wait-any returning which matched).
5. [M] Golden-frame snapshot regression test for tui-ui (baseline + diff).
6. [M] Shared easing.py + Gradient(stops,steps,direction) builder for cmd-art.
7. [S-M] Ship spectrum-bars + cbonsai fx effects ([[spectrum-bars]] / [[procedural-branching]]
   are ready); verify with test_fx_contract.py + on the real run path.
8. [L] mkdocs-material docs site + CONTRIBUTING.md + pytest/coverage badge.
Discoverability (0 stars): record a demo GIF/asciinema for README top, then Show HN /
r/commandline / awesome-claude-code + awesome-cli-apps PRs.
Still-open replica polish: eyeball effort_selector cadence in a REAL Windows Terminal
(keep field.Ripple travel SMALL, ~lambda x1..1.6; travel < ~26 keeps low/med/high/xhigh
clean dim-gray; distances ultracode 4/max 14/xhigh 25/high 34/medium 45/low 53). POSIX-
verify drive-tui (daemon start_new_session + C-c path) on Linux/mac; tmux launchers need a
real tmux host. Rely on WebSearch/WebFetch (codex dispatcher is dead).

VERIFY WHAT YOU SHIP (all should exit 0):
  python tests\run_all.py                # unified runner (readiness/degenerate/fx-contract/probes)
  cd skills\cmd-art && python -m fx list && python -m fx gallery   # 19 effects
  python skills\tui-ui\examples\effort_selector.py --once --stage ultracode --frame 1
  python skills\drive-tui\scripts\tui.py start --cmd "python" --cols 80 --rows 24
    -> wait-regex --id <SID> ">>> " --timeout-ms 15000 -> send-line -> snapshot -> close
  cd skills\tui-ui && python -m ui widgets && python self_test.py   # 15 widgets
  python skills\tui-ui\ui\box_junction.py                          # box_junction _selftest
  python tests\verify_fx.py && python tests\_readme_literal.py && python tests\probe_pty_fx.py
Then open the visual result in a real Windows Terminal and show the user before calling
anything done.
```


