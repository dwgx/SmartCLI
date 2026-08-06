# SmartCLI — Handoff (承上启下)

*Written 2026-07-08, last updated **2026-07-27**. This is the single document a fresh AI reads first to pick up SmartCLI without re-deriving anything. It records the **current release state**, what the project IS, what already WORKS (with the exact commands to see it), the brain (`knowledge/`), the hard-won rules that must never be re-lost, the environment, and the open tasks framed so you can start in one move. Baked-in truths (re-verified against code 2026-07-27): there are **THREE** skills, the live `fx` registry has **30** effects, `tui-ui` has **17** widgets, drive-tui has **8** recipes, and `knowledge/` has **143** `.md` files. **Read §10 (2026-07-27, v0.2.0 on branch) first for the most recent work — control-plane security hardening, visual_hash + wait_visual_change, the wheel gaining smartcli_drive + three console scripts, MCP Registry OIDC auto-publish, and a full-repo doc-accuracy review; then §9 (v0.1.3→v0.1.8) and §8/§7 for history.***

---

## 0. Release & current state (v0.1.8) — READ THIS FIRST

SmartCLI is **published and public**; latest release **v0.2.0** (2026-07-27, live on PyPI + GitHub + MCP Registry). v0.2.0 shipped from branch `codex/cross-platform-mcp-hardening`, merged to `main` and tagged; `publish.yml` published to PyPI and re-published `server.json` to the MCP Registry via OIDC — all three jobs green, verified by installing `smartcli-toolkit==0.2.0` from PyPI in a clean venv. This section is the authoritative current-state record; anything older in this doc that contradicts it is stale. See §10 for the whole 0.2.0 arc: drive-tui control-plane security hardening, `visual_hash` + `wait_visual_change` (closes old known-#3), the wheel now shipping `smartcli_drive` + three console scripts, `mcp` as a required dependency, Python floor 3.10, CI drive-smoke/package jobs, and **twelve screen-emulation bugs** found by differential testing against real terminals — including the alternate screen buffer, which pyte does not implement at all, so every full-screen TUI was previously unreadable. **BREAKING in 0.2.0:** Python 3.9 dropped; the MCP SDK is a required dependency. v0.1.8 added `wait_any`, **Sixel graphics output**, and a **Terminal-Bench agent adapter** (§9h). v0.1.7 shipped `spectrum_bars` + `cbonsai` (catalog 30) and the **MCP Registry** listing (`io.github.dwgx/smartcli`, active — §9g).

**Where it lives:**
- **PyPI:** `pip install smartcli-toolkit` → https://pypi.org/project/smartcli-toolkit/ . The dist name is **`smartcli-toolkit`**; the **import package stays `smartcli_core`** (`from smartcli_core import PtySession`). Latest on PyPI = **0.2.0** (the JSON index can lag a few minutes after a release — the `Publish to PyPI` workflow going green is the source of truth, not the index).
- **MCP Registry:** **LIVE** — `io.github.dwgx/smartcli` on `registry.modelcontextprotocol.io` (published 2026-07-15 via `mcp-publisher`; ownership verified by the `mcp-name` marker in the PyPI README). MCP clients (Claude/Cursor/VS Code) + aggregators (Smithery/Glama/MCP.so) auto-discover it.
- **GitHub:** public repo **github.com/dwgx/SmartCLI**, branch `main`, tags **v0.1.0 … v0.2.0** each with a matching GitHub Release.
- **Claude plugin marketplace:** `.claude-plugin/marketplace.json` is present → users run **`/plugin marketplace add dwgx/SmartCLI`**.
- **skillhu.bz:** all 3 skills published — skillhu.bz/skill/cmd-art, skillhu.bz/skill/drive-tui, skillhu.bz/skill/tui-ui.
- **Codecov:** live (badge in README, ~50% on the deterministic subset). **Read the Docs:** live at https://smartcli.readthedocs.io/ (mkdocs, separate from the hand-written showcase site on GitHub Pages).

**Version consistency (VERSION = 0.2.0, released) — TEN sites must move together on a bump:** `pyproject.toml`, `smartcli_core/__init__.py` `__version__`, `skills/cmd-art/fx/__init__.py` `__version__`, all 3 `skills/*/SKILL.md` `version:` fields, `.claude-plugin/marketplace.json` plugin version, **`.claude-plugin/plugin.json`** (the site that historically drifted — it sat at 0.1.2 until v0.2.0 re-aligned it), **`skills/drive-tui/_vendor/smartcli_core/__init__.py`** (the vendored copy — `test_vendor_sync` requires it byte-identical), and **`server.json`** (TWO version fields there: top-level + `packages[0].version`, both must equal the package version or the MCP-registry publish fails). After bumping, run `python tools/sync_vendor.py`, then `python tests/test_vendor_sync.py` and `python tests/test_version_sync.py` (the anti-drift gate over all ten sites, added 2026-07-27).

**CI / publishing (9 workflows — updated 2026-07-27):**
- `.github/workflows/ci.yml` — **3-OS matrix** (windows-latest + ubuntu-latest + macos-latest × **py3.10/3.14**, the support boundaries since v0.2.0), deterministic gates on every push/PR: `verify_fx`, `test_fx_contract`, `test_readiness`, `test_degenerate_inputs`, `_sandbox_fuzz_core`, `test_vendor_sync`, **`test_doc_counts` (anti-drift)**, **`test_version_sync` (ten version sites)**, `test_visual_change`, `test_drive_security`, `_readme_literal`, tui-ui `self_test`, `fx list`, `ui widgets`, plus POSIX-only `_sandbox_posix_backend.py` on the non-Windows legs. v0.2.0 added two more jobs: **`drive-smoke`** (3 OS, 15-min timeout — the real-PTY probes `_tui_cli_probe`/`_mcp_probe`/`_sandbox_daemon_robustness` run in CI for the first time, serially, one child at a time) and **`package`** (20-min timeout — wheel build + twine check + `server.json` schema validation + version-site assertions + clean-venv install exercising `smartcli-tui doctor`, the installed MCP entry, and a uvx launch).
- `.github/workflows/publish.yml` — PyPI **Trusted Publishing (OIDC)**, tag-push triggered (prerelease tags guarded off prod). `publish-testpypi.yml` mirrors it to TestPyPI.
- `publish.yml` also gained (v0.2.0) a **`publish-mcp` job**: after a successful PyPI tag publish it re-publishes `server.json` metadata to the MCP Registry via GitHub OIDC using a pinned, checksum-verified `mcp-publisher` — no more manual device-login step.
- Other workflows: `pages.yml` (deploy docs/site), `docker.yml` (GHCR image), `codeql.yml` (security scan), `lint.yml` (since v0.2.0 the ruff correctness subset E9,F63,F7,F82 + mypy BLOCK; full ruff/format stay advisory), `release-drafter.yml`, `bench.yml` (Terminal-Bench, workflow_dispatch).
- publish.yml OIDC — ✅ **WORKING (verified 2026-07-13):** the one-time setup is done — a Trusted Publisher is registered on PyPI (owner `dwgx`, **repo `SmartCLI`** — the GitHub repo name, NOT the PyPI dist name; that mismatch was the original `invalid-publisher` bug) and the `pypi` GitHub Environment exists. A `workflow_dispatch` run (29245353129) completed green: the OIDC handshake succeeded and the publish step ran against `upload.pypi.org` (0.1.2 files were `skip-existing`-skipped as already present). So **tag-push auto-publish now works**: bump the version everywhere, `git tag vX.Y.Z && git push origin vX.Y.Z`. `skip-existing:true` is set so a re-run on an existing version is a no-op, not an error. (Historical: v0.1.0/0.1.1/0.1.2 were originally uploaded **manually with `twine --disable-progress-bar`** because OIDC was not yet configured — no longer necessary.)

**Live counts (re-verified against code 2026-07-27):** cmd-art **30 effects / 8 themes**; drive-tui **8 recipes**; tui-ui **17 widgets** (11 core + 6 in `ui/widgets_ext/`: `braille_chart`, `gradient_rule`, `radial_glow`, `slider_track`, `fuzzy_filter_list`, `preview_pane`); knowledge **143 `.md` files**. `python -m fx list` prints 30; `python -m ui widgets` prints 17. The anti-drift gates: `tests/test_doc_counts.py` enforces the effect AND widget counts (incl. CJK phrasings, plus a D:-path ban) across shipping docs, and `tests/test_version_sync.py` enforces the ten version sites — knowledge-note counts are still verified by hand against disk.

**Security note:** a PyPI API token's plaintext appeared in a prior session's chat. The owner chose **not** to revoke it. Recommended action still stands: revoke it and rely on the OIDC publish workflow (after the one-time Trusted-Publisher setup above).

**Excluded from release (keep excluded):** `research/cc-decompiled/` and `research/real-frames/` are gitignored (0 tracked files, verified) and carry the project's internal reverse-engineering assets. All provenance wording in *shipping* files was neutralized per the owner's decision. Do **not** re-expose these dirs or reintroduce fresh provenance wording.

---

## 1. What SmartCLI IS

**Shared core (`smartcli_core/`).** A pluggable PTY backend + `pyte` screen model + semantic snapshot + readiness sync — modules `pty_backend / screen_model / snapshot / readiness / session`. **⚠️ POLICY: DO-NOT-MODIFY except with real-run-path verification + independent adversarial review + no regression across the full recipe suite.** (It was DO-NOT-MODIFY outright; in v0.1.1/v0.1.2 it was deliberately modified under this exception with user authorization — see §2 core fixes #1/#2/#4.) The deliberate architecture call: the core is a **pluggable PTY layer, NOT tmux-bound**. Target programs may run in Linux containers (tmux there) while local dev runs on Windows (ConPTY via pywinpty). Screen perception uses `pyte` structured-text snapshots (chosen over screenshot/vision on purpose) so one screen model feeds both the agent (perceive, up) and rendering (down). The hard, valuable part is the ACI layer: readiness sync, compression of raw screen to a semantic tree, and action translation (intent → key sequence).

**drive-tui skill (`skills/drive-tui/`).** Teaches an AI to DRIVE interactive terminal programs (REPLs, installers, vim, agent CLIs like kiro-cli, arrow-key menus, y/N prompts, password fields, curses UIs) through a PTY via a **perceive → decide → act → wait → confirm** loop — never blind-`sleep`, always re-snapshot after acting. The surface is a thin CLI `scripts/tui.py` with two modes: **A) persistent session** (a detached localhost-only daemon owns one live program; state survives across shell calls — `start/snapshot/send-text/send-line/keys/wait/wait-regex/wait-change/wait-visual-change/wait-any/alive/close/list/doctor`, most with `--json` machine-readable output since v0.2.0) and **B) one-shot `run`** (a JSON step list against a fresh process). On top sits an importable **pattern library** (`patterns/`) that `classify()`s a screen and `drive()`s it with one of **8 recipes**. Fault-isolated `@register` + pkgutil discovery; recipes fail loud on bad intent.

**cmd-art skill (`skills/cmd-art/`).** Helps a human design CMD/terminal visual effects and ASCII art from a one-line request, via `fx` — a "living-template" engine: an `Effect` ABC + `@register` decorator + pkgutil auto-discovery, so effects, themes, and multi-effect shows all compose. Pure Python stdlib (optional `pyfiglet`/`PIL`), truecolor tuned for Windows Terminal. CLI is `python -m fx <list|show|play|gallery|random|show --seq/--script>`; `play` is **bounded by default** (10s on a TTY), degrades to one plain frame on non-TTY, and always restores the terminal via try/finally. Effects are **pure frame producers** (return one full frame; never print/sleep/touch ANSI modes — the play loop owns the terminal). 8 themes; a legacy `scripts/ascii_fx.py` shim preserves the old surface.

**tui-ui skill (`skills/tui-ui/`).** A web-like terminal UI layout engine + widgets emitting **tmux-safe ANSI frames** (SGR color runs + newlines only — no cursor moves, no alt-screen). You compose a tree of renderables (CSS box model margin→border→padding→content, border-box default; `VStack/HStack/Grid/Page` with `Fr` fractional units); it resolves sizes, composites cell grids, and serializes **once**. Everything is display-cell accurate (CJK/emoji/ZWJ/VS16/flag-pairs via `ui.core.width()`, never `len()`), so columns never desync. Beyond widgets it has a real **ENGINE**: `field.py` (CellField shader — LinearGradient/RadialGlow/Ripple/Plasma + Over/Add/Mask/Translate compositors, ASPECT=2 distance), `raster.py` (sub-cell half/quad/braille pixels), `box_junction.py` (edge-algebra auto-connecting `┼┬┤`), `color_model.py` (honest truecolor→256→16→mono degrade). It produces *frames*; something else owns the terminal (contrast drive-tui). **17 widgets live** (11 core + 6 in `ui/widgets_ext/`: `gradient_rule`, `radial_glow`, `slider_track`, `braille_chart`).

**Knowledge graph (`knowledge/`).** A navigable wiki-link graph — **143 `.md` files**, of which **125 concept/works entries** (98 concept incl. 3 ground-truth + 27 works; 123 unique slugs — `tmux-capture-pane` intentionally ×3), plus 7 READMEs, INDEX, and 10 `sources/` research digests. Each note carries an exact formula/sequence/constant, a **Source:**, and double-bracketed cross-links. Core discipline is lane-selection: **replica task → measure ground truth first** (start at `[[hard-lessons]]` + `[[effort-selector]]`); **creative task → compose the four primitives** (start at `[[rendering-model]]`). Integrity (re-checked 2026-07-13): 0 dangling links (every `[[slug]]` resolves; the only bracketed non-links are the literal `[[filename-slug]]`/`[[links]]`/`[[see also]]` syntax examples in the section READMEs). A handful of digest-level uncertainties are still honestly marked `*(verify)*` in `INDEX.md` (neo/sl/notcurses/chafa) — see §3 for the correct status.

---

## 2. Current state — DONE & verified (with the exact commands to see it)

Run everything from the repo root unless a `cd` is shown (commands below use Windows-style `\` from the original session; swap for `/` on POSIX). Set `PYTHONIOENCODING=utf-8` first (the CLIs also auto-reconfigure stdout).

**cmd-art — 30 effects, all render.**
```
cd skills\cmd-art
python -m fx list            # 30: banner_scroll, boids, cbonsai, cube, decrypt,
                             # donut, fire, fireworks, flames, gradient_text,
                             # image2ascii, julia, life, mandelbrot, nebula, perlin,
                             # plasma, rain, solarsystem, sparkle, spectrum_bars,
                             # sphere, starfield, text3d, text_converge,
                             # text_decrypt, text_flyin, tunnel, typewriter, water
python -m fx gallery         # one frame of each
python -m fx play donut --seconds 5
python -m fx show --seq "donut:fire:3,plasma::3"
```
Themes: mono, fire, ocean, synthwave, viridis, pastel, matrix-green, rainbow. Verified by `python tests\verify_fx.py` — **38/38 pass** (30 effects + 8 fixed checks; is_animated routing mirrors the CLI). New in v0.1.4-v0.1.6: fractals `julia`/`mandelbrot` (smooth coloring) + `perlin`; noise-composition fields `flames`/`water`/`nebula` (domain warping + black-body/caustics, shared `_noiselib.py`); TTE-style text intros `text_flyin`/`text_converge`/`text_decrypt` (on `_texteffect.py` + shared `easing.py`). New in v0.1.7: `spectrum_bars` (cava log-bins + gravity smoothing + eighth-blocks) and `cbonsai` (procedural branching turtle) — the last two knowledge→effect ports.

**effort_selector replica — violet-ripple selector.**
```
python skills\tui-ui\examples\effort_selector.py --once --stage ultracode --frame 1
```
24 KB, composing engine `field.Ripple` with **zero inline ripple math** (the ripple is sampled from the primitive; verified at runtime — `.sample` called, no inline `math.cos`). Measured constants: XDR 8-step violet palette `rgb(62,22,118)→rgb(140,80,240)`, `trackChars` with `┋` (U+2506), triangle cols `[1,10,20,30,40,53]`, `λ=20`, `travel = elapsed_ticks × 0.03`, aspect-corrected distance, SS3 `ESC O C` navigation. (Caveat: real-terminal cadence eyeball still open — see §6.)

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
python -m ui widgets                       # 17 widgets
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
- **#3 RESOLVED in v0.2.0** (was: `content_hash` blind to selection-only cursor movement, recorded as a design tradeoff): `content_hash` deliberately stays text-only, and a parallel primitive **`visual_hash`** (text + SGR attributes + cursor) with **`wait_visual_change`** now covers highlight-bar moves and cursor-only motion, across core/daemon/CLI/one-shot-run/MCP. See §10.

*Skill-code degenerate-input fixes (all with regression locks in `tests/test_degenerate_inputs.py`):* `field.Ripple` (wavelength 0 / falloff 0 / empty palette), `SliderTrack` (empty positions list), `BrailleChart` (non-finite series), and `fx` **Param int coerce** (zero-padded `08`/`010` and `+`/`-` signed based literals now parse; clean error otherwise).

**Regression set (all exit 0).** Unified runner: `python tests\run_all.py`.
```
# deterministic / mutation-verified suite (all GENUINE, not false-green):
python tests\test_readiness.py          # virtual-clock unit tests + blank-gate locks (#1)
python tests\test_degenerate_inputs.py  # the degenerate-input regression locks above
python tests\test_fx_contract.py        # 30 effects x sizes, exact frame contract (enumerates all_effects())
python tests\_drive_probe6.py           # pager/form/wizard driven LIVE
python tests\_tui_cli_probe.py          # drive-tui CLI + token-auth
python skills\tui-ui\ui\box_junction.py # box_junction _selftest (module-level)
# standing regression gate (must stay exit-0):
python tests\verify_fx.py               # 38/38 (30 effects + 8 fixed checks); known random-seconds flake — rerun once
python tests\_readme_literal.py         python tests\probe_pty_fx.py
```
Plus: 3 external-AI fixes (2026-07-07) still exit 0 — README literal import-order crash, verify_fx dispatch, repl_session settle-loop (documented in `AUDIT-REPORT.md`; those did NOT touch `smartcli_core` — the authorized core changes above came later, in v0.1.1/v0.1.2).

---

## 3. The knowledge graph — what it is, how to use it

`knowledge/` is the project's brain: a wiki-link graph of exact formulas, ANSI sequences, and constants, each note carrying a **Source:** and cross-links. Entry point is **`knowledge/INDEX.md`**. Read it before building anything — it exists so you don't head-canon a formula that's already measured on disk.

**Lane selection (the one discipline that matters):**
- **Replica task** (recreate a real program's look) → *measure ground truth first.* Start at **`[[hard-lessons]]`** (the 10 rules, §4 below) and **`[[effort-selector]]`** (the worked replica). Decompile / drive / capture the real thing before you write render code.
- **Creative task** (design something new) → *compose the four primitives.* Start at **`[[rendering-model]]`**: field shaders (`field.py`), sub-cell raster (`raster.py`), box junctions (`box_junction.py`), honest color degrade (`color_model.py`). Most "new" effects are a composition of these plus a case study in `works/`.

The **Works wing** (`works/`, 27 studied programs — cbonsai, no-more-secrets, sl, asciiquarium, cava, firework-rs, chafa, notcurses, neo …) is the design brain: each has a real source URL and the extracted algorithm. The six newest concept notes distilled from them are the ready building blocks: `effects/procedural-branching` (cbonsai recursion), `effects/decrypt-reveal` (nms 3-phase reveal), `effects/sprite-scroll` (sl/asciiquarium blit), `effects/color-mask-sprites` (parallel glyph/color layers), `effects/particle-system` (firework-rs float physics), `effects/spectrum-bars` (cava log-bins + eighth-blocks). `sources/` holds the 10 raw research digests behind the notes. The `neo`/`sl`/`notcurses`/`chafa` notes were **source-verified on 2026-07-08** (each note's `Source:` line names the file checked) and carry no inline `*(verify)*` flags; the one remaining unresolved `*(verify)*` is the galleries note in `works/README.md`. (Re-checked against disk 2026-07-27 — an earlier draft of this paragraph had the direction reversed; when in doubt, grep the notes themselves.)

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

- **Current working copy (since 2026-07-19): macOS (Apple Silicon), Python 3.14.6**, checkout at `/Users/dwgx/Documents/Project/SmartCLI` — the v0.2.0 branch work and the 2026-07-27 review both happened here. The Windows 11 machine below remains the historical primary dev target; treat the project as dual-host and write repo-relative paths in anything agent-facing.
- **OS/host (historical primary):** Windows 11 Pro (10.0.26200) + MSYS2 bash + PowerShell. **NO tmux, NO WSL distro** — tmux cannot run locally; `skills/cmd-art/tmux/*.sh` can't be exercised there. Git-bash / MSYS2 tooling at `D:/Software/Git`.
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
2. **[DONE 2026-07-14] Linux (+ macOS) CI matrix.** `ci.yml` is a **3-OS matrix** (windows/ubuntu/macos; since v0.2.0 the Python legs are the support boundaries **3.10/3.14**) running the deterministic gates on every push/PR, plus `tests/_sandbox_posix_backend.py` on the non-Windows legs — the POSIX backend (verified on real Debian 13 2026-07-13, #5/#6 fixed) is kept green automatically instead of by a manual SSH run. The `test_doc_counts` anti-drift gate also gates PRs now.
3. **[DONE 2026-07-15, v0.1.4; grown since] MCP-server wrapper** — `skills/drive-tui/scripts/mcp_server.py` (FastMCP), now **14 tools** (wait_change/wait_any/wait_visual_change joined over v0.1.6–v0.2.0) mapping the daemon verbs, reusing tui.py's client so the per-session token is auto-attached (no unauthenticated verb), all with standard `ToolAnnotations`. Since v0.2.0 plain `pip install smartcli-toolkit` suffices (`mcp` is a required dep) and the wheel ships `smartcli-mcp`/`smartcli-toolkit` entry points. Covered by `tests/_mcp_probe.py`. **MCP Registry: LIVE** (`io.github.dwgx/smartcli`), and re-publishing on release is automated (publish.yml `publish-mcp` OIDC job) — no human step remains.
4. **[DONE 2026-07-15, v0.1.6] Await-change wait primitive** — `wait_change` (not multi-marker, but the higher-value "did my action land?" primitive pilotty/termscope converged on): block until the screen content-hash changes from a baseline. In session/daemon/CLI (`wait-change`)/MCP. `tests/test_wait_change.py`. Multi-marker `wait-any` remains a smaller open nicety.
5. **[DONE 2026-07-15, v0.1.4] Golden-frame snapshot test** — `tests/test_golden_frames.py` + `tests/golden/*.txt`: every widget rendered to a deterministic frame, diffed against a committed baseline (`--update` to regen), renders twice to reject non-determinism. Skips widgets whose optional dep is absent (banner→pyfiglet).
6. **[DONE 2026-07-15, v0.1.6] Shared `easing.py`** — 14 canonical Penner easings, used by the text effects. (A `Gradient(stops,…)` builder was NOT separately done; theme.gradient already covers most of it.)
7. **[DONE 2026-07-15, v0.1.7] Ship `spectrum_bars` + `cbonsai` effects** — the knowledge notes `[[spectrum-bars]]` / `[[procedural-branching]]` were the ready building blocks. Both shipped as pure-frame `fx` effects (`skills/cmd-art/fx/effects/spectrum_bars.py` + `cbonsai.py`): `spectrum_bars` = cava's log-bins + gravity/integral smoothing + eighth-block sub-cell render over a synthesized signal (aliases `spectrum`/`bars`); `cbonsai` = the stochastic branching turtle (lifeStart 32, multiplier 5, cooldown-gated shoots), seeded RNG generates the whole tree once as an ordered draw-event list, each frame reveals the grown prefix (deterministic). Both pass `test_fx_contract.py` (30 effects x 6 sizes x 5 contracts = 150/150). Catalog 28→30; these were the last two "knowledge → effect" gaps.
8. **[PARTIAL] Docs site + contributor onramp:** `CONTRIBUTING.md` + `SECURITY.md` DONE (v0.1.4); Codecov badge live; **Read the Docs is LIVE** at https://smartcli.readthedocs.io/ (mkdocs, via `.readthedocs.yaml` + `tools/build_docs.py` which rewrites repo-relative links to absolute GitHub URLs). Still open: `TestPyPI`/`conda-forge`/`Homebrew` publishing (configs prepared, human steps in `docs/PACKAGING-NOTES.md`).

**Discoverability (0 stars today):** the README top now carries **real re-driven proof reels** (lazygit/htop/ncdu/nano as 60/30fps MP4+WebM video, not GIFs, incl. Windows/macOS/Linux variants + dialog/vim) — the "record a demo" chore is DONE. Remaining: Show HN / r/commandline / `awesome-claude-code` + `awesome-cli-apps` PRs (copy ready in `docs/LAUNCH-COPY.md`, owner-gated). A calibrated `/deep-research` prompt list exists (anchors: conch, terminal-bench, plotille, TTE, PyPI trusted publishing) — worth saving as `RESEARCH-PROMPTS.md`.

**Release chore — DONE (was: blocks tag-push auto-publish):** the PyPI Trusted-Publisher setup + `pypi` GitHub Environment are complete and OIDC-verified (§0). Tag-push auto-publish now works; twine is no longer needed.

**Still-open replica polish (unchanged from earlier rounds):** eyeball `effort_selector.py`'s animation cadence in a REAL Windows Terminal. Keep `field.Ripple` `travel` **small (~λ×1..1.6, breathing)** so the ripple stays localized on the ultracode/max side; `travel < ~26` keeps low/medium/high/xhigh clean dim-gray. Label distances: ultracode 4, max 14, xhigh 25, high 34, medium 45, low 53. It's bit-exact in pyte; the only gap is the real-terminal eyeball. **drive-tui is now POSIX-verified** (2026-07-13, Debian 13 over SSH: spawn/read/write/resize, DECCKM SS3 arrows, and zombie-free terminate all pass `tests/_sandbox_posix_backend.py`). **macOS: the POSIX backend core is now verified** (2026-07-13, GitHub Actions `macos-latest`: `tests/_sandbox_posix_backend.py` PASSed spawn/read/drive/resize + #6 zombie-free reap on the BSD pty path). The interactive curses DECCKM/SS3-arrow probe is SKIPPED on CI runners (no controllable terminal) — it still wants one real-Mac run over SSH (see `docs/MACOS-VERIFY.md`). **tmux launchers VERIFIED 2026-07-27** on real tmux 3.6b (macOS): `tests/_tmux_launcher_probe.py` drives both `skills/cmd-art/tmux/*.sh` through all five states (no tmux / outside a session / detached / attached client / real split) — 18/18. It found a real bug: `fx-popup` leaked tmux's raw "no current client" with exit 1 when no client was attached, violating its own clean-exit contract; now guarded.

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

## 8. 2026-07-13 → 07-14 SESSION(S) — CI/CD, video reels, hardening (承上启下)

The 21 commits after §7's `8fafa0e` (range `8be24ed..784bf74`). §7 described the
site + POSIX fixes; this section catches up everything since. Verified against disk
2026-07-14. Ordered by durability.

### 8a. CI/CD went from 2 workflows to 8 — the big structural change
`.github/workflows/` now has **8** workflows (was `ci.yml` + `publish.yml`):
- **`ci.yml` is now a 3-OS matrix** — `windows-latest + ubuntu-latest + macos-latest`
  × py3.11/3.12, running ~12 **deterministic** gates on every push/PR (`verify_fx`,
  `test_fx_contract`, `test_readiness`, `test_degenerate_inputs`, `_sandbox_fuzz_core`,
  `test_vendor_sync`, `test_doc_counts`, `_readme_literal`, tui-ui `self_test`,
  `fx list`, `ui widgets`) + POSIX-only `_sandbox_posix_backend.py` on the
  non-Windows legs. This closes OPEN TASK §6#2 (Linux matrix) AND finally covers the
  macOS BSD-pty path in CI. The interactive PTY probes stayed OUT of CI at the time
  (need a live TTY, hang-prone on runners) — *changed in v0.2.0*: they now run
  serially inside the bounded `drive-smoke`/`package` jobs (see §0/§10); the
  pure-memory gates remain the per-matrix-leg crown jewels.
- **`publish.yml`** now guards prod PyPI against prerelease tags; **`publish-testpypi.yml`**
  mirrors to TestPyPI. **`docker.yml`** builds a GHCR image (buildx cache).
  **`codeql.yml`** security scan, **`lint.yml`**, **`release-drafter.yml`**,
  **`pages.yml`** (deploys `docs/site/`). Repo templates + Dependabot added
  (commits 48c62f6, ec5ae05, 65d1146, 61c5a93).
- **Anti-drift now gates PRs:** `test_doc_counts.py` is a CI step, so a doc that says
  a stale count like 18 instead of 19 (or its CJK equivalents — hardened 2026-07-14,
  see 8e) fails the PR.

### 8b. Video proof reels replaced the GIF galleries on the site
The site's "Driving a real TUI" + fx galleries are now **`<video>` (MP4 + WebM)**,
not GIFs: fx at 60fps, drive reels re-driven at 30fps, with a click-to-zoom
**lightbox** (commits 913e738, f8ec911, 3815e19). New captures: **real
cross-platform reels** — Windows (ConPTY) + macOS (BSD pty) + Linux — plus
**dialog-form** and **vim** drives. A **three-OS gallery** section (fixed to 3
columns, ec10f5c) shows the same tool driven on all three platforms. Assets live in
`docs/site/assets/drive-*.{mp4,webm}` (+ `-macos`/`-windows` variants). GIFs are kept
only as `<video>` posters / `showcase/` stills.

### 8c. drive-tui daemon hardening (authorized core-adjacent fixes)
- **Token-leak surfaces closed** (7c21bec): the session daemon's local socket paths
  that could echo screen contents without auth were tightened; `_tui_cli_probe.py`
  now asserts wrong/missing token → rejected with NO screen leak, correct token →
  succeeds (this is the C2-era per-session TOKEN auth, now probe-covered).
- **PTY close-on-error** (47ad62a): a red-line fix — a PTY that errored mid-drive was
  leaking (never `close()`d), the exact concurrency-leak class the CLAUDE.md red-line
  warns about. Now closed on the error path.
- **`--stdin` for send-text/send-line** (8be24ed): values now come via stdin so MSYS
  Git-bash path-conversion can't mangle a payload like `/model` into `D:/…/model`.
  (See memory `[[model-slash-msys-pathconv]]`.)

### 8d. Probes 1–5 became asserting tests; `_tui_cli_probe` wired into run_all
`_drive_probe1..5` were print-only (a human had to eyeball them) — they now **assert**
and return non-zero on failure (0d3b3b4), so `run_all.py` actually gates on them.
`_tui_cli_probe.py` (drive-tui CLI end-to-end + token auth) is now in the `run_all.py`
suite (added 2026-07-14). run_all's suite has grown since — count it with
`build_suite()`, never from this line (it was stale twice); the deterministic
subset is what the CI matrix runs.

### 8e. i18n + anti-drift accuracy pass (2026-07-14)
- **The 4 localized READMEs (zh-Hans/zh-Hant/ja/ko) said a stale 18 (should be 19) and
  omitted `solarsystem`** in their feature paragraphs while the English README + their own
  quick-start/tree said 19 — a self-contradiction the English-only `test_doc_counts`
  regex couldn't see. Fixed all 4 to **19 + solarsystem**.
- **`test_doc_counts.py` hardened** to catch the CJK phrasings (`种效果` / `種效果` /
  `種のエフェクト` / `개 이펙트`) that let the drift slip through, and to force UTF-8
  stdout so it's safe to run standalone on a CP936 console. Mutation-proven: it FAILS
  on the pre-fix READMEs, PASSES after. This is why the anti-drift gate (8a) is now
  trustworthy for localized docs, not just English.
- **grok de-branded from hero surfaces** (ec10f5c + 2026-07-14 follow-up): the static
  hero (`demo.svg` orrery-style animation) and the `app.js` carousel scenario were
  neutralized to a generic `agent` CLI / `Fable 5` model (the three-scenario carousel
  is intentionally KEPT per owner). grok now survives ONLY in the `.chip` tags of the
  5 `index*.html` pages — that is deliberate.

### 8f. Also done
- **i18n README parity** (f169cf1, e37f1f8): "Driving a real TUI" section, dynamic
  badges, tri-platform scope, drive reels, three-OS section, and the live DRIVE-TUI
  `/model` menu toy ported to all 5 locales; dead legacy `.menu/.mrow` CSS + unused
  CSS var aliases removed (6183fc0).
- **tools/ cleanup** (947df4a): one-shot migration/recording helper scripts removed.
- **OIDC publish confirmed working** (229e1bd): §0's Trusted-Publisher story — the
  one-time setup is done, tag-push auto-publish verified green.

### NEXT STEPS for the next AI (updated 2026-07-14)
1. **Owner-gated launch** (unchanged): C2 awesome-list PRs, C4 Show HN/Reddit/X, C5
   skill community — copy is in `docs/LAUNCH-COPY.md`; the owner posts. Proof reels
   now exist (8b), so C1's blocker is cleared.
2. **Host the mkdocs site** (§6#8 PARTIAL): `mkdocs.yml` exists but isn't on Pages yet;
   add `CONTRIBUTING.md` + a coverage badge. Do NOT include `research/cc-decompiled/`.
3. **macOS / tmux real-host verification**: CI covers the macOS POSIX core, but the
   interactive DECCKM/SS3 curses probe is still CI-skipped (needs a real Mac over SSH,
   see `docs/MACOS-VERIFY.md`). tmux launchers are now VERIFIED on real tmux 3.6b
   (2026-07-27, `tests/_tmux_launcher_probe.py`).
4. **A-grade backlog** (§6): MCP-server wrapper (biggest adoption lever), `wait_any`
   multi-marker wait, tui-ui golden-frame snapshot test, `easing.py`/`Gradient` builder,
   spectrum-bars + cbonsai effects.

**Standing (unchanged):** never fan out concurrent real-PTY spawns (CLAUDE.md red-line
— verify serially, one PTY/TUI at a time, close + confirm zero leaks before the next).
The deterministic gates are pure-memory and safe to run freely; the drive probes /
verify_fx spawn real PTYs and are the heavy ones — run them serially, with consent.

---

## 9. 2026-07-15 SESSION — v0.1.3 → v0.1.6 (承上启下)

One long session that shipped four PyPI releases and lit up two external
integrations. All on `main`, pushed, gate-green. Ordered by release. **Standing
rule that held throughout and MUST continue: quality only goes up. Every
smartcli_core touch went through the DO-NOT-MODIFY exception (real-run-path
verify + independent adversarial review + full-suite green).**

### 9a. v0.1.3 — doc-accuracy + anti-drift hardening
- The 4 localized READMEs (zh-Hans/zh-Hant/ja/ko) stated a stale effect count and
  omitted `solarsystem` while English was correct — fixed to match (this was the
  19-effect era; the count is 28 now).
- **`test_doc_counts.py` gained CJK matching** (种效果/種效果/種のエフェクト/개 이펙트)
  and UTF-8 stdout, so the anti-drift gate now catches localized drift too.
  Mutation-verified (failed on the old READMEs, passed after).
- `_tui_cli_probe.py` wired into `run_all.py`.

### 9b. v0.1.4 — MCP server + golden-frame + coverage + a real fx bug
- **MCP server** (§6#3): 11 annotated tools over the daemon, token auto-attached.
- **Golden-frame regression** (§6#5): `tests/test_golden_frames.py` + `tests/golden/`.
- **Multi-process coverage**: `tools/coverage_run.py` + `.coveragerc` +
  `sitecustomize.py` (COVERAGE_PROCESS_START so each run_all subprocess is
  instrumented), advisory CI job uploads to Codecov. Deterministic subset only
  (the PTY probes + fuzz sandbox don't compose with the process-start hook).
- **`fx random` real bug**: it picked from the class `animated` flag, which is
  True for `text3d` even though `is_animated(defaults)` is False → ~1/18 chance
  of a static pick that never entered alt-screen = the `verify_fx` "random" flake.
  Fixed to select on `is_animated(param_defaults())`; verify_fx assertion broadened.
- `CONTRIBUTING.md` + `SECURITY.md` + PR template. bug_report version placeholder.

### 9c. v0.1.5 — CPR device-query answer (core) + diagnose + width knobs + 3 fractals
- **DSR-CPR / DA auto-answer (smartcli_core, DO-NOT-MODIFY exception)**: a driven
  program that emits `ESC[6n` / `ESC[c` and synchronously waits would stall. pyte
  already builds the correct reply and routes it to `Screen.write_process_input`
  (a no-op by default); `ScreenModel` now captures it and `PtySession.pump()`
  writes it back to the PTY. This is conch's "killer feature" — we have it now.
  Locked by `tests/test_cpr_reply.py`, adversarially reviewed (7 risk points).
- **`python -m smartcli_core`** diagnostics (OS/Python/terminal/PTY backend/deps) —
  the Textual `diagnose` idea, the top issue-reducer for a terminal-sensitive tool.
  Added `smartcli_core/__main__.py` (pure addition, vendored copy synced → 8 files).
- **`char_width`/`width` gained `unicode_version` + `ambiguous_wide` knobs** (defaults
  unchanged, forwarded to wcwidth). `tests/test_char_width.py`.
- fractals `julia`/`mandelbrot` (smooth/continuous iteration coloring) + `perlin` (fBm).
- **Codecov + Read the Docs went live.** Codecov: repo tokenless upload works
  (dwgx org enabled it); the CI upload step is advisory/soft-fail and uses
  `CODECOV_TOKEN` only if that secret is configured (see the ci.yml step comment).
  RTD: `.readthedocs.yaml` runs `tools/build_docs.py` (assembles docs/*.md from
  README/SKILL/CHANGELOG/INDEX and REWRITES repo-relative links to absolute
  github.com URLs — the fix for the localized-README language switcher 404ing).

### 9d. v0.1.6 — god-tier fx + sextant/OKLab + 2 widgets + wait_change (reviewed)
- **6 new effects** (see §2): fields `flames`/`water`/`nebula` (Inigo Quilez domain
  warping + Tanner Helland black-body ramp + ridged-noise caustics, shared
  `_noiselib.py`), text intros `text_flyin`/`text_converge`/`text_decrypt`
  (`_texteffect.py` rasterizes via `text3d.big_text`, each char eased from a
  start to its target; shared `easing.py`).
- **2 new widgets**: `FuzzyFilterList` (fzf-style subsequence match + highlight)
  and `PreviewPane`. Golden baselines committed.
- **sextant blitter (2x3) + OKLab perceptual color distance** in `raster.py`.
- **`wait_change`** (§6#4) in session/daemon/CLI/MCP.
- Website playground shows a copy-able `python -m fx play <effect>` command.
- **A TWO-REVIEWER code-review pass caught a HIGH-severity bug before release:**
  the sextant glyph table was wrong for 42/62 masks (the U+1FB00 block OMITS the
  left/right-column patterns, which are the half blocks U+258C/U+2590 — a naive
  offset misaligns everything past mask 21 and overruns into diagonals). Rebuilt
  by reading each glyph's "BLOCK SEXTANT-<n>" Unicode name; self-test now asserts
  the exact mapping (the old test only hit mask 1 and 63, which happened to be
  right, so it never caught it). Also fixed: OKLab crash on negative channels
  (complex-number compare), perlin `int()`-vs-`floor` negative-coord seam,
  PreviewPane negative-scroll wrap. **This is why review is non-negotiable — the
  bug was invisible to me and to the passing test.**

### 9e. Standing state after this session *(2026-07-15 snapshot — superseded by §10)*
- **Regression: `python tests\run_all.py` = 27/27** at the time (the suite has grown
  a lot since — count via `build_suite()`).
- **git clean, synced with origin** was true then. *No longer:* the v0.2.0 work sits
  developed on branch `codex/cross-platform-mcp-hardening`, since merged to `main` and
  tagged `v0.2.0` — see §10.
  Latest tag **v0.1.8** (§9h; §9g = v0.1.7).
- **The default `%TEMP%\smartcli_tui` dir often holds ONE session that is NOT ours**
  (`s10456_*`, a SaoMoLa/VRChat uploader). It's a live third-party process — do
  NOT close it. Probes use an isolated `SMARTCLI_TUI_DIR`, unaffected.
- **Subagents frequently died silently this session** (0-byte transcript, no
  result). If one stalls, don't wait — do the (read-only) work yourself. Never
  trust a subagent's "passed" — re-verify.

### 9f. NEXT — what's genuinely left (see the continuation prompt below for the framed version)
1. **[DONE 2026-07-15, v0.1.7] MCP Registry publish** — `io.github.dwgx/smartcli`
   is LIVE on `registry.modelcontextprotocol.io` (status active). See §9g.
2. **Launch** (human, owner-timed): copy ready in `docs/LAUNCH-COPY.md` — Show HN
   / r/commandline / awesome-list PRs. Proof reels + RTD + Codecov all live now.
3. **Technical backlog** — three big items shipped in v0.1.8 (§9h): **`wait_any`**
   (pexpect multi-marker wait), **Sixel graphics output** (`ui/sixel.py`), and a
   **Terminal-Bench adapter** (`smartcli_tbench/`). STILL OPEN from the design
   research: tui-ui reactive/declarative system + color degrade (Textual/Lipgloss);
   **kitty** graphics protocol (sixel done, kitty is the other image protocol);
   running the Terminal-Bench score on CI (adapter + `bench.yml` ready — needs the
   owner to add an LLM API-key secret and dispatch the workflow); a Harbor / TB-2.0
   port (the current leaderboard uses a different agent interface — see §9h).
4. **Real-terminal eyeball** of effort_selector cadence, a real-Mac/real-tmux run,
   and a **real Windows-Terminal render of `python -m ui sixel`** remain unverified
   platform bits (the sixel BYTES are spec-locked + reviewed; only the visual
   render in a live WT tab is uneyeballed — it can't go through captured stdout).

### 9g. v0.1.7 — spectrum_bars + cbonsai (catalog 30) + MCP Registry LIVE
- **Two new fx effects, the last two knowledge→effect ports** (catalog 28→30):
  - `spectrum_bars` (`skills/cmd-art/fx/effects/spectrum_bars.py`, aliases
    `spectrum`/`bars`): cava's meter pipeline over a synthesized moving-sine
    signal — log-spaced pseudo-bins, gravity-fall + integral smoothing (the
    reusable half of `cavacore.c`), eighth-block `U+2581..U+2588` sub-cell
    vertical resolution. Bass-tilt envelope so lows sit higher, like real audio.
  - `cbonsai` (`skills/cmd-art/fx/effects/cbonsai.py`): the `[[procedural-branching]]`
    stochastic turtle — lifeStart 32, multiplier 5, five branch types
    (trunk/shootL/shootR/dying/dead), cooldown-gated side shoots, direction→glyph
    selection. Because an Effect is a PURE frame producer (no per-char nanosleep),
    a seeded RNG generates the WHOLE tree once as an ordered draw-event list and
    each frame reveals the "grown" prefix — so it animates AND is deterministic.
  - Both pass `test_fx_contract.py` (30 effects × 6 sizes × 5 contracts = 150/150,
    incl. 1×1/2×2 no-crash + 20×8 no-overflow) and were verified LIVE in a real
    PTY (`verify_fx.py spectrum_bars cbonsai` = 2/2: alt-screen enter/leave +
    truecolor + self-exit). Zero PTY leaks confirmed after (CLAUDE.md red-line).
- **MCP Registry: PUBLISHED & LIVE.** `io.github.dwgx/smartcli` on
  `registry.modelcontextprotocol.io`, status **active**. Flow used (repeatable):
  installed `mcp-publisher` v1.8.0 (Windows amd64 binary → `~/bin/`), `mcp-publisher
  validate server.json` (caught: registry caps `description` at **100 chars** — ours
  was 234; trimmed to 98), `mcp-publisher login github` (device code, must run to
  completion so the token lands in `~/.config/mcp-publisher/` — a login interrupted
  mid-authorize does NOT persist the token), `mcp-publisher publish`. Ownership
  verified via the `mcp-name` marker in the PyPI README (was already in 0.1.6's).
- **Docs + site reconciled to 30**: READMEs (5 langs), SKILL/USAGE, MACOS-VERIFY,
  LAUNCH-COPY, and the showcase site's effect-count stat on all 5 localized pages
  (was a stale **19**). `test_doc_counts` green (fx=30).
- **`.gitattributes` language-bar fix**: `docs/site` sources (HTML/JS/CSS) marked
  `linguist-detectable`; localized translations + vendored core marked
  generated/vendored. Was reading ~99% Python because linguist excludes `docs/`
  by default — now reflects the real HTML+JS+Python mix (takes effect after GitHub
  re-runs linguist on push).
- Nine version sites bumped 0.1.6→0.1.7, vendored core re-synced (`test_vendor_sync`
  green), CHANGELOG entry added. Tag `v0.1.7` pushed → OIDC publish + Pages deploy.

### 9h. v0.1.8 — wait_any + Sixel graphics + Terminal-Bench adapter (all reviewed)
Three backlog items, each independently adversarially reviewed (subagent tried to
disprove; findings fixed before ship).
- **`wait_any`** (smartcli_core, DO-NOT-MODIFY exception — real-run + review + full
  suite): pexpect `expect([...])`. `readiness.wait_any(patterns) -> (index, snap)`,
  `-1` on timeout, earliest-in-list wins a same-poll tie, empty list short-circuits.
  `PtySession.wait_any` + drive-tui daemon action + CLI `wait-any` (`--pattern`/
  `--stdin`) + one-shot run step + MCP tool. `tests/test_wait_any.py` (mutation-
  verified: 2 mutations caught). Review clean; added an empty-list short-circuit.
  Live-PTY confirmed (index 0 on a real Python REPL). Vendored copy synced.
- **Sixel graphics** (tui-ui, pure addition — zero regression surface). `ui/sixel.py`:
  `encode_sixel(pixels)` / `raster_to_sixel(raster)` / `print_sixel` / `supports_sixel`
  (DA1 probe). Band-based, 6x6x6 cube quant, RLE, P2=1 transparent, `char=0x3F+mask`
  (bit0=TOP), colors 0..100%. `python -m ui sixel [image] [--probe]`. Spec locked by
  `tests/test_sixel.py` (26 checks incl. DEC "HI" bit-math + round-trip decode;
  mutation-verified). Review clean (esp. the DA1 param parser — splits on `;` before
  membership, so `64`/`14` can't false-positive as attribute `4`). **Real WT render
  NOT eyeballed** (captured stdout can't display sixel — see §9f#4); bytes are proven
  correct. Exact spec/constants from a research pass (VT330/340 + Dankwardt + libsixel).
- **Terminal-Bench adapter** (`smartcli_tbench/`, NOT in the wheel — the `packages`
  list excludes it; since v0.2.0 that list is `smartcli_core` + `smartcli_drive`). Targets **classic `laude-institute/terminal-bench`**
  (`BaseAgent.perform_task(instruction, session: TmuxSession)` — verified from source).
  `driver.py` reimplements `wait_stable`/`wait_for`/`wait_any`/`wait_change` over
  `capture_pane()`; `loop.py` = the perceive→decide→act→wait→confirm loop
  parametrised by a `decide_fn`; `agent.py` = `SmartCliAgent(BaseAgent)` importing TB
  lazily (module imports on a non-TB host → `SmartCliAgent=None`). Pure driver+loop
  unit-tested WITHOUT Docker/TB/LLM (`tests/test_tbench_adapter.py`, 23 checks). Review
  found a MEDIUM bug — `wait_stable` had dropped the core's `min_wait` floor, so a
  slow command would settle on the echoed-command (pre-output) screen; FIXED with
  `min_wait_sec` + a regression test, plus robustness fixes (lazy-import distinguishes
  "not installed" from "broken install"; `poll_ms=0` fake-clock guard). CI
  `bench.yml` (workflow_dispatch, ubuntu-latest) runs an oracle smoke test + the
  scored subset — **needs the owner to add an LLM API-key secret + a `decide_fn`**.
  **Biggest caveat:** the public leaderboard is now TB-2.0 / Harbor with a DIFFERENT
  agent interface (tool/env-mediated, no raw tmux handle) — a classic-TB score is
  real but NOT directly comparable to the 2.0 board; a Harbor port is separate work.
- Nine version sites bumped 0.1.7→0.1.8, vendored core re-synced, CHANGELOG added.
  `smartcli_tbench` is NEW and intentionally excluded from the wheel packaging.

---

## 10. 2026-07-19 → 2026-07-27 — the v0.2.0 arc (RELEASED 2026-07-27)

The work was authored ~2026-07-19 (by a codex-branded agent; it sat uncommitted in the
working tree for a week) and was audited, verified, fixed, committed, and reconciled on
2026-07-27 by a 3-workflow ultracode review (10-agent understand pass → 13-agent doc
review → staged fix fan-out). **This section is the record of both.**

### 10a. What v0.2.0 contains (all committed on the branch; NOT tagged/merged/published)

- **drive-tui control-plane security hardening** (`scripts/tui.py`): session ids
  validated (`^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$`) before any registry path use (no
  traversal); registry moved to a per-user dir (`$XDG_RUNTIME_DIR` / macOS
  `~/Library/Caches/SmartCLI/sessions` / `~/.cache/smartcli/sessions`,
  `SMARTCLI_TUI_DIR` overrides) with POSIX symlink/ownership/0700 checks fail-closed;
  registry files O_EXCL (+O_NOFOLLOW/O_CLOEXEC POSIX, O_NOINHERIT Windows) 0600 — a
  capability cannot be replaced; the driven child no longer inherits
  `SMARTCLI_TUI_TOKEN`; `--env` cannot override `SMARTCLI_TUI_*`; caps: max sessions
  default 8 (`SMARTCLI_MAX_SESSIONS` 1–128), terminal size ≤1000×500 / 100k cells.
  Locked by `tests/test_drive_security.py` (deterministic, in CI).
- **`visual_hash` + `wait_visual_change`** (smartcli_core, DO-NOT-MODIFY exception):
  `ScreenModel.visual_hash()` = chained crc32 over cell text + SGR attributes +
  cursor; `PtySession.wait_visual_change()`; wired through daemon/CLI
  (`wait-visual-change`)/one-shot run/MCP. Resolves old known-#3 (§2). `content_hash`
  stays text-only by design. Plus a real bug fix: `wait_change`'s explicit baseline is
  **int end-to-end** (the old `Optional[str]` annotation made CLI/MCP pass strings
  that never compared equal → instant false "changed"; CLI now parses
  `--baseline-hash` as int and honors 0). Typing modernized to PEP 604/585 →
  **Python floor 3.9→3.10** (runtime union alias in snapshot.py). Locked by
  `tests/test_visual_change.py`.
- **Packaging:** the wheel ships `smartcli_drive` (mapped from
  `skills/drive-tui/scripts`, new `scripts/__init__.py`) next to `smartcli_core`;
  console scripts `smartcli-tui` / `smartcli-mcp` / `smartcli-toolkit` (dist-named
  alias so `uvx smartcli-toolkit` starts the MCP server); `mcp>=1.0` promoted from
  `[mcp]` extra to required dep; `server.json` gains registryBaseUrl+runtimeHint=uvx;
  plugin.json (drifted at 0.1.2) re-aligned. Docker entrypoint gained an `mcp` verb.
- **CI/publishing:** matrix → py3.10/3.14 boundaries; new bounded `drive-smoke`
  (3-OS real-PTY probes, first time in CI) + `package` (wheel/registry contract)
  jobs; lint partially blocking (ruff correctness subset + mypy); publish.yml
  `publish-mcp` job auto-publishes to the MCP Registry via OIDC with a pinned,
  sha256-verified mcp-publisher.

### 10b. The 2026-07-27 verification & review session (this is the adversarial review the core policy requires)

- **Verified before committing:** mypy clean (7 files — the only CI blocking gate with
  zero prior local verification); all deterministic gates green locally; vendored copy
  byte-identical; ten version sites = 0.2.0; **live single-session PTY end-to-end** of
  `wait-visual-change` (idle → changed=False; explicit int baseline after a screen
  change → changed=True; `--json` surfaces; zero leaked sessions).
- **Bugs found & fixed during review:** daemon `resize` with out-of-range dims raised
  `SystemExit` (a BaseException) straight through the per-connection
  `except Exception` guard → killed the whole session; now converted to an error
  reply, mutation-verified in `test_drive_security.py`. MCP `start` rows default
  aligned 24→30. `python -m smartcli_core` diagnostics now reports `mcp`.
- **New anti-drift gates:** `tests/test_version_sync.py` (ten sites);
  `test_doc_counts.py` extended to widget counts + a D:-path ban over shipping docs.
- **Doc-accuracy review:** 13-agent partitioned review of every agent-facing doc
  (3 SKILL.md + references, MCP tool descriptions, README*/INSTALL/CONTRIBUTING/
  SECURITY, CLAUDE.md, 8 i18n files, 5 site pages, runbooks, knowledge/) produced
  **157 adversarially-confirmed findings** (40 high) — headline classes: the 0.2.0
  surface (wait-visual-change/--json/--cwd/--env/session caps) was absent from every
  doc an agent reads; widget count 15→17 drift across 8+ files; machine-specific
  `D:/Project` paths in portable docs; an end-anchored regex example in the MCP
  wait_any docstring (the project's own documented never-matches anti-pattern);
  stale runbooks (mkdocs/"not yet live", packaging configs pinned to 0.1.2/py3.9,
  invalid bench model id). Fixes applied by a staged fix fan-out + re-verify pass
  (initial 8-wide fan-out died to API 529 storms; re-run in batches of 2 — that
  pacing lesson generalizes: match fan-out width to API health).
### 10c. Differential testing against a real terminal (2026-07-27) — the premise is now MEASURED

The project's central premise — that pyte's cell grid matches what a real
terminal shows — had never been measured. The screenshot harness honestly labels
itself `pyte-simulation`, and a simulation agreeing with itself proves nothing.
**This machine has tmux 3.6b**, which invalidated the long-standing "no tmux on
this box" assumption and made the measurement possible.

**`tests/_diff_tmux_pyte.py`** feeds identical bytes to a real tmux pane and to
`ScreenModel`, then diffs the grids cell by cell — 25 cases over cursor
addressing, erase ops, autowrap/deferred wrap, DECSTBM, IL/DL, DCH/ICH,
DECSC/DECRC, RI, CJK width, tabs, box drawing, truecolor and emoji. Result:
**26/26 agree**, but only after finding two real bugs and three rig artifacts.

- **REAL BUG (fixed, core):** `pyte.Screen.draw` does `else: break` on a
  character that is neither width-1, width-2, nor a true combining mark —
  abandoning the rest of the batch. **VS16 (U+FE0F) and ZWJ (U+200D) are exactly
  that shape**, so a program printing `"MENU ♀️ Settings  Quit  Help"` in one
  write left us perceiving `"MENU ♀"`: the agent would act on a menu whose other
  entries were invisible to it, with nothing reporting a problem. `ScreenModel`
  now uses a `_Screen` subclass that attaches those codepoints to the previous
  cell (as pyte already does for combining marks), stepping over a wide char's
  stub slot. Locked by `tests/test_zwj_text_loss.py` (mutation-verified:
  reverting to `pyte.Screen` fails 7 checks). Core policy satisfied — real-run
  verified by driving a live REPL, fuzz 17030 iterations / 0 defects, mypy clean,
  16 deterministic gates green, vendored copy re-synced.
- **REAL BUG (fixed, cmd-art):** see 10d below — the tmux launchers.
- **Three rig artifacts, NOT emulation differences** (each traced, then
  normalized in the probe with the reason written down): capture-pane emits a
  literal TAB where we have already expanded to 8-col stops; NFC vs NFD for
  combining marks; and — the instructive one — the pane's tty had `ONLCR` on, so
  it rewrote LF to CRLF *before* the emulator saw it. With `stty -onlcr`, real
  tmux stair-steps bare LF exactly as we do, **confirming HARD RULE 7** rather
  than contradicting it. Lesson: when a differential test disagrees, suspect the
  rig before the code — two of three "divergences" here were the harness.

### 10d. tmux launchers verified (2026-07-27) — a permanently-open item closed

`skills/cmd-art/tmux/fx-{split,popup}.sh` had shipped unverified since they were
written. On real tmux: `fx-split` works (window really splits, effect renders in
the new pane), `fx-popup` was **broken** — `display-popup` needs an attached
client, and from a detached session it leaked tmux's raw `no current client` with
exit 1, violating its own documented clean-exit contract. Now guarded.
`tests/_tmux_launcher_probe.py` locks all five states, 18/18, zero residue; it
SKIPs itself where tmux is absent, so it is safe to register everywhere.

### 10e. Generative differential fuzz + the performance contract (2026-07-27)

Hand-written differential cases only find bugs someone thought to look for.
**`tests/_diff_fuzz_tmux.py`** removes the author from the loop: it generates
random-but-structured VT streams, feeds each to a real tmux pane AND to
`ScreenModel`, and diffs the grids. It found **seven more emulation bugs** that
every existing test missed — each minimized to a 2-3 sequence repro and each
checked against a SECOND emulator (GNU screen) before the core was touched:

1. **IL/DL homed the cursor column** (pyte calls `carriage_return`); real
   terminals keep it. A TUI repainting a list by inserting a line and writing at
   the current column landed its text in the wrong column.
2. **IL with count > 1 left rows MISSING** from pyte's sparse buffer instead of
   present-and-blank, so a later DL renumbered around the holes and deleted the
   wrong row (`ESC[3L Q ESC[1M` left `Q` on screen).
3. **Half-overwriting a wide glyph** kept the glyph AND dropped the incoming
   character — the write silently vanished. Affects CJK, not just emoji.
4. **DCH on a wide glyph** removed one cell, leaving its stub as a stray blank
   that shifted every following column.
5. **NEL (`ESC E`) did not return to column 0** — pyte routes it to `linefeed`,
   which only carriage-returns under LNM. Fixed with a `_ByteStream` that
   dispatches `ESC E` separately, since plain LF must keep its column.
6. **A cursor OUTSIDE a DECSTBM region** was dragged into it by `index()` and
   clamped by `cursor_up()`, so anything painted below a scroll region (a status
   bar under a pager) landed on the wrong rows.
7. **An overwritten wide base left an orphaned stub** one cell right, so every
   following column rendered one place off. This one needed a VS16 cluster plus a
   DECSTBM change plus two ICH rounds to surface — every mechanism agreed in
   isolation; the fault was purely in their accumulation.

Plus: a two-column glyph with one column left now wraps whole instead of being
squeezed into the last cell.

**Where the reference emulators DISAGREE** (IL/DL from outside a region; ZWJ
cluster width) the probe documents the divergence instead of picking a side —
with no ground truth there is nothing to match. That judgement call matters:
two of the first three "divergences" were the harness, not the code (tty `ONLCR`,
capture-pane's literal TAB, NFC vs NFD). **Suspect the rig first.**

Convergence: **10/10 seeds x 40 payloads clean**, curated probe 26/26.

**Performance contract (`tests/test_perf_contract.py`) — the suite had NO perf
test at all.** `visual_hash` cost **16.6 ms on a 300x100 screen**, i.e. 55% of
the default 30 ms `wait_visual_change` polling budget, rehashing rows that had
not changed. It is now incremental (per-row CRCs, recomputing only pyte's dirty
rows): **16.566 ms → 0.008 ms** idle, 0.225 ms with one row changed. A first
attempt was *slower* (22 ms) because the cache key cost more to build than the
hash it saved — measuring caught that. The test asserts equivalence against a
separate from-scratch computation (80 chunked adversarial payloads) as well as
timing ceilings set ~20x above measured values; both mutation-verified.

### 10f. Two references, property tests, and the alt-screen bug (2026-07-27, cont.)

**A second reference emulator.** Matching tmux alone cannot distinguish "correct"
from "identical to tmux". `tests/_diff_two_refs.py` adds **GNU screen** (a
different codebase, its own VT parser) and treats a behaviour as ground truth
only when BOTH agree; where they disagree the case is recorded as UNDEFINED
rather than judged. **35/35** on everything the two agree about — so every fix
made during the fuzz work is now justified by two independent implementations.
Measured, not assumed: screen renders U+FFFD for astral-plane codepoints, so
those cases are reported as SKIPPED (a decoding limitation) rather than lumped in
with genuine disagreement.

**Property-based tests over readiness.** `tests/test_readiness_properties.py`
states seven invariants as Hypothesis properties (250 generated schedules each,
virtual clock so runs are instant and cannot flake): never settle before
`min_wait_ms` or `quiet_ms`; always terminate within budget; the `blank_hash`
gate never lets a never-painted screen settle but DOES release once real output
arrives; `wait_for_regex` only reports a real match; `wait_any` returns a valid,
earliest-in-list index. Mutation-verified with three independent breakages, each
caught by exactly the property that should catch it.

**The alt-screen bug — the most consequential find of the whole exercise.**
pyte implements **no** alternate-screen mode (1049/1047/47 just set an unknown
bit). So `vim`, `less`, `htop` — every full-screen program drive-tui exists to
drive — painted their alternate screen ON TOP of the main one, and on exit the
main screen was never restored: an agent read a merged, impossible screen with
nothing reporting a problem. Now implemented per xterm and verified against tmux:
1049 saves the cursor + clears the alt buffer on entry and restores both on exit,
47/1047 switch without the cursor save, and the cursor is deliberately NOT homed
on entry (measured). `ScreenModel.screen.alt_screen` exposes the state.

**SGR sub-parameters.** pyte's parser does not know ':' (ITU-T T.416), so
`ESC[4:3mU` drew the literal `"3mU"` on the grid. Neovim/kitty/delta emit this
routinely. Colons inside `CSI ... m` are now normalised to ';' before parsing —
the attribute may degrade, no debris reaches the grid.

Also verified already-correct and now locked: DECCKM, mouse 1000/1002/1006,
OSC 0/7, bracketed paste, DECAWM off, cursor hide/show.

Totals after this round: curated tmux probe **35/35**, three-way probe **35/35**,
generative fuzz **10/10 seeds x 40 payloads**, deterministic gates **17** + the
Hypothesis suite, `visual_hash` **2000x faster** on idle polls.

- **Process notes:** commits follow Conventional Commits on the branch (core → tests →
  drive-tui → packaging → ci → docs → reconcile). `B-SEC` (leaked PyPI token) was
  re-raised to the owner per NEXT-STEPS' standing order — still owner-gated.
  **Releasing v0.2.0 (merge + `git tag v0.2.0 && git push origin v0.2.0`) is the
  owner's decision** — it drops Python 3.9 and makes `mcp` a hard dep (breaking for
  some users; CHANGELOG documents both).

---

### 10g. Release of v0.2.0 and the distribution work (2026-07-27, end of session)

**v0.2.0 is LIVE.** Merged to `main`, tagged `v0.2.0`, and published — all three
`publish.yml` jobs green (build → PyPI via OIDC → MCP Registry via OIDC), no
long-lived secret anywhere. Verified by installing `smartcli-toolkit==0.2.0` from
PyPI into a clean venv: `smartcli-tui doctor` works, the alt-screen and ZWJ fixes
are live, `smartcli_drive.mcp_server` imports. A GitHub Release was created from
the CHANGELOG entry. PyPI reports `requires_python >=3.10`, so 3.9 installs are
correctly blocked.

**Then discovery work, which turned up four more real bugs.** The valuable part of
this stretch was not the promotion — it was that preparing for MCP-directory
listing exercised paths nothing had exercised before:

1. **Docker image defaulted to a demo.** `CMD ["fx gallery"]` — an effects
   animation. MCP directories validate a server by running the image with no
   arguments and speaking JSON-RPC; they would have received animation frames and
   scored the server broken. Now `CMD ["mcp"]`, with a comment so it does not get
   "optimised" back. Docker is not installed on this host, so the image build is
   verified by CI (`docker.yml`, green), not locally.
2. **MCP `serverInfo` reported the SDK's version** (`1.28.1`) instead of ours
   (`0.2.0`), because FastMCP does not forward a version to the `Server` it
   wraps. That value is what directory pages display, so it read as a bogus
   version claim. Locked by an assertion in `_mcp_probe.py`.
3. **Two genuine CI failures**, exposed the first time the bounded `drive-smoke`
   job ran the real-PTY probes on all three OSes:
   - macOS+Linux: `_sandbox_daemon_robustness` had re-implemented the registry
     path as `/tmp/smartcli_tui`; v0.2.0 moved the real registry to a per-user
     location and the copy did not follow → `FileNotFoundError`. It now imports
     `tui.REG_DIR`; duplicating that logic is exactly what caused the bug.
   - Windows: the probe printed the full cwd and matched it with a single-line
     regex, but a Windows temp path wraps an 80-column screen, splitting
     `child-workdir` across rows — a working feature failing. The child now
     prints short verdict tokens that cannot wrap. (First attempt at that fix
     asserted `"TOKEN_LEAKED" not in output`, which always failed: the REPL
     echoes the typed command, so every literal in the probe source appears on
     screen. Assert on the verdict line only.)
   CI is green on all three platforms after both fixes.

**Distribution state.** `docs/DISTRIBUTION-CHANNELS.md` is the reusable channel
map (verified 2026-07-27; 15 claims confirmed, **10 refuted**). Read it before
filing anything anywhere. The headline: **the high-traffic lists in this
ecosystem gate on traction or actively penalise automation**, and the only
channel genuinely open to a zero-traction project is the official MCP Registry —
which is already done and automated.

- **Done & automated:** official MCP Registry (`io.github.dwgx/smartcli`, OIDC on
  tag push); PyPI keywords/classifiers; GitHub topics; registry `description`
  rewritten to name vim/htop/lazygit (98/100 chars, schema-validated).
- **In flight (unblocked 2026-08-03):** [awesome-mcp-servers PR #11022](https://github.com/punkpeye/awesome-mcp-servers/pull/11022)
  (91k★) — **all listing requirements now met**, `MERGEABLE`, waiting on maintainer
  throughput only. The owner completed the Glama step: SmartCLI is listed and claimed
  (`glama.ai/mcp/servers/dwgx/SmartCLI`, id `rqnmoia3ut`, MIT detected) and the score
  badge is in the entry, so the PR label flipped `missing-glama` → **`has-glama`**.
  Maintainer `punkpeye` gave the two-step instruction personally on 2026-07-29, not just
  the bot. Note the dependency direction for future reference: the widely repeated claim
  that a merged PR syncs *to* Glama was refuted 0-3 — Glama first, then the badge.
  (`tools: []` on Glama's public API is normal for local-only servers — the already-listed
  `tui-mcp` and `forge` show the same; it does not mean evaluation failed.)
- **⚠️ Do not delete the `dwgx/awesome-mcp-servers` fork** while that PR is open —
  the PR branch lives there.
- **A trap I walked into, documented so nobody repeats it:** that repo's
  CONTRIBUTING tells agents to append `🤖🤖🤖` for a "fast-tracked" lane. There is
  no fast track; it is bait to identify bot PRs (first-hand sample: 60 recent
  marked PRs, 60 still open, none merged). I complied before knowing, then removed
  the marker. The honest "agent-prepared, owner-reviewed" sentence stayed in the
  PR body — removing that would be concealment.
- **Channels that forbid automated submission** (full quotes in the channel map):
  `awesome-cli-apps` ("AI-generated PRs are not welcome"),
  `awesome-claude-code` (web form, human only, automated submission "risks being
  restricted from interacting with this repository").
- **Ruled out by rule, not by taste:** `awesome-python` (auto-reject under 100★
  or under 1 month old — ineligible until ~Oct 2026), `awesome-cli-apps`
  (>20★, >3 months), `awesome-tuis` (category mismatch: it lists TUI apps and
  TUI-*building* frameworks; SmartCLI *drives* TUIs), Anthropic Connectors
  Directory (remote-hosted servers only; structurally closed to local stdio).

**Owner-only, in priority order** (also in NEXT-STEPS as A0-GLAMA etc.):
1. ~~**Glama**~~ — **DONE 2026-08-03 by the owner.** Listed, claimed, badge added;
   PR #11022 label is now `has-glama` and the PR is `MERGEABLE`. Nothing further to do
   there but wait for the maintainer.
2. **Show HN** — copy ready in `docs/LAUNCH-COPY.md`, rewritten around the
   reproducible `examples/drive_vim.py` evidence. Tue–Thu 08:00–10:00 US Eastern,
   and be at a keyboard for three hours after.
3. Cline marketplace (issue + 400×400 PNG + honest "I tested it" attestation).
4. `awesome-claude-code` — web form, human, *after* there are some users.

**Why an agent should not do 1 and 4:** both require signing in to a third-party
service or posting as the owner. Given that this ecosystem is actively penalising
bot submissions, an agent acting under the owner's identity there is a real risk
to the account and the project's name, not a convenience.

### 10h. Harbor adapter, dependency-drift gate, and three self-inflicted bugs (2026-08-05)

**Harbor adapter — the leaderboard path is now real.** The public Terminal-Bench
leaderboard moved to Harbor (`laude-institute/harbor`, 3.9k★, pushed 2026-08-05;
terminal-bench itself last moved 2026-07-11), so the classic-TB adapter in
`agent.py` cannot produce a comparable score. `smartcli_tbench/harbor_agent.py`
targets Harbor. The interface difference was read from Harbor's source, not docs:

    classic TB:  perform_task(instruction, session: TmuxSession) → capture_pane()
    Harbor:      async run(instruction, environment: BaseEnvironment, context)
                 → await environment.exec(command) → ExecResult

**Harbor gives a one-shot command runner — no tmux handle, no `capture_pane`** — so
`driver.py`'s whole approach is unavailable there. That is also the opening: the
adapter's `setup()` pip-installs smartcli-toolkit *inside* the environment and the
loop drives its persistent-session CLI over `exec`, supplying the PTY and
screen-state waits Harbor lacks natively. Selectable without forking Harbor via
`AgentConfig.import_path` (verified that field exists):

    agent:
      import_path: "smartcli_tbench.harbor_agent:SmartCliHarborAgent"

Validated against the **real** base class, not a stand-in: Harbor was installed
into a venv and the class confirmed to be a genuine `BaseAgent` subclass with zero
unimplemented abstract methods, instantiable, `version()` → 0.2.0, and
`run`/`setup` signatures matching the caller. `tests/test_harbor_agent.py` (22
checks, no Harbor/Docker/PTY needed) drives the loop against a fake environment
shaped from the real `exec()` signature, and locks the two things a benchmark
harness must not get wrong: the session closes **even when `decide_fn` raises**,
and a missing `decide_fn` is reported rather than silently scoring zero.
**Still needed for an actual leaderboard number (owner only):** a `decide_fn`
(a model client — deliberately not bundled) and an LLM API-key secret for
`bench.yml`.

**Dependency-drift gate.** `tests/test_dependency_sync.py` asserts that one
dependency fact has one value: `requirements.txt` must equal pyproject's runtime
`dependencies` exactly, `requires-python` must agree wherever restated (including
the mypy and ruff targets), and packaging drafts must not leave unbounded a
dependency pyproject caps. It exists because the same fault fired twice in a day —
`mcp` capped in `pyproject.toml` but left open in `requirements.txt`, **which is
what the Docker image installs, and that image is what MCP directories run to
validate the server**. It caught a live drift on its first run (conda-forge recipe
still had a bare `mcp >=1.0`, i.e. an uninstallable package for anyone submitting
that draft).

**Three bugs I introduced and fixed in the same session.** Recorded because each
is a recurring shape, not a one-off:

1. **A gate that violated the constraint it checks.** The dependency gate imported
   `tomllib`, stdlib only from 3.11 — while this project's floor is 3.10, the very
   fact it asserts. It failed on every py3.10 CI leg. `test_version_sync.py` reads
   pyproject with regexes for exactly this reason; I did not follow the precedent.
   **Lesson: a gate must run on the floor it enforces.**
2. **A bug only reachable on the fallback path.** The regex fallback added in (1)
   was greedy past the dependencies array and collected a quoted string out of a
   *comment* as a dependency. It surfaced only because I forced the no-tomllib path
   instead of trusting the primary one. **Lesson: exercise the degraded path, or it
   is untested code.**
3. **A timing-dependent assertion.** The zero-leak check ran `list` immediately
   after `close`, but the daemon unlinks its registry entry afterwards in its own
   `finally` — a race, not a leak. It passed locally and failed on the slower macOS
   runner. `_mcp_probe.py` already polled for this reason. **Lesson: assertions
   that pass on the fast machine that wrote them are the classic CI flake.**

Suite is now **43 entries** in `build_suite()`; deterministic gates green, CI green
on all three OSes. (Registration is unconditional — the tmux probes SKIP
themselves rather than deregistering — so this count does not vary by host. Count
it with `build_suite()`, never from memory: this line said 39 for a day.)

### 10i. The alternate screen goes upstream, and two dependency timebombs (2026-08-06)

**pyte issue #90, open since 2017 with a `help-wanted` label from the maintainer
himself and zero competing PRs, is now [selectel/pyte#212](https://github.com/selectel/pyte/pull/212).**
pyte implements no alternate screen buffer at all, which is why `_Screen` has one:
without it `vim`/`less`/`htop` paint over the primary screen and never restore it,
so an agent reads a merged, impossible screen with nothing reporting a problem.
The PR is three commits, `MERGEABLE`, and its history is worth reading as method
rather than as code — two rounds of review found ten defects in my own patch.

**Behaviour was measured, not derived.** Sixteen alt-screen cases diffed against a
real tmux pane, then a three-way against tmux AND GNU screen. That settled one
point the xterm documentation actively misleads on: the "without clearing" wording
for 47/1047 describes the clearing action, not buffer lifetime. Taken literally it
implies alternate-screen contents survive a round trip. **They do not, in either
emulator.** I implemented the literal reading first and the differential test
rejected it.

**Two dependency timebombs, same shape, both defused with capability detection.**
Once #212 ships in a release, `pyte>=0.8.1` (open range, in both
`requirements.txt` and `pyproject.toml`) means every install picks it up — and
subclass plus base class both switching restores a BLANK primary screen on every
full-screen program exit. Measured: `['', '', '']`. The second is `delete_characters`,
which widens DCH over a wide glyph; against a pyte that does the same, `中x` + CR +
DCH went from `"x"` to `""`, silently eating a character. Neither is a code change
you would notice — they arrive as `pip install --upgrade`.

Fixed by asking the installed pyte what it can do (`_PYTE_HAS_ALT` via `hasattr`,
`_PYTE_DCH_HANDLES_WIDE` via a one-shot behavioural probe) rather than pinning
`pyte<0.8.3`. A cap would keep users off the upstream fix forever and need revising
every release. **Both are verified in BOTH directions** — under stock 0.8.2 and
under a patched checkout — because a one-sided test cannot distinguish "correct"
from "the branch that happens to run here". Mutation testing needed both ends too:
hardcoding the DCH probe False is only observable under a pyte that widens DCH,
hardcoding it True only under one that does not.

**`tests/run_all.py` is 43/43 on macOS — the first full green here.** It was 39/43,
and the four failures had nothing to do with the code: `tests/_menu_app.py` and its
four siblings opened with `import sys, msvcrt`, so on POSIX they died before
drawing anything and three drive probes saw a traceback instead of a menu.
`examples/drive_vim.py` could not import `smartcli_core` from a checkout. That
noise floor was the real cost — with four known failures, a genuine regression was
indistinguishable from the platform gap. `tests/_kbd.py` now provides a
cross-platform `getwch()` (raw mode entered once, not per keystroke, or an
`ESC [ A` gets split across three separate raw-mode entries). `_diff_fuzz_tmux`
gained `rerun=True` for a load-dependent flake: its seed is FIXED, so a real
divergence fails twice while a slow tmux capture fails once.

**Also this session:** `tests/_diff_two_refs.py` was driving GNU screen without
`altscreen on`, which **defaults off** — so both alt-screen cases had been
comparing against a reference with the feature disabled and were reported as
reference-vs-reference disagreements for a rig reason. The probe went 35 → 37
arbitrated cases. Mode 1048 is now supported with its weaker evidence level stated
in the code (xterm defines it; neither reference emulator implements it). And
`alt_screen` reached the surfaces an agent actually reads — `ScreenModel`,
`Snapshot`, the `to_text()` header, the JSON hints, and every drive-tui reply —
having previously been available only by reaching through to the pyte object.

**Seven other pyte defects were triaged for upstreaming, and the premise did not
survive.** The claim was "all seven are implemented and verified in `_Screen`, so
upstreaming is a porting job". Two are wrong. Defect 7 (orphaned wide stub) is
**not a pyte defect**: its locked repro passes on untouched master and on 0.8.2,
and the orphan it "fixes" is manufactured by SmartCLI's own `draw()` override —
the test that locks it would pass without the fix. Defect 2's root cause is
misattributed to `insert_lines` (which pops unconditionally; holes render as
`default_char`, correctly) when it lives in `delete_lines`, and SmartCLI's own fix
does not cover the minimal case `b"Q\r\x1b[1M"`. **Five are confirmed live on
master and port mechanically**: half-overwriting a wide glyph, DCH on a wide glyph,
NEL not returning to column 0, and DECSTBM region-escape in both `index()` and
`cursor_up()`.

**IL/DL homing the cursor column was REMOVED from that list by an independent
re-check, and this is the most important correction in this section.** pyte is
right and this project is the one deviating. The documented split:

    column 0 (pyte)   xterm, vte, and the DEC VT reference — terminalguide gives
                      the reference as "Moves the cursor to the left margin"
    column kept (us)  tmux 3.6b, GNU screen, urxvt, konsole, linuxvc

Five implementations keep the column and two reset it, so SmartCLI keeping it is a
defensible CHOICE and it stays. But pyte's docstrings cite VT102/VT220, whose
reference says column 0 — so upstreaming this would move pyte away from the
standard it targets and would rightly be rejected. **Do not file it.** The
`_Screen` docstring previously asserted "real terminals keep the column" as though
it were unanimous, which is exactly what made the mistaken upstream plan look
sound; it now records the full split. This is the ZWJ mistake's near-repeat, caught
one step earlier. Three more were found that are
not in the seven: last-column wide-glyph wrap, ICH/ECH straddling a wide glyph
(no reference measurement — do not upstream), and SGR colon sub-parameters drawn
as literal text — **which already has an open upstream PR**. pyte #180
("Understand (and discard) SGR subparameters", open since 2024-10-08, MERGEABLE)
fixes exactly that symptom, and issues #179/#178 cover it; the bottleneck is
maintainer review, not a missing report, so filing again would waste the very
credibility this triage exists to protect. A +1 or a rebase offer on #180 is the
useful move. Also worth knowing before writing any wide-glyph patch: pyte #206 is
actively rewriting the same `draw()`/grapheme path.

Defect 7 (orphaned wide stub) needs splitting in two. Its RECORDED evidence is
stale — the payload locked in `tests/test_terminal_fidelity.py` produces the wanted
result on untouched master and on 0.8.2 with zero SmartCLI code, so filing that
would be the credibility failure. But the defect as NAMED is still live on master
with a 3-byte repro (`b"a" + 中 + CR + 文` renders width 7 in an 8-column screen),
and it shares a root cause with the half-overwrite defect, so it folds into that
one patch rather than being filed separately.

Their independence from #212 was MEASURED, not assumed. The triage built its port
on top of the alternate-screen branch (its 145-test run gives that away — untouched
master is 117), so "these do not depend on #212" was an assertion. Extracting the
130-line diff and applying it to an untouched `upstream/master` worktree: both
files apply cleanly and the suite stays at 117 passed / 1 xfailed. So the six can
be filed without waiting on #212 — which matters, because that upstream's last
merge was ~11 months ago and attaching mechanical wins to an unreviewed PR makes
them hostage to it. Do NOT upstream IL/DL from outside a scroll region (tmux performs
it, GNU screen discards it — no ground truth) or ZWJ cluster width (master already
picked tmux's side via `grapheme_clusters`).

**Method notes worth more than any of the fixes.** Three separate times a
differential failure turned out to be the RIG: `less -X` disables the alternate
screen (the feature under test), GNU screen's `altscreen` defaults off, and a
`git stash push` with nothing staged meant a control experiment ran the same code
twice. Suspecting the rig first is not a slogan here; it has a measured hit rate.
The mutation harness itself was non-deterministic — Python validates a `.pyc`
against **(mtime in whole seconds, size)**, and two mutations of one line produce
identical-size files, so same-second writes ran the previous mutation's bytecode.
The published "11/11 caught" was measured on that harness; it was re-established
at 11/11 after fixing it, but it had to be re-established rather than assumed.
And twice a test was written with its expected value copied from my own broken
output, so it locked the bug in — both now derive expectations from a path that
cannot contain the defect (resizing a screen that never entered the alternate
buffer). One batch of locks was appended *after* the module's `sys.exit(0)` and
never ran at all; mutation testing reporting 0/4 caught is the only reason that
was noticed instead of shipping as a green-looking no-op.

---

## CONTINUATION PROMPT (paste to next AI)

```
You are the next AI taking over SmartCLI. The repo lives at the checkout root you were
launched in (historically D:\Project\SmartCLI on Windows 11; since 2026-07-19 also
/Users/dwgx/Documents/Project/SmartCLI on macOS — treat it as dual-host, use
repo-relative paths). Read HANDOFF.md (§0 then §10 first) and knowledge/INDEX.md
before doing anything else.

STANDING DIRECTIVES (non-negotiable):
- Token budget is UNLIMITED. Optimize for MAX QUALITY, never for brevity or cost.
- Default to concurrent ULTRACODE / multi-agent workflows for any non-trivial task,
  each with an adversarial verify pass. Parallelize independent work.
- Quality only goes UP, never down. Never regress a working artifact to "simplify."
- VERIFY ON THE REAL RUN PATH. A green preview or a monkeypatched harness is not proof.
  Run the script's own full startup (python script.py, no patches), capture stderr,
  and open the result in a REAL terminal to show the user.
- CONSULT knowledge/INDEX.md FIRST. The exact formulas, ANSI sequences, and constants
  are already measured on disk. Do not head-canon anything that a note already states.
- smartcli_core\ is DO-NOT-MODIFY *except* with real-run-path verification + independent
  adversarial review + no regression across the full recipe suite (this is how the
  v0.1.1/v0.1.2 core fixes #1/#2/#4 were made). Never touch it casually.

WHAT SMARTCLI IS:
Three Agent Skills over one pluggable PTY+pyte core (smartcli_core\ = pty_backend/
screen_model/snapshot/readiness/session; NOT tmux-bound — pluggable so Windows uses
ConPTY/pywinpty and Linux/mac use posix pty). The skills:
  - drive-tui  : DRIVE interactive TUIs via perceive->decide->act->wait->confirm,
                 never blind-sleep. CLI scripts/tui.py (persistent daemon + one-shot run;
                 wait/wait-regex/wait-change/wait-visual-change/wait-any primitives,
                 --json machine output) + 8 importable recipes (repl, menu_select,
                 pager, search_filter, confirm, form, progress, wizard). Also a stdio
                 MCP server (smartcli-mcp, 14 tools, per-session token auto-attached).
  - cmd-art    : DESIGN terminal visuals via `python -m fx` — 30 effects, 8 themes,
                 pure frame-producer Effect ABC + @register auto-discovery.
  - tui-ui     : web-like cell-accurate layout engine emitting tmux-safe ANSI frames
                 (SGR + newlines only). 17 widgets + ENGINE (field/raster/box_junction/
                 color_model). Produces frames; something else owns the terminal.
The BRAIN is knowledge/ (143 md files, 0 dangling links):
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

ENVIRONMENT: dual-host. macOS working copy (current): Python 3.14.6, POSIX pty backend.
Windows 11 box (historical primary): pywinpty/ConPTY, NO tmux, NO WSL, Git-bash at
D:/Software/Git. Everywhere: pyte (pyte.__version__ does not exist), set
PYTHONIOENCODING=utf-8. ConPTY: first prompt can lag ~3s — use strict wait-regex w/
15000ms timeout, not bare wait; raw Ctrl-C is unreliable on ConPTY — recover with
close+start. Target programs: use "python3 -i -q" (POSIX) / "py -i -q" (Windows),
never assume a bare `python` on PATH. The codex subagent dispatcher (192.168.11.4:8990)
is QUOTA-EXHAUSTED / DEAD — do live research with built-in WebSearch / WebFetch.
Pace multi-agent fan-outs to API health: an 8-wide fan-out died to 529 storms on
2026-07-27; batches of 2 completed fine.

RELEASE STATE: latest RELEASED = **v0.2.0** (2026-07-27; PyPI + GitHub tags v0.1.0…v0.2.0
+ a GitHub Release). It merged the codex/cross-platform-mcp-hardening branch — see HANDOFF
§10 for the whole arc — and was BREAKING: dropped Python 3.9, made the MCP SDK a required
dependency. All three publish.yml jobs went green (build → PyPI OIDC → MCP Registry OIDC),
verified by a clean-venv install from PyPI. PUBLIC surfaces: PyPI `pip install smartcli-toolkit`
(import stays smartcli_core; from 0.2.0 the wheel also ships smartcli_drive + the
smartcli-tui / smartcli-mcp / smartcli-toolkit commands); GitHub github.com/dwgx/SmartCLI;
3 skills on skillhu.bz; `/plugin marketplace add dwgx/SmartCLI`; Codecov + Read the Docs
(smartcli.readthedocs.io) live; MCP Registry LIVE (io.github.dwgx/smartcli, re-publish
automated via publish.yml OIDC). VERSION must stay consistent across TEN sites:
pyproject / smartcli_core __init__ / fx __init__ / 3 SKILL.md / marketplace.json /
plugin.json / _vendor/smartcli_core/__init__ / server.json (2 fields there). After a
bump run `python tools/sync_vendor.py`, then `python tests/test_vendor_sync.py` and
`python tests/test_version_sync.py`. publish.yml (OIDC) auto-publishes on tag push
(`git tag vX.Y.Z && git push origin vX.Y.Z`; twine not needed; PyPI JSON index lags a
few min — the workflow going green is the truth). CI: 3-OS matrix (win/ubuntu/macos ×
py3.10/3.14) deterministic gates incl. anti-drift test_doc_counts + test_version_sync,
plus bounded drive-smoke (real-PTY probes) and package (wheel/registry contract) jobs;
9 workflows. cc-decompiled/ stays gitignored/excluded.

UPSTREAM WORK IN FLIGHT (2026-08-06, see §10i):
- selectel/pyte#212 implements the alternate screen buffer, closing a 9-year-old
  help-wanted issue. Three commits, MERGEABLE, unreviewed. That upstream's most
  recent merge was ~11 months before now, so do NOT make anything depend on it.
- SmartCLI now detects pyte's capabilities at import (_PYTE_HAS_ALT,
  _PYTE_DCH_HANDLES_WIDE) instead of pinning a version, because BOTH the
  alternate screen and DCH-over-wide-glyph would double-apply once upstream ships
  them — a dependency upgrade, not a code change, restoring a blank primary
  screen or eating a character. Verify any screen-model change under BOTH stock
  pyte and a patched checkout; a one-sided run cannot tell correct from
  happens-to-run-here.
- Six MORE pyte defects are confirmed live on master and port mechanically
  (IL/DL cursor column, half-overwrite of a wide glyph, DCH on a wide glyph, NEL,
  DECSTBM escape in index() and cursor_up()). Two of the original seven did NOT
  survive triage — read §10i before filing anything, and do not upstream IL/DL
  from outside a scroll region or ZWJ cluster width.

OPEN OBJECTIVES (the §6 A-grade list #1–#7 is DONE through v0.1.8; what actually remains):
1. [OWNER, the only thing blocking a leaderboard number] Supply a `decide_fn` (a model
   client) for the Harbor adapter and add an LLM API-key secret for bench.yml. The
   adapter itself is DONE and validated against Harbor's real base class (§10h); it
   deliberately ships no model client, because this project supplies perception and the
   drive loop, not inference. Without those two, scored runs cannot happen.
2. [OWNER] Show HN. Copy is ready in docs/LAUNCH-COPY.md, rewritten around the
   reproducible examples/drive_vim.py evidence. Tue-Thu 08:00-10:00 US Eastern; be at a
   keyboard for three hours after — an unanswered first question kills a Show HN.
   B-SEC (the leaked PyPI token) was raised and the owner decided on 2026-07-27 NOT to
   revoke it. Decision recorded; stop re-raising it.
3. [S] D1: write RESEARCH-PROMPTS.md from the calibrated /deep-research anchor list
   (conch, terminal-bench, plotille, TTE, PyPI trusted publishing) — see NEXT-STEPS D1.
4. [DONE 2026-08-05] Harbor adapter — see §10h. `smartcli_tbench/harbor_agent.py`,
   selectable via `import_path`, validated against the real Harbor BaseAgent.
5. [M] tui-ui reactive/declarative layer; [M] kitty graphics protocol next to sixel.
6. [Human eyeball] effort_selector cadence in a real Windows Terminal (travel SMALL,
   ~lambda x1..1.6; distances ultracode 4/max 14/xhigh 25/high 34/medium 45/low 53);
   real-Mac interactive curses DECCKM/SS3 probe over SSH; real-WT sixel render
   eyeball. (tmux launchers: DONE 2026-07-27 on real tmux 3.6b.)
BEFORE FILING ANYTHING ANYWHERE: read docs/DISTRIBUTION-CHANNELS.md. It maps each
channel's real acceptance rule and flags the ones that FORBID automated/AI submissions.
One list baits agents with a fake "fast-track" marker (🤖🤖🤖) — do not comply with it.
Assume automation is unwelcome unless a channel says otherwise in writing.
Discoverability (owner-gated, copy ready in docs/LAUNCH-COPY.md): C2 awesome-list PRs,
then C4 Show HN / r/commandline + C5 skill-community posts (C1 proof reels are DONE).

VERIFY WHAT YOU SHIP (all should exit 0; paths POSIX-style, swap \ on Windows).
Heavy PTY spawners (run_all, verify_fx, probes) need user consent first — red line:
  python tests/run_all.py                # unified runner (43 entries; consent first)
    # 43/43 on macOS as of 2026-08-06. If you see 39/43 you are on an older
    # checkout: the four platform-gap failures (msvcrt fixtures, drive_vim
    # import) were fixed — see HANDOFF 10i.
  cd skills/cmd-art && python -m fx list && python -m fx gallery   # 30 effects
  python skills/tui-ui/examples/effort_selector.py --once --stage ultracode --frame 1
  python skills/drive-tui/scripts/tui.py start --cmd "python3 -i -q" --cols 80 --rows 24
    -> wait-regex --id <SID> ">>> " --timeout-ms 15000 -> send-line -> snapshot -> close
    -> list   # zero leaked sessions (ONE session at a time)
  cd skills/tui-ui && python -m ui widgets && python self_test.py   # 17 widgets
  python skills/tui-ui/ui/box_junction.py                          # box_junction _selftest
  Deterministic quick gates (safe anytime): python tests/test_fx_contract.py,
    test_readiness.py, test_visual_change.py, test_drive_security.py,
    test_vendor_sync.py, test_doc_counts.py, test_version_sync.py
Then open the visual result in a real terminal and show the user before calling
anything done.
```


