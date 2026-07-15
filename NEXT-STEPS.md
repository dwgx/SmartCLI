# NEXT-STEPS — SmartCLI prioritized task queue

Written 2026-07-12 at the end of a long session. This file is the single source of
truth for "what to do next". Tasks are ordered by impact/effort and written as
**self-contained prompts**: a fresh AI with no memory of this session can pick any
task and start. Each task states the goal, why it matters, a concrete first step,
how to verify, and effort (S/M/L).

Read the "Standing method" section at the bottom BEFORE touching code. It is
non-negotiable and overrides any shortcut that looks faster.

---

## How to use this file

1. Pick the lowest-numbered unblocked task in "Safe to do now on Windows".
2. Re-verify the ground-truth snapshot below against disk first (counts drift).
3. Do the work on a branch, verify on the REAL run path, then update this file:
   strike the task and add a one-line result note.
4. Never regress a passing gate. Quality only goes up.

---

## Verified ground-truth snapshot (checked against disk 2026-07-14)

- Release: **v0.1.2** live on PyPI as dist `smartcli-toolkit` (import stays
  `smartcli_core`): `pip install smartcli-toolkit`. Repo github.com/dwgx/SmartCLI,
  branch `main`, tags v0.1.0/v0.1.1/v0.1.2 with GitHub Releases. 3 skills also on
  skillhu.bz. `.claude-plugin/marketplace.json` present.
- Version 0.1.2 is consistent across pyproject.toml, smartcli_core/__init__.py,
  skills/cmd-art/fx/__init__.py, all 3 skills/*/SKILL.md, marketplace.json. VERIFIED.
- Live counts (re-verified against code 2026-07-13): cmd-art **22 effects / 8 themes**
  (solarsystem added 2026-07-13, after the v0.1.2 tag); drive-tui **8 recipes**
  (patterns/recipes/); tui-ui **15 widgets** (braille_chart present in
  ui/widgets_ext/braille_chart.py); knowledge **140 md files / 122-note graph**.
  If any doc still says 18 effects or 14 widgets it is STALE (`python -m fx list` = 19,
  `python -m ui widgets` = 15).
- CI (updated 2026-07-14): **8 workflows**. `ci.yml` is a **3-OS matrix**
  (windows/ubuntu/macos × py3.11/3.12) running ~12 deterministic gates incl.
  `test_doc_counts` (anti-drift) + POSIX-only `_sandbox_posix_backend.py` on the
  non-Windows legs. Plus `publish.yml` + `publish-testpypi.yml` (OIDC),
  `pages.yml`, `docker.yml` (GHCR), `codeql.yml`, `lint.yml`, `release-drafter.yml`.
  VERIFIED present.
- Core fixes (smartcli_core, done WITH authorization + adversarial verify):
  #1 blank_hash readiness gate, #2 unanchored `>>> ` docstrings, #4 WinptyBackend
  EOF/queue reset. **#5 + #6 FIXED & verified on real Debian 13 (2026-07-13)**:
  #5 arrows now adaptive (SS3 under DECCKM via ScreenModel.app_cursor, CSI else),
  #6 POSIX terminate() now reaps the child (no zombie). Verified with
  tests/_sandbox_posix_backend.py over SSH; Windows zero-regression.
  NOT fixed (recorded known): #3 content_hash blind to selection-only move
  (design tradeoff — fixing risks false-unstable). See
  skills/drive-tui/references/LIMITATIONS.md for the living log.
- `research/cc-decompiled/` is gitignored and EXCLUDED from release. VERIFIED. Keep
  it excluded — do not re-expose it. Provenance wording already neutralized.
- Env: Windows 11, Python 3.14.6, pyte 0.8.2 + pywinpty 3.0.5. No tmux, no WSL.
  Always `export PYTHONIOENCODING=utf-8` (box/CJK glyphs crash on gbk).

---

## A. Safe to do now on Windows (no external accounts, no POSIX box, no human)

These are fully executable and verifiable on the current Windows machine.

### ~~A1. Ship a `py.typed` marker in smartcli_core~~  [S] — DONE 2026-07-13
- **Result:** created `smartcli_core/py.typed` (empty PEP 561 marker) + added
  `[tool.setuptools.package-data] smartcli_core = ["py.typed"]` to pyproject.toml.
  Verified on the REAL build path: `python -m build --wheel` then inspected the wheel
  zip — `smartcli_core/py.typed` IS inside the built wheel (not just the source tree).
  mypy not installed on this box so the optional downstream check was skipped; the
  wheel-contents proof is the authoritative PEP 561 check. run_all.py still 15/15.
  Build artifacts cleaned. **NOT version-bumped / NOT published** — bump all six
  version sites together to 0.1.3 only when the user cuts the next release (bumping
  the repo ahead of PyPI would break the "six sites == what's on PyPI" invariant).
- *(original task, for reference)* **Goal:** make smartcli_core a PEP 561 typed
  package so downstream users get type checking against the public API.
- **Why it matters:** cheapest A-grade signal; every serious library ships it. VERIFIED
  MISSING today (no smartcli_core/py.typed, no package-data in pyproject.toml).
- **First step:** create empty file `smartcli_core/py.typed`; add package-data to
  pyproject.toml so it ships in the wheel (under `[tool.setuptools.package-data]` or
  the build backend's equivalent — check which backend pyproject.toml uses first).
- **Verify:** `python -m build`, unzip the wheel, confirm `smartcli_core/py.typed` is
  inside. Optionally `python -m mypy` against a tiny sample import. Bump patch version
  everywhere (see version list in snapshot) if you publish.
- **Effort:** S

### A4. pexpect-style multi-marker wait (wait-any returning which matched)  [S]
- **Goal:** add a `wait_any(patterns) -> (index, match)` style API to the readiness
  layer so callers can wait on several possible outcomes at once (prompt vs error vs
  EOF), like pexpect's `expect([...])`.
- **Why it matters:** closes a concrete feature gap vs pexpect; small surface, high
  utility for recipe authors driving branchy TUIs.
- **First step:** read `smartcli_core/readiness.py` (the `wait_ready`/`wait_until_stable`
  functions and the blank_hash gate) and `session.py` to see how markers are matched
  today; design `wait_any` to reuse the same scan loop, returning the winning index.
- **Verify:** add deterministic virtual-clock unit tests in tests/test_readiness.py
  (mirror the existing style — those are mutation-verified genuine). Cover: first
  pattern wins, later pattern wins, timeout with none matched. Run tests/run_all.py.
  This touches smartcli_core → obey the core-modification rule (adversarial review +
  full recipe suite green).
- **Effort:** S

### A7. Ship spectrum-bars + cbonsai effects in cmd-art  [S-M]
- **Goal:** add two new effects to reach a rounder catalog: an audio-style
  `spectrum-bars` and a procedural `cbonsai`-style branching tree.
- **Why it matters:** cheap catalog growth; the knowledge notes `[[spectrum-bars]]` and
  `[[procedural-branching]]` already contain the real algorithm constants, so this is
  implementation, not research.
- **First step:** read those two knowledge notes; read one existing anim effect in
  skills/cmd-art/fx/ (e.g. `fire` or `plasma`) to learn the effect contract (frame
  size, theme gradient, Param handling); scaffold the new effect files following that
  contract.
- **Verify:** `cd skills/cmd-art && python -m fx list` shows the new effects; run each
  via `python -m fx play <name>`; extend tests/test_fx_contract.py so the new effects
  are covered by the exact frame contract (it enumerates all_effects(), so the count
  rises automatically from the current 19 as you add each). Run
  verify_fx.py to exit-0 (known random-seconds flake — rerun once if it trips).
- **Effort:** S-M

### A5. Golden-frame snapshot regression test for tui-ui  [M]
- **Goal:** commit a baseline rendered-frame per widget and diff on every run, like
  pytest-textual-snapshot.
- **Why it matters:** locks all 15 widgets against silent visual regressions; today
  only degenerate-input crashes and the fx frame contract are guarded, widget output
  is not.
- **First step:** `cd skills/tui-ui && python -m ui widgets` to enumerate the 15
  widgets (badge, banner, braille_chart, card, gradient_rule, kv, meter, panel,
  progress, radial_glow, rule, slider_track, table, tabs, tree). Render each at a
  fixed size/seed to a deterministic string; write the strings to a committed
  `tests/golden/` dir; add a test that re-renders and diffs, with an `--update` env
  escape hatch.
- **Verify:** run the new test twice — stable pass. Mutate one widget's output by one
  char and confirm the test FAILS (proves it is not false-green). Revert. Run run_all.py.
- **Effort:** M

### A6. Shared easing.py + Gradient(stops, steps, direction) builder for cmd-art  [M]
- **Goal:** factor the repeated easing curves and gradient math into reusable
  `easing.py` and a `Gradient(stops, steps, direction)` builder.
- **Why it matters:** removes duplication across the 22 effects, makes new effects (A7)
  cheaper, and is a clean public sub-API.
- **First step:** grep skills/cmd-art/fx/ for inline lerp/ease/gradient math to find
  the duplication; design the smallest API that covers existing call sites; refactor
  one effect to use it as a proof.
- **Verify:** tests/test_fx_contract.py must still produce byte-identical frames for
  every unchanged effect (the contract is exact — any drift is a real regression to
  investigate, not to rebaseline blindly). Run verify_fx.py exit-0.
- **Effort:** M

### A3. MCP-server wrapper over the drive-tui daemon verb surface  [M]
- **Goal:** expose the drive-tui daemon's verbs (spawn, send, wait, read-screen, etc.)
  as an MCP server so any MCP client can drive TUIs.
- **Why it matters:** biggest adoption lever in the backlog — turns the project from
  "a skill" into "a tool any agent can call". Note: partially POSIX-relevant but the
  wrapper itself and its token-auth path ARE testable on Windows via the existing
  live probes.
- **First step:** read skills/drive-tui/ daemon code + `_tui_cli_probe.py` to
  enumerate the exact verb surface and the per-session token-auth scheme (added this
  session). Map each verb to an MCP tool with a typed schema. Pick a minimal MCP
  server lib compatible with Python 3.14.
- **Verify:** stand up the MCP server locally, drive one recipe end-to-end through it
  (e.g. paginate or form_fill), assert the screen state matches the direct-daemon
  path. Keep the token-auth requirement — flag loudly if any verb is exposed
  unauthenticated (network-exposed surface).
- **Effort:** M

### A8. mkdocs-material docs site + CONTRIBUTING.md + coverage badge  [L] — PARTIAL (2026-07-14)
- **Status:** `mkdocs.yml` **now exists** (config prepared, commit 61c5a93) but is NOT
  yet hosted on Pages — the live site at dwgx.github.io/SmartCLI is the hand-written
  `docs/site/`, deployed by `pages.yml`. Still open: actually build+host the mkdocs
  site, add `CONTRIBUTING.md`, and a pytest/coverage badge.
- **Goal:** a real docs site (mkdocs-material), a CONTRIBUTING.md, and a
  pytest/coverage badge in the README.
- **Why it matters:** last structural A-grade gap; makes the repo look maintained and
  lowers the contribution barrier once stars start arriving.
- **First step:** `mkdocs.yml` is scaffolded — flesh out `docs/` sections mirroring the
  3 skills + smartcli_core API; wire a coverage run (pytest-cov over tests/run_all.py)
  and emit a badge. Do NOT include anything from research/cc-decompiled.
- **Verify:** `mkdocs build --strict` exits 0 with no broken internal links; coverage
  command produces a number and the badge renders. Confirm the built site references no
  neutralized-provenance terms.
- **Effort:** L

---

## B. Needs POSIX box, a human, or an external account

Do NOT fake these on Windows. A green monkeypatched harness is not proof for the
POSIX backend — that is exactly the class of false-green the standing method forbids.

### ~~B2. Add a Linux CI matrix running the deterministic tests~~  [DONE 2026-07-14]
- **Result:** `ci.yml` is now a **3-OS matrix** — `os: [windows-latest, ubuntu-latest,
  macos-latest] × python: [3.11, 3.12]`, `fail-fast: false`. Runs ~12 deterministic
  gates (verify_fx, test_fx_contract, test_readiness, test_degenerate_inputs,
  _sandbox_fuzz_core, test_vendor_sync, test_doc_counts, _readme_literal, tui-ui
  self_test, fx list, ui widgets) on all three OSes, plus `_sandbox_posix_backend.py`
  gated `if: runner.os != 'Windows'` so the POSIX pty backend (#5 SS3 arrows / #6
  zombie reap) stays green on ubuntu + macos automatically — no more manual SSH run.
  The interactive drive-tui PTY probes + effort_selector stay OUT of CI (need a live
  TTY, hang-prone on runners); the pure-memory gates cover the code paths.
- *(original task, for reference)* validate the POSIX backend in CI instead of by a
  manual SSH run to Debian 13 — now automated.

### B-PyPI. PyPI Trusted-Publisher setup  [DONE 2026-07-13]
- **Status:** DONE and verified. Trusted Publisher registered on PyPI (owner `dwgx`,
  **repo `SmartCLI`** — GitHub repo name, not the `smartcli-toolkit` dist name; that
  mismatch was the original `invalid-publisher` failure) + `pypi` GitHub Environment
  created. A `workflow_dispatch` run (29245353129) went green: OIDC handshake succeeded,
  publish ran against `upload.pypi.org`. `skip-existing:true` added so re-runs are no-ops.
- **Releasing now:** bump the version everywhere, `git tag vX.Y.Z && git push origin vX.Y.Z`
  — publish.yml auto-uploads via OIDC, no stored token. (twine no longer needed; the old
  `--disable-progress-bar` note was only because twine's rich bar crashes on gbk.)

### B-SEC. Revoke the leaked PyPI API token  [S] (needs human; owner previously declined)
- **Goal:** revoke the plaintext PyPI token that appeared in a prior session's chat.
- **Why it matters:** live credential exposure. Owner chose NOT to revoke last time —
  re-surface it, do not silently drop it.
- **First step (human):** on PyPI, delete that API token; rely on the OIDC publish flow
  (B-PyPI) instead.
- **Verify:** old token 401s; a fresh OIDC publish still works.
- **Effort:** S

### B-Skillhu. Retry external skill-publish CLIs  [S] (needs working external CLIs)
- **Goal:** publish/refresh on LobeHub / agentskillhub if their CLIs get fixed.
- **Why it matters:** the publish CLIs had real upstream bugs this session (spawn
  `start` ENOENT / IPv6-only callback / server 401) — not the project's fault. Skills
  are already live on skillhu.bz.
- **First step:** retry the publish CLI; if it still errors, log the exact error and
  move on — do not work around a broken external tool.
- **Verify:** the skill page reflects v0.1.2.
- **Effort:** S (blocked on external tooling)

---

## C. Launch / growth plan — TWO PHASES (2 stars today)

Strategy (owner's call, 2026-07-13): **seed first, then ignite.** Target three
audiences: **(1) AI-agent developers** (core pitch: "agents can't drive
interactive CLIs — SmartCLI gives them eyes+hands"), **(2) terminal/CLI
enthusiasts** (hook: cmd-art effects + tui-ui widgets), **(3) Claude Code / skill
users** (show: drop the skill into their agent).

Honest gate before igniting: the showcase layer is strong (live site, GIFs,
interactive playground, 5 languages) but there is **~zero external validation** —
the first real users will hit `skills/drive-tui/references/LIMITATIONS.md` edges.
So Phase 1 buys credibility + resilience; Phase 2 spends it.

Already done (do NOT redo): README fx demos + **real re-driven proof reels as
MP4+WebM video** (lazygit/htop/ncdu/nano at 60/30fps, incl. Windows/macOS/Linux
variants + dialog/vim, with click-to-zoom lightbox — replaced the old GIF galleries
2026-07-14), live showcase site https://dwgx.github.io/SmartCLI/ (interactive, 5-lang,
grok de-branded to a generic agent except the `.chip` tags), PyPI `smartcli-toolkit`,
skillhu.bz listings, POSIX verified on real Linux + macOS CI, 3-OS CI matrix + 8
workflows.

### PHASE 1 — SEED (build discoverability + proof; low blast radius)

#### ~~C1. Real-world proof reel~~ — DONE 2026-07-13
- Drove the REAL lazygit 0.63 TUI in a throwaway Debian 13 container via
  smartcli_core (SS3/DECCKM arrows, reverse-video selection reading, opened a
  real commit diff, highlighted a branch). Captured to `showcase/drive-lazygit.gif`
  and featured at the top of README ("Driving a real TUI"). Reproduce:
  `tests/_demo_lazygit.py` + `tools/make_lazygit_gif.py`. Container torn down.
- **Copy for all channels drafted + fact-checked in `docs/LAUNCH-COPY.md`.**

#### C1-orig. Real-world proof reel (original task, for reference)  [M]
- **Goal:** short recordings/writeups of SmartCLI driving REAL third-party TUIs end
  to end — e.g. drive `htop`/`k9s` read-only, answer a real installer's prompts, page
  through `less`/`git log`. Not toy apps — real programs.
- **Why:** this is the missing social proof. "Drove <real tool> autonomously" is what
  converts skeptics; it also surfaces + fixes LIMITATIONS edges before strangers do.
- **First step (AI):** in the Linux sandbox, drive 3 real TUIs, capture asciinema/GIF +
  a short "here's the perceive→act loop" writeup; log any gap in LIMITATIONS.md and fix
  what's cheap. **Human:** confirm which tools are fair game.
- **Verify:** each reel loops clean, no mojibake; the case study reproduces from the repo.

#### C2. awesome-list PRs (durable long-tail)  [S] (human/PR — copy ready)
- **PR text drafted** for awesome-cli-apps, awesome-tuis, awesome-claude-code,
  awesome-python in `docs/LAUNCH-COPY.md` §C2. **Human:** fork each, add the line
  in the right category per its CONTRIBUTING, open the PR.

#### ~~C3. SEO / metadata polish~~ — DONE 2026-07-13
- Repo topics already good; **repo homepage set to the live site**; **OpenGraph +
  Twitter cards added to the site head** (links now unfurl with title + pitch +
  the solarsystem GIF). Remaining optional: OG tags on the 4 localized pages.

### PHASE 2 — IGNITE (spend the credibility; higher variance)

#### C4. Show HN + r/commandline + r/Python + X thread  [S] (human posts; blocked on C1)
- **Goal:** coordinated launch once C1 proof exists. Lead with a real-TUI reel + one-line
  install. Per-audience framing: agent-dev angle for HN, visual angle for r/commandline.
- **AI can:** draft the Show HN title + first comment, the Reddit posts, the X thread
  (each tuned to its audience) + a FAQ pre-empting "does it work with <my TUI>?".
- **Human:** post, and be available to answer for the first few hours (matters a lot).

#### C5. Claude Code / skill-community push  [S] (human; hottest circle)
- **Goal:** post in Claude Code / agent-skill channels showing "drop drive-tui in, your
  agent can now drive interactive CLIs." Reuse the marketplace one-liner.
- **AI can:** draft the post + a 20s "install → drive" clip. **Human:** post to the
  communities they're in.

Sequencing: C1→C3 (seed, mostly AI-doable) land first; C4/C5 (human, ignite) fire
together once C1's proof reel is real. Never ignite before C1 — a launch with no
external proof invites "does it actually work?" with no answer.

---

## D. Save the calibrated deep-research anchors

### D1. Write RESEARCH-PROMPTS.md from the session's /deep-research anchor list  [S]
- **Goal:** persist the calibrated `/deep-research` prompt list so it is not lost.
- **Why it matters:** these anchors were tuned this session and drive the competitive
  benchmarking that keeps the A-grade gaps honest.
- **Anchors to include:** conch, terminal-bench, plotille, TTE (terminaltexteffects),
  PyPI trusted publishing. (Also benchmarked against: pexpect, Textual,
  pytest-textual-snapshot.)
- **First step:** create RESEARCH-PROMPTS.md, one section per anchor, each with the
  specific question to research and what a good answer changes in this backlog.
- **Verify:** file exists, each anchor has a runnable prompt. (Docs-only — no code gate.)
- **Effort:** S

---

## Standing method — NON-NEGOTIABLE (never regress this)

Every task above is done under these rules. They override any faster-looking shortcut.

1. **Measure ground truth.** Never head-canon a count, a file's contents, or a
   behavior. Read disk, run the command, look at the real output. The snapshot at the
   top of this file was re-verified against disk — re-verify it again before you rely
   on it, because counts drift.

2. **Verify on the REAL run path.** A green preview, a monkeypatched harness, or a
   mocked backend is NOT proof. Drive the actual PtySession / daemon / effect the way a
   real user would and inspect the real result.

3. **Mutation-test against false-green.** After a test passes, deliberately break the
   code it covers and confirm the test FAILS. A test that stays green under a real
   mutation is worthless — fix it before trusting it. Every test in this repo is
   mutation-verified genuine; keep it that way.

4. **Concurrent workflows + adversarial verify.** Run multi-agent workflows in
   parallel, and always finish with an independent adversarial verification pass that
   tries to disprove the result. Unlimited tokens — default to the higher-quality
   concurrent path.

5. **Quality only goes UP.** Never trade a passing gate for speed. Regression gates
   that must stay exit-0: verify_fx.py (30/30 = 22 effects + 8 fixed checks; known
   random-seconds flake — rerun once), _readme_literal.py, probe_pty_fx.py, tests/run_all.py.

6. **The smartcli_core modification rule.** smartcli_core was DO-NOT-MODIFY. Changes
   are now allowed ONLY with: (a) real-run-path verification, (b) independent
   adversarial review, and (c) no regression across the FULL recipe suite. Any core
   task above (A4, A3's daemon touches, B2 findings) is bound by all three.

7. **Keep research/cc-decompiled/ excluded.** It is gitignored and out of the release.
   Do not re-expose it; keep provenance wording neutral in all shipping files.



