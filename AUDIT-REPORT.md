# SmartCLI 审计与修复报告

> **已归档 · 时点报告 (2026-07-07)。** 这是一份一次性的修复日志，非活文档。
> 记录的三个 bug 均已修复并回归验证，修复至今仍在源码中生效
> （`_readme_literal.py` 导入顺序、`repl_session.py` 有界轮询、`verify_fx.py` 分派
> 仍为 26/26）。项目入口见根 [`README.md`](README.md) 与 [`README-USAGE.md`](README-USAGE.md)。

**范围**：`smartcli_core`（PTY+pyte 引擎）+ `skills/cmd-art` + `skills/drive-tui`
**环境**：Windows 11 · Python 3.14.6 · pyte + pywinpty(ConPTY) · 无 tmux
**日期**：2026-07-07
**方法**：反造假纪律——每个 bug 必须用可运行命令复现并贴真实输出/traceback；文档化的 ConPTY 限制不计为 bug。所有结论经一手复核。

---

## 一、结论一览

发现 **3 个真实 bug（0 误报）**，全部已修复并回归验证通过。`smartcli_core` 核心**未改动**（无可运行证据要求改动，DO-NOT-MODIFY 得到尊重）。

| 编号 | 文件 | 严重度 | 状态 | 复现命令 |
|---|---|---|---|---|
| B | `tests/_readme_literal.py` + `README-USAGE.md` | 崩溃 | ✅ 已修 | `python tests/_readme_literal.py` |
| #2 | `skills/drive-tui/patterns/recipes/repl_session.py` | 错误结果 | ✅ 已修 | 延迟重绘提示符的假 REPL |
| #1 | `tests/verify_fx.py` | 错误结果(脚手架) | ✅ 已修 | `python tests/verify_fx.py text3d` |

回归：`probe_pty_fx.py` PASS(exit 0)、`verify_fx.py` 26/26、`_readme_literal.py` OK(exit 0)。

---

## 二、逐条根因与修复

### Bug B（崩溃，优先级最高）— README 导入顺序

**复现**：`python tests/_readme_literal.py` → `ModuleNotFoundError: No module named 'smartcli_core'`

**根因**：仓库根路径是由 `patterns/__init__.py` 的**导入副作用**注入 `sys.path` 的。README 片段（及该测试）先 `import smartcli_core` 再 `import patterns`——作为 `tests/` 子目录脚本运行时 `sys.path[0]=tests/`，此时 patterns 尚未导入、根路径未注入，故 `smartcli_core` 不可达。`-c`/交互式形态因 cwd(`''`) 恰在 `sys.path` 上而**假性通过**，掩盖了缺陷。

**修复**：交换两行 import——**先 `patterns` 后 `smartcli_core`**（正是片段自己的行内注释所声称的"patterns/ auto-adds the repo root"）。README-USAGE.md 与 tests/_readme_literal.py 同步。验证：`README literal import order OK` EXIT=0。

### Bug #2（错误结果）— repl recipe expect 分支自相矛盾

**复现（确定性）**：写一个假 REPL，发出结果 `42` 后 sleep 1.2s 才重绘 `>>> ` 提示符；`run_line(session,'6*7', expect='42')` → `ok=False, reason=MARKER, out=['42'], prompt=None`（成功标志与自己捕获的证据自相矛盾）。

**根因**：`repl_session.drive()` 的 expect 分支里 `session.wait_for(expect)` 在 marker 一渲染就立即返回（`readiness.wait_for_regex` 首次命中即返回）。此刻 `42` 已在屏，但新的 `>>> ` 提示符尚未重绘到光标行，于是 `prompt_back=_prompt_kind(...)=None`、光标未越过输入行 → `executed=False` → `ok=False`，即便 `reason=='MARKER'` 且输出已正确捕获。

**关键教训**：第一版想用 `wait_ready(marker=None)` 稳定性补丁——**实测失败**：它会在子进程静默间隙误判 STABLE。正解是按 recipe 自身契约**轮询光标行**直到出现提示符且行号大于输入行。

**修复**：`repl_session.py` 加 `import time`，在 `matched` 分支加有界轮询循环（`:112-115`）：命中 marker 后继续 pump 到提示符回到光标行下方再确认。回归：真实 `python -q` expect 42/100、continuation、marker 不出现时干净 TIMEOUT 均通过。

### Bug #1（脚手架，错误结果）— verify_fx 分派

**复现**：`python tests/verify_fx.py text3d`（修前）→ `FAIL play text3d -- no alt-screen enter...`，全套 26/27 EXIT=1。

**根因**：**产品本身是对的**。fx.cli 按 `is_animated(params)` 路由；`text3d.is_animated` 返回 `bool(params.get('shimmer'))`，默认 False → 渲染**一帧静态**到普通屏、不进 alt 缓冲（实测 `python -m fx play text3d --once` → truecolor 存在、`\x1b[?1049h` 缺席，正确）。但测试脚手架 `main()` 按**类属性 `cls.animated`**（=True）分派，误调 `check_animated()` 去断言 ALT_ENTER/LEAVE 必须存在 → 全失败。text3d 是全 18 个效果中**唯一** `cls.animated(True) != is_animated(defaults)(False)` 的。

**修复**：`verify_fx.py:194` 分派改为镜像 CLI——`if cls.is_animated(cls.param_defaults()): check_animated() else: check_static()`，删除冗余的显式 `check_static('text3d')`。回归：26/26 EXIT=0。

---

## 三、运行良好的部分（据两轮实操 probe）

- **fx.core.play restore 契约稳固**：`ALT_ENTER` 在 try 内，任何渲染失败都会走到 finally 发出 RESET/WRAP/SHOW/ALT_LEAVE——17 个动画效果末尾均为正确 restore tail（`\x1b[?7h\x1b[?25h\x1b[?1049l`）。
- **No-TTY 降级安全**：`fire --seconds 9999` 管道输出 exit 0、单帧、不触 alt 屏——无界动画不会挂死非交互调用方。
- **静态/动画路由正确**：产品 `fx.cli._run_effect` 按 `is_animated(params)` 路由；text3d shimmer=off 静态、on 动画，均已验证。Bug 只在测试脚手架，不在 CLI。
- **smartcli_core 设计扎实**：`ScreenModel` 用单条长生命周期 `pyte.ByteStream`（跨读重组半个 ANSI/UTF-8 序列，实测喂分裂 banner 字节正常）；`content_hash` 排除光标+属性以稳定判稳；readiness 全部有硬上限（不会无界等待）。
- **drive-tui classify 排名正确**：REPL 屏上 repl 0.97 居首；broken recipe 被跳过不使 classify 崩溃。

## 四、剩余缺口 / 建议（非 bug）

- **text3d 类属性标签不一致**：`cls.animated=True` 与 `is_animated(defaults)=False` 仅是标签松散（CLI 行为正确）。建议把类属性 `animated` 统一为"默认参数下是否动画"，或直接移除该冗余类属性、全依赖 `is_animated()`。
- **drive probe 依赖未文档化的 `sys.path.insert(0,'.')`**：各 probe 脚本能跑是因为额外插了 cwd。既然 Bug B 已把"patterns 先导入"确立为规范，建议 probe 也统一走这个规范，去掉隐式 cwd 依赖。

## 五、smartcli_core 未改动声明

三个修复分别落在 `tests/`、`README-USAGE.md`、`skills/drive-tui/patterns/recipes/repl_session.py`，**均不触碰 `smartcli_core`**。核心的 DO-NOT-MODIFY 约定得到尊重；无任何可运行证据要求改动核心引擎。

## 六、复现命令与退出码清单（供复核）

```
python tests/_readme_literal.py        # 修后: "README literal import order OK"  EXIT=0
python tests/probe_pty_fx.py           # PASS  EXIT=0
python tests/verify_fx.py              # 26/26 passed  EXIT=0
python tests/verify_fx.py text3d       # PASS once text3d 1/1  EXIT=0
cd skills/cmd-art && python -m fx list # 18 effects  EXIT=0
python -m fx play text3d --once        # 5350B, truecolor 存在, alt-screen 缺席(正确静态)
```

