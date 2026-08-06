# NEXT-STEPS — SmartCLI prioritized task queue

Written 2026-07-12; snapshot + queue last reconciled **2026-08-06** (post-v0.2.0-release
work — see HANDOFF §10h/10i). This file is the single source of truth for "what to do
next". Tasks are ordered by impact/effort and written as **self-contained prompts**:
a fresh AI with no memory of this session can pick any task and start. Each task
states the goal, why it matters, a concrete first step, how to verify, and effort
(S/M/L).

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

## Verified ground-truth snapshot (checked against disk 2026-08-06)

- **v0.2.1 IS RELEASED (2026-08-06).** Tagged from `main` at `9454f05`; all three
  publish.yml jobs green including `publish-mcp` (which only runs on a real tag push, so
  the bumped action pins executed there for the first time). Live and verified: PyPI
  serves 0.2.1 as wheel + sdist, the MCP Registry lists 0.2.1 `active`, the GitHub
  Release is published and Latest, GHCR image built. A clean-venv
  `pip install smartcli-toolkit==0.2.1` confirms the fixes reached users. This closes
  the pyte-upgrade timebomb exposure for new installs (HANDOFF §10j). The PyPI JSON
  index lagged a few minutes behind the green publish — the workflow is the truth,
  not the index.
- Previous release: **v0.2.0** on PyPI as dist `smartcli-toolkit` (import
  stays `smartcli_core`). Repo github.com/dwgx/SmartCLI, tags v0.1.0…v0.2.0 with
  GitHub Releases (`git tag | tail -3` → v0.1.8, v0.2.0; `git log --oneline -1
  v0.2.0` → `f2a0db0 release: v0.2.0 — hardened control plane, installable MCP,
  terminal fidelity`). **v0.2.0 was merged to `main`, tagged, and published on
  2026-07-27** — PyPI + GitHub Release + MCP Registry, all three publish.yml jobs
  green (build → PyPI OIDC → MCP Registry OIDC). It carries: security-hardened
  drive-tui control plane, visual_hash + wait-visual-change, wheel ships
  smartcli_drive + smartcli-tui/smartcli-mcp/smartcli-toolkit commands, mcp
  required dep, Python floor 3.10. Since release, two more sessions landed on
  `main` (HANDOFF §10h/10i, both 2026-08-05/06): a real Harbor adapter, a
  dependency-drift gate, alt_screen surfaced end-to-end, mode 1048, and a
  cursor_down DECSTBM fix — none of these bumped the version. 3 skills also on
  skillhu.bz. `.claude-plugin/marketplace.json` present. Codecov + Read the Docs
  (smartcli.readthedocs.io) live.
- Version 0.2.0 (in-tree) is consistent across **TEN** sites: pyproject.toml,
  smartcli_core/__init__.py, skills/cmd-art/fx/__init__.py, all 3 skills/*/SKILL.md,
  marketplace.json, **plugin.json**, _vendor/smartcli_core/__init__.py, server.json
  (2 fields). After a bump run tools/sync_vendor.py + tests/test_vendor_sync.py +
  **tests/test_version_sync.py** (anti-drift gate added 2026-07-27). VERIFIED.
- Live counts (re-verified against code 2026-07-27): cmd-art **30 effects / 8 themes**;
  drive-tui **8 recipes** (patterns/recipes/); tui-ui **17 widgets** (11 core + 6 in
  ui/widgets_ext/); knowledge **143 md files**. `python -m fx list` = 30,
  `python -m ui widgets` = 17. Anti-drift gate (test_doc_counts.py) enforces effect
  AND widget counts across shipping docs (extended 2026-07-27).
- Suite size: `tests/run_all.py` `build_suite()` is **43 entries**, **43/43 green on
  macOS as of 2026-08-06** — the first full green here. It was 39/43 for a while; the
  four earlier failures were platform gaps in test fixtures (`_menu_app.py` and three
  siblings opening with `import sys, msvcrt` and dying on POSIX before drawing
  anything; `examples/drive_vim.py` unable to import `smartcli_core` from a checkout),
  not product bugs. See HANDOFF §10i. Registration is unconditional — tmux probes SKIP
  themselves rather than deregistering — so 43 does not vary by host.
- CI (updated 2026-07-27): **9 workflows**. `ci.yml` is a **3-OS matrix**
  (windows/ubuntu/macos × **py3.10/3.14**) running the deterministic gates incl.
  `test_doc_counts` + `test_version_sync` (anti-drift), `test_visual_change`,
  `test_drive_security`, + POSIX-only `_sandbox_posix_backend.py` on non-Windows
  legs; plus bounded **drive-smoke** (real-PTY probes, 3 OS) and **package**
  (wheel/registry contract) jobs. Plus `publish.yml` (OIDC PyPI + `publish-mcp`
  OIDC MCP-Registry job) + `publish-testpypi.yml`, `pages.yml`, `docker.yml`
  (GHCR), `codeql.yml`, `lint.yml` (ruff correctness subset + mypy now BLOCK),
  `release-drafter.yml`, `bench.yml`. VERIFIED present.
- Core fixes (smartcli_core, done WITH authorization + adversarial verify):
  #1 blank_hash readiness gate, #2 unanchored `>>> ` docstrings, #4 WinptyBackend
  EOF/queue reset. **#5 + #6 FIXED & verified on real Debian 13 (2026-07-13)**:
  #5 arrows now adaptive (SS3 under DECCKM via ScreenModel.app_cursor, CSI else),
  #6 POSIX terminate() now reaps the child (no zombie). **#3 RESOLVED in v0.2.0**:
  content_hash stays text-only by design; new visual_hash + wait_visual_change
  cover selection/attribute/cursor-only changes end-to-end. See
  skills/drive-tui/references/LIMITATIONS.md for the living log.
- `research/cc-decompiled/` is gitignored and EXCLUDED from release. VERIFIED. Keep
  it excluded — do not re-expose it. Provenance wording already neutralized.
- Env: dual-host. Current working copy: macOS (Apple Silicon), Python 3.14.6, POSIX
  pty. Historical primary: Windows 11, pyte 0.8.2 + pywinpty 3.0.5, no tmux/WSL.
  Everywhere `export PYTHONIOENCODING=utf-8` (box/CJK glyphs crash on gbk). Since
  v0.2.0 `mcp>=1.0` is a required dependency.

---

## A0. NEW since v0.2.0 (added 2026-07-27)

### ~~A0-GLAMA. List on Glama to unblock the 91k-star awesome-mcp-servers PR~~  [DONE 2026-08-03 — owner]
- **Goal:** submit SmartCLI at <https://glama.ai/mcp/servers> ("Add Server"), then
  add the returned score badge to PR
  [#11022](https://github.com/punkpeye/awesome-mcp-servers/pull/11022).
- **Result:** owner listed and claimed the server (`glama.ai/mcp/servers/dwgx/SmartCLI`,
  id `rqnmoia3ut`) and added the score badge; PR #11022 flipped to `has-glama` and is
  MERGEABLE. Maintainer `punkpeye` had given the two-step instruction personally on
  2026-07-29. Verified 2026-08-03: Glama's API returns the server (it returned
  `not_found` on 2026-07-27).
- **Why it was needed:** the `glama-check` bot labelled that PR `missing-glama`; a Glama listing
  is a stated precondition. Note the dependency direction — the claim that a
  merged PR syncs *to* Glama was refuted 0-3. Verified we are NOT on Glama today:
  `curl -s https://glama.ai/api/mcp/v1/servers/dwgx/SmartCLI` → `not_found`.
- **Readiness:** already verified — the server passes the introspection check Glama
  runs (`initialize` → serverInfo 0.2.0, `tools/list` → 14 tools).
- **Why owner-only:** the Add Server flow is behind a sign-in; an agent should not
  authenticate to a third-party service as you.
- **Verify:** the two `curl` calls in docs/DISTRIBUTION-CHANNELS.md §3 return the
  server instead of `not_found`.
- **Effort:** S (~5 min)

### ~~A0-REL. Release v0.2.0~~  [DONE 2026-07-27]
- **Result:** merged to `main`, tagged `v0.2.0`, pushed. publish.yml green on all
  three jobs (build / PyPI OIDC / MCP Registry OIDC). Verified by installing
  `smartcli-toolkit==0.2.0` from PyPI into a clean venv: `smartcli-tui doctor`
  works, the alt-screen and ZWJ fixes are live, `smartcli_drive.mcp_server`
  imports. GitHub Release created from the CHANGELOG entry.
- *(original task below)*

### ~~A0-REL-orig~~. Release v0.2.0  [S] (OWNER decision — breaking changes)
- **Goal:** merge `codex/cross-platform-mcp-hardening` into `main` and cut v0.2.0.
- **Why it matters:** the branch carries security hardening + the installable
  drive/MCP surface; until tagged, PyPI users get none of it. It is BREAKING:
  drops Python 3.9, makes `mcp` a required dependency — that call is the owner's.
- **First step (human):** review HANDOFF §10 + CHANGELOG [0.2.0]; merge the branch;
  `git tag v0.2.0 && git push origin v0.2.0` (publish.yml then does PyPI + MCP
  Registry via OIDC automatically). Before tagging, refresh the CHANGELOG date to
  the actual release day.
- **Verify:** publish.yml green (both publish + publish-mcp jobs); `pip install
  smartcli-toolkit==0.2.0` in a clean 3.10 venv → `smartcli-tui doctor` works;
  pip refuses the install on a 3.9 interpreter (Requires-Python metadata).
- **Effort:** S

### ~~A0-DIST. Map the distribution channels and file what is fileable~~ [DONE 2026-07-27]
- **Result:** `docs/DISTRIBUTION-CHANNELS.md` is the reusable map (105-agent research pass,
  23 sources, 25 claims verified 3 votes each → 15 confirmed / **10 refuted**, plus
  first-hand checks that override the research where they disagreed). Filed the one PR that
  is both a category fit and rule-compliant: awesome-mcp-servers #11022 (91k★), now blocked
  on A0-GLAMA (since cleared — see that task). Also done: PyPI keywords/classifiers (mcp, agent, pexpect, `Typing :: Typed`),
  8 GitHub topics, registry `description` rewritten to name vim/htop/lazygit.
- **Bugs this exposed** (the real value): Docker image defaulted to `fx gallery` so any MCP
  directory validating it would have scored the server broken; MCP `serverInfo` reported the
  SDK's version instead of ours; and two genuine CI failures in the new drive-smoke job
  (stale registry path on macOS/Linux, an 80-column wrap breaking a Windows assertion).
- **Ruled out by rule, do not retry:** awesome-python (auto-reject <100★ / <1 month —
  ineligible until ~Oct 2026), awesome-cli-apps (>20★, >3 months, and "AI-generated PRs are
  not welcome"), awesome-tuis (category mismatch), Anthropic Connectors (remote-only).
- **Unmapped, the biggest known gap:** Smithery, MCP.so, mcpservers.org, PulseMCP, and the
  Cursor/Continue marketplaces produced no surviving claims. Smithery and MCP.so are *said*
  to auto-crawl; if true they would be the cheapest channels available.

### ~~A0-HARBOR. Port the Terminal-Bench adapter to Harbor~~  [DONE 2026-08-05]
- **Result:** `smartcli_tbench/harbor_agent.py` — a real `harbor.agents.base.BaseAgent`
  subclass, selectable via `import_path` without forking Harbor. Verified against the
  actual Harbor base class (installed it): genuine subclass, zero unimplemented abstract
  methods, instantiates, `run`/`setup` signatures match the caller.
- **The interface difference, read from source not docs:** Harbor gives
  `async exec(command) -> ExecResult` — a one-shot runner, no tmux handle, no
  `capture_pane`. `driver.py`'s approach does not apply. So `setup()` pip-installs
  smartcli-toolkit *inside* the environment and the loop drives its persistent-session
  CLI over `exec`, which is how the agent gets a PTY and screen-state waits that Harbor
  does not provide natively.
- **Locked by** `tests/test_harbor_agent.py` (22 checks, no Harbor/Docker/PTY needed):
  drives the loop against a fake environment shaped from the real `exec()` signature,
  and asserts the two things a benchmark harness must not get wrong — the session closes
  even when `decide_fn` raises, and a missing `decide_fn` is reported rather than
  silently scoring zero.
- **Still needed for an actual leaderboard number (owner):** a `decide_fn` (a model
  client — deliberately not bundled) and an LLM API-key secret for `bench.yml`.

### ~~A0-DEPDRIFT. Gate the dependency declarations against each other~~ [DONE 2026-08-05]
- **Result:** `tests/test_dependency_sync.py`. `requirements.txt` must equal pyproject's
  runtime `dependencies` exactly, `requires-python` must agree wherever restated
  (including the mypy/ruff targets), and packaging drafts must not leave a dependency
  unbounded that pyproject caps. Mutation-verified with three breakages, one of which
  replays the real bug exactly.
- **Why:** the same fault fired twice in a day — `mcp` capped in pyproject but not in
  `requirements.txt` (which is what the **Docker image** installs, and that image is what
  MCP directories run to validate the server), and the same facts drifted in the
  conda-forge recipe. The gate found a live drift on its first run: the conda recipe still
  had a bare `mcp >=1.0`, which would have shipped an uninstallable package.

### ~~A0-HARBOR-orig~~. A0-HARBOR. Port the Terminal-Bench adapter to TB-2.0 / Harbor  [M-L]
- **Goal:** the classic-TB adapter (`smartcli_tbench/`) targets an interface the
  public leaderboard no longer uses; port to Harbor's tool/env-mediated agent API.
- **First step:** read HANDOFF §9h (adapter design + caveat) and the Harbor agent
  interface docs; map driver.py's wait primitives onto Harbor's session surface.
- **Verify:** oracle smoke run green in bench.yml; scored runs additionally need the
  owner to add an LLM API-key secret.
- **Effort:** M-L

### ~~A0-TMUX. Verify the cmd-art tmux launchers on a real tmux host~~ [DONE 2026-07-27]
- **Result:** verified on real tmux 3.6b (macOS). `fx-split` works (window splits,
  effect renders in the new pane). `fx-popup` was **broken**: `display-popup`
  needs an attached client, and from a detached session it leaked tmux's raw
  "no current client" with exit 1, violating its own clean-exit contract — now
  guarded. `tests/_tmux_launcher_probe.py` locks all five states (18/18, zero
  residue) and SKIPs itself where tmux is absent.

### A0-DIFF2. Extend differential testing beyond tmux  [M]
- **Goal:** `tests/_diff_tmux_pyte.py` proves our grid matches real tmux on 26
  cases. Extend the same technique: (a) more cases — alt-screen enter/exit,
  DECCKM arrows, mouse-mode sequences, OSC title, bracketed paste, SGR
  underline styles/colours; (b) a second reference emulator (xterm via
  `xterm -e`, kitty, or Alacritty) so we are not proving "we match tmux"
  specifically; (c) generative payloads — random control-sequence soup diffed
  against the reference, which is how remaining emulation gaps will surface.
- **Why it matters:** this is the only evidence that perception is correct
  rather than self-consistent, and it already found a real text-loss bug that
  every existing test missed. It is also the most credible external artifact
  this project can show.
- **First step:** read `_diff_tmux_pyte.py` (note the rig-artifact section — tty
  ONLCR, literal TAB, NFC — before adding cases); add the alt-screen and
  DECCKM cases first, since drive-tui depends on both.
- **Verify:** probe stays exit 0 with zero leaked sessions; any new divergence
  is triaged as rig-vs-real before touching the core.
- **Effort:** M

### A0-PERF. Performance contract for the wait primitives  [M]
- **Goal:** no perf test exists anywhere in the suite. Measured 2026-07-27 on
  this machine: `content_hash` 0.34 ms and `visual_hash` 1.16 ms at 80x24, but
  **5.35 / 16.85 ms at 300x100** — at the default `poll_ms=30`, `visual_hash`
  eats 56% of the polling budget on a large terminal. Nothing prevents a change
  from making that worse.
- **First step:** add a deterministic benchmark (fixed payload, fixed sizes,
  in-memory) asserting a per-call ceiling at a few sizes; then make
  `visual_hash` incremental (hash only rows pyte marks dirty) instead of
  re-walking every cell.
- **Verify:** the benchmark fails if a change regresses the ceiling; the
  optimized `visual_hash` must keep `test_visual_change` and the differential
  probe green.
- **Effort:** M

### ~~A0-DIFF2 / A0-PERF (partial)~~ [DONE 2026-07-27]
- **Result:** generative differential fuzz (`tests/_diff_fuzz_tmux.py`) shipped
  and found **7 emulation bugs** hand-written cases missed (IL/DL column homing,
  IL count>1 buffer holes, wide-glyph half-overwrite, DCH on wide, NEL column,
  DECSTBM cursor clamping, orphaned wide stub) — all fixed, all cross-checked
  against GNU screen, 10/10 seeds x 40 payloads now clean. Performance contract
  (`tests/test_perf_contract.py`) shipped: `visual_hash` made incremental,
  16.566 ms → 0.008 ms idle on 300x100. See HANDOFF §10e.
- **Still open from those tasks:** a SECOND reference emulator in the差分 harness
  (kitty/Alacritty via brew — `screen` is used ad-hoc today but is not wired into
  the probe), alt-screen / DECCKM / mouse-mode / OSC / bracketed-paste cases, and
  property-based tests (Hypothesis) over `readiness.py`'s timing invariants.

### ~~A0-DIFF3. Second reference emulator + alt-screen/mode coverage~~ [DONE 2026-07-27]
- **Result:** `_diff_two_refs.py` (tmux AND GNU screen, ground truth only where
  both agree) 35/35; `test_readiness_properties.py` (7 Hypothesis invariants,
  mutation-verified); and two more real bugs fixed — **pyte implements no
  alternate screen buffer at all** (vim/less/htop painted over the main screen
  and never restored it) and SGR ':' sub-parameters spilled escape debris onto
  the grid. See HANDOFF §10f.
- **Still open:** a GUI-terminal reference (kitty/Alacritty — neither is
  installed here; both would need `brew install`), and DCS/DECRQSS round-trips.

### A0-PYTE-UPSTREAM. File the five confirmed-live pyte defects, mechanically ported  [M]
- **Goal:** upstream port patches for the five pyte defects that were MEASURED (not
  assumed) to be both real on pyte master and independent of the unreviewed
  alternate-screen PR: half-overwriting a wide glyph, DCH on a wide glyph, NEL not
  returning to column 0, and DECSTBM region-escape in both `index()` and
  `cursor_up()`. Independence was proven by extracting the 130-line diff and
  applying it to an untouched `upstream/master` worktree — both files applied
  cleanly and the suite stayed at 117 passed / 1 xfailed, so these five do not need
  to wait on selectel/pyte#212.
- **Why it matters:** `selectel/pyte#212` (the alternate-screen buffer, closing a
  9-year-old help-wanted issue) is `MERGEABLE` with 0 reviews and that upstream's
  last merge was ~11 months ago — attaching mechanical, independent wins to an
  unreviewed PR would make them hostage to it for no reason. See HANDOFF §10i for
  the full triage, including the two defects that did NOT survive independent
  re-check and must stay out of any upstream filing:
  - **Do NOT** file IL/DL homing the cursor column outside a scroll region — a
    second re-check found pyte's column-0 behavior matches xterm/vte/the DEC VT
    reference (terminalguide: "moves the cursor to the left margin"); SmartCLI
    keeping the column is a defensible choice (tmux 3.6b, GNU screen, urxvt,
    konsole, linuxvc all keep it too) but upstreaming it would move pyte away
    from the standard it targets and would rightly be rejected.
  - **Do NOT** file ZWJ cluster width — pyte master already picked tmux's side
    via `grapheme_clusters`.
  - **Do NOT** re-file SGR colon sub-parameters (`ESC[4:3mU` drawing literal
    `"3mU"`) — pyte #180 ("Understand (and discard) SGR subparameters", open
    since 2024-10-08) is already `MERGEABLE` for exactly that symptom, plus
    issues #179/#178 cover it. The bottleneck there is maintainer review, not a
    missing report; a +1 or a rebase offer on #180 is the useful move, not a new
    issue.
  - The orphaned-wide-stub defect (originally counted as a seventh) is **not a
    pyte defect** — its repro passes on untouched master with zero SmartCLI code;
    the orphan is manufactured by SmartCLI's own `draw()` override. Do not file it
    as a standalone issue, but its 3-byte repro (`b"a" + 中 + CR + 文` renders
    width 7 in an 8-column screen) folds into the half-overwrite patch since they
    share a root cause.
  - Read pyte #206 (actively rewriting the same `draw()`/grapheme path) before
    writing any wide-glyph patch — a patch against code #206 is about to replace
    is wasted work.
- **First step:** read HANDOFF §10i in full (the independence-measurement
  paragraph and the two "corrected the upstream plan" paragraphs) before touching
  anything; re-derive each of the five repros against current pyte master yourself
  rather than trusting the prior session's numbers, since pyte master moves.
- **Verify:** each patch applies cleanly to an untouched `upstream/master`
  worktree and pyte's own test suite stays green (no new failures) after
  applying it; SmartCLI's own capability-detection tests
  (`_PYTE_HAS_ALT`, `_PYTE_DCH_HANDLES_WIDE` in `smartcli_core/screen_model.py`)
  must keep passing against BOTH stock pyte and the patched checkout — a
  one-sided run cannot tell "correct" from "the branch that happens to run
  here" (this project's own §10i mutation-testing note: hardcoding the DCH
  probe to a fixed value is only ever observable under one of the two pytes,
  never both).
- **Effort:** M

### A0-DOCKER-RUN. Make CI actually RUN the image, not just build it  [S]
- **Goal:** `docker.yml` builds and pushes but never runs the result
  (`grep -nE "run:|docker run" .github/workflows/docker.yml` returns nothing). Add a
  step that starts the built image with no arguments and speaks one JSON-RPC
  `initialize` + `tools/list` over stdio, asserting `serverInfo.version` equals the
  package version and that 14 tools come back.
- **Why it matters:** that is exactly how an MCP directory validates a server, and
  it is the check that would have caught the v0.2.0 bug where the image defaulted to
  `CMD ["fx gallery"]` — a directory would have received animation frames and scored
  the server broken. The `CMD ["mcp"]` fix has shipped in two releases now with **no
  automated test ever running it**; the only evidence is that the build is green,
  which proves nothing about what the image does when started.
- **Partial evidence as of 2026-08-06 (v0.2.1):** verified by RECONSTRUCTING the
  image layout rather than running a container (no Docker on this host) — copied
  `smartcli_core/` + `skills/` into a scratch dir, set the Dockerfile's exact
  `PYTHONPATH`, installed only `requirements.txt` (not the package, matching the
  image), and spoke JSON-RPC from outside the repo: `serverInfo` = 0.2.1, 14 tools,
  `snapshot`'s description mentions `alt_screen`. So the bootstrap path resolves and
  the entrypoint's `mcp` branch is sound. **This is not a container run** — it does
  not cover the base image, the `ENTRYPOINT` script itself, or anything the
  Dockerfile's own layers do.
- **First step:** in `docker.yml`, build with `load: true` for the smoke step (a
  pushed multi-arch manifest cannot be run directly), then
  `printf '<initialize>\n<initialized>\n<tools/list>\n' | docker run -i --rm <tag>`
  and parse the replies. Note the server needs the `notifications/initialized`
  message between the two requests or `tools/list` never answers — that cost a round
  when probing it by hand.
- **Verify:** the step fails if `CMD` is changed back to a demo, and fails if
  `serverInfo` reports the SDK's version instead of ours (both are real bugs this
  project has already had).
- **Effort:** S

### ~~A0-CLI-RESIZE. Expose resize as a CLI subcommand~~  [DONE 2026-08-06]
- **Result:** `tui.py resize --id <SID> --cols N --rows M` (plus `--json`). Validation
  deliberately stays in the daemon, which converts `_validate_size`'s `SystemExit` into
  an error REPLY — `SystemExit` is a `BaseException` and would otherwise sail through the
  per-connection `except Exception` guard and tear down the live session. `_call` turns
  that reply back into `SystemExit` for the CLI caller, matching every other verb here.
- **Verified on a live PTY** (one session at a time, zero leaks after each): 80x24 →
  `resize 100x30` reports `[screen 30x100]`; `--json` returns
  `{"ok": true, "sid": ..., "cols": 90, "rows": 28}`; `99999x99999` exits 1 with the
  daemon's limits message and `alive` still reports alive afterwards — a rejected size
  does not kill the session. No new PTY proof was needed for the resize itself:
  `PtySession.resize` already drives `TIOCSWINSZ` / `setwinsize` and the pyte grid
  together. SKILL.md's MCP-only caveat removed and `resize` added to both verb lists.
- **Still open (was an aside on this task):** `--theme` fallback for unthemed `fx show`
  segments — SKILL.md documents current behavior honestly; making the flag real is a
  small cli.py change.

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

### ~~A4. pexpect-style multi-marker wait (wait-any returning which matched)~~  [DONE 2026-07-15, v0.1.8]
- **Result:** `wait_any(patterns) -> (index, snapshot)` shipped in v0.1.8 across
  readiness.py + `PtySession.wait_any` + drive-tui daemon/CLI (`wait-any`,
  `--pattern`/`--stdin`)/one-shot-run/MCP. `-1` on timeout, earliest-in-list wins a
  same-poll tie, empty list short-circuits. `tests/test_wait_any.py` (mutation-
  verified), independent adversarial review clean, live-PTY confirmed. Made under
  the smartcli_core DO-NOT-MODIFY exception. `wait_change` (single-marker) shipped
  earlier in v0.1.6. *(original task below, for reference)*
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

### ~~A7. Ship spectrum-bars + cbonsai effects in cmd-art~~  [DONE 2026-07-15, v0.1.7]
- **Result:** both shipped as pure-frame effects. `skills/cmd-art/fx/effects/spectrum_bars.py`
  = cava's log-spaced bins + gravity-fall/integral smoothing + eighth-block
  (`U+2581..U+2588`) sub-cell render over a synthesized moving-sine signal
  (aliases `spectrum`/`bars`, viridis theme). `skills/cmd-art/fx/effects/cbonsai.py`
  = the [[procedural-branching]] stochastic turtle (lifeStart 32, multiplier 5,
  five branch types, cooldown-gated shoots); a seeded RNG generates the whole tree
  once as an ordered draw-event list and each frame reveals the "grown" prefix, so
  it animates AND is deterministic (matrix-green theme). Catalog 28→30. Both pass
  `test_fx_contract.py` (30 effects x 6 sizes x 5 contracts = 150/150) + the anti-drift
  `test_doc_counts` gate (9 shipping docs bumped 28→30). *(original task below)*
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

### ~~A5. Golden-frame snapshot regression test for tui-ui~~  [DONE 2026-07-15, v0.1.4]
- **Result:** tests/test_golden_frames.py + tests/golden/*.txt — every widget rendered
  to a deterministic frame, diffed vs a committed baseline (`--update` to regen),
  rendered twice to reject non-determinism, skips widgets whose optional dep is
  absent (banner→pyfiglet). In run_all + coverage subset. *(original task below)*
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

### A6. Shared easing.py + Gradient builder for cmd-art  [M] — easing DONE 2026-07-15 (v0.1.6)
- **Result:** `skills/cmd-art/fx/easing.py` — 14 canonical Penner easings, used by the
  new text-intro effects. The `Gradient(stops,steps,direction)` builder was NOT
  separately factored out (theme.gradient covers most call sites); do it only if a
  real duplication pain shows up. *(original task below)*
- **Goal:** factor the repeated easing curves and gradient math into reusable
  `easing.py` and a `Gradient(stops, steps, direction)` builder.
- **Why it matters:** removes duplication across the 30 effects, makes new effects (A7)
  cheaper, and is a clean public sub-API.
- **First step:** grep skills/cmd-art/fx/ for inline lerp/ease/gradient math to find
  the duplication; design the smallest API that covers existing call sites; refactor
  one effect to use it as a proof.
- **Verify:** tests/test_fx_contract.py must still produce byte-identical frames for
  every unchanged effect (the contract is exact — any drift is a real regression to
  investigate, not to rebaseline blindly). Run verify_fx.py exit-0.
- **Effort:** M

### ~~A3. MCP-server wrapper over the drive-tui daemon verb surface~~  [DONE 2026-07-15, v0.1.4]
- **Result:** `skills/drive-tui/scripts/mcp_server.py` (FastMCP), now **14** annotated
  tools (wait_change/wait_any/wait_visual_change joined over v0.1.6–v0.2.0) reusing
  tui.py's client so the per-session token auto-attaches. MCP Registry listing is
  **LIVE** (`io.github.dwgx/smartcli`) and re-publish on release is **automated**
  (publish.yml `publish-mcp` OIDC job — no human step left). Since v0.2.0 the wheel
  ships `smartcli-mcp`/`smartcli-toolkit` entry points and `mcp` is a required dep.
  Covered by tests/_mcp_probe.py (+ CI drive-smoke/package jobs). *(original task below)*
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

### A8. docs site + contributor onramp + coverage badge  [L] — MOSTLY DONE (2026-07-15)
- **Status:** **Read the Docs is LIVE** at https://smartcli.readthedocs.io/ (mkdocs via
  `.readthedocs.yaml` + `tools/build_docs.py`, which assembles docs/*.md from the
  canonical sources and rewrites repo-relative links to absolute GitHub URLs).
  `CONTRIBUTING.md` + `SECURITY.md` DONE (v0.1.4). Codecov badge live (~50% on the
  deterministic subset via tools/coverage_run.py). Still open: `TestPyPI`/`conda-forge`/
  `Homebrew` publishing channels (configs prepared; human steps in docs/PACKAGING-NOTES.md).
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
  The interactive drive-tui PTY probes + effort_selector stayed OUT of CI at the time.
  *(Update 2026-07-19, v0.2.0: the probes now DO run in CI, serially inside the
  bounded drive-smoke/package jobs; the matrix legs test py3.10/3.14.)*
- *(original task, for reference)* validate the POSIX backend in CI instead of by a
  manual SSH run to Debian 13 — now automated.

### ~~B-PyPI. PyPI Trusted-Publisher setup~~  [DONE 2026-07-13]
- **Status:** DONE and verified. Trusted Publisher registered on PyPI (owner `dwgx`,
  **repo `SmartCLI`** — GitHub repo name, not the `smartcli-toolkit` dist name; that
  mismatch was the original `invalid-publisher` failure) + `pypi` GitHub Environment
  created. A `workflow_dispatch` run (29245353129) went green: OIDC handshake succeeded,
  publish ran against `upload.pypi.org`. `skip-existing:true` added so re-runs are no-ops.
- **Releasing now:** bump the version everywhere, `git tag vX.Y.Z && git push origin vX.Y.Z`
  — publish.yml auto-uploads via OIDC, no stored token. (twine no longer needed; the old
  `--disable-progress-bar` note was only because twine's rich bar crashes on gbk.)

### ~~B-SEC. Revoke the leaked PyPI API token~~  [CLOSED 2026-07-27 — owner decision]
- **Status:** raised again on 2026-07-27 with the argument that OIDC publishing is now
  verified working (all three publish jobs green on the v0.2.0 tag), so the token has no
  remaining utility. **The owner decided not to revoke it.** That is their call to make;
  the decision is recorded here and this item is closed. **Do not keep re-raising it** —
  the standing "re-surface every session" instruction from earlier sessions is superseded.
- **If it ever matters again:** delete the token in PyPI account settings; the release
  path does not depend on it (publish.yml uses Trusted Publishing / OIDC, no stored
  secret). Residual risk is unauthorised uploads to the existing project if the token
  string is still recoverable from the old chat log.

### B-Skillhu. Retry external skill-publish CLIs  [S] (needs working external CLIs)
- **Goal:** publish/refresh on LobeHub / agentskillhub if their CLIs get fixed.
- **Why it matters:** the publish CLIs had real upstream bugs this session (spawn
  `start` ENOENT / IPv6-only callback / server 401) — not the project's fault. Skills
  are already live on skillhu.bz.
- **First step:** retry the publish CLI; if it still errors, log the exact error and
  move on — do not work around a broken external tool.
- **Verify:** the skill page reflects the current release version.
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

### ~~D1. Write RESEARCH-PROMPTS.md from the session's /deep-research anchor list~~  [DONE 2026-08-06]
- **Result:** `RESEARCH-PROMPTS.md`. Five anchors (conch, terminal-bench/Harbor, plotille,
  TTE, PyPI trusted publishing), each with a specific question, a **Last checked** line,
  and — the part that makes the file worth keeping — what a good answer would actually
  CHANGE in this backlog. Anchors whose answer changes nothing are named as such rather
  than padded: pexpect, Textual and pytest-textual-snapshot are recorded as already
  benchmarked with no open sub-question, so nobody re-runs them to re-confirm measured
  facts.
- **Notable:** it states the real cost of the "just add one more effect/widget" answers —
  a catalog bump has to clear `test_fx_contract`, move `verify_fx` 38/38 → 39/39, and
  update every count site `test_doc_counts` gates. That is the kind of thing that makes a
  research answer actionable instead of aspirational.
- **Claims spot-checked against disk before committing:** the TTE snapshot in
  `research/R1-effects-catalog.md` PART C (its frozen upstream catalog size @ HEAD
  `7a91dd9`), the publish.yml action pin (`pypa/gh-action-pypi-publish@release/v1`), and
  `braille_chart.py`'s existence.
- **Gate note:** `test_doc_counts` initially FAILED on this entry — it read TTE's upstream
  catalog size as an fx count and demanded 30. The gate was right to be suspicious of a
  bare effect number in a shipping doc, so the figure is named rather than written as a
  digit here. RESEARCH-PROMPTS.md itself passes: it discusses the fx catalog as 30→31.

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
   that must stay exit-0: verify_fx.py (38/38 = 30 effects + 8 fixed checks; known
   random-seconds flake — rerun once), _readme_literal.py, probe_pty_fx.py, tests/run_all.py.

6. **The smartcli_core modification rule.** smartcli_core was DO-NOT-MODIFY. Changes
   are now allowed ONLY with: (a) real-run-path verification, (b) independent
   adversarial review, and (c) no regression across the FULL recipe suite. Any core
   task above (A4, A3's daemon touches, B2 findings) is bound by all three.

7. **Keep research/cc-decompiled/ excluded.** It is gitignored and out of the release.
   Do not re-expose it; keep provenance wording neutral in all shipping files.



