# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

Product changes sitting on `main` and NOT in v0.2.2. `pip install smartcli-toolkit`
does not contain them.

### Fixed
- **One connection could stall the daemon for every other caller.** The accept loop
  was serial with the UNAUTHENTICATED transport read inline, so any local process
  could connect, send bytes with no newline, and head-of-line block every other
  caller — measured at ~18s of denial from nine held connections, repeatable and
  needing no credential. Now the accept thread only accepts, a per-connection reader
  performs the unauthenticated work (read, parse, constant-time token check) so a
  silent peer burns only its own 2s budget, and a single worker thread is the only
  thread that touches the session. Measured after: an authenticated request is served
  in 0.00s under the same attack. A previous release note described this as bounded
  30x but not fixed; it is now fixed.
- **A long wait blocked unrelated fast verbs.** A `wait-regex --timeout-ms 60000`
  occupied the session worker, so a concurrent `snapshot` waited behind it (8.00s,
  measured). `smartcli_core`'s four wait loops and `PtySession`'s six wait methods
  gained an optional `on_poll` hook, invoked in the idle gap **on the waiting
  thread**, so a fast verb is answered without a second thread ever entering the
  session — `PtySession` is not thread-safe (`visual_hash()` clears `screen.dirty`
  as a side effect, `pump()` is read-modify-write, `resize()` mutates four fields in
  sequence). Default `None`, so every existing caller behaves identically. On a live
  PTY: `snapshot` in 0.13s during a 20s `wait-regex`. A second LONG wait still queues
  behind the first — one session owns one PTY child, so that is inherent.
  `resize` is deliberately NOT answered mid-wait: it re-dimensions the pyte screen and
  therefore changes the content hash, which would make a caller blocked in
  `wait-change` conclude its own keystroke had landed.

### Added
- `tests/test_daemon_concurrency.py` — drives the real accept loop against a fake
  session (no PTY, no child process) and locks: an authenticated request is served
  while `listen` backlog + 1 silent peers hold connections; a 200 KB request spanning
  many `recv()` calls still succeeds; auth is still enforced with no screen leak; a
  fast verb is answered during a long wait; and session access provably stays on one
  thread. Suite is 44 entries.
- `tools/mcp_stdio_smoke.py`, run by `docker.yml` against the built image — the check
  an MCP directory performs (start the container with no arguments, speak JSON-RPC).
  The image had shipped with `CMD ["mcp"]` for three releases with no test ever
  running it.

### Changed
- `test_perf_contract` declines to measure timing ceilings when a tracer is attached
  (coverage runs it under one), because the number measured there describes the
  tracer. Raising the ceiling instead would have destroyed the 2000x regression window
  the gate exists to protect.
- `test_doc_counts` gates README's quoted `drive_vim` output against the example's
  `step()` literals, and the four localized READMEs gained the 30-second quickstart
  and the `drive_vim` comparison.

## [0.2.2] - 2026-08-09

A control-plane correctness release. The headline is that **`close` could delete a
live daemon's registry entry**, stranding a real PTY child while the very command
this project tells you to use for confirming cleanliness reported zero sessions.
Everything else here either closes a security bypass or makes a check capable of
failing; there are no new features.

### Fixed
- **`close` after a failed request deleted the registry entry of a LIVE daemon.**
  `_call` turns any transport failure — *including a plain timeout* — into a
  `SystemExit` telling the operator to run `close --id <sid>` "to clean up the stale
  entry", and `close` then unlinked the file unconditionally. But the daemon's accept
  loop is serial, so a busy daemon is indistinguishable from a dead one at the socket,
  and that file is the only store of both the capability token and the pid. The
  documented recovery could therefore leave a live daemon owning a running PTY child
  that was unreachable by protocol (token gone) and unfindable for a manual kill (pid
  gone) — while `close` printed `closed <sid>`, exited 0, and `list` reported zero
  sessions. Since this project's own guidance is to confirm "zero leaked sessions" with
  exactly that `list`, the check would have confirmed a lie. Death is now proven before
  deletion (`os.kill(pid, 0)` on POSIX, `OpenProcess` + `GetExitCodeProcess` on
  Windows, where signal 0 does not exist); `close` refuses and exits 1 with the pid, and
  the new `--force` overrides it while saying in its help what that costs.
- **`--env` could re-inject the session token on Windows.** The control-plane guard was
  `key.startswith("SMARTCLI_TUI_")` — an exact-case check — while Windows environment
  names are case-insensitive and CPython upcases keys on assignment. So
  `--env smartcli_tui_token=…` passed validation and `os.environ.update()` installed it
  **as `SMARTCLI_TUI_TOKEN`** in the driven child: precisely the capability the daemon
  pops so a child cannot control its own session. Now compared uppercased
  unconditionally, with the deny-list widened to `SMARTCLI_ROOT`,
  `SMARTCLI_MAX_SESSIONS` and `SMARTCLI_AUTO_INSTALL`. Your own variable names are
  unaffected.
- **An unauthenticated peer could head-of-line block the daemon for 60s per
  connection.** `conn.settimeout(60.0)` was set *before* the token check, so any local
  process could connect, send bytes with no newline, and stall every other caller with
  no credential at all; with `listen(8)`, nine such connections starve the owner. The
  budget is now split — 2s pre-auth, re-armed against a **fixed deadline** so a peer
  dribbling bytes cannot renew it, and 60s only for an authenticated caller's reply.
  **Measured: nine held connections went from 540s to 18s. That is a 30× reduction and
  NOT a fix** — the residual is inherent to the serial accept loop. Per-connection
  threading is the real answer and is deliberately not attempted here, because
  `PtySession` is not thread-safe; `SECURITY.md` now documents the residual instead of
  claiming the bound prevents it.
- **A non-dict JSON request was answered with an interpreter exception, pre-auth.**
  `[1,2,3]` reached the handler and died on `req.get()`; `AttributeError` was not in the
  connection guard's tuple, so an unauthenticated peer received
  `{"error": "AttributeError: …"}` with no `ok` field, unlike every other reply on the
  socket. Rejected explicitly now, before dispatch.
- **`examples/drive_vim.py` sent five keystrokes blind and did not set `TERM`.** The
  mode changes (`Escape`, `G`, `o`) were issued back to back with nothing between them —
  the blind send this project exists to argue against — so under load the keystrokes
  were swallowed and nothing was inserted. It now confirms `-- INSERT --` before typing,
  which proves both `G` and `o` landed. And without a `TERM` vim never enters the
  alternate screen nor saves the file, so two of the six steps failed for the absence of
  an environment variable rather than for anything in the code; it is set explicitly now.

### Changed
- **`tests/run_all.py` no longer reports success for a gate that was deleted.** 29 of 43
  entries were `optional=True`, including 20 committed deterministic gates, so renaming
  or removing any of them was a green SKIP — while the runner is documented as
  pass-or-fail. A missing file that git tracks is now a FAIL regardless of the flag,
  which is derived rather than hand-maintained and so covers a new gate the moment it is
  committed. Entries that depend on an external binary (tmux, vim, less) still skip
  themselves internally, so a green run on a host lacking those covers less.
- **`run_all.py` retains and prints child output on failure** (last 40 lines), and
  surfaces internal `SKIP:` lines even on a PASS. Previously a suite failure was
  reportable only as an exit code and had to be re-run standalone — exactly the case
  where an order- or load-dependent failure does not reproduce.
- **Anti-drift gates that could not fail, fixed.** `test_fx_contract`'s exact-width
  contract was gated on a predicate that evaluated the very condition it asserts, so any
  effect *violating* it was reclassified "sparse" and passed; the classification is now
  a frozen 24-name set with a second check so it cannot rot in either direction, and
  skipped contracts are no longer counted as passes (the summary reads
  `174/174 passed, 6 skipped`, where "150/150" had included six checks that never ran).
  `test_doc_counts` exempted its own authoritative counts line by inferring intent from
  nearby words — exemption is now an explicit `doc-counts:ignore` marker — and it now
  gates the recipe count it had only been printing. The dependency gate's Homebrew
  half ran a pip-shaped regex over a Ruby formula and could not match under any
  circumstances; each draft is now parsed in its own syntax.
- **`tests/_tmux_launcher_probe.py` read the new pane the instant the launcher
  returned.** The single-effect branch ends in `exec tmux split-window`, which returns
  when the pane *exists* — measured, the first frame arrives ~0.5s later — so it
  sampled a legitimately blank screen. It now polls for the condition with a bound. It
  also sets `TERM`, without which tmux refuses to attach a client and two more checks
  failed for a rig reason.

### Notes
- No API or behaviour change for library users beyond `close`'s new refusal (and the
  `--force` escape hatch). `smartcli_core`'s public surface is unchanged.
- `tests/run_all.py` is 43/43 on macOS with no FAIL, no SKIP and no rerun.

## [0.2.1] - 2026-08-06

A perception-correctness release. The headline is not a feature: **an upgrade of
`pyte` alone could have blanked the primary screen for every 0.2.0 user**, and
this release defuses that before it ships upstream. Everything else is the
alternate-screen work reaching the surfaces an agent actually reads, plus five
more measured emulation fixes.

### Fixed
- **Two dependency timebombs, defused by capability detection rather than a
  version pin.** `pyte>=0.8.1` is an open range in both `requirements.txt` and
  `pyproject.toml`, so the day upstream ships its own alternate screen
  ([selectel/pyte#212](https://github.com/selectel/pyte/pull/212), which this
  project authored), subclass *and* base class would both switch — restoring a
  BLANK primary screen on every full-screen program exit. Measured: `['', '', '']`.
  The second is `delete_characters` widening DCH over a wide glyph; against a pyte
  that does the same, `中x` + CR + DCH went from `"x"` to `""`, silently eating a
  character. Both now ask the installed pyte what it can do (`_PYTE_HAS_ALT` via
  `hasattr`, `_PYTE_DCH_HANDLES_WIDE` via a one-shot behavioural probe). A cap
  would have kept users off the upstream fix forever and needed revising every
  release. Verified under BOTH stock 0.8.2 and a patched checkout, because a
  one-sided test cannot distinguish "correct" from "the branch that happens to run
  here".
- **`CUD` (cursor down) was missing its DECSTBM override.** `index()` and
  `cursor_up()` were overridden for exactly this defect class; their mirror was
  not, so from below a scroll region `ESC[3;6r ESC[8;1H ESC[1B` landed on row 6
  where tmux and GNU screen both give row 9. Found by asking why the third
  override was absent — a gap a generative fuzzer cannot surface, because it
  generates sequences, not absences.
- **`DL` (delete lines) left the rows it vacated populated** instead of blanking
  them.
- **Resizing while on the alternate screen** clipped the saved primary screen
  correctly, restored the pen along with the cursor, and left the alternate screen
  on RIS.
- **Mode 1048 no longer collides with 1049's save slot.** Adding 1048 initially
  routed it through the same `_alt_savepoint` as 1049, reintroducing the defect
  the dedicated slot was created for one commit earlier.
- **The MCP `snapshot` tool silently dropped `alt_screen`.** The daemon has always
  sent it and the CLI has always printed it, so MCP clients — the surface this
  project promotes hardest — were the only ones that could not tell whether a
  full-screen program owned the screen. That is precisely the blindness the
  alternate-screen work exists to remove.
- **The mypy gate was checking a state that does not exist.** CI installed only
  `ruff` and `mypy`, so `pyte` was absent, `ignore_missing_imports` degraded
  `pyte.Screen` to `Any`, and a correct `type: ignore` was reported as unused
  while two genuine errors present since 0.2.0 went unseen. The gate now installs
  the runtime dependencies and is mutation-verified to still bite.
- `examples/drive_vim.py` runs from a source checkout, not only an install, and
  the driven test fixtures no longer `import msvcrt` unconditionally — that alone
  was four of the suite's failures on POSIX.

### Added
- **Private mode 1048** (cursor save/restore without the buffer switch), with its
  weaker evidence level stated in the code: xterm defines it, but neither
  reference emulator implements it, so there is no ground truth to check against.
- **`alt_screen` on every surface an agent reads** — `ScreenModel`, `Snapshot`,
  the `to_text()` header (it leads the flags, because it changes what an action
  MEANS), the JSON hints, and every drive-tui daemon reply. Previously reachable
  only by poking the underlying pyte object.
- **`tui.py resize`** — the daemon and MCP had supported resize since the control
  plane was hardened; the CLI had no verb. A rejected size returns an error and
  leaves the session alive.
- `tests/test_terminal_fidelity.py` locks, including DECCOLM against the alternate
  screen, and a cross-platform `getwch()` (`tests/_kbd.py`) that enters raw mode
  once rather than per keystroke — otherwise an `ESC [ A` gets split across three
  separate raw-mode entries.
- `RESEARCH-PROMPTS.md` — the calibrated research anchors, each recording what a
  good answer would actually change in the backlog.
- CLI coverage for `resize` in `tests/_tui_cli_probe.py`, including the check that
  a *rejected* size leaves the session alive. `_validate_size` raises `SystemExit`,
  a `BaseException` that would otherwise pass straight through the daemon's
  per-connection `except Exception` and tear the session down; nothing had pinned
  that from the CLI side.

### Fixed after an adversarial self-review
The release was reviewed before tagging. Five real defects came back, all
introduced by this release's own work, and all fixed here — **four found by
independent adversarial agents, and the last (the version contradictions) found by
reading back over the release commit rather than by any agent or gate**.

To be precise about what that does and does not claim: the *defects* were found
independently, but the *fixes written in response* were verified by the author only.
One of them touches `smartcli_core`, whose policy requires independent adversarial
review before a change ships. That review happened AFTER the tag, not before, so the
policy was not met for this release. It has since been run and the fix held up; the
gap is recorded rather than smoothed over.
- **The lint-gate fix would have re-broken the gate from the other direction.** The
  `type: ignore[misc]` on `super().alternate_screen` is correct only while pyte
  *lacks* the attribute; the day pyte ships it, `warn_unused_ignores` fails on an
  ignore that has become unused. Reproduced by injecting the attribute. Replaced
  with `getattr(super(), "alternate_screen", False)`, which needs no ignore in
  either state — a version-dependent ignore would have needed revising on the very
  release that makes the capability check unnecessary.
- **`resize` was invisible in `tui.py --help`**: the subparser metavar is a
  hand-maintained string and the new verb was never added to it.
- **A rejected resize printed `error: error: ...`** — the daemon stored
  `_validate_size`'s already-prefixed message while every other daemon reply
  stores a bare one for `_call` to prefix once.
- **The HANDOFF continuation prompt listed six portable pyte defects including
  IL/DL cursor column.** It is five, and IL/DL is explicitly excluded — filing it
  upstream would have been rejected, since pyte matches the standard there and
  this project is the deviation. That prompt is what a fresh session pastes and
  follows, so the error was one step from becoming a bad upstream patch.
- **Two version contradictions inside HANDOFF.md** — a `VERSION = 0.2.0` line nine
  lines below the 0.2.1 banner, and a "read this first" pointer still routing to
  work from two rounds earlier. The ten-site version gate cannot see prose.

### Changed
- `tests/run_all.py` is **43/43 on macOS**, the first full green on this host. The
  four prior failures were platform gaps in test fixtures, not product bugs — and
  with four known failures a genuine regression was indistinguishable from the
  noise floor.
- Documented as a deliberate CHOICE rather than a bug: **IL/DL keep the cursor
  column.** An independent re-check found pyte matches xterm, vte and the DEC VT
  reference here; tmux, GNU screen, urxvt, konsole and linuxvc keep the column as
  this project does. Five implementations against two, so the behaviour stays —
  but it must not be upstreamed, and the docstring that had asserted "real
  terminals keep the column" now records the full split.
- **GitHub Actions pins brought current** — 27 pins across 9 workflows
  (`checkout` v4→v7, `setup-python` v5→v7, `deploy-pages` v4→v5,
  `configure-pages` v5→v6, `upload-pages-artifact` v3→v5, `login-action` v3→v4,
  `codeql-action` v3→v4), clearing a seven-PR Dependabot backlog and the Node 20
  deprecation warning on every run. The breaking changes were read rather than
  assumed: `checkout` v7 blocks fork-PR checkout under `pull_request_target` /
  `workflow_run` and `setup-python` v7 removed the `pip-install` input — this repo
  uses neither. `mkdocs-material` docs-build floor raised to 9.7.7.

## [0.2.0] - 2026-07-27

Security hardening of the drive-tui control plane, an installable MCP surface,
and — from a differential-testing campaign against real terminals — **twelve
screen-emulation bugs fixed**, including one that made every full-screen TUI
unreadable. See HANDOFF §10 for the full arc.

### Added
- Installable `smartcli-tui`, `smartcli-mcp`, and registry-compatible
  `smartcli-toolkit` console commands; the wheel now includes the drive/MCP
  implementation instead of shipping only `smartcli_core`.
- `cwd` and repeated `KEY=VALUE` environment controls for persistent sessions,
  machine-readable start/list/close output, and structured MCP snapshots.
- `visual_hash` + `wait_visual_change` across core, daemon, CLI, one-shot steps,
  and MCP for attribute-only selection and cursor movement.
- **Alternate screen buffer support** (modes 1049/1047/47) with
  `ScreenModel.screen.alt_screen`. pyte implements none of these, so until now a
  full-screen program (vim, less, htop) painted its alternate screen on top of
  the main one and never restored it — an agent read a merged, impossible screen.
- **SGR sub-parameter tolerance** (ITU-T T.416 `:` syntax, e.g. `ESC[4:3m`,
  `ESC[38:2::R:G:Bm`), which pyte's parser aborted on, drawing the remainder of
  the sequence onto the grid as literal text. Neovim, kitty and delta emit it.
- Differential test suite against real terminals: `_diff_tmux_pyte.py` (35
  curated cases vs tmux), `_diff_two_refs.py` (tmux AND GNU screen; ground truth
  only where both agree), `_diff_fuzz_tmux.py` (generative VT fuzz),
  `_tmux_launcher_probe.py`, plus deterministic locks in
  `test_terminal_fidelity.py`.
- `test_perf_contract.py` — the first performance test in the suite — and
  `test_readiness_properties.py` (Hypothesis invariants for the wait primitives).
- `test_version_sync.py`, a ten-site version anti-drift gate; widget-count and
  dev-box-path gates in `test_doc_counts.py`.
- Cross-platform package/MCP smoke jobs and Python 3.10/3.14 CI boundaries.
- OIDC MCP Registry publishing after a successful PyPI tag release.

### Fixed
- Explicit `wait_change` baseline hashes are integers end to end; CLI/MCP calls
  no longer report an immediate false change because of a string/int mismatch.
- Session ids can no longer traverse outside the registry directory, registry
  writes refuse symlinks on POSIX, and controlled children no longer inherit
  the daemon capability token.
- Detached session count is bounded (8 by default, configurable up to 128),
  stale close actually removes its registry entry, and MCP close is idempotent.
- An out-of-range `resize` no longer kills the daemon and its live session
  (`SystemExit` escaped the per-connection guard).
- **Screen-emulation fidelity**, each divergence measured against real tmux and,
  where it could arbitrate, GNU screen: IL/DL no longer home the cursor column;
  IL with count > 1 no longer leaves buffer holes that make a later DL delete the
  wrong row; half-overwriting a wide glyph blanks it instead of dropping the
  incoming character; DCH removes both cells of a wide glyph; NEL returns to
  column 0; a cursor outside a DECSTBM region is neither dragged into it nor
  clamped by it; a two-column glyph with one column left wraps whole; an
  overwritten wide base leaves no orphaned stub; and a zero-width joiner or
  variation selector no longer truncates the rest of the write (`"MENU ♀️
  Settings  Quit"` used to be perceived as `"MENU ♀"`).
- `visual_hash` is incremental — 16.6 ms → 0.008 ms per idle poll on a 300x100
  screen, where it previously consumed 55% of the 30 ms polling budget.
- `fx-popup.sh` refuses cleanly when no tmux client is attached instead of
  leaking tmux's `no current client` with a non-zero exit.
- Real-session probes use the running Python interpreter with platform-correct
  quoting instead of assuming a `python` command exists on PATH (not true on
  current macOS installations).

### Changed
- Python 3.10 is now the supported floor because the packaged MCP surface uses
  modern type syntax; the MCP SDK is a required package dependency so `uvx`
  launch from the official MCP Registry works without extra flags.

## [0.1.8] - 2026-07-15

Two capability additions and a benchmark adapter, each with an independent
adversarial review pass. Closes the last of the pexpect feature gap, adds a true
graphics protocol, and makes "drives TUIs" a runnable Terminal-Bench score.

### Added
- **`wait_any` — pexpect `expect([...])` multi-marker wait** (smartcli_core, made
  under the DO-NOT-MODIFY exception: real-run-path + independent adversarial review
  + full-suite green). Race several regexes and learn WHICH matched first: returns
  `(index, snapshot)`, `-1` on timeout, earliest-in-list wins a same-poll tie, empty
  list short-circuits. In `readiness.py` + `PtySession.wait_any` + the drive-tui
  daemon action, CLI (`wait-any`, `--pattern`/`--stdin`), one-shot run step, and MCP
  tool. `tests/test_wait_any.py` (mutation-verified); live-PTY confirmed.
- **Sixel graphics output** (tui-ui, pure addition). `ui/sixel.py` encodes an RGB
  pixel grid — including a `SubcellRaster.px` buffer via `raster_to_sixel` — to a
  Sixel DCS string for terminals that support it (Windows Terminal >=1.22, xterm,
  WezTerm, mlterm): band-based encoding, 6x6x6 cube quantization, RLE, transparent
  zero-bits, `char=0x3F+mask` (bit0=top), 0..100 color scaling. Plus `supports_sixel`
  (DA1 probe) and `python -m ui sixel [image] [--probe]`. Wire format locked to the
  VT330/340 spec by `tests/test_sixel.py` (incl. the DEC "HI" bit-math + a round-trip
  decode), mutation-verified, adversarially reviewed. The sub-cell glyph path
  (half/quad/sextant/braille) still works everywhere; sixel is the upgrade where
  available.
- **Terminal-Bench agent adapter** (`smartcli_tbench/`, not shipped in the wheel).
  A classic-`terminal-bench` `BaseAgent` that drives the harness's tmux session with
  SmartCLI's perceive→decide→act→wait→confirm loop and its wait primitives
  reimplemented over `capture_pane()` — the reliability the stock fire-and-forget
  `naive` agent lacks. `driver.py`/`loop.py` are pure and unit-tested without Docker/
  LLM (`tests/test_tbench_adapter.py`, adversarially reviewed — a stale-screen
  `min_wait` guard was added from that review); `agent.py` imports terminal-bench
  lazily. New `.github/workflows/bench.yml` runs the scored subset on CI ubuntu-latest
  (oracle smoke test + `SmartCliAgent`, gated on an LLM API-key secret).

### Changed
- CI gains deterministic gates for `test_wait_any`, `test_sixel`, and
  `test_tbench_adapter`; all three added to `run_all.py`. drive-tui + tui-ui SKILL.md
  document the new verbs/commands. (Stale "19 effects" CI comments corrected to 30.)

## [0.1.7] - 2026-07-15

The last two "knowledge → effect" ports, an MCP Registry listing, and a
docs/website accuracy pass. Catalog grows to 30 effects.

### Added
- **Two new fx effects** (30 total): `spectrum_bars` — an audio-style spectrum
  meter over a synthesized signal, faithful to cava's pipeline (log-spaced bins,
  gravity-fall + integral smoothing, eighth-block `U+2581..U+2588` sub-cell
  vertical resolution; aliases `spectrum`/`bars`) — and `cbonsai` — a procedural
  ASCII bonsai grown by a stochastic branching turtle (the cbonsai recursion:
  lifeStart 32, multiplier 5, five branch types, cooldown-gated side shoots). The
  whole tree is generated once with a seeded RNG as an ordered draw-event list and
  each frame reveals the "grown" prefix, so it animates and is fully deterministic.
  Both ship as pure frame producers and pass the frame contract at all sizes.
- **Official MCP Registry listing** — `io.github.dwgx/smartcli` is now published
  on `registry.modelcontextprotocol.io`, so MCP clients (Claude / Cursor / VS Code)
  and aggregators (Smithery / Glama / MCP.so) auto-discover the drive-tui server.

### Changed
- Docs + showcase site reconciled to the 30-effect catalog (READMEs in all five
  languages, both SKILL/USAGE, the site's effect-count stat across all five
  localized pages, and the anti-drift `test_doc_counts` gate).
- `server.json` `description` trimmed to the registry's 100-char limit.
- `.gitattributes` now marks the `docs/site` sources (HTML/JS/CSS) as
  `linguist-detectable` and the localized translations / vendored core as
  generated/vendored, so GitHub's language bar reflects the real HTML+JS+Python
  mix instead of reading ~99% Python.

## [0.1.6] - 2026-07-15

Six new "god-tier" effects, two new widgets, a rendering-quality pass, a new
drive-tui wait primitive, and a website upgrade — all through a two-reviewer
code-review pass that caught and fixed a high-severity bug before release.

### Added
- **Six new fx effects** (28 total): three noise-composition **field** effects —
  `flames` (rising domain-warped heat convection + physical black-body color),
  `water` (sum-of-sines swell + caustic net), `nebula` (domain-warped gas
  filaments + multi-color mixing + stars) — and three **TTE-style text intros**
  — `text_flyin`, `text_converge`, `text_decrypt` — built on a new TextEffect
  base and a shared `easing.py` (14 canonical easings). Fractal effects
  (`julia`/`mandelbrot`) gained smooth/continuous iteration coloring; `perlin`
  gained fBm. Noise techniques (domain warping, ridged noise, black-body ramp)
  live in a shared `_noiselib`.
- **Two new tui-ui widgets** (17 total): `FuzzyFilterList` (fzf-style subsequence
  fuzzy filter with match highlighting) and `PreviewPane` (its companion content
  preview).
- **`sextant` sub-cell blitter** (2x3, +50% vertical resolution over quad) and
  **OKLab perceptual color distance** for color clustering (chafa's quality
  lever).
- **`wait_change`** in drive-tui (CLI / MCP / daemon): block until the screen
  content changes — the precise "did my action land?" primitive.
- Website playground shows a copy-able `python -m fx play <effect>` command.

### Fixed
- **sextant glyph mapping** was wrong for 42/62 masks (the U+1FB00 block omits
  the left/right-column patterns, which are the half blocks U+258C/U+2590) —
  found in review, rebuilt from the Unicode names, now asserted exactly.
- OKLab color distance no longer crashes on out-of-range/negative channels.
- `perlin` noise uses `math.floor` (not truncation), fixing negative-coordinate
  seams the field effects hit constantly.

## [0.1.5] - 2026-07-15

Three new effects, a device-query fix in the core, diagnostics, width knobs, MCP
tool annotations, and a knowledge-graph expansion.

### Added
- **Three new fx effects** (22 total), implemented from the knowledge-graph
  formulas: `julia` (animated escape-time fractal with **smooth/continuous
  iteration coloring** — no concentric banding), `mandelbrot` (infinite zoom,
  same smooth coloring), and `perlin` (Ken Perlin's improved gradient noise as a
  flowing **fBm** field of 4 octaves).
- **`python -m smartcli_core`** — environment diagnostics (OS, Python, terminal,
  PTY backend, dependency versions) to paste into bug reports.
- **MCP server** now declares standard tool annotations (readOnly / destructive
  / idempotent / open-world) on all 11 tools, and a `server.json` is prepared for
  listing on the official MCP Registry.
- **Knowledge graph**: notes for `solarsystem` and `sphere`, plus a
  `choosing-an-effect` decision guide that maps "I want to show X" to a
  direction, formula, and shipped effect.
- `char_width` / `width` gain optional `unicode_version` and `ambiguous_wide`
  knobs (defaults unchanged) so callers can pin width to their terminal.

### Fixed
- **`smartcli_core` device queries (DSR-CPR / DA)** — a driven program that
  emitted `ESC[6n` / `ESC[c` and synchronously waited for the reply could stall
  or degrade, because nothing answered. `PtySession.pump()` now writes back the
  reply pyte generates from its own cursor/attr state (touched the core under the
  DO-NOT-MODIFY exception, with adversarial review + full-suite verification).
- **`fx random`** no longer picks an effect that renders statically under its
  defaults (`text3d`), which was the source of the `verify_fx` `random` flake.
- Read-the-Docs site: repo-relative links (the README language switcher) are
  rewritten to absolute GitHub URLs, so localized-README links no longer 404.

## [0.1.4] - 2026-07-15

New MCP server (the biggest adoption lever in the backlog), a real fx bug fix, a
golden-frame regression suite for tui-ui, multi-process coverage, and the
contributor onramp.

### Added
- **MCP server over the drive-tui daemon** (`skills/drive-tui/scripts/mcp_server.py`,
  `pip install "smartcli-toolkit[mcp]"`). Exposes the daemon's verb surface as 11
  MCP tools (`start`, `list_sessions`, `snapshot`, `send_text`, `send_line`,
  `send_keys`, `wait_regex`, `wait_ready`, `alive`, `resize`, `close`) so any MCP
  client can drive interactive TUIs. It reuses the CLI's client layer, so the
  per-session capability token is attached automatically and no verb is exposed
  unauthenticated. Covered end-to-end by `tests/_mcp_probe.py`.
- **Golden-frame snapshot regression for tui-ui** (`tests/test_golden_frames.py`
  + `tests/golden/`). Every widget is rendered to a deterministic frame and
  diffed against a committed baseline (`--update` to regenerate); locks all 15
  widgets against silent visual regressions.
- **Multi-process test coverage** (`tools/coverage_run.py` + `.coveragerc` +
  `sitecustomize.py`) over the script-style suite, wired into CI with a Codecov
  upload. Measures the deterministic, instrument-friendly gates.
- **Contributor onramp**: `CONTRIBUTING.md`, `SECURITY.md`, and a Read-the-Docs
  config (`.readthedocs.yaml` + `tools/build_docs.py`) that assembles the mkdocs
  site from the canonical sources.

### Fixed
- **`fx random` could pick a static effect** (`text3d`, whose `animated` class
  flag is True but whose `is_animated(defaults)` is False). It now selects only
  effects that actually animate under their defaults — matching the "play a
  random effect" promise and removing the `verify_fx` `random --seconds 1` flake
  at its source. `verify_fx`'s assertion was also broadened as defense-in-depth.

## [0.1.3] - 2026-07-14

Documentation accuracy, anti-drift hardening, and test-suite coverage. No
`smartcli_core` code changes — the published package is byte-for-byte 0.1.2; this
release re-cuts it alongside the repo-consistency and doc fixes below.

### Fixed
- **Localized READMEs drifted from the code.** The four i18n READMEs
  (`zh-Hans` / `zh-Hant` / `ja` / `ko`) stated **18 effects** and omitted
  `solarsystem` in their feature paragraphs while the English README and their own
  quick-start/tree already said 19. Corrected all four to **19 effects** with
  `solarsystem` listed.
- **Anti-drift gate was blind to CJK phrasings.** `tests/test_doc_counts.py` only
  matched the English `"N effects"` form, so the localized drift above slipped
  past it. It now also matches the CJK unit phrasings
  (`种效果` / `種效果` / `種のエフェクト` / `개 이펙트`) and forces UTF-8 stdout so it
  runs standalone on a legacy Windows codepage. Mutation-verified: it fails on the
  pre-fix READMEs and passes after.

### Added
- `tests/_tui_cli_probe.py` (drive-tui CLI end-to-end + per-session token auth) is
  now wired into the unified `tests/run_all.py` runner.

### Changed
- Website hero de-branded: the static `demo.svg` animation and the `app.js`
  carousel scenario now use a generic agent CLI placeholder instead of a specific
  vendor's branding (the three-scenario carousel is unchanged).
- `HANDOFF.md` / `NEXT-STEPS.md` reconciled with the shipped state: 3-OS CI matrix
  (was Windows-only), 8 workflows, video proof reels, and the daemon-hardening work.

## [0.1.2] - 2026-07-11

Correctness fixes found by a deep review + mutation-testing pass, each with a
repro and a regression-lock test (all independently re-verified for drift).

### Fixed
- **`smartcli_core` readiness (#1)** — `wait_ready`/`wait_until_stable` could
  declare STABLE on a never-painted blank screen during a startup quiet-gap.
  Added an optional `blank_hash` gate (default off = old behavior); `PtySession`
  passes its blank baseline so a blank+no-output screen TIMEOUTs instead of
  falsely settling, while a drawn static screen still settles.
- **`smartcli_core` docs (#2)** — the quickstart marker `r">>> $"` can never
  match (pyte space-pads lines); examples now use unanchored `r">>> "`.
- **`smartcli_core` PTY backend (#4)** — `WinptyBackend.spawn` now resets its
  queue/EOF/reader so a re-used backend can't inherit a stale EOF sentinel or a
  latched `_eof`.
- **Degenerate-input crashes** in skill code: `field.Ripple` (wavelength 0,
  falloff 0, empty palette), `SliderTrack` (empty positions list),
  `BrailleChart` (non-finite series values), and `fx` `Param` int coercion
  (zero-padded `08`/`010` and `±`-signed based literals now parse; clean error
  message otherwise).

### Added
- Regression-lock tests: `test_readiness.py` (blank-gate + false-green hardening),
  `test_degenerate_inputs.py`, `test_fx_contract.py` (exact fx frame contract,
  18×6), a `box_junction` self-test, and a unified `tests/run_all.py` runner.

## [0.1.1] - 2026-07-11

Test coverage, release maturity, and metadata. No `smartcli_core` code changes.

### Added
- **Test coverage** for previously-uncovered paths: live end-to-end driving of the
  pager / form / wizard recipes (`_drive_probe6.py` + fixtures), deterministic
  virtual-clock unit tests for the readiness TIMEOUT/STABLE/MARKER/late-flush/min_wait
  paths (`test_readiness.py`), drive-tui CLI + per-session token-auth E2E
  (`_tui_cli_probe.py`), a `box_junction` engine self-test, and a unified
  `tests/run_all.py` runner.
- **PyPI Trusted Publishing (OIDC)** workflow (`.github/workflows/publish.yml`) —
  tokenless releases on tag push.
- **Packaging metadata** — trove classifiers, keywords, and `[project.urls]`.

### Changed
- Skill `SKILL.md` descriptions trimmed to ≤500 chars, made agent-neutral, and
  YAML-hardened for marketplace listings.

## [0.1.0] - 2026-07-08

Initial public release.

### Added
- **Shared core (`smartcli_core`)** — a pluggable PTY backend + `pyte` screen model +
  semantic snapshot + readiness sync (`pty_backend / screen_model / snapshot /
  readiness / session`). Not tmux-bound: Windows uses ConPTY via `pywinpty`, POSIX uses
  the stdlib `pty` backend. Exposes `PtySession` as the importable entry point.
- **`cmd-art` skill** — a frame-producer effect engine (`Effect` ABC + `@register`
  auto-discovery) with **18 effects** and **8 themes**, driven by `python -m fx`
  (`list / show / play / gallery / random`). `play` is bounded by default and restores
  the terminal via try/finally.
- **`drive-tui` skill** — drives interactive terminal programs through a PTY via a
  perceive → decide → act → wait → confirm loop. Thin CLI (`scripts/tui.py`) with a
  persistent detached session and a one-shot `run` mode, plus an importable pattern
  library of **8 recipes** (repl, menu_select, pager, search_filter, confirm, form,
  progress, wizard) with fault-isolated discovery.
- **`tui-ui` skill** — a web-like, cell-accurate terminal layout engine emitting
  tmux-safe ANSI frames (SGR + newlines only), with **15 widgets** and an engine of four
  primitives (`field.py`, `raster.py`, `box_junction.py`, `color_model.py`). Correct
  CJK/emoji/ZWJ cell-width handling so columns never desync.
- **Knowledge graph (`knowledge/`)** — a 122-note wiki-link graph of measured rendering
  formulas, ANSI sequences, and constants, each note sourced and cross-linked; entry
  point `knowledge/INDEX.md`.
- **Screenshot harness (`tools/screenshot/`)** — renders terminal output through `pyte`
  and Pillow into PNG files for smoke testing, honestly labelled `pyte-simulation`.
- **AGENTCLI harness (`tools/agentcli/`)** — validates PTY control of agent-like CLIs
  against a local mock (no API keys) with an optional `--external` probe of installed
  agent CLIs.
- **Packaging metadata** — `pyproject.toml` (installs the `smartcli_core` package),
  `requirements.txt` (required deps), and `requirements-optional.txt` /
  `[art] [image] [width] [all]` extras with graceful stdlib fallbacks.
- **MIT license** and project documentation (`README.md`, `README-USAGE.md`).

[0.1.0]: https://keepachangelog.com/en/1.1.0/
