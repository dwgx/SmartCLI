# AGENTCLI Control Validation

This document defines how SmartCLI validates control over agent-like CLIs.
The goal is not to prove that every vendor model is correct. The goal is to
prove that SmartCLI can observe, classify, drive, screenshot, and cleanly close
the terminal behavior an agent CLI exposes.

## Current Status

SmartCLI already has the required control layers:

- `smartcli_core.PtySession`: real PTY launch, input, resize, snapshot, waits.
- `skills/drive-tui`: screen classification and recipes for REPL, confirm,
  menu, search, pager, progress, form, and wizard flows.
- `tools/screenshot`: pyte/PIL screenshots and size/color-depth matrices.
- `skills/tui-ui`: web-like terminal UI frames for dashboards and reports.

The new `tools/agentcli/validate_agentcli.py` harness uses these layers directly.

## Open-Source Agent CLI Targets

External projects to track as optional validation targets:

| Target | Upstream | Local probe |
| --- | --- | --- |
| Codex CLI | https://github.com/openai/codex | `codex --help` |
| Aider | https://github.com/Aider-AI/aider | `aider --help` |
| OpenCode | https://github.com/anomalyco/opencode | `opencode --help` |
| Goose | https://github.com/aaif-goose/goose | `goose --help` |

Only installed tools are probed. Missing tools are reported as skipped rather
than failed. Model/API-key paths should be tested separately and never assumed
available in CI.

## Local Synthetic Scenarios

The harness includes a deterministic mock agent CLI so behavior validation does
not depend on provider auth:

- `repl`: drive a Python REPL with `patterns.recipes.repl_session.run_line`.
- `confirm`: detect and answer an `[y/N]` style tool approval.
- `progress`: wait for a long-running task to emit `DONE`.
- `menu_select`: drive an arrow-key menu fixture to `Cherry`.
- `search_filter`: drive an fzf-like query to `grape`.
- `subagents`: observe a coordinator emitting three worker lifecycle lines.

Each scenario runs through a real PTY and can write a PNG screenshot of the final
screen state.

## Run

From the repo root:

```powershell
python tools\agentcli\validate_agentcli.py
python tools\agentcli\validate_agentcli.py --external
python tools\agentcli\validate_agentcli.py --no-screenshots
```

Outputs:

- `tools/agentcli/out/agentcli_report.json`
- `tools/agentcli/out/screens/*.png`

## Pass/Fail Rules

A scenario passes only when SmartCLI observes an expected screen state and the
recipe/action confirms the requested result. Examples:

- Confirm passes when `confirm.drive(..., True)` returns ok and the screen shows
  `APPROVED`.
- Search passes when the fzf-style app reports `PICKED: grape`.
- Subagent observation passes when three completed worker lifecycle lines are
  visible before the timeout.
- External help probes pass when installed CLIs produce recognizable help text.

## Limits

- Screenshots are `pyte-simulation`, not a real tmux binary capture.
- External agent CLIs may require auth or API keys for full model runs.
- This harness validates terminal control and behavioral observability, not model
  reasoning quality.
- Windows-only fixtures that use `msvcrt` are skipped on non-Windows hosts.
