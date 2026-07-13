<!-- Thanks for contributing to SmartCLI. Keep changes focused; match the
     surrounding code's style and conventions. -->

## What & why
<!-- What does this change do, and what problem does it solve? -->

## Area
<!-- Tick all that apply -->
- [ ] smartcli_core (PTY / screen model / readiness) — **DO-NOT-MODIFY except with real-run-path verification + adversarial review + no regression across the recipe suite**
- [ ] drive-tui (recipes / tui.py / patterns)
- [ ] cmd-art (fx effects / themes)
- [ ] tui-ui (layout engine / widgets)
- [ ] docs / packaging / CI
- [ ] knowledge graph

## Verification
<!-- Show it works. Paste the relevant command output. -->
- [ ] `python tests/run_all.py` is green (or the relevant subset, noted below)
- [ ] For a new fx effect: `test_fx_contract.py` passes + it renders on the real run path
- [ ] For a new widget: `python -m ui widgets` lists it + `self_test.py` still cell-accurate
- [ ] Counts stay consistent if this changes effect/recipe/widget totals (docs + SKILL.md)

## Notes
<!-- Anything a reviewer should know: tradeoffs, follow-ups, platforms not yet verified. -->
