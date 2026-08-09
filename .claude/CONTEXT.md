# smartcli —— 项目背景（给 subagent 看）

本文件是**专门给 subagent 的项目背景**。主会话和 subagent 都应该先读这里再动手，
避免每次从零摸索。读到的内容当作已确认事实，不要重新验证。详细文档见根 `CLAUDE.md`（249 行，本文件是它的浓缩）。

## 这是什么

一个 Python CLI 工具包 + MCP server（`mcp-name: io.github.dwgx/smartcli`），也是三个
Claude skill（cmd-art / drive-tui / tui-ui）的真源。PyPI 发布，通过 `pyproject.toml`
管理。

## 硬性红线（2026-07-13 事故的教训）

**严禁密集/并发 spawn 真实进程** —— 曾有一个会话反复起多个全屏 TUI + daemon +
反复 checkout + 每次 verify 开一堆 PTY 子进程，瞬时并发峰值把机器拖到卡死。

subagent 尤其要遵守：
- 一次只驱动一个 PTY/TUI 会话，跑完立刻 `close` + 确认零残留
- 重活（`verify_fx`、`run_all`、drive-probe 全套）先征得用户同意再跑，且串行
- 看到 `uv_spawn`/`EUNKNOWN`/exit 143/45 这类 spawn 层错误 = 系统在示警资源紧张，**立即停手**
- 需要用户自己跑重活时，建议用 `! python tests/verify_fx.py` 前缀直接在会话里跑

## 跑测试/命令的关键坑

- **先设 `PYTHONIOENCODING=utf-8`**，否则 box-drawing/CJK 字符在 legacy codepage 上崩
- **用装了 pyte 的解释器**：每个测试都 import `smartcli_core`，裸 python 会
  `ModuleNotFoundError: No module named 'pyte'`，看着像测试坏了其实只是解释器不对
- **直接取命令退出码**，不要 `python tests/x.py 2>&1 | tail` —— 那样取到的是 `tail`
  的退出码，import 崩溃也会被读成 pass
- 工具优先级：`ruff`/`mypy` 已装且 pyproject 已配好；有 `.codegraph/` 索引，先 `codegraph explore`

## 给 subagent 的提醒

- 搜内容用 `rg` 不用 `grep`，找文件用 `fd` 不用 `find`
- 读文件用 Read 工具不用 `cat`/`head`
- 涉及 key/secret 先读 `~/.claude/SECRETS.md`，值绝不 echo/写文件/进 commit
