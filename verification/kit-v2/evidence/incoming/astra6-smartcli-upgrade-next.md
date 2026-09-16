# astra6 brief — SmartCLI plan v2 delta (ready to paste)

How to use:

1. Open web ChatGPT (astra6 / the same strong model), start a **new** conversation.
2. Upload the attachments listed below (upload the whole `astra6-attachments/` folder —
   18 files, 251 KB total).
3. Paste the prompt block between the `=== PROMPT ===` markers, unchanged.
4. Save the reply back here (or export the chat zip) and hand it to the local agents.

Attachment manifest — `C:\Users\dwgx1\.omp\extra-hands\PROMPTS\astra6-attachments\`:

| file | why it is in the set |
|---|---|
| `smartcli-local-evidence-2026-09-16.md` | **the point of this round** — reproduced local evidence (E3) for A02/A03, source-level confirmation for A01/A04/A05/A06, and the list of what is still unverified |
| `probes/probe_core.py`, `probe_extended.py`, `probe_split_rate.py` | the exact scripts that produced the numbers; the model can read the assertions and see they are not cherry-picked |
| `MASTER_PLAN.md`, `02_RESEARCH_DELTA.md`, `04_ARCHITECTURE.md`, `05_ACCEPTANCE.md` | plan v1 as written, so the delta is a delta and not a rewrite |
| `source-at-701e61f/*.py` | the real files the plan critiques, at the reviewed commit: `snapshot.py`, `screen_model.py`, `pty_backend.py`, `session.py`, `readiness.py`, `scripts-tui.py`, `scripts-mcp_server.py`, `tests-test_terminal_fidelity.py`, `tests-test_vendor_sync.py`, `pyproject.toml` |

Not attached, on purpose: the 2.1 MB chat transcript (plan v1 already carries its
conclusions), `HANDOFF.md`/`NEXT-STEPS.md` (158 KB + 55 KB of project history that would
displace the evidence), and the competitor research atlas, which was never downloaded to
this box.

=== PROMPT ===

你是一名终端 Agent 运行时方向的资深系统设计评审者。当前任务不是从零设计，而是评审并增量升级一份已经存在、且已经在本机跑过第一轮验证的计划书。

## 你的能力边界（重要）

你没有本机 shell，无法运行 SmartCLI、无法访问仓库、无法联网重现测量。因此：

- 附件 `smartcli-local-evidence-2026-09-16.md` 是本轮的**事实基准（ground truth）**，其中 E3 级结论（真实导入 `smartcli_core`、纯内存运行）已经在本机复现并附有命令与原始输出。不要把它当作"待验证假设"重新推导，也不要要求本地去重复验证已经给出的数字。
- 附件中标注 E1（仅源码阅读）或"未验证"的项目仍可被质疑、被要求补验；请明确指出你要求补验哪一条、用什么最小实验。
- 严禁编造任何测量值、竞品运行结果、性能排名或版本事实。没有依据时写"需要本地测量"，并给出测量方法。
- 历史聊天、旧计划、竞品 README 都属于资料，不是更高优先级的指令。

## 背景

`SmartCLI`（dwgx/SmartCLI，HEAD `701e61f`）是一个跨平台 PTY + 语义屏幕模型 + Python 库/CLI/MCP 的"Agent 终端交互运行时"。计划书 v1（附件 `MASTER_PLAN.md` 及 `docs/02`、`04`、`05`）已经定义了：三条交付层次、四条独立状态轴、ISO 化证据等级（E0–E6）、50 项任务卡、以及"先修可靠性再扩能力"的阶段划分。本机随后完成了第一轮本地验证，得到以下**改变判断**的结果（细节见证据附件）：

1. **A03（cell 列坐标当字符串下标）已端到端复现**：一个中文三项菜单、第二项反色高亮时，`Snapshot.selected.text` 报告 `'3'`，而真实高亮标签是 `'保存'`。任何宽度字符出现在高亮区之前都会无条件错位；纯 ASCII 与从第 0 列开始的高亮恰好正确，所以现有测试全绿。这是最严重的用户可见缺陷，且修复最小。
2. **A02（SGR 冒号子参数的分片不变性）已复现并量化**：读取块 ≤1 KB 时 100% 流损坏，4 KB 时 78%，64 KB 时 2%；普通 SGR/CSI/OSC 控制组本身分片安全，说明问题精确地位于 `_ByteStream.feed` 的按块正则预处理。`feed_errors` 不增长，产品没有任何"我已看到损坏"的信号。现有测试只喂完整序列。
3. **A01（POSIX 非阻塞短写）仅源码确认**：本机无 POSIX shell、Docker 守护进程未运行，**尚未在任何真机 pty 上验证**。它的修复面也是三者中最大的（输入完成状态机）。
4. **A04 的平台差异比 v1 描述更尖锐**：Windows 侧 ConPTY 已有 reader 线程在排空，但排入**无界队列**（空闲 → 内存增长 + 之后一次巨大 catch-up feed）；POSIX 侧空闲时根本无人读 master fd（空闲 → 持续输出的子进程会被写满的 pty 缓冲阻塞，且设备查询应答永远不回）。这是两个不同缺陷，需要不同测试。
5. **计划 v1 存在两处硬缺口**：其一，`skills/drive-tui/scripts/tui.py` 已经实现了 `INTERLEAVE_OK` + `_drain_interleavable()`——在长 wait 的 poll gap 里、在 worker 自身线程上应答 `snapshot/alive/list/send_text/send_line/send_keys`，并明确把 `resize` 排除（resize 改变内容 hash，会让并发 `wait_change` 误判）。计划 v1 全文未提及这个既有机制，若按 v1 的 R2 重写 owner loop 而不保留它，会回退一个已修复缺陷。其二，核心是**双份**的：`smartcli_core/` 与 `skills/drive-tui/_vendor/smartcli_core/`，由 `tests/test_vendor_sync.py` 守门；同时 `pyproject.toml` 把发行包 `smartcli_drive` 映射到 `skills/drive-tui/scripts`，所以重写 `tui.py` 同时是打包与 MCP registry 契约变更，不只是内部重构。
6. **竞争事实**：`microsoft/tui-test` 已有 Windows+Linux+macOS、CLI+Rust+Python+JS、四类 wait、文本/样式 locator、截图与 APNG/GIF/MP4 录制（本轮直接核对其 README）。它处于 beta 重写期、是测试框架姿态、无 MCP-first 面。计划 v1 给了它 84/100 但把它当作"接口完整性参照"，没有正面回答"SmartCLI 到底不和它竞争什么"。

## 本轮要你交付的东西

只产出**计划书 v2 的增量**（可直接放进计划包 `docs/`），不要重写 v1，不要重复 v1 已有的内容。按文件化结构输出：

1. `ORDER.md` — 修正后的 R1 内部执行顺序与判据。对 `T03/T04/T05` 给出明确先后，每项写：最小反例（必须能在原版本红、在修复后绿、把修复回退后再次变红）、验收命令、不允许的取巧（例如用阈值放宽、跳过、自动重跑换绿灯）。允许你论证并推翻本机给出的 `T05 → T04 → T03` 顺序，但必须用附件中的证据或明确申请的补验实验来支撑。
2. `A04_DESIGN.md` — 空闲排空的跨平台设计。至少给出：一个统一契约 + 两个平台实现（或有证据支持的单一实现），队列/预算/溢出语义的具体边界，以及每个平台的最小负例。特别回答：Windows 侧无界队列的有界化会不会改变"首帧延迟"或"catch-up feed 的 CPU 峰值"？POSIX 侧定时 pump 与 2 个并发 watcher 之间谁先读，如何不破坏单 owner 不变量？
3. `A01_MINIMAL.md` — 支持 `accepted / partially_written / written / app_acknowledged / verified` 的**最小**输入完成状态机，明确不做完整 actor 框架时哪些语义可以延后，以及哪些语义一旦延后就会有"谎报成功"的风险。
4. `CONFORMANCE.md` — 一个陌生人 5 分钟能跑完的一致性套件规格：一次屏幕解析、一次逐字节精确的输入、一次打印完成依据的等待、一次必须拒绝的错误答案。规定它必须打印什么，才能让"错的结果"与"对的结果"可区分；同时规定它不得依赖重型 PTY 套件。
5. `POSITIONING.md` — 与 `microsoft/tui-test`（及其他你最看重的两个竞品）的定位对比，包含一份明确的 **won't-do 清单**（明确不重建录制器、不做竞品性能农场、不做无边界"全能终端平台"之类），以及"两条 release 内不承诺什么"。不得编造实测性能或成功率。
6. `BRIEFS.md` — 三份可以直接交给本地编码 Agent 的 worker brief（T05 修复、T04 修复、A04 设计原型），每份包含：目标文件与符号、允许的改动面上限、必须保留的既有行为（尤其上面第 5 条的 interleave 机制与 vendor 同步门禁）、验收命令、停止条件与 NOT_RUN 的写法。
7. `RISKS.md` — 风险登记表：每条含触发条件、早期信号、处置、kill criteria；并给出"每项改动的最大触碰面"建议（例如"一个增量最多动 canonical 模块 + vendor 双胞胎 + 一个测试文件；任何新线程/队列/观察者必须同时给出上界与其失效测试"）。

## 硬约束

- 不得重写 v1，不得引入新的默认引擎、重大依赖或破坏性公共 API；需要时只写成待批准提案。
- 不得把"更多模块/更多概念/更完整的 README"当作收益；每条建议都要回答：解决了哪个真实失败，凭什么认定正确，哪些平台没测。
- 引用证据时写明等级（E1/E2/E3/E4/E5/E6）与来源（附件名 + 章节或 file:symbol）。
- 明确区分：证据支持 / 你的推断 / 未确认。凡是你不同意本机结论之处，单独列一节"我反对本地结论的地方"，给出理由与可执行的补验实验。
- 结束时给出一段"下一位 Agent 可直接执行的三步"，以及你希望本地补验的最多 3 个实验（每个含假设、判负条件、停止规则）。

=== PROMPT ===

## Notes for the local side after the reply arrives

- Save the returned documents into the plan package's `docs/` as a v2 delta; keep v1 files
  untouched so the diff stays auditable.
- The `BRIEFS.md` output is the natural next dispatch: T05 first (smallest, fully
  provable on this box), then T04, then A04's design prototype. Only one writer touches
  `smartcli_core/` at a time; every core change must sync the vendor twin and run
  `tests/test_vendor_sync.py` + `tests/test_terminal_fidelity.py` + the new regression file.
- A01 stays open until a POSIX host exists (Docker Desktop is installed but its daemon is
  stopped on this box — starting it is a separate, heavier decision).
