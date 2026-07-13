# SmartCLI Usage Cheat Sheet

SmartCLI is a local Python toolkit for terminal agents and terminal UI work.
It has three skills over a shared PTY/pyte core:

- `cmd-art` (`skills/cmd-art`): 19 terminal visual effects via `python -m fx`.
- `drive-tui` (`skills/drive-tui`): classify and drive real interactive TUI screens.
- `tui-ui` (`skills/tui-ui`): web-like terminal layout/widgets that render tmux-safe ANSI frames.

Verified here on Windows 11, Python 3.14.6, `pyte` + `pywinpty` / ConPTY.
This machine has no real `tmux`; screenshot reports are honestly labelled
`pyte-simulation`, not real tmux captures.

Related docs:

- [`knowledge/INDEX.md`](knowledge/INDEX.md) — the 122-note knowledge graph
  (rendering principles, effect math, color/type, TUI patterns, agent-eng,
  ground truth, real-project case studies).
- [`AGENTCLI-VALIDATION.md`](AGENTCLI-VALIDATION.md) — agent-CLI control test
  matrix and limits.
- [`AUDIT-REPORT.md`](AUDIT-REPORT.md) — archived point-in-time repair log
  (2026-07-07, three verified bug fixes).
- [`research/README.md`](research/README.md) — archived first-pass research,
  superseded by `knowledge/sources/`; kept for provenance.

---

## cmd-art

Run from `skills/cmd-art`:

```powershell
cd D:\Project\SmartCLI\skills\cmd-art

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

```powershell
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

CLI wrapper:

```powershell
cd D:\Project\SmartCLI
python skills\drive-tui\scripts\tui.py start --cmd "python" --cols 80 --rows 24
python skills\drive-tui\scripts\tui.py wait-regex --id <SID> ">>> " --timeout-ms 15000
python skills\drive-tui\scripts\tui.py send-line --id <SID> "print(6*7)"
python skills\drive-tui\scripts\tui.py wait --id <SID>
python skills\drive-tui\scripts\tui.py close --id <SID>
```

ConPTY caveats:

- Use `wait_for(regex)` / `wait-regex` for the first prompt; startup can be quiet.
- On Windows, raw Ctrl-C does not reliably interrupt line-mode children.
  Close and restart the session when needed.
- Always close sessions you start.

---

## tui-ui

Run from `skills/tui-ui`:

```powershell
cd D:\Project\SmartCLI\skills\tui-ui

python -m ui widgets
python -m ui demo table --width 80 --height 12 --theme dashboard
python -m ui demo tabs --width 80 --height 12
python -m ui gallery --width 100 --height 30
python self_test.py
```

Or by path from anywhere:

```powershell
python D:\Project\SmartCLI\skills\tui-ui\ui\cli.py gallery --width 100 --height 30
```

Widget catalog (15): `badge`, `banner`, `braille_chart`, `card`, `gradient_rule`,
`kv`, `meter`, `panel`, `progress`, `radial_glow`, `rule`, `slider_track`,
`table`, `tabs`, `tree`. The last four (`gradient_rule`, `radial_glow`,
`slider_track`, `braille_chart`) live in `ui/widgets_ext/`. Run `python -m ui
widgets` for the live list.

Add a widget by dropping a registered class into `skills/tui-ui/ui/widgets_ext/`.
The widget contract is `measure(avail_w, avail_h)` and `render(region_w, region_h)`.

---

## Screenshot Harness

The screenshot tools render terminal output through pyte and PIL into real PNG
files. They are useful for smoke testing terminal rendering in this environment.
They are not proof of a real tmux binary run.

Run from the repo root:

```powershell
cd D:\Project\SmartCLI

python tools\screenshot\cli.py selftest
python tools\screenshot\cli.py fx plasma --out tools\screenshot\out\fx_plasma.png
python tools\screenshot\cli.py matrix fx:plasma --out tools\screenshot\out\matrix_plasma
python tools\screenshot\cli.py matrix edge:cjk_wide --out tools\screenshot\out\matrix_cjk
python tools\screenshot\cli.py matrix edge:emoji --out tools\screenshot\out\matrix_emoji
python tools\screenshot\perception_matrix.py
python tools\screenshot\tui_ui_smoke.py
python tools\screenshot\sweep.py
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

```powershell
python tools\agentcli\validate_agentcli.py
python tools\agentcli\validate_agentcli.py --external
python tools\agentcli\validate_agentcli.py --no-screenshots
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

Run from the repo root unless noted:

```powershell
python tests\_readme_literal.py
python tests\probe_pty_fx.py
python tests\verify_fx.py
python tests\verify_fx.py text3d

python tests\_drive_probe1.py
python tests\_drive_probe2.py
python tests\_drive_probe3.py
python tests\_drive_probe4.py
python tests\_drive_probe5.py

python tools\screenshot\cli.py selftest
python tools\screenshot\perception_matrix.py
python tools\screenshot\tui_ui_smoke.py
python tools\screenshot\sweep.py

python tests\_agentcli_harness_probe.py

cd D:\Project\SmartCLI\skills\tui-ui
python self_test.py
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
  knowledge/               122-note knowledge graph (see knowledge/INDEX.md)
  showcase/                rendered effect PNGs
  tests/                   direct script-style regressions
  research/                archived first-pass research notes
```
