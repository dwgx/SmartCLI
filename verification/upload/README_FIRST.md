# SmartCLI v3 上传包 — 先读我

生成：2026-09-16（本机 session `01a0a700`，Windows 11 / CPython 3.14.7）
对象：网页端最强模型（astrapro 等），用于产出 `PROMPT_PASTE_THIS.md` 里要求的 7 份文件。

## 30 秒定位

SmartCLI（`dwgx/SmartCLI`，HEAD `701e61f`）= 跨平台 PTY + 语义屏幕模型 + Python 库/CLI/MCP 的
**Agent 终端交互运行时**。本包 = 计划（v1/v2）+ 本机**已验证**的实现与实测证据 + 待批准的 A04 提案。
所有数字都来自本机真实运行，不是推测；每份收据都写了环境、命令、退出码与 `NOT_RUN`。

**证据等级**（本包统一使用）：E1 源码阅读 · E2 参考模型 · E3 真实 `smartcli_core` 纯内存 ·
E4 本机真实终端（真 pty / ConPTY / Linux 容器）· E5 端到端任务 + 独立裁判 · E6 发行物验证。

## 目录

| 目录 | 内容 | 为什么给它 |
|---|---|---|
| `01_plan/` | v1 主计划 + 50 任务卡 + 验收/架构；v2 的 ORDER、A04 设计、A01 最小契约、conformance、定位、风险、以及 v2 对本地结论的反驳 | 让模型知道"已决定的"和"已被推翻的"，避免重复设计 |
| `02_evidence/` | v1 本机 ground truth；**X2（Windows/ConPTY 实测）**、**X3（POSIX 实测）**、**T03 真机写**的原始 JSON 与说明 | 这是模型自己拿不到的事实，也是本轮最重要的输入 |
| `03_receipts/` | T05/T04/T03 的 `last.md`+`closure.json`（含四阶段突变证据）、A04-P 原型收据、**A04 生产提案** | 证明"已完成"的边界，A04 提案是待批准项 |
| `04_code/` | **已落地**的 `snapshot.py`(T05)、`screen_model.py`(T04)、`pty_backend.py`(T03) 与三个新测试；**当前** `tui.py` daemon（A04 的目标）、`mcp_server.py`、`pyproject.toml` | 让模型对着真实代码给 A04 生产设计，而不是对着描述 |
| `05_verification/` | kit 的 `conformance.py`、closure 模板、三份任务模板、突变脚本 `mutate.py`、被取代的合并测试 | 让"怎么验证"也是可执行的 |

## 建议的上传优先级（若附件数量有上限）

1. `PROMPT_PASTE_THIS.md`（不是附件，是提示词本体）
2. `01_plan/MASTER_PLAN_v1.md`、`01_plan/v2_ORDER.md`、`01_plan/v2_A04_DESIGN.md`
3. `02_evidence/v1_local_evidence.md`、`02_evidence/X2_windows_conpty.md`、`02_evidence/X3_posix_idle.md`
4. `03_receipts/A04P_PROPOSAL.md`、`03_receipts/A04P_DESIGN_DELTA.md`
5. `04_code/tui.py_CURRENT_daemon_A04_target.py`、`04_code/screen_model.py_T04_implemented.py`、`04_code/pty_backend.py_T03_implemented.py`
6. 其余全部（越全越好，尤其是 `02_evidence/*.json` 与 `05_verification/`）

## 事实基线摘要（模型应直接采信，不要重新推导）

* **T05**（E3，18 测试）：中文菜单反色项的高亮标签正确返回 `保存`（旧实现返回 `3`）。
* **T04**（E3，22 测试）：流式 SGR 规范化。`4:3` 只能是下划线、**不得**带斜体；`38:2::255:0:128` → fg `ff0080`；
  `58:2::1:2:3` 整组丢弃（不得泄漏成 dim/bold/italic）；OSC/DCS 载荷不改写；未终止 CSI 上限 1024 字节后丢弃、可恢复。
* **T03**（E4，12 测试 + 真机）：真 POSIX pty 上一次 `write()` 262 144 字节逐字节正确、44 次可写等待；
  旧实现 0 ms "成功"返回而子进程收不全。
* **A04 Windows 现状**（E4）：无人轮询时队列无界增长（7.5 s → 271 307 B / 2 906 项）；投递成批且慢于产出；
  1 MiB 突发只剩约 12 KB 合成流 ⇒ **不可能 byte-exact**。
* **A04 POSIX 现状**（E4）：无人轮询时子进程卡在 12 288 B、`ESC[6n` 无人应答；owner 循环下 512 KiB / 0.93 s 完成并正确应答。
* **未运行**：真实竞品运行、真实用户负载基准、Windows 长跑 RSS 曲线、多 watcher 产品 API、commit/push（均由 Owner 决定）。

## 给 Owner 的两句提醒

* 仓库 `D:\Project\SmartCLI` 目前是**未提交**状态（7 个修改 + 3 个新测试），我没有 commit/push。
* 收到网页模型回复后，最直接的下一步是：把 `BRIEFS_V3.md` 的第一份（A04 生产切片）交回本机执行；
  它会先提小提案（新线程/队列/公共 API 需批准），随后按 `RUN/A04/{last.md,closure.json}` 的格式留证。
