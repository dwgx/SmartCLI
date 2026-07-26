# SmartCLI Usage Cheat Sheet

SmartCLI is a local Python toolkit for terminal agents and terminal UI work.
It has three skills over a shared PTY/pyte core:

- `cmd-art` (`skills/cmd-art`): 30 terminal visual effects via `python -m fx`.
- `drive-tui` (`skills/drive-tui`): classify and drive real interactive TUI screens.
- `tui-ui` (`skills/tui-ui`): web-like terminal layout/widgets that render tmux-safe ANSI frames.

Verified here on Windows 11, Python 3.14.6, `pyte` + `pywinpty` / ConPTY.
This machine has no real `tmux`; screenshot reports are honestly labelled
`pyte-simulation`, not real tmux captures.

Related docs:

- [`knowledge/INDEX.md`](knowledge/INDEX.md) — the knowledge graph (140+ `.md`
  files: rendering principles, effect math, color/type, TUI patterns, agent-eng,
  ground truth, real-project case studies).
- [`AGENTCLI-VALIDATION.md`](AGENTCLI-VALIDATION.md) — agent-CLI control test
  matrix and limits.
- [`AUDIT-REPORT.md`](AUDIT-REPORT.md) — archived point-in-time repair log
  (2026-07-07, three verified bug fixes).
- [`research/README.md`](research/README.md) — archived first-pass research,
  superseded by `knowledge/sources/`; kept for provenance.

---

## cmd-art

Run from `skills/cmd-art` (any repo checkout location):

```bash
cd skills/cmd-art

python -m fx list
python -m fx list --tag 3d
python -m fx list --json

python -m fx play donut --seconds 5
python -m fx play text3d --set text="SmartCLI" --theme rainbow --seconds 4
python -m fx play rain --theme matrix-green --seconds 5
python -m fx play fire --seconds 5
python -m fx play donut --once
python -m fx gallery --seconds-per 2
python -m fx show --seq "donut:fire:3,plasma::3,rain:matrix-green:3"
python -m fx random --seconds 3
```

Themes: `mono`, `fire`, `ocean`, `synthwave`, `viridis`, `pastel`,
`matrix-green`, `rainbow`.

Add an effect by dropping one registered module into
`skills/cmd-art/fx/effects/`:

```python
from ..base import Effect, FrameCtx
from ..registry import register

@register
class Hello(Effect):
    name = "hello"
    description = "prints a moving greeting"
    tags = ("text",)

    def render(self, ctx: FrameCtx) -> str:
        pad = int(ctx.t * 8) % max(1, ctx.width - 6)
        return "\n" * (ctx.height // 2) + " " * pad + "hello!"
```

Then run:

```bash
python -m fx play hello --seconds 3
```

---

## drive-tui

Python API from the repo root:

```python
import sys
sys.path.insert(0, "skills/drive-tui")

# Import patterns first. Its __init__.py adds the repo root so smartcli_core resolves.
from patterns import classify, explain, all_patterns, get, load_all
from smartcli_core import PtySession
from patterns.recipes.repl_session import run_line

load_all()
print([p.name for p in all_patterns()])

s = PtySession()
s.start([sys.executable, "-q"])
s.wait_for(r">>> ")

snap = s.snapshot()
print(explain(snap))
print(snap.to_text())

res = run_line(s, "6*7")
print(res.ok, res.data.get("output"))

s.close()
```

Pattern recipes:

- `repl`: run one line; helper `run_line(session, code)`.
- `menu_select`: choose by index or substring.
- `search_filter`: type a query and optionally accept a match.
- `pager`: page forward with `Space`, `PageDown`, or `f`.
- `confirm`: answer `[y/N]`, `[Y/n]`, or yes/no prompts.
- `form`: fill line-mode or tabbed forms.
- `progress`: wait for a spinner/progress completion marker.
- `wizard`: drive multi-step flows.

CLI wrapper — a detached daemon owns one live program per session, so state
survives across shell calls. Run from the repo root:

```bash
python skills/drive-tui/scripts/tui.py start --cmd "python3 -i -q" --cols 80 --rows 24
python skills/drive-tui/scripts/tui.py wait-regex --id <SID> ">>> " --timeout-ms 15000
python skills/drive-tui/scripts/tui.py send-line --id <SID> "print(6*7)"
python skills/drive-tui/scripts/tui.py wait --id <SID>
python skills/drive-tui/scripts/tui.py snapshot --id <SID>
python skills/drive-tui/scripts/tui.py close --id <SID>
python skills/drive-tui/scripts/tui.py list          # verify zero leaked sessions
```

(On Windows use `py -i -q` as the child command.)

Full subcommand surface (`tui.py --help`):

- `start` — spawn a program in a detached persistent session. Options:
  `--cmd`, `--id`, `--cols/--rows`, `--cwd` (working directory for the target),
  `--env KEY=VALUE` (repeatable; extra environment for the target).
- `snapshot` — print a semantic snapshot (text, styled spans, cursor,
  selected row, hashes).
- `send-text` / `send-line` — type literal text, without / with a trailing
  Enter. Use `--stdin` for text starting with `/` (MSYS path-conversion-safe).
- `keys` — send key tokens, e.g. `Down Down Enter`, `C-c`, `M-x`.
- The **wait family** (never sleep — pick the right primitive):
  - `wait` — race a `--marker` regex against screen **stability**; with no
    marker it waits for stability alone. The general-purpose "settle" wait.
  - `wait-regex` — wait strictly for a regex to appear. Use for a known
    prompt/marker (first prompt after `start` especially).
  - `wait-change` — wait until screen **text content** changes from a baseline
    hash (or from now). The precise "did my action land?" primitive.
  - `wait-visual-change` — like `wait-change` but also fires on styling,
    selection or cursor-state changes that leave the text identical (e.g. a
    highlight moving); takes `--baseline-hash` from a prior snapshot's
    `visual_hash`.
  - `wait-any` — race **several** `--pattern` regexes, pexpect
    `expect([...])`-style; reports which matched first (earliest in the list
    wins a same-poll tie). `--stdin` reads patterns one per line.
- `alive` — check whether the child process is still running.
- `close` — terminate the session and its daemon.
- `list` — list active sessions (use to confirm zero leaks).
- `run` — one-shot mode: run a JSON step list against a fresh program.
- `doctor` — report where `smartcli_core` resolved from + dependency status.

Every subcommand takes `--json` for machine-readable output. All waits take
`--timeout-ms`.

Console scripts — `pip install smartcli-toolkit` installs the same surface as
commands:

```bash
smartcli-tui start --cmd "python3 -i -q"   # identical to scripts/tui.py
smartcli-mcp                               # stdio MCP server: same verbs as MCP tools,
                                           # per-session token attached automatically
smartcli-toolkit                           # alias of smartcli-mcp (for `uvx smartcli-toolkit`)
```

From a source checkout the MCP server is
`python skills/drive-tui/scripts/mcp_server.py`.

Limits & hardening:

- At most **8 concurrent sessions** by default; raise/lower with
  `SMARTCLI_MAX_SESSIONS` (1–128). Drive **one** session at a time anyway —
  see the hard rules in [`CONTRIBUTING.md`](CONTRIBUTING.md).
- `--env` may **not** override `SMARTCLI_TUI_*` control variables (the daemon's
  token and registry channel are protected).
- Terminal size is bounded: max 1000 cols × 500 rows, 100,000 cells total.
- The session registry directory is created `0700` on POSIX and refused if it
  is a symlink or owned by another user; see [`SECURITY.md`](SECURITY.md).

ConPTY caveats:

- Use `wait_for(regex)` / `wait-regex` for the first prompt; startup can be quiet.
- On Windows, raw Ctrl-C does not reliably interrupt line-mode children.
  Close and restart the session when needed.
- Always close sessions you start.

---

## tui-ui

Run from `skills/tui-ui`:

```bash
cd skills/tui-ui

python -m ui widgets
python -m ui demo table --width 80 --height 12 --theme dashboard
python -m ui demo tabs --width 80 --height 12
python -m ui gallery --width 100 --height 30
python self_test.py
```

Or by path from the repo root:

```bash
python skills/tui-ui/ui/cli.py gallery --width 100 --height 30
```

Widget catalog (17): `badge`, `banner`, `braille_chart`, `card`,
`fuzzy_filter_list`, `gradient_rule`, `kv`, `meter`, `panel`, `preview_pane`,
`progress`, `radial_glow`, `rule`, `slider_track`, `table`, `tabs`, `tree`.
Six live in `ui/widgets_ext/`: `gradient_rule`, `radial_glow`, `slider_track`,
`braille_chart`, `fuzzy_filter_list`, `preview_pane`. Run `python -m ui widgets`
for the live list.

Add a widget by dropping a registered class into `skills/tui-ui/ui/widgets_ext/`.
The widget contract is `measure(avail_w, avail_h)` and `render(region_w, region_h)`.

---

## Screenshot Harness

The screenshot tools render terminal output through pyte and PIL into real PNG
files. They are useful for smoke testing terminal rendering in this environment.
They are not proof of a real tmux binary run.

Run from the repo root:

```bash
python tools/screenshot/cli.py selftest
python tools/screenshot/cli.py fx plasma --out tools/screenshot/out/fx_plasma.png
python tools/screenshot/cli.py matrix fx:plasma --out tools/screenshot/out/matrix_plasma
python tools/screenshot/cli.py matrix edge:cjk_wide --out tools/screenshot/out/matrix_cjk
python tools/screenshot/cli.py matrix edge:emoji --out tools/screenshot/out/matrix_emoji
python tools/screenshot/perception_matrix.py
python tools/screenshot/tui_ui_smoke.py
python tools/screenshot/sweep.py
```

Expected output locations:

- `tools/screenshot/out/selftest/`
- `tools/screenshot/out/perception/index.html`
- `tools/screenshot/out/tui_ui/`
- `tools/screenshot/out/sweep/sweep_report.json`
- matrix contact sheets under the chosen `--out` directory

---

## AGENTCLI Validation

The AGENTCLI harness validates whether SmartCLI can control agent-like CLIs
through a real PTY: observe the screen, classify it, answer confirmations,
wait through progress, drive menu/search fixtures, observe subagent lifecycle
text, and capture screenshots.

Run from the repo root:

These spawn real PTY sessions serially — per the repo red line, get the user's
consent before running the full harness, and don't stack it with other PTY work.

```bash
python tools/agentcli/validate_agentcli.py
python tools/agentcli/validate_agentcli.py --external
python tools/agentcli/validate_agentcli.py --no-screenshots
```

Outputs:

- `tools/agentcli/out/agentcli_report.json`
- `tools/agentcli/out/screens/*.png`

The default run uses a local mock agent CLI and does not require API keys. The
`--external` run probes installed open-source agent CLIs by help output. Current
tracked targets are Codex CLI (`openai/codex`), Aider (`Aider-AI/aider`),
OpenCode (`anomalyco/opencode`), and Goose (`aaif-goose/goose`). Missing tools
are reported as skipped, not failed.

See `AGENTCLI-VALIDATION.md` for the test matrix and limits.

---

## Regression Commands

Run from the repo root unless noted. **`tests/run_all.py` is the main entry** —
it aggregates every self-test as a subprocess and reports one pass/fail:

```bash
python tests/run_all.py
```

The suite has two tiers. **Deterministic gates** are pure/in-memory (no PTY) and
safe to run any time:

```bash
python tests/test_fx_contract.py        # 30 effects x sizes x contracts
python tests/test_readiness.py          # virtual-clock wait primitives
python tests/test_wait_any.py
python tests/test_visual_change.py      # selection/cursor-aware waits
python tests/test_drive_security.py     # control-plane boundaries
python tests/test_vendor_sync.py        # vendored core byte-identical
python tests/test_doc_counts.py         # docs match the live registries
python tests/test_version_sync.py       # ten version sites agree
python tests/_readme_literal.py
cd skills/tui-ui && python self_test.py
```

**PTY probes** spawn real ConPTY/pty sessions. They are heavy and must run
**serially, one at a time** — per the repo red line, get the user's consent
first and never stack them:

```bash
python tests/verify_fx.py               # spawns many PTY children
python tests/probe_pty_fx.py
python tests/_drive_probe1.py           # ... _drive_probe2..6, one at a time
python tests/_tui_cli_probe.py
python tests/_mcp_probe.py
python tests/_agentcli_harness_probe.py
```

Note: `_drive_probe2.py` intentionally creates a broken recipe to verify
fail-soft discovery. It prints one warning by design, then removes its temporary
source and bytecode.

---

## Project Map

```text
SmartCLI/
  README.md                repo entry point (links usage / knowledge / research)
  smartcli_core/           shared PTY + pyte engine
  skills/cmd-art/          fx effect package and CLI
  skills/drive-tui/        TUI pattern library and PTY driver CLI
  skills/tui-ui/           terminal UI layout/widgets
  tools/screenshot/        pyte -> PNG smoke-test harness
  tools/agentcli/          agent-CLI control validation harness
  knowledge/               wiki-link knowledge graph, 140+ .md files (see knowledge/INDEX.md)
  showcase/                rendered effect PNGs
  tests/                   direct script-style regressions
  research/                archived first-pass research notes
```
