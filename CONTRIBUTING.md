# Contributing to SmartCLI

Thanks for your interest. SmartCLI is a terminal/PTY toolkit — three Agent
Skills (`cmd-art`, `drive-tui`, `tui-ui`) over one shared `smartcli_core`
(pluggable PTY backend + `pyte` screen model). This guide covers how to set up,
what the quality bar is, and the few hard rules that keep the project honest.

## Quick start

```bash
git clone https://github.com/dwgx/SmartCLI SmartCLI
cd SmartCLI
python -m pip install -r requirements.txt          # pyte (+ pywinpty on Windows)
python -m pip install -r requirements-optional.txt  # pyfiglet / Pillow / wcwidth (optional)
```

The three skills run in place from the checkout — there is no build step to
develop them. On Windows, set `PYTHONIOENCODING=utf-8` first so box-drawing and
CJK glyphs encode (the CLIs also auto-reconfigure stdout, but set it to be safe).

## Running the tests

One unified runner exercises every engine + integration probe:

```bash
python tests/run_all.py
```

It must exit `0`. Some probes drive real ConPTY sessions and are slow; each has
a generous timeout. The deterministic, pure-in-memory gates (no PTY spawn) are
the crown jewels and run fast on every OS in CI:

```bash
python tests/test_fx_contract.py       # every fx effect x sizes, exact frame contract
python tests/test_readiness.py          # readiness virtual-clock + blank-gate locks
python tests/test_degenerate_inputs.py  # degenerate-input regression locks
python tests/test_doc_counts.py         # docs match code (anti-drift)
python tests/test_golden_frames.py      # tui-ui widget golden-frame snapshots
```

CI runs a 3-OS matrix (Windows + Linux + macOS × Python 3.11/3.12). Please make
sure `python tests/run_all.py` is green locally before opening a PR.

## The hard rules (non-negotiable)

These are distilled from real incidents. They override any shortcut that looks
faster.

1. **Never densely/concurrently spawn real processes.** SmartCLI drives real
   PTYs; spawning many at once (multiple full-screen agent CLIs, repeated daemon
   churn, fan-out `verify_fx` runs) has locked up a developer machine. Drive
   **one** PTY/TUI session at a time, close it, confirm `tui.py list` shows zero
   leaks, then start the next. Verify serially, never in parallel.

2. **`smartcli_core/` is DO-NOT-MODIFY except under an explicit exception.**
   Changes are allowed ONLY with all three of: (a) verification on the real run
   path (not a monkeypatched harness), (b) independent adversarial review, and
   (c) no regression across the full `run_all.py` suite. The core is small and
   load-bearing — treat it as frozen unless you have all three.

3. **Verify on the REAL run path.** A green preview, a monkeypatched harness, or
   a mocked backend is not proof. Run the actual script/effect/daemon the way a
   user would and inspect the real output.

4. **Mutation-test against false-green.** After a new test passes, deliberately
   break the code it covers and confirm the test FAILS. A test that stays green
   under a real mutation is worthless. Every test in this repo is
   mutation-verified genuine — keep it that way.

5. **Docs must match the code.** `test_doc_counts.py` gates effect/recipe/widget
   counts (including CJK phrasings in the localized READMEs). If you add an
   effect or widget, update every doc that states a count, or the anti-drift gate
   fails the PR.

## Adding an effect / recipe / widget

All three registries use the same `@register` + auto-discovery pattern, so
dropping a new module in the right folder is all it takes:

- **fx effect** → `skills/cmd-art/fx/effects/<name>.py` (subclass `Effect`, a
  pure frame producer: `render(ctx) -> str`, never print/sleep/touch ANSI modes).
  Verify with `python -m fx play <name>` and `tests/test_fx_contract.py`.
- **drive-tui recipe** → `skills/drive-tui/patterns/recipes/<name>.py`
  (`classify()` then `drive()`).
- **tui-ui widget** → `skills/tui-ui/ui/widgets_ext/<name>.py` with a
  `sample(theme)` classmethod. `tests/test_golden_frames.py` will pick it up;
  regenerate the baseline with `python tests/test_golden_frames.py --update`.

## Pull requests

- Branch off `main`; keep the change focused.
- Explain what changed and how you verified it (paste the relevant test output).
- Keep commit messages about the change itself.
- Do not commit anything from `research/cc-decompiled/` or `research/real-frames/`
  (gitignored, excluded from release).

## Security

Found a vulnerability? See [SECURITY.md](SECURITY.md) — please report privately
rather than opening a public issue.

