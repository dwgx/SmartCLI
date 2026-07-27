# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## ⚠️ 硬性红线:严禁密集/并发 spawn 真实进程(会卡死/崩溃本机)

2026-07-13 事故:在一个会话里短时间内反复 spawn 大量真实进程(多个 grok/codex/
kiro-cli 全屏 TUI + 反复起关 daemon + mutation 来回 git checkout + verify_fx 每次
又开一堆 PTY 子进程),累积瞬时并发把用户 Windows 机器拖到卡死,用户被迫重启。
单个进程都清理干净了(零残留),元凶是**叠加的瞬时并发峰值**。

以后必须遵守:
1. **一次只驱动一个 PTY/TUI 会话。** 跑完立刻 `close` + 确认 `tui.py list` 零残留,
   再起下一个。绝不同时开多个 agent CLI(grok/codex/kiro-cli 每个都拉起
   node/rust 进程 + winpty,极吃资源)。
2. **重活(verify_fx、run_all、drive-probe 全套)先征得用户同意再跑**,且串行、
   分开跑,不在一个会话里堆几十个进程。verify_fx 每跑一次要 spawn 一大批 PTY 特效
   子进程——尤其重。
3. **mutation 验证要克制**:来回 git checkout + 重跑 PTY 探针代价高;能用代码级
   断言证明的就别反复起真实进程。
4. **看到 spawn 层错误**(`uv_spawn`、`EUNKNOWN`、exit 143/45、Git-bash spawn
   失败)= 系统在示警资源紧张,**立即停手**,别换 shell 硬上。
5. 需要用户自己跑重活时,建议用 `! python tests/verify_fx.py`(前缀 `!` 在会话里
   直接跑),而不是我又开一批子进程。

## Git commits

- 不加任何 AI 署名(遵循用户全局 CLAUDE.md)。
- 只有用户明确要求才 commit。

## Commands

Set `PYTHONIOENCODING=utf-8` before running anything (box-drawing/CJK glyphs crash
on legacy codepages; CI sets it too).

```bash
# Full self-test aggregator — exit 0 iff everything passes. SLOW: spawns real
# PTY sessions serially. Per the red line above, get user consent before running.
python tests/run_all.py

# Run a single test (each test file is a standalone script, exit 0 = pass):
python tests/test_fx_contract.py          # deterministic, pure-memory — safe
python tests/test_readiness.py
python tests/test_vendor_sync.py
python tests/_drive_probe1.py             # spawns a real PTY — run serially

# fx effect regression (spawns many PTY children — heavy, consent first):
python tests/verify_fx.py

# Coverage over the deterministic subset (no PTY spawn; --full drives PTYs):
python tools/coverage_run.py
python tools/coverage_run.py --xml        # also write coverage.xml for Codecov

# Lint / type-check (CI lint job is advisory, not blocking):
ruff check .
mypy                                      # config in pyproject.toml; checks smartcli_core only

# cmd-art effect engine (run from skills/cmd-art):
python -m fx list                         # live catalog (30 effects)
python -m fx play donut --seconds 5
python -m fx gallery

# tui-ui layout engine (run from skills/tui-ui):
python -m ui widgets                      # 17 widgets
python self_test.py

# drive-tui: drive a real interactive program (ONE session at a time).
# Use "python3 -i -q" (POSIX) / "py -i -q" (Windows) — don't assume a bare
# `python` exists on PATH (modern macOS has none):
python skills/drive-tui/scripts/tui.py start --cmd "python3 -i -q" --cols 100 --rows 30
python skills/drive-tui/scripts/tui.py wait-regex --id <SID> ">>> " --timeout-ms 15000
python skills/drive-tui/scripts/tui.py send-line --id <SID> "print(6*7)"
python skills/drive-tui/scripts/tui.py snapshot --id <SID>
python skills/drive-tui/scripts/tui.py close --id <SID>
python skills/drive-tui/scripts/tui.py list   # verify zero leaked sessions

# After ANY change to smartcli_core: re-sync the vendored copy and verify.
python tools/sync_vendor.py
python tests/test_vendor_sync.py
```

## Architecture

**One shared core, three skills on top.** SmartCLI drives, perceives, and renders
terminals through a pluggable PTY + `pyte` cell-grid screen model (not a byte
pipe), so it knows which menu row is highlighted rather than pattern-matching a
stream.

### `smartcli_core/` — the shared typed core (the only mypy-checked package)

- `pty_backend.py` — pluggable PTY: `WinptyBackend` (ConPTY via pywinpty, the
  primary dev target) and `PosixPtyBackend` (stdlib `pty`, Linux/macOS).
  `get_default_backend()` picks per-platform.
- `screen_model.py` — `ScreenModel` wraps a `pyte` screen: cell grid, cursor,
  alt-screen, DECCKM app-cursor state (arrow keys adapt SS3 vs CSI from it).
- `snapshot.py` — semantic `Snapshot`/`Span`: styled runs, selected-row
  detection, content hashes.
- `readiness.py` — the wait primitives: `wait_until_stable`, `wait_for_regex`,
  `wait_ready` (races marker vs stability), `wait_any` (pexpect-style
  multi-marker). Never `sleep` — always these.
- `session.py` — `PtySession` ties it together; `KEY_MAP` translates key tokens
  to escape sequences.

Gotcha baked into the API docs: pyte right-pads lines with spaces, so
end-anchored markers like `r">>> $"` never match — use unanchored markers.

### `skills/` — three self-contained skills run in place from the checkout

- `skills/drive-tui/` — drives interactive TUIs via a perceive → decide → act →
  wait → confirm loop. `scripts/tui.py` is the CLI: a detached daemon owns one
  live program; commands connect over a localhost-only, token-authenticated
  socket so state survives across shell calls. `scripts/mcp_server.py` exposes
  the same surface as a stdio MCP server. `_vendor/smartcli_core/` is a
  byte-identical vendored copy of the core (enforced by `test_vendor_sync`);
  `smartcli_bootstrap.locate_core()` resolves the real core first
  (`$SMARTCLI_ROOT` → parent walk → `_vendor/` → pip install).
- `skills/cmd-art/` — the `fx` effect engine: `Effect` ABC + `@register` +
  pkgutil auto-discovery. Effects are **pure frame producers** (return one full
  frame; never print/sleep/touch ANSI modes — the play loop owns the terminal).
  30 effects, 8 themes.
- `skills/tui-ui/` — web-like layout engine emitting **tmux-safe ANSI frames**
  (SGR runs + newlines only; no cursor moves, no alt-screen). CSS box model,
  `VStack/HStack/Grid` with `Fr` units, 17 widgets, plus engine modules:
  `field.py` (shaders), `raster.py` (sub-cell braille/quad pixels),
  `box_junction.py` (auto-connecting borders), `color_model.py` (truecolor→mono
  degrade). All sizing is display-cell accurate via `ui.core.width()` — never
  `len()`. It produces frames; something else owns the terminal (contrast with
  drive-tui).

### Packaging duality

The PyPI dist is `smartcli-toolkit`; the import package is `smartcli_core`.
`pyproject.toml` maps `smartcli_drive` → `skills/drive-tui/scripts`, so one
implementation serves source checkouts, skill installs, the `smartcli-tui` /
`smartcli-mcp` / `smartcli-toolkit` console scripts, and MCP Registry clients
(`io.github.dwgx/smartcli`). cmd-art and tui-ui are intentionally not packaged —
they run in place via `python -m fx` / `python -m ui`.

### Version bump = TEN sites move together

`pyproject.toml`, `smartcli_core/__init__.py`, `skills/cmd-art/fx/__init__.py`,
all 3 `skills/*/SKILL.md` `version:` fields, `.claude-plugin/marketplace.json`,
`.claude-plugin/plugin.json`, the vendored `_vendor/smartcli_core/__init__.py`,
and `server.json` (two fields: top-level + `packages[0].version`). After
bumping: `python tools/sync_vendor.py`, then `python tests/test_vendor_sync.py`
and `python tests/test_version_sync.py` (anti-drift gate over all ten sites).

### Tests

`tests/run_all.py` aggregates every self-test as a subprocess and reports one
pass/fail. Tests are standalone scripts, not pytest. Two tiers:

- **Deterministic gates** (pure/in-memory, no PTY): `test_fx_contract`,
  `test_readiness`, `test_wait_any`, `test_visual_change`,
  `test_drive_security`, `test_zwj_text_loss`, `test_sixel`, `test_doc_counts`
  (anti-drift: doc counts must match code), `test_version_sync` (ten version
  sites), `test_vendor_sync`, `_sandbox_fuzz_core`. The authoritative list is
  `build_suite()` in run_all.py. These run in CI on a 3-OS matrix
  (Windows/Ubuntu/macOS × py3.10/3.14).
- **Real-process probes** — spawn real ConPTY/pty/tmux; slow, serial-only, one
  at a time, consent required: `_drive_probe*`, `_tui_cli_probe`, `_mcp_probe`,
  `verify_fx`, `probe_pty_fx`, `_sandbox_posix_backend`,
  `_sandbox_daemon_robustness`, plus the two real-tmux probes
  (`_diff_tmux_pyte`, `_tmux_launcher_probe`), which SKIP themselves when tmux
  is absent.

Docs and counts are contract-tested: changing the number of effects/widgets
requires updating README/SKILL.md counts or `test_doc_counts` fails (it also
bans hard-coded dev-box paths from portable docs).

**Differential testing is the strongest evidence available here.**
`tests/_diff_tmux_pyte.py` diffs our grid against a real tmux pane cell by
cell — it is how the ZWJ/VS16 text-loss bug was found, and how HARD RULE 7 was
confirmed. When it disagrees, suspect the rig first (tty `ONLCR`, capture-pane's
literal TAB, NFC vs NFD were all harness artifacts, not emulation gaps).

### Project docs

`HANDOFF.md` is the authoritative current-state record a fresh session reads
first; `NEXT-STEPS.md` is the prioritized task queue. Both must be kept
reconciled with reality after significant work.
