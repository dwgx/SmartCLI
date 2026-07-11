# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
