# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
