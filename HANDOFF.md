# SmartCLI — Handoff (承上启下)

*Written 2026-07-08, last updated **2026-07-27**. This is the single document a fresh AI reads first to pick up SmartCLI without re-deriving anything. It records the **current release state**, what the project IS, what already WORKS (with the exact commands to see it), the brain (`knowledge/`), the hard-won rules that must never be re-lost, the environment, and the open tasks framed so you can start in one move. Baked-in truths (re-verified against code 2026-07-27): there are **THREE** skills, the live `fx` registry has **30** effects, `tui-ui` has **17** widgets, drive-tui has **8** recipes, and `knowledge/` has **143** `.md` files. **Read §10 (2026-07-27, v0.2.0 on branch) first for the most recent work — control-plane security hardening, visual_hash + wait_visual_change, the wheel gaining smartcli_drive + three console scripts, MCP Registry OIDC auto-publish, and a full-repo doc-accuracy review; then §9 (v0.1.3→v0.1.8) and §8/§7 for history.***

---

## 0. Release & current state (v0.1.8) — READ THIS FIRST

SmartCLI is **published and public**; latest **released** version is **v0.1.8** (2026-07-15). **v0.2.0 is code-complete but UNRELEASED**: the whole workstream sits committed on branch **`codex/cross-platform-mcp-hardening`** (commits landed 2026-07-27; no tag, not merged to `main`, not on PyPI yet — releasing it is the owner's call). See §10 for its contents: drive-tui control-plane security hardening, `visual_hash` + `wait_visual_change` (closes old known-#3), the wheel now shipping `smartcli_drive` + three console scripts (`smartcli-tui`/`smartcli-mcp`/`smartcli-toolkit`), `mcp` as a required dependency, Python floor 3.10, CI drive-smoke/package jobs, and MCP Registry OIDC auto-publish. This section is the authoritative current-state record; anything older in this doc that contradicts it is stale. v0.1.8 added `wait_any`, **Sixel graphics output**, and a **Terminal-Bench agent adapter** (§9h). v0.1.7 shipped `spectrum_bars` + `cbonsai` (catalog 30) and the **MCP Registry** listing (`io.github.dwgx/smartcli`, active — §9g).

**Where it lives:**
- **PyPI:** `pip install smartcli-toolkit` → https://pypi.org/project/smartcli-toolkit/ . The dist name is **`smartcli-toolkit`**; the **import package stays `smartcli_core`** (`from smartcli_core import PtySession`). Latest on PyPI = **0.1.8** (the JSON index can lag a few minutes after a release — the `Publish to PyPI` workflow going green is the source of truth, not the index).
- **MCP Registry:** **LIVE** — `io.github.dwgx/smartcli` on `registry.modelcontextprotocol.io` (published 2026-07-15 via `mcp-publisher`; ownership verified by the `mcp-name` marker in the PyPI README). MCP clients (Claude/Cursor/VS Code) + aggregators (Smithery/Glama/MCP.so) auto-discover it.
- **GitHub:** public repo **github.com/dwgx/SmartCLI**, branch `main`, tags **v0.1.0 … v0.1.8** each with a matching GitHub Release.
- **Claude plugin marketplace:** `.claude-plugin/marketplace.json` is present → users run **`/plugin marketplace add dwgx/SmartCLI`**.
- **skillhu.bz:** all 3 skills published — skillhu.bz/skill/cmd-art, skillhu.bz/skill/drive-tui, skillhu.bz/skill/tui-ui.
- **Codecov:** live (badge in README, ~50% on the deterministic subset). **Read the Docs:** live at https://smartcli.readthedocs.io/ (mkdocs, separate from the hand-written showcase site on GitHub Pages).

**Version consistency (VERSION = 0.2.0 in-tree; 0.1.8 on PyPI) — TEN sites must move together on a bump:** `pyproject.toml`, `smartcli_core/__init__.py` `__version__`, `skills/cmd-art/fx/__init__.py` `__version__`, all 3 `skills/*/SKILL.md` `version:` fields, `.claude-plugin/marketplace.json` plugin version, **`.claude-plugin/plugin.json`** (the site that historically drifted — it sat at 0.1.2 until v0.2.0 re-aligned it), **`skills/drive-tui/_vendor/smartcli_core/__init__.py`** (the vendored copy — `test_vendor_sync` requires it byte-identical), and **`server.json`** (TWO version fields there: top-level + `packages[0].version`, both must equal the package version or the MCP-registry publish fails). After bumping, run `python tools/sync_vendor.py`, then `python tests/test_vendor_sync.py` and `python tests/test_version_sync.py` (the anti-drift gate over all ten sites, added 2026-07-27).

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
suite (added 2026-07-14). run_all's suite has since grown to 29 entries (count them
via `build_suite()`, don't trust this number); the deterministic subset is what the
CI matrix runs.

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
- **Regression: `python tests\run_all.py` = 27/27** at the time (the suite has since
  grown to 29 entries — count via `build_suite()`).
- **git clean, synced with origin** was true then. *No longer:* the v0.2.0 work sits
  committed on branch `codex/cross-platform-mcp-hardening`, unmerged/untagged — see §10.
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

## 10. 2026-07-19 → 2026-07-27 — the v0.2.0 arc (branch `codex/cross-platform-mcp-hardening`, UNRELEASED)

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

- **Process notes:** commits follow Conventional Commits on the branch (core → tests →
  drive-tui → packaging → ci → docs → reconcile). `B-SEC` (leaked PyPI token) was
  re-raised to the owner per NEXT-STEPS' standing order — still owner-gated.
  **Releasing v0.2.0 (merge + `git tag v0.2.0 && git push origin v0.2.0`) is the
  owner's decision** — it drops Python 3.9 and makes `mcp` a hard dep (breaking for
  some users; CHANGELOG documents both).

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

RELEASE STATE: latest RELEASED = v0.1.8 (2026-07-15, PyPI + GitHub tags v0.1.0…v0.1.8).
**v0.2.0 is code-complete but UNRELEASED on branch codex/cross-platform-mcp-hardening**
(see HANDOFF §10) — releasing it (merge + tag) is the OWNER's decision (it drops py3.9
and makes mcp a required dep). PUBLIC surfaces: PyPI `pip install smartcli-toolkit`
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

OPEN OBJECTIVES (the §6 A-grade list #1–#7 is DONE through v0.1.8; what actually remains):
1. [OWNER] Decide & cut the v0.2.0 release: merge codex/cross-platform-mcp-hardening,
   `git tag v0.2.0 && git push origin v0.2.0` (publish.yml then does PyPI + MCP Registry).
   Breaking: drops py3.9, mcp becomes required — CHANGELOG documents both.
2. [OWNER, standing] B-SEC: revoke the leaked PyPI API token (OIDC publish makes it
   unnecessary). Re-raise every session until done — do not silently drop.
3. [S] D1: write RESEARCH-PROMPTS.md from the calibrated /deep-research anchor list
   (conch, terminal-bench, plotille, TTE, PyPI trusted publishing) — see NEXT-STEPS D1.
4. [M-L] Harbor / TB-2.0 port of the Terminal-Bench adapter (classic-TB adapter exists;
   the public leaderboard moved to a different agent interface). bench.yml scored runs
   also need the owner to add an LLM API-key secret.
5. [M] tui-ui reactive/declarative layer; [M] kitty graphics protocol next to sixel.
6. [Human eyeball] effort_selector cadence in a real Windows Terminal (travel SMALL,
   ~lambda x1..1.6; distances ultracode 4/max 14/xhigh 25/high 34/medium 45/low 53);
   real-Mac interactive curses DECCKM/SS3 probe over SSH; real-WT sixel render
   eyeball. (tmux launchers: DONE 2026-07-27 on real tmux 3.6b.)
Discoverability (owner-gated, copy ready in docs/LAUNCH-COPY.md): C2 awesome-list PRs,
then C4 Show HN / r/commandline + C5 skill-community posts (C1 proof reels are DONE).

VERIFY WHAT YOU SHIP (all should exit 0; paths POSIX-style, swap \ on Windows).
Heavy PTY spawners (run_all, verify_fx, probes) need user consent first — red line:
  python tests/run_all.py                # unified runner (29 entries; consent first)
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


